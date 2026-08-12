import hashlib
import json
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

from orin_runner.contract import (
    ERROR_CONTENT_PLAN_SELECTION_MISMATCH,
    ERROR_PIPELINE_BLOCKED,
    ERROR_PIPELINE_EXIT_NONZERO,
    ERROR_PIPELINE_RESULT_MISSING,
    ERROR_PIPELINE_TIMEOUT,
    SCHEMA_VERSION,
)
from orin_runner.runner import configured_repo_root, default_code_version, run_client
from orin_runner.runner import IdempotencyConflictError
from orin_shopify.hidden_draft import DraftResult, ShopifyRequestError


def fake_pipeline(tmp_path: Path, preview: dict | None, exit_code: int = 0) -> tuple[list[str], Path, Path]:
    preview_path = tmp_path / "pipeline-preview.json"
    counter_path = tmp_path / "counter.txt"
    script_path = tmp_path / "fake_pipeline.py"
    script_path.write_text(
        "import json, pathlib, sys\n"
        f"counter = pathlib.Path({str(counter_path)!r})\n"
        "count = int(counter.read_text()) + 1 if counter.exists() else 1\n"
        "counter.write_text(str(count))\n"
        + (f"pathlib.Path({str(preview_path)!r}).write_text(json.dumps({preview!r}))\n" if preview is not None else "")
        + f"raise SystemExit({exit_code})\n",
        encoding="utf-8",
    )
    return [sys.executable, str(script_path)], preview_path, counter_path


def invoke(
    tmp_path: Path,
    command: list[str],
    preview_path: Path,
    request_id: str,
    *,
    mode: str = "dry-run",
    timeout: float = 900,
    job_number: str | None = None,
) -> dict:
    workspace = tmp_path / "workspace"
    workspace.mkdir(exist_ok=True)
    return run_client(
        client_id="hoverboard_store",
        request_id=request_id,
        mode=mode,
        workspace_root=workspace,
        artifact_root=tmp_path / "artifacts",
        repo_root=Path.cwd(),
        pipeline_command=command,
        pipeline_preview_path=preview_path,
        pipeline_timeout_seconds=timeout,
        job_number=job_number,
    )


@pytest.mark.parametrize(
    "client_id",
    ["aroma_store", "", "Hoverboard_Store", "../hoverboard_store"],
)
def test_python_api_rejects_unsupported_client_before_pipeline_or_evidence(
    tmp_path,
    client_id,
):
    preview_path = tmp_path / "pipeline-preview.json"
    command, _, counter_path = fake_pipeline(
        tmp_path,
        {"blocked": False, "planner_decision": "no_job_due"},
    )
    artifact_root = tmp_path / "unsupported-client-artifacts"

    with pytest.raises(ValueError, match="unsupported client"):
        run_client(
            client_id=client_id,
            request_id=str(uuid.uuid4()),
            mode="hidden-draft",
            workspace_root=tmp_path / "workspace",
            artifact_root=artifact_root,
            repo_root=Path.cwd(),
            pipeline_command=command,
            pipeline_preview_path=preview_path,
        )

    assert counter_path.exists() is False
    assert artifact_root.exists() is False


def test_no_job_run_writes_versioned_durable_result(tmp_path):
    preview = {
        "blocked": False,
        "planner_decision": "no_job_due",
        "selected_job": None,
        "effective_mode": "dry-run",
        "shopify_touched": False,
        "queue_touched": False,
    }
    command, preview_path, _ = fake_pipeline(tmp_path, preview)
    result = invoke(tmp_path, command, preview_path, str(uuid.uuid4()))

    assert result["schema"] == SCHEMA_VERSION
    assert result["status"] == "completed"
    assert result["decision"] == "no_job_due"
    assert result["shopify_create_count"] == 0
    assert result["shopify_published"] is False
    assert result["queue_changed"] is False
    assert result["replay_disposition"] == "terminal"
    assert result["shopify_write_state"] == "not_attempted"
    final_path = Path(result["artifact_uri"]) / "final_result.json"
    assert json.loads(final_path.read_text()) == result
    assert final_path.stat().st_mode & 0o077 == 0
    contract = json.loads(Path("schemas/final_result.v2.schema.json").read_text())
    assert set(result) == set(contract["required"])


