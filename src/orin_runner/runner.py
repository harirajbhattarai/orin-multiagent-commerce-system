"""Execute one ORIN client request and preserve durable run evidence."""

from __future__ import annotations

import fcntl
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Sequence

from orin_runner.contract import (
    ERROR_APPROVED_DRAFT_INVALID,
    ERROR_CONTENT_PLAN_SELECTION_MISMATCH,
    ERROR_PIPELINE_BLOCKED,
    ERROR_PIPELINE_EXIT_NONZERO,
    ERROR_PIPELINE_RESULT_INVALID,
    ERROR_PIPELINE_RESULT_MISSING,
    ERROR_PIPELINE_START_FAILED,
    ERROR_PIPELINE_TIMEOUT,
    ERROR_RUNNER_BUSY,
    ERROR_SHOPIFY_RECONCILIATION_FAILED,
    FinalResult,
    SCHEMA_VERSION,
)
from orin_runner.content_plan import render_content_plan_markdown
from orin_shopify import (
    BODY_CANONICALIZATION,
    DraftReconciliationError,
    ReviewedDraftContractError,
    ShopifyRequestError,
    approved_review_draft_from_snapshot,
    canonical_shopify_body_sha256,
    ensure_approved_review_draft,
    idempotency_marker,
)


SUPPORTED_CLIENTS = {"hoverboard_store", "hcs_gadgets"}
SUPPORTED_MODES = {"dry-run", "hidden-draft"}
PIPELINE_PREVIEW_PATH = Path("/tmp/orin_phase3b_cron_entrypoint_preview.json")
APPROVED_PIPELINE_PATH = Path("tools/shopify_publisher/orin/cron_entrypoint.py")


class RunnerBusyError(RuntimeError):
    """Raised when another local runner owns the process lock."""


class IdempotencyConflictError(RuntimeError):
    """Raised when a request ID is reused with different immutable inputs."""


class UnsupportedClientError(ValueError):
    """Raised when the Python API receives a client without a pipeline binding."""


def configured_repo_root() -> Path:
    """Resolve and validate the checkout containing the approved ORIN pipeline."""
    configured = os.environ.get("ORIN_REPO_ROOT")
    candidate = (
        Path(configured).expanduser().resolve()
        if configured
        else Path(__file__).resolve().parents[2]
    )
    if not (candidate / APPROVED_PIPELINE_PATH).is_file():
        raise ValueError(
            "ORIN_REPO_ROOT does not contain tools/shopify_publisher/orin/cron_entrypoint.py"
        )
    return candidate


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def make_run_id(client_id: str) -> str:
    prefix = {"hoverboard_store": "hb", "hcs_gadgets": "hcs"}.get(client_id, "run")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{prefix}_{stamp}_{uuid.uuid4().hex[:8]}"


