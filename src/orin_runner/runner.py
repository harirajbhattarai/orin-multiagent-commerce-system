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
    ERROR_PIPELINE_BLOCKED,
    ERROR_PIPELINE_EXIT_NONZERO,
    ERROR_PIPELINE_RESULT_INVALID,
    ERROR_PIPELINE_RESULT_MISSING,
    ERROR_PIPELINE_START_FAILED,
    ERROR_PIPELINE_TIMEOUT,
    ERROR_RUNNER_BUSY,
    FinalResult,
    SCHEMA_VERSION,
)


SUPPORTED_CLIENTS = {"hoverboard_store"}
SUPPORTED_MODES = {"dry-run", "hidden-draft"}
PIPELINE_PREVIEW_PATH = Path("/tmp/orin_phase3b_cron_entrypoint_preview.json")


class RunnerBusyError(RuntimeError):
    """Raised when another local runner owns the process lock."""


class IdempotencyConflictError(RuntimeError):
    """Raised when a request ID is reused with different immutable inputs."""


class UnsupportedClientError(ValueError):
    """Raised when the Python API receives a client without a pipeline binding."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def make_run_id(client_id: str) -> str:
    prefix = "hb" if client_id == "hoverboard_store" else "run"
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
) -> tuple[dict[str, Any] | None, int]:
    if not request_index.exists():
        return None, 1
    pointer = json.loads(request_index.read_text(encoding="utf-8"))
    expected = {
        "client_id": client_id,
        "requested_mode": requested_mode,
        "as_of_date": as_of_date,
    }
    actual = {key: pointer.get(key) for key in expected}
    if actual != expected:
        raise IdempotencyConflictError(f"request inputs differ: expected={actual}, received={expected}")
    result_path = Path(pointer["final_result_path"])
    result = json.loads(result_path.read_text(encoding="utf-8"))
    attempt = int(result.get("attempt", pointer.get("attempt", 1)))
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


def run_client(
    *,
    client_id: str,
    request_id: str,
    mode: str,
    workspace_root: Path,
    artifact_root: Path,
    repo_root: Path,
    as_of_date: str | None = None,
    durable_db_mode: bool = False,
    pipeline_command: Sequence[str] | None = None,
    pipeline_preview_path: Path = PIPELINE_PREVIEW_PATH,
    pipeline_timeout_seconds: float = 900,
) -> dict[str, Any]:
    """Run one idempotent client request and return its final-result payload."""
    if client_id not in SUPPORTED_CLIENTS:
        raise UnsupportedClientError(f"unsupported client: {client_id}")

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

        environment = os.environ.copy()
        environment["ORIN_WORKSPACE_ROOT"] = str(workspace_root.resolve())
        durable_execution = durable_db_mode or mode == "hidden-draft"
        if durable_execution:
            environment["ORIN_DURABLE_DB_MODE"] = "1"
            environment["ORIN_RUN_ARTIFACT_DIR"] = artifact_uri
        if mode == "hidden-draft":
            environment["ORIN_IDEMPOTENCY_KEY"] = f"{client_id}:{request_id}"
        if mode == "dry-run":
            for name in (
                "HOVERBOARD_STORE_SHOPIFY_STORE_DOMAIN",
                "HOVERBOARD_STORE_SHOPIFY_ACCESS_TOKEN",
                "HOVERBOARD_STORE_SHOPIFY_ACCESS_TOKEN_FILE",
                "HOVERBOARD_STORE_SHOPIFY_API_VERSION",
                "HOVERBOARD_STORE_SHOPIFY_BLOG_ID",
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
                "attempt": attempt,
                "replay_disposition": result.replay_disposition,
            },
        )
        _event(events_path, "run_finished", run_id=run_id, status=result.status, decision=result.decision, error_code=result.error_code)
        return payload