def test_database_content_plan_is_private_pipeline_input(tmp_path):
    preview_path = tmp_path / "pipeline-preview.json"
    script_path = tmp_path / "assert_content_plan.py"
    script_path.write_text(
        "import json, os, pathlib\n"
        "projection = pathlib.Path(os.environ['ORIN_CONTENT_QUEUE_PATH'])\n"
        "artifact_root = pathlib.Path(os.environ['ORIN_RUN_ARTIFACT_DIR'])\n"
        "assert os.environ['ORIN_DURABLE_SELECTED_JOB'] == '31'\n"
        "assert projection.parent == artifact_root\n"
        "assert '## Job 31' in projection.read_text()\n"
        f"pathlib.Path({str(preview_path)!r}).write_text(json.dumps({{'blocked': False, 'planner_decision': 'job_selected', 'selected_job': 31, 'effective_mode': 'dry-run', 'shopify_touched': False, 'queue_touched': False}}))\n",
        encoding="utf-8",
    )
    content_plan = {
        "schema": "orin.content-plan-snapshot/v1",
        "client_id": "hoverboard_store",
        "selected_item_number": 31,
        "items": [
            {
                "item_number": 31,
                "target_date": "2026-08-01",
                "status": "planned",
                "topic": "Database pipeline input",
                "target_keyword": "database pipeline input",
                "draft_path": "clients/hoverboard_store/content_engine/drafts/db-input.html",
            }
        ],
    }

    result = run_client(
        client_id="hoverboard_store",
        request_id=str(uuid.uuid4()),
        mode="dry-run",
        workspace_root=tmp_path / "workspace",
        artifact_root=tmp_path / "artifacts",
        repo_root=Path.cwd(),
        durable_db_mode=True,
        content_plan_snapshot=content_plan,
        pipeline_command=[sys.executable, str(script_path)],
        pipeline_preview_path=preview_path,
    )

    run_dir = Path(result["artifact_uri"])
    assert (run_dir / "content_queue_projection.md").stat().st_mode & 0o077 == 0
    assert json.loads((run_dir / "content_plan_snapshot.json").read_text()) == content_plan


def test_selected_database_item_cannot_complete_as_no_job_due(tmp_path):
    preview_path = tmp_path / "pipeline-preview.json"
    command, _, _ = fake_pipeline(
        tmp_path,
        {
            "blocked": False,
            "planner_decision": "no_job_due",
            "selected_job": None,
            "effective_mode": "dry-run",
            "shopify_touched": False,
            "queue_touched": False,
        },
    )
    content_plan = {
        "schema": "orin.content-plan-snapshot/v1",
        "client_id": "hoverboard_store",
        "selected_item_number": 33,
        "items": [
            {
                "item_number": 33,
                "target_date": "2026-08-23",
                "status": "in_progress",
                "topic": "Approved future concept",
            }
        ],
    }

    result = run_client(
        client_id="hoverboard_store",
        request_id=str(uuid.uuid4()),
        mode="dry-run",
        workspace_root=tmp_path / "workspace",
        artifact_root=tmp_path / "artifacts",
        repo_root=Path.cwd(),
        durable_db_mode=True,
        content_plan_snapshot=content_plan,
        pipeline_command=command,
        pipeline_preview_path=preview_path,
    )

    assert result["status"] == "failed"
    assert result["error_code"] == ERROR_CONTENT_PLAN_SELECTION_MISMATCH
    assert result["decision"] == "content_plan_selection_mismatch"