def default_code_version(repo_root: Path) -> str:
    configured = os.environ.get("ORIN_CODE_VERSION")
    if configured:
        return configured
    try:
        result = subprocess.run(
            [
                "git",
                "-c",
                f"safe.directory={repo_root.resolve()}",
                "-C",
                str(repo_root),
                "rev-parse",
                "HEAD",
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        return result.stdout.strip() if result.returncode == 0 else "unknown"
    except (OSError, subprocess.TimeoutExpired):
        return "unknown"


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.chmod(0o600)
    temporary.replace(path)


def _write_private(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o600)


def _event(events_path: Path, event: str, **fields: Any) -> None:
    payload = {"timestamp": utc_now(), "event": event, **fields}
    line = json.dumps(payload, sort_keys=True)
    with events_path.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")
    events_path.chmod(0o600)
    print(line, file=sys.stderr)


@contextmanager
def _runner_lock(artifact_root: Path) -> Iterator[None]:
    lock_path = artifact_root / ".runner.lock"
    lock_path.touch(mode=0o600, exist_ok=True)
    with lock_path.open("r+", encoding="utf-8") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RunnerBusyError(ERROR_RUNNER_BUSY) from exc
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _safe_request_name(request_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", request_id)


def _read_existing_result(
    request_index: Path,
    *,
    client_id: str,
    requested_mode: str,
    as_of_date: str | None,
    job_number: str | None,
    claim_attempt: int | None = None,
) -> tuple[dict[str, Any] | None, int]:
    if not request_index.exists():
        return None, claim_attempt or 1
    pointer = json.loads(request_index.read_text(encoding="utf-8"))
    expected = {
        "client_id": client_id,
        "requested_mode": requested_mode,
        "as_of_date": as_of_date,
        "job_number": job_number,
    }
    actual = {key: pointer.get(key) for key in expected}
    if actual != expected:
        raise IdempotencyConflictError(f"request inputs differ: expected={actual}, received={expected}")
    result_path = Path(pointer["final_result_path"])
    result = json.loads(result_path.read_text(encoding="utf-8"))
    attempt = int(result.get("attempt", pointer.get("attempt", 1)))
    if claim_attempt is not None and attempt != claim_attempt:
        if requested_mode != "dry-run":
            raise IdempotencyConflictError(
                "a database claim attempt cannot replace cached Shopify-write evidence"
            )
        # A dry-run can be executed again safely when database finalization did
        # not consume the prior local result. Bind the replacement evidence to
        # the exact durable lease attempt so completion cannot persist a stale
        # runner-local attempt number.
        return None, claim_attempt
    disposition = result.get("replay_disposition")
    if result.get("schema") != SCHEMA_VERSION:
        # v1 did not encode replay safety. Re-execute through the marker-first
        # pipeline so every cached result is upgraded to the v2 contract.
        disposition = "reconcile" if requested_mode == "hidden-draft" else "retry"
    elif disposition is None:
        # Recover safely from pre-v2 request indexes. Hidden-draft process
        # failures may have reached Shopify and must not remain cached.
        uncertain_errors = {
            ERROR_PIPELINE_TIMEOUT,
            ERROR_PIPELINE_RESULT_MISSING,
            ERROR_PIPELINE_RESULT_INVALID,
            ERROR_PIPELINE_EXIT_NONZERO,
        }
        disposition = (
            "reconcile"
            if requested_mode == "hidden-draft"
            and result.get("error_code") in uncertain_errors
            else "terminal"
        )
    if disposition == "terminal":
        return result, attempt
    return None, attempt + 1


def _pipeline_decision(preview: dict[str, Any]) -> str:
    return str(
        preview.get("transaction_decision")
        or preview.get("planner_decision")
        or preview.get("publisher_decision")
        or ("blocked" if preview.get("blocked") else "completed")
    )


def _execute_pipeline(
    command: Sequence[str],
    *,
    cwd: Path,
    environment: dict[str, str],
    timeout_seconds: float,
) -> subprocess.CompletedProcess[str]:
    process = subprocess.Popen(
        command,
        cwd=cwd,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        stdout, stderr = process.communicate(timeout=timeout_seconds)
    except subprocess.TimeoutExpired as exc:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            stdout, stderr = process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            stdout, stderr = process.communicate()
        raise subprocess.TimeoutExpired(command, timeout_seconds, output=stdout, stderr=stderr) from exc
    return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)


def _result_from_pipeline(
    *,
    preview: dict[str, Any],
    run_id: str,
    request_id: str,
    client_id: str,
    requested_mode: str,
    code_version: str,
    started_at: str,
    finished_at: str,
    artifact_uri: str,
    pipeline_exit_code: int,
    attempt: int,
) -> FinalResult:
    reconciliation_status = str(preview.get("reconciliation_status") or "not_required")
    article_id = preview.get("shopify_article_id")
    shopify_write_state = str(
        preview.get("shopify_write_state")
        or (
            "article_observed"
            if article_id is not None
            else "unknown"
            if requested_mode == "hidden-draft"
            and reconciliation_status == "needs_review"
            else "not_attempted"
        )
    )
    replay_disposition = str(
        preview.get("replay_disposition")
        or (
            "reconcile"
            if requested_mode == "hidden-draft"
            and (
                reconciliation_status == "needs_review"
                or shopify_write_state == "unknown"
            )
            else "terminal"
        )
    )
    if pipeline_exit_code != 0:
        replay_disposition = (
            "reconcile"
            if requested_mode == "hidden-draft"
            and shopify_write_state != "not_attempted"
            else "retry"
        )

    blocked = bool(preview.get("blocked")) or replay_disposition != "terminal"
    error_code = ERROR_PIPELINE_BLOCKED if blocked else None
    status = "blocked" if blocked else "completed"
    if pipeline_exit_code != 0:
        status = "failed"
        error_code = ERROR_PIPELINE_EXIT_NONZERO

    transaction_decision = str(preview.get("transaction_decision") or "")
    create_count = int(
        preview.get(
            "shopify_create_count",
            1 if transaction_decision == "DRAFT_CREATED_VERIFICATION_PASSED" else 0,
        )
    )
    if article_id is not None and shopify_write_state == "article_observed":
        create_count = 1
    effective_mode = (
        "hidden-draft"
        if requested_mode == "hidden-draft"
        else str(preview.get("effective_mode") or preview.get("mode") or requested_mode)
    )

    return FinalResult(
        schema=SCHEMA_VERSION,
        run_id=run_id,
        request_id=request_id,
        client_id=client_id,
        job_id=str(preview["selected_job"]) if preview.get("selected_job") is not None else None,
        attempt=attempt,
        requested_mode=requested_mode,
        effective_mode=effective_mode,
        status=status,
        decision=_pipeline_decision(preview),
        code_version=code_version,
        config_version=os.environ.get("ORIN_CONFIG_VERSION"),
        idempotency_key=f"{client_id}:{request_id}",
        replay_disposition=replay_disposition,
        shopify_write_state=shopify_write_state,
        shopify_idempotency_marker=(
            preview.get("shopify_idempotency_marker")
            or (
                f"orin-v1:{client_id}:{request_id}"
                if requested_mode == "hidden-draft"
                else None
            )
        ),
        shopify_article_id=str(article_id) if article_id is not None else None,
        shopify_create_count=create_count,
        shopify_published=False,
        queue_changed=bool(preview.get("queue_touched", False)),
        reconciliation_status=reconciliation_status,
        started_at=started_at,
        finished_at=finished_at,
        artifact_uri=artifact_uri,
        error_code=error_code,
        pipeline_exit_code=pipeline_exit_code,
    )


def _failure_result(
    *,
    error_code: str,
    decision: str,
    run_id: str,
    request_id: str,
    client_id: str,
    requested_mode: str,
    code_version: str,
    started_at: str,
    artifact_uri: str,
    pipeline_exit_code: int | None,
    attempt: int,
    replay_disposition: str,
    shopify_write_state: str,
    reconciliation_status: str,
) -> FinalResult:
    return FinalResult(
        schema=SCHEMA_VERSION,
        run_id=run_id,
        request_id=request_id,
        client_id=client_id,
        job_id=None,
        attempt=attempt,
        requested_mode=requested_mode,
        effective_mode="none",
        status="failed",
        decision=decision,
        code_version=code_version,
        config_version=os.environ.get("ORIN_CONFIG_VERSION"),
        idempotency_key=f"{client_id}:{request_id}",
        replay_disposition=replay_disposition,
        shopify_write_state=shopify_write_state,
        shopify_idempotency_marker=(
            f"orin-v1:{client_id}:{request_id}" if requested_mode == "hidden-draft" else None
        ),
        shopify_article_id=None,
        shopify_create_count=0,
        shopify_published=False,
        queue_changed=False,
        reconciliation_status=reconciliation_status,
        started_at=started_at,
        finished_at=utc_now(),
        artifact_uri=artifact_uri,
        error_code=error_code,
        pipeline_exit_code=pipeline_exit_code,
    )


def _reviewed_hidden_draft_result(
    *,
    snapshot: dict[str, Any],
    run_dir: Path,
    run_id: str,
    request_id: str,
    client_id: str,
    code_version: str,
    started_at: str,
    artifact_uri: str,
    attempt: int,
) -> FinalResult:
    """Execute the frozen review draft directly; never invoke the writer pipeline."""
    marker = idempotency_marker(f"{client_id}:{request_id}")
    try:
        approved = approved_review_draft_from_snapshot(snapshot, client_id=client_id)
        _write_private(run_dir / "approved_review_draft.html", approved.body_html)
        _atomic_json(run_dir / "approved_review_draft.json", approved.evidence())
    except (OSError, ReviewedDraftContractError, ValueError) as error:
        _write_private(run_dir / "stdout.log", "")
        _write_private(run_dir / "stderr.log", f"{type(error).__name__}: {error}\n")
        return _failure_result(
            error_code=ERROR_APPROVED_DRAFT_INVALID,
            decision="approved_review_draft_invalid",
            run_id=run_id,
            request_id=request_id,
            client_id=client_id,
            requested_mode="hidden-draft",
            code_version=code_version,
            started_at=started_at,
            artifact_uri=artifact_uri,
            pipeline_exit_code=None,
            attempt=attempt,
            replay_disposition="retry",
            shopify_write_state="not_attempted",
            reconciliation_status="not_started",
        )

    try:
        draft_result = ensure_approved_review_draft(
            approved,
            client_id=client_id,
            request_id=request_id,
        )
    except (OSError, ReviewedDraftContractError, ValueError) as error:
        _atomic_json(
            run_dir / "reviewed_draft_transaction.json",
            {
                "status": "failed",
                "approved_draft": approved.evidence(),
                "shopify_idempotency_marker": marker,
                "shopify_write_state": "not_attempted",
                "reconciliation_status": "not_started",
                "error_type": type(error).__name__,
            },
        )
        _write_private(run_dir / "stdout.log", "")
        _write_private(run_dir / "stderr.log", f"{type(error).__name__}: {error}\n")
        return _failure_result(
            error_code=ERROR_APPROVED_DRAFT_INVALID,
            decision="shopify_hidden_draft_configuration_invalid",
            run_id=run_id,
            request_id=request_id,
            client_id=client_id,
            requested_mode="hidden-draft",
            code_version=code_version,
            started_at=started_at,
            artifact_uri=artifact_uri,
            pipeline_exit_code=None,
            attempt=attempt,
            replay_disposition="retry",
            shopify_write_state="not_attempted",
            reconciliation_status="not_started",
        )
    except (DraftReconciliationError, ShopifyRequestError) as error:
        _atomic_json(
            run_dir / "reviewed_draft_transaction.json",
            {
                "status": "needs_review",
                "approved_draft": approved.evidence(),
                "shopify_idempotency_marker": marker,
                "shopify_write_state": "unknown",
                "reconciliation_status": "needs_review",
                "error_type": type(error).__name__,
            },
        )
        _write_private(run_dir / "stdout.log", "")
        _write_private(run_dir / "stderr.log", f"{type(error).__name__}: {error}\n")
        failed = _failure_result(
            error_code=ERROR_SHOPIFY_RECONCILIATION_FAILED,
            decision="approved_review_draft_reconciliation_required",
            run_id=run_id,
            request_id=request_id,
            client_id=client_id,
            requested_mode="hidden-draft",
            code_version=code_version,
            started_at=started_at,
            artifact_uri=artifact_uri,
            pipeline_exit_code=None,
            attempt=attempt,
            replay_disposition="reconcile",
            shopify_write_state="unknown",
            reconciliation_status="needs_review",
        )
        return FinalResult(**{**failed.to_dict(), "status": "blocked", "effective_mode": "hidden-draft"})

    transaction_evidence = {
        "status": "completed",
        "approved_draft": approved.evidence(),
        "stored_body_sha256": approved.body_sha256,
        "sent_body_sha256": approved.body_sha256,
        "fetched_body_sha256": draft_result.body_sha256,
        "approved_canonical_body_sha256": canonical_shopify_body_sha256(
            approved.body_html
        ),
        "fetched_canonical_body_sha256": draft_result.canonical_body_sha256,
        "body_canonicalization": BODY_CANONICALIZATION,
        "shopify_article_id": str(draft_result.numeric_article_id),
        "shopify_graphql_article_id": draft_result.article_id,
        "shopify_idempotency_marker": draft_result.idempotency_marker,
        "shopify_create_count": draft_result.create_count,
        "shopify_published": False,
        "reconciliation_status": draft_result.reconciliation_status,
    }
    _atomic_json(run_dir / "reviewed_draft_transaction.json", transaction_evidence)
    _write_private(
        run_dir / "stdout.log",
        "Approved review draft reconciled as one unpublished Shopify article.\n",
    )
    _write_private(run_dir / "stderr.log", "")
    return FinalResult(
        schema=SCHEMA_VERSION,
        run_id=run_id,
        request_id=request_id,
        client_id=client_id,
        job_id=str(approved.item_number),
        attempt=attempt,
        requested_mode="hidden-draft",
        effective_mode="hidden-draft",
        status="completed",
        decision="APPROVED_REVIEW_DRAFT_CREATED_VERIFICATION_PASSED",
        code_version=code_version,
        config_version=os.environ.get("ORIN_CONFIG_VERSION"),
        idempotency_key=f"{client_id}:{request_id}",
        replay_disposition="terminal",
        shopify_write_state=draft_result.shopify_write_state,
        shopify_idempotency_marker=draft_result.idempotency_marker,
        shopify_article_id=str(draft_result.numeric_article_id),
        shopify_handle=draft_result.handle,
        shopify_create_count=draft_result.create_count,
        shopify_published=False,
        queue_changed=False,
        reconciliation_status=draft_result.reconciliation_status,
        started_at=started_at,
        finished_at=utc_now(),
        artifact_uri=artifact_uri,
        error_code=None,
        pipeline_exit_code=0,
    )


def run_client(
    *,
    client_id: str,
    request_id: str,
    mode: str,
    workspace_root: Path,
    artifact_root: Path,
    repo_root: Path,
    as_of_date: str | None = None,
    job_number: str | None = None,
    durable_db_mode: bool = False,
    content_plan_snapshot: dict[str, Any] | None = None,
    claim_attempt: int | None = None,
    pipeline_command: Sequence[str] | None = None,
    pipeline_preview_path: Path = PIPELINE_PREVIEW_PATH,
    pipeline_timeout_seconds: float = 900,
) -> dict[str, Any]:
    """Run one idempotent client request and return its final-result payload."""
    if client_id not in SUPPORTED_CLIENTS:
        raise UnsupportedClientError(f"unsupported client: {client_id}")
    if client_id == "hcs_gadgets" and mode != "dry-run":
        raise UnsupportedClientError("hcs_gadgets is commissioned for dry-run only")
    if job_number is not None:
        if not re.fullmatch(r"[1-9][0-9]*", job_number):
            raise ValueError("job_number must be a positive integer")
        job_number = str(int(job_number))
    if claim_attempt is not None and claim_attempt < 1:
        raise ValueError("claim_attempt must be a positive integer")

    artifact_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    artifact_root.chmod(0o700)
    requests_dir = artifact_root / "requests"
    requests_dir.mkdir(mode=0o700, exist_ok=True)
    requests_dir.chmod(0o700)
    request_index = requests_dir / f"{_safe_request_name(request_id)}.json"

    with _runner_lock(artifact_root):
        existing, attempt = _read_existing_result(
            request_index,
            client_id=client_id,
            requested_mode=mode,
            as_of_date=as_of_date,
            job_number=job_number,
            claim_attempt=claim_attempt,
        )
        if existing is not None:
            return existing

        run_id = make_run_id(client_id)
        run_dir = artifact_root / run_id
        run_dir.mkdir(mode=0o700)
        events_path = run_dir / "events.jsonl"
        final_path = run_dir / "final_result.json"
        started_at = utc_now()
        code_version = default_code_version(repo_root)
        artifact_uri = str(run_dir.resolve())
        _event(events_path, "run_started", run_id=run_id, client_id=client_id, request_id=request_id, mode=mode)

        content_queue_projection: Path | None = None
        if content_plan_snapshot is not None:
            projection = render_content_plan_markdown(
                content_plan_snapshot,
                client_id=client_id,
            )
            content_queue_projection = run_dir / "content_queue_projection.md"
            _write_private(content_queue_projection, projection)
            _atomic_json(run_dir / "content_plan_snapshot.json", content_plan_snapshot)
            _event(
                events_path,
                "content_plan_bound",
                selected_item_number=content_plan_snapshot.get("selected_item_number"),
                item_count=len(content_plan_snapshot.get("items", [])),
            )

        if mode == "hidden-draft" and durable_db_mode:
            result = _reviewed_hidden_draft_result(
                snapshot=content_plan_snapshot or {},
                run_dir=run_dir,
                run_id=run_id,
                request_id=request_id,
                client_id=client_id,
                code_version=code_version,
                started_at=started_at,
                artifact_uri=artifact_uri,
                attempt=attempt,
            )
            payload = result.to_dict()
            _atomic_json(final_path, payload)
            _atomic_json(
                request_index,
                {
                    "run_id": run_id,
                    "final_result_path": str(final_path.resolve()),
                    "client_id": client_id,
                    "requested_mode": mode,
                    "as_of_date": as_of_date,
                    "job_number": job_number,
                    "attempt": attempt,
                    "replay_disposition": result.replay_disposition,
                },
            )
            _event(
                events_path,
                "run_finished",
                run_id=run_id,
                status=result.status,
                decision=result.decision,
                error_code=result.error_code,
            )
            return payload

        command = list(pipeline_command or [
            sys.executable,
            str(repo_root / "tools/shopify_publisher/orin/cron_entrypoint.py"),
        ])
        command.append("--dry-run" if mode == "dry-run" else "--live-draft")
        if mode == "hidden-draft":
            command.append("--confirm-live-draft")
        command.extend([f"--client={client_id}", "--json"])
        if as_of_date:
            command.append(f"--as-of-date={as_of_date}")
        if job_number:
            command.append(f"--job={job_number}")

        environment = os.environ.copy()
        environment["ORIN_WORKSPACE_ROOT"] = str(workspace_root.resolve())
        durable_execution = durable_db_mode or mode == "hidden-draft"
        if durable_execution:
            environment["ORIN_DURABLE_DB_MODE"] = "1"
            environment["ORIN_RUN_ARTIFACT_DIR"] = artifact_uri
        if content_plan_snapshot is not None:
            selected_item_number = content_plan_snapshot.get("selected_item_number")
            if selected_item_number is not None:
                environment["ORIN_DURABLE_SELECTED_JOB"] = str(selected_item_number)
        if content_queue_projection is not None:
            environment["ORIN_CONTENT_QUEUE_PATH"] = str(content_queue_projection.resolve())
        if mode == "hidden-draft":
            environment["ORIN_IDEMPOTENCY_KEY"] = f"{client_id}:{request_id}"
        if mode == "dry-run":
            for name in (
                "HOVERBOARD_STORE_SHOPIFY_STORE_DOMAIN",
                "HOVERBOARD_STORE_SHOPIFY_ACCESS_TOKEN",
                "HOVERBOARD_STORE_SHOPIFY_ACCESS_TOKEN_FILE",
                "HOVERBOARD_STORE_SHOPIFY_API_VERSION",
                "HOVERBOARD_STORE_SHOPIFY_BLOG_ID",
                "HCS_GADGETS_SHOPIFY_STORE_DOMAIN",
                "HCS_GADGETS_SHOPIFY_ACCESS_TOKEN",
                "HCS_GADGETS_SHOPIFY_ACCESS_TOKEN_FILE",
                "HCS_GADGETS_SHOPIFY_API_VERSION",
                "HCS_GADGETS_SHOPIFY_BLOG_ID",
            ):
                environment.pop(name, None)
        if pipeline_preview_path.exists():
            shutil.move(str(pipeline_preview_path), run_dir / "preexisting_pipeline_preview.json")

        completed: subprocess.CompletedProcess[str] | None = None
        result: FinalResult | None = None
        try:
            completed = _execute_pipeline(
                command,
                cwd=repo_root,
                environment=environment,
                timeout_seconds=pipeline_timeout_seconds,
            )
            _write_private(run_dir / "stdout.log", completed.stdout)
            _write_private(run_dir / "stderr.log", completed.stderr)
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
            stderr = exc.stderr.decode() if isinstance(exc.stderr, bytes) else (exc.stderr or "")
            _write_private(run_dir / "stdout.log", stdout)
            _write_private(run_dir / "stderr.log", stderr)
            result = _failure_result(
                error_code=ERROR_PIPELINE_TIMEOUT,
                decision="pipeline_timeout",
                run_id=run_id,
                request_id=request_id,
                client_id=client_id,
                requested_mode=mode,
                code_version=code_version,
                started_at=started_at,
                artifact_uri=artifact_uri,
                pipeline_exit_code=None,
                attempt=attempt,
                replay_disposition=(
                    "reconcile" if mode == "hidden-draft" else "retry"
                ),
                shopify_write_state=(
                    "unknown" if mode == "hidden-draft" else "not_attempted"
                ),
                reconciliation_status=(
                    "needs_review" if mode == "hidden-draft" else "not_required"
                ),
            )
        except OSError as exc:
            _write_private(run_dir / "stdout.log", "")
            _write_private(run_dir / "stderr.log", str(exc))
            result = _failure_result(
                error_code=ERROR_PIPELINE_START_FAILED,
                decision="pipeline_start_failed",
                run_id=run_id,
                request_id=request_id,
                client_id=client_id,
                requested_mode=mode,
                code_version=code_version,
                started_at=started_at,
                artifact_uri=artifact_uri,
                pipeline_exit_code=None,
                attempt=attempt,
                replay_disposition="retry",
                shopify_write_state="not_attempted",
                reconciliation_status=(
                    "not_started" if mode == "hidden-draft" else "not_required"
                ),
            )

        if completed is not None and not pipeline_preview_path.exists():
            result = _failure_result(
                error_code=ERROR_PIPELINE_RESULT_MISSING,
                decision="pipeline_result_missing",
                run_id=run_id,
                request_id=request_id,
                client_id=client_id,
                requested_mode=mode,
                code_version=code_version,
                started_at=started_at,
                artifact_uri=artifact_uri,
                pipeline_exit_code=completed.returncode,
                attempt=attempt,
                replay_disposition=(
                    "reconcile" if mode == "hidden-draft" else "retry"
                ),
                shopify_write_state=(
                    "unknown" if mode == "hidden-draft" else "not_attempted"
                ),
                reconciliation_status=(
                    "needs_review" if mode == "hidden-draft" else "not_required"
                ),
            )
        elif completed is not None:
            try:
                preview = json.loads(pipeline_preview_path.read_text(encoding="utf-8"))
                _atomic_json(run_dir / "pipeline_preview.json", preview)
                result = _result_from_pipeline(
                    preview=preview,
                    run_id=run_id,
                    request_id=request_id,
                    client_id=client_id,
                    requested_mode=mode,
                    code_version=code_version,
                    started_at=started_at,
                    finished_at=utc_now(),
                    artifact_uri=artifact_uri,
                    pipeline_exit_code=completed.returncode,
                    attempt=attempt,
                )
                selected_item_number = (
                    content_plan_snapshot.get("selected_item_number")
                    if content_plan_snapshot is not None
                    else None
                )
                if (
                    selected_item_number is not None
                    and result.status == "completed"
                    and str(result.job_id) != str(selected_item_number)
                ):
                    result = _failure_result(
                        error_code=ERROR_CONTENT_PLAN_SELECTION_MISMATCH,
                        decision="content_plan_selection_mismatch",
                        run_id=run_id,
                        request_id=request_id,
                        client_id=client_id,
                        requested_mode=mode,
                        code_version=code_version,
                        started_at=started_at,
                        artifact_uri=artifact_uri,
                        pipeline_exit_code=completed.returncode,
                        attempt=attempt,
                        replay_disposition="terminal",
                        shopify_write_state="not_attempted",
                        reconciliation_status="not_required",
                    )
            except (json.JSONDecodeError, OSError, TypeError, ValueError):
                result = _failure_result(
                    error_code=ERROR_PIPELINE_RESULT_INVALID,
                    decision="pipeline_result_invalid",
                    run_id=run_id,
                    request_id=request_id,
                    client_id=client_id,
                    requested_mode=mode,
                    code_version=code_version,
                    started_at=started_at,
                    artifact_uri=artifact_uri,
                    pipeline_exit_code=completed.returncode,
                    attempt=attempt,
                    replay_disposition=(
                        "reconcile" if mode == "hidden-draft" else "retry"
                    ),
                    shopify_write_state=(
                        "unknown" if mode == "hidden-draft" else "not_attempted"
                    ),
                    reconciliation_status=(
                        "needs_review" if mode == "hidden-draft" else "not_required"
                    ),
                )

        assert result is not None
        payload = result.to_dict()
        _atomic_json(final_path, payload)
        _atomic_json(
            request_index,
            {
                "run_id": run_id,
                "final_result_path": str(final_path.resolve()),
                "client_id": client_id,
                "requested_mode": mode,
                "as_of_date": as_of_date,
                "job_number": job_number,
                "attempt": attempt,
                "replay_disposition": result.replay_disposition,
            },
        )
        _event(events_path, "run_finished", run_id=run_id, status=result.status, decision=result.decision, error_code=result.error_code)
        return payload