def test_selected_database_item_preserves_pipeline_blocker_without_job_echo(tmp_path):
    preview_path = tmp_path / "pipeline-preview.json"
    command, _, _ = fake_pipeline(
        tmp_path,
        {
            "blocked": True,
            "block_reason": "Phase 2A content quality blocked",
            "selected_job": None,
            "effective_mode": "dry-run",
            "shopify_touched": False,
            "queue_touched": False,
        },
    )
    content_plan = {
        "schema": "orin.content-plan-snapshot/v1",
        "client_id": "hoverboard_store",
        "selected_item_number": 33,
        "items": [
            {
                "item_number": 33,
                "target_date": "2026-08-23",
                "status": "in_progress",
                "topic": "Approved future concept",
            }
        ],
    }

    result = run_client(
        client_id="hoverboard_store",
        request_id=str(uuid.uuid4()),
        mode="dry-run",
        workspace_root=tmp_path / "workspace",
        artifact_root=tmp_path / "artifacts",
        repo_root=Path.cwd(),
        durable_db_mode=True,
        content_plan_snapshot=content_plan,
        pipeline_command=command,
        pipeline_preview_path=preview_path,
    )

    assert result["status"] == "blocked"
    assert result["error_code"] == ERROR_PIPELINE_BLOCKED
    assert result["decision"] == "blocked"


def test_code_version_matches_checkout_without_global_git_configuration():
    repo_root = Path.cwd().resolve()
    expected = subprocess.run(
        ["git", "-c", f"safe.directory={repo_root}", "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert default_code_version(repo_root) == expected


def test_configured_repo_root_accepts_checkout_with_approved_pipeline(tmp_path, monkeypatch):
    entrypoint = tmp_path / "tools/shopify_publisher/orin/cron_entrypoint.py"
    entrypoint.parent.mkdir(parents=True)
    entrypoint.touch()
    monkeypatch.setenv("ORIN_REPO_ROOT", str(tmp_path))

    assert configured_repo_root() == tmp_path.resolve()


def test_configured_repo_root_rejects_missing_approved_pipeline(tmp_path, monkeypatch):
    monkeypatch.setenv("ORIN_REPO_ROOT", str(tmp_path))

    with pytest.raises(ValueError, match="does not contain"):
        configured_repo_root()


def test_missing_pipeline_result_fails_with_stable_error(tmp_path):
    command, preview_path, _ = fake_pipeline(tmp_path, None)
    result = invoke(tmp_path, command, preview_path, str(uuid.uuid4()))

    assert result["status"] == "failed"
    assert result["error_code"] == ERROR_PIPELINE_RESULT_MISSING
    assert result["shopify_create_count"] == 0
    assert result["queue_changed"] is False


def test_request_id_is_locally_idempotent(tmp_path):
    preview = {"blocked": False, "planner_decision": "no_job_due", "effective_mode": "dry-run"}
    command, preview_path, counter_path = fake_pipeline(tmp_path, preview)
    request_id = str(uuid.uuid4())

    first = invoke(tmp_path, command, preview_path, request_id)
    second = invoke(tmp_path, command, preview_path, request_id)

    assert second == first
    assert counter_path.read_text() == "1"


def test_legacy_cached_result_is_reexecuted_into_v2_contract(tmp_path):
    preview = {"blocked": False, "planner_decision": "no_job_due", "effective_mode": "dry-run"}
    command, preview_path, counter_path = fake_pipeline(tmp_path, preview)
    request_id = str(uuid.uuid4())
    first = invoke(tmp_path, command, preview_path, request_id)
    final_path = Path(first["artifact_uri"]) / "final_result.json"
    legacy = dict(first)
    legacy["schema"] = "orin.final-result/v1"
    legacy.pop("replay_disposition")
    legacy.pop("shopify_write_state")
    final_path.write_text(json.dumps(legacy), encoding="utf-8")

    upgraded = invoke(tmp_path, command, preview_path, request_id)

    assert upgraded["schema"] == SCHEMA_VERSION
    assert upgraded["attempt"] == 2
    assert counter_path.read_text() == "2"


def test_request_id_reuse_with_different_mode_is_rejected(tmp_path):
    preview = {"blocked": False, "planner_decision": "no_job_due", "effective_mode": "dry-run"}
    command, preview_path, counter_path = fake_pipeline(tmp_path, preview)
    request_id = str(uuid.uuid4())
    invoke(tmp_path, command, preview_path, request_id)

    with pytest.raises(IdempotencyConflictError):
        invoke(tmp_path, command, preview_path, request_id, mode="hidden-draft")

    assert counter_path.read_text() == "1"


def test_nonzero_pipeline_exit_is_durable_failure(tmp_path):
    preview = {"blocked": False, "planner_decision": "no_job_due", "effective_mode": "dry-run"}
    command, preview_path, _ = fake_pipeline(tmp_path, preview, exit_code=7)
    result = invoke(tmp_path, command, preview_path, str(uuid.uuid4()))

    assert result["status"] == "failed"
    assert result["error_code"] == ERROR_PIPELINE_EXIT_NONZERO
    assert result["pipeline_exit_code"] == 7


def test_timeout_is_recorded_as_durable_failure(tmp_path):
    preview_path = tmp_path / "never-written.json"
    script_path = tmp_path / "slow_pipeline.py"
    script_path.write_text("import time; time.sleep(2)\n", encoding="utf-8")
    result = invoke(
        tmp_path,
        [sys.executable, str(script_path)],
        preview_path,
        str(uuid.uuid4()),
        timeout=0.01,
    )

    assert result["status"] == "failed"
    assert result["error_code"] == ERROR_PIPELINE_TIMEOUT
    assert result["replay_disposition"] == "retry"
    assert Path(result["artifact_uri"], "final_result.json").exists()


def test_hidden_draft_timeout_is_replayed_for_marker_reconciliation(tmp_path):
    preview_path = tmp_path / "replay-preview.json"
    counter_path = tmp_path / "timeout-counter.txt"
    script_path = tmp_path / "timeout_then_reconcile.py"
    script_path.write_text(
        "import json, pathlib, sys, time\n"
        f"counter = pathlib.Path({str(counter_path)!r})\n"
        "count = int(counter.read_text()) + 1 if counter.exists() else 1\n"
        "counter.write_text(str(count))\n"
        "if count == 1:\n"
        "    time.sleep(2)\n"
        "else:\n"
        f"    pathlib.Path({str(preview_path)!r}).write_text(json.dumps({{"
        "'blocked': False, 'transaction_decision': 'DRAFT_CREATED_VERIFICATION_PASSED', "
        "'effective_mode': 'live-draft', 'shopify_article_id': 9001, "
        "'shopify_create_count': 1, 'shopify_write_state': 'article_observed', "
        "'reconciliation_status': 'reconciled', 'replay_disposition': 'terminal'"
        "}))\n",
        encoding="utf-8",
    )
    request_id = str(uuid.uuid4())

    first = invoke(
        tmp_path,
        [sys.executable, str(script_path)],
        preview_path,
        request_id,
        mode="hidden-draft",
        timeout=0.1,
    )
    second = invoke(
        tmp_path,
        [sys.executable, str(script_path)],
        preview_path,
        request_id,
        mode="hidden-draft",
        timeout=1,
    )
    third = invoke(
        tmp_path,
        [sys.executable, str(script_path)],
        preview_path,
        request_id,
        mode="hidden-draft",
        timeout=1,
    )

    assert first["replay_disposition"] == "reconcile"
    assert first["shopify_write_state"] == "unknown"
    assert second["attempt"] == 2
    assert second["replay_disposition"] == "terminal"
    assert second["shopify_create_count"] == 1
    assert third == second
    assert counter_path.read_text() == "2"


def test_needs_review_preview_cannot_be_terminalized(tmp_path):
    preview = {
        "blocked": False,
        "transaction_decision": "DRAFT_CREATED_VERIFICATION_FAILED",
        "effective_mode": "live-draft",
        "shopify_article_id": 9001,
        "shopify_create_count": 1,
        "shopify_write_state": "article_observed",
        "reconciliation_status": "needs_review",
    }
    command, preview_path, _ = fake_pipeline(tmp_path, preview)

    result = invoke(
        tmp_path,
        command,
        preview_path,
        str(uuid.uuid4()),
        mode="hidden-draft",
    )

    assert result["status"] == "blocked"
    assert result["replay_disposition"] == "reconcile"


def test_hidden_draft_maps_to_existing_double_confirmation_gate(tmp_path):
    preview_path = tmp_path / "pipeline-preview.json"
    args_path = tmp_path / "args.json"
    script_path = tmp_path / "capture_args.py"
    script_path.write_text(
        "import json, pathlib, sys\n"
        f"pathlib.Path({str(args_path)!r}).write_text(json.dumps(sys.argv[1:]))\n"
        f"pathlib.Path({str(preview_path)!r}).write_text(json.dumps({{'blocked': True, 'effective_mode': 'live-draft'}}))\n",
        encoding="utf-8",
    )
    invoke(
        tmp_path,
        [sys.executable, str(script_path)],
        preview_path,
        str(uuid.uuid4()),
        mode="hidden-draft",
        job_number="29",
    )

    captured = json.loads(args_path.read_text())
    assert "--live-draft" in captured
    assert "--confirm-live-draft" in captured
    assert "--client=hoverboard_store" in captured
    assert "--job=29" in captured
    assert "--dry-run" not in captured


def test_request_id_reuse_with_different_job_pin_is_rejected(tmp_path):
    preview = {"blocked": False, "planner_decision": "no_job_due", "effective_mode": "dry-run"}
    command, preview_path, counter_path = fake_pipeline(tmp_path, preview)
    request_id = str(uuid.uuid4())
    invoke(tmp_path, command, preview_path, request_id, job_number="28")

    with pytest.raises(IdempotencyConflictError):
        invoke(tmp_path, command, preview_path, request_id, job_number="29")

    assert counter_path.read_text() == "1"


def test_hidden_draft_child_receives_durable_marker_context(tmp_path):
    preview_path = tmp_path / "pipeline-preview.json"
    env_path = tmp_path / "durable-env.json"
    request_id = str(uuid.uuid4())
    script_path = tmp_path / "capture_hidden_env.py"
    script_path.write_text(
        "import json, os, pathlib\n"
        f"pathlib.Path({str(env_path)!r}).write_text(json.dumps(dict("
        "key=os.environ.get('ORIN_IDEMPOTENCY_KEY'), "
        "durable=os.environ.get('ORIN_DURABLE_DB_MODE'), "
        "artifact_dir=os.environ.get('ORIN_RUN_ARTIFACT_DIR'))))\n"
        f"pathlib.Path({str(preview_path)!r}).write_text(json.dumps({{'blocked': True, 'effective_mode': 'live-draft'}}))\n",
        encoding="utf-8",
    )

    result = invoke(
        tmp_path,
        [sys.executable, str(script_path)],
        preview_path,
        request_id,
        mode="hidden-draft",
    )

    child_environment = json.loads(env_path.read_text())
    assert child_environment["key"] == f"hoverboard_store:{request_id}"
    assert child_environment["durable"] == "1"
    assert child_environment["artifact_dir"] == result["artifact_uri"]
    assert result["effective_mode"] == "hidden-draft"


def test_database_hidden_draft_uses_exact_reviewed_html_without_pipeline(
    tmp_path, monkeypatch
):
    body = "<article><h1>Approved article</h1><p>Exact reviewed body.</p></article>"
    body_sha256 = hashlib.sha256(body.encode()).hexdigest()
    content_plan = {
        "schema": "orin.content-plan-snapshot/v1",
        "client_id": "hoverboard_store",
        "selected_item_id": "dededede-dede-4ede-8ede-dededededede",
        "selected_item_number": 33,
        "items": [
            {
                "content_item_id": "dededede-dede-4ede-8ede-dededededede",
                "item_number": 33,
                "target_date": "2026-08-23",
                "status": "local_draft_created",
                "topic": "Approved article",
                "draft_path": "clients/hoverboard_store/content_engine/drafts/approved-article.html",
            }
        ],
        "approved_draft": {
            "draft_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
            "content_item_id": "dededede-dede-4ede-8ede-dededededede",
            "content_item_version": 5,
            "source_run_id": "hb_20260804T123458Z_729bc75f",
            "title": "Approved article",
            "body_html": body,
            "body_sha256": body_sha256,
            "handle": "approved-article",
        },
    }
    observed = {}

    def ensure(approved, *, client_id, request_id):
        observed["approved"] = approved
        observed["client_id"] = client_id
        observed["request_id"] = request_id
        return DraftResult(
            article_id="gid://shopify/Article/9001",
            numeric_article_id=9001,
            handle="approved-article",
            create_count=1,
            reconciliation_status="reconciled",
            shopify_write_state="article_observed",
            idempotency_marker=f"orin-v1:hoverboard_store:{request_id}",
            body_sha256=body_sha256,
            canonical_body_sha256=body_sha256,
        )

    monkeypatch.setattr("orin_runner.runner.ensure_approved_review_draft", ensure)
    request_id = str(uuid.uuid4())
    result = run_client(
        client_id="hoverboard_store",
        request_id=request_id,
        mode="hidden-draft",
        workspace_root=tmp_path / "workspace",
        artifact_root=tmp_path / "artifacts",
        repo_root=Path.cwd(),
        durable_db_mode=True,
        content_plan_snapshot=content_plan,
        pipeline_command=["/must/not/run"],
    )

    assert observed["approved"].body_html == body
    assert result["status"] == "completed"
    assert result["job_id"] == "33"
    assert result["shopify_article_id"] == "9001"
    assert result["shopify_handle"] == "approved-article"
    assert result["shopify_published"] is False
    run_dir = Path(result["artifact_uri"])
    assert (run_dir / "approved_review_draft.html").read_text() == body
    evidence = json.loads((run_dir / "reviewed_draft_transaction.json").read_text())
    assert evidence["stored_body_sha256"] == body_sha256
    assert evidence["sent_body_sha256"] == body_sha256
    assert evidence["fetched_body_sha256"] == body_sha256
    assert evidence["approved_canonical_body_sha256"] == body_sha256
    assert evidence["fetched_canonical_body_sha256"] == body_sha256
    assert evidence["body_canonicalization"] == "shopify-safe-html-serialization/v2"


def test_database_hidden_draft_rejects_tampered_review_body_before_shopify(
    tmp_path, monkeypatch
):
    content_plan = {
        "schema": "orin.content-plan-snapshot/v1",
        "client_id": "hoverboard_store",
        "selected_item_id": "dededede-dede-4ede-8ede-dededededede",
        "selected_item_number": 33,
        "items": [
            {
                "content_item_id": "dededede-dede-4ede-8ede-dededededede",
                "item_number": 33,
                "status": "local_draft_created",
                "topic": "Approved article",
            }
        ],
        "approved_draft": {
            "draft_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
            "content_item_id": "dededede-dede-4ede-8ede-dededededede",
            "content_item_version": 5,
            "source_run_id": "hb_20260804T123458Z_729bc75f",
            "title": "Approved article",
            "body_html": "<p>Tampered.</p>",
            "body_sha256": "0" * 64,
            "handle": "approved-article",
        },
    }
    called = False

    def ensure(*_args, **_kwargs):
        nonlocal called
        called = True
        raise AssertionError("Shopify must not be contacted")

    monkeypatch.setattr("orin_runner.runner.ensure_approved_review_draft", ensure)
    result = run_client(
        client_id="hoverboard_store",
        request_id=str(uuid.uuid4()),
        mode="hidden-draft",
        workspace_root=tmp_path / "workspace",
        artifact_root=tmp_path / "artifacts",
        repo_root=Path.cwd(),
        durable_db_mode=True,
        content_plan_snapshot=content_plan,
    )

    assert called is False
    assert result["status"] == "failed"
    assert result["error_code"] == "ORIN_APPROVED_DRAFT_INVALID"
    assert result["shopify_write_state"] == "not_attempted"


def test_database_hidden_draft_reconciles_same_marker_after_uncertain_write(
    tmp_path, monkeypatch
):
    body = "<article><h1>Approved article</h1><p>Exact reviewed body.</p></article>"
    body_sha256 = hashlib.sha256(body.encode()).hexdigest()
    content_plan = {
        "schema": "orin.content-plan-snapshot/v1",
        "client_id": "hoverboard_store",
        "selected_item_id": "dededede-dede-4ede-8ede-dededededede",
        "selected_item_number": 33,
        "items": [
            {
                "content_item_id": "dededede-dede-4ede-8ede-dededededede",
                "item_number": 33,
                "status": "local_draft_created",
                "topic": "Approved article",
            }
        ],
        "approved_draft": {
            "draft_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
            "content_item_id": "dededede-dede-4ede-8ede-dededededede",
            "content_item_version": 5,
            "source_run_id": "hb_20260804T123458Z_729bc75f",
            "title": "Approved article",
            "body_html": body,
            "body_sha256": body_sha256,
            "handle": "approved-article",
        },
    }
    calls = 0

    def ensure(_approved, *, client_id, request_id):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise ShopifyRequestError("response lost after mutation")
        return DraftResult(
            article_id="gid://shopify/Article/9001",
            numeric_article_id=9001,
            handle="approved-article",
            create_count=1,
            reconciliation_status="reconciled",
            shopify_write_state="article_observed",
            idempotency_marker=f"orin-v1:{client_id}:{request_id}",
            body_sha256=body_sha256,
            canonical_body_sha256=body_sha256,
        )

    monkeypatch.setattr("orin_runner.runner.ensure_approved_review_draft", ensure)
    request_id = str(uuid.uuid4())
    arguments = dict(
        client_id="hoverboard_store",
        request_id=request_id,
        mode="hidden-draft",
        workspace_root=tmp_path / "workspace",
        artifact_root=tmp_path / "artifacts",
        repo_root=Path.cwd(),
        durable_db_mode=True,
        content_plan_snapshot=content_plan,
    )

    first = run_client(**arguments)
    second = run_client(**arguments)
    third = run_client(**arguments)

    assert first["status"] == "blocked"
    assert first["replay_disposition"] == "reconcile"
    assert second["status"] == "completed"
    assert second["attempt"] == 2
    assert second["shopify_create_count"] == 1
    assert third == second
    assert calls == 2


def test_database_worker_dry_run_uses_private_artifact_directory(tmp_path):
    preview_path = tmp_path / "pipeline-preview.json"
    env_path = tmp_path / "durable-dry-run-env.json"
    script_path = tmp_path / "capture_durable_dry_run_env.py"
    script_path.write_text(
        "import json, os, pathlib\n"
        f"pathlib.Path({str(env_path)!r}).write_text(json.dumps(dict("
        "durable=os.environ.get('ORIN_DURABLE_DB_MODE'), "
        "artifact_dir=os.environ.get('ORIN_RUN_ARTIFACT_DIR'))))\n"
        f"pathlib.Path({str(preview_path)!r}).write_text(json.dumps("
        "{'blocked': False, 'effective_mode': 'dry-run'}))\n",
        encoding="utf-8",
    )
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    result = run_client(
        client_id="hoverboard_store",
        request_id=str(uuid.uuid4()),
        mode="dry-run",
        workspace_root=workspace,
        artifact_root=tmp_path / "artifacts",
        repo_root=Path.cwd(),
        durable_db_mode=True,
        pipeline_command=[sys.executable, str(script_path)],
        pipeline_preview_path=preview_path,
    )

    child_environment = json.loads(env_path.read_text())
    assert child_environment["durable"] == "1"
    assert child_environment["artifact_dir"] == result["artifact_uri"]


def test_dry_run_removes_shopify_credentials_from_child(tmp_path, monkeypatch):
    preview_path = tmp_path / "pipeline-preview.json"
    env_path = tmp_path / "shopify-env.json"
    script_path = tmp_path / "capture_env.py"
    script_path.write_text(
        "import json, os, pathlib\n"
        f"pathlib.Path({str(env_path)!r}).write_text(json.dumps(dict("
        "direct=os.environ.get('HOVERBOARD_STORE_SHOPIFY_ACCESS_TOKEN', 'missing'), "
        "file=os.environ.get('HOVERBOARD_STORE_SHOPIFY_ACCESS_TOKEN_FILE', 'missing'))))\n"
        f"pathlib.Path({str(preview_path)!r}).write_text(json.dumps({{'blocked': False, 'effective_mode': 'dry-run'}}))\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("HOVERBOARD_STORE_SHOPIFY_ACCESS_TOKEN", "must-not-reach-child")
    monkeypatch.setenv(
        "HOVERBOARD_STORE_SHOPIFY_ACCESS_TOKEN_FILE",
        "/must/not/reach/child",
    )
    invoke(tmp_path, [sys.executable, str(script_path)], preview_path, str(uuid.uuid4()))

    assert json.loads(env_path.read_text()) == {"direct": "missing", "file": "missing"}
