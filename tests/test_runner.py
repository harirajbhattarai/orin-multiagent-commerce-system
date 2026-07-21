import json
import sys
import uuid
from pathlib import Path

from orin_runner.contract import (
    ERROR_PIPELINE_EXIT_NONZERO,
    ERROR_PIPELINE_RESULT_MISSING,
    ERROR_PIPELINE_TIMEOUT,
    SCHEMA_VERSION,
)
from orin_runner.runner import run_client


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
    )


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
    final_path = Path(result["artifact_uri"]) / "final_result.json"
    assert json.loads(final_path.read_text()) == result
    assert final_path.stat().st_mode & 0o077 == 0


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
    assert Path(result["artifact_uri"], "final_result.json").exists()


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
    )

    captured = json.loads(args_path.read_text())
    assert "--live-draft" in captured
    assert "--confirm-live-draft" in captured
    assert "--dry-run" not in captured


def test_dry_run_removes_shopify_credentials_from_child(tmp_path, monkeypatch):
    preview_path = tmp_path / "pipeline-preview.json"
    env_path = tmp_path / "shopify-env.txt"
    script_path = tmp_path / "capture_env.py"
    script_path.write_text(
        "import json, os, pathlib\n"
        f"pathlib.Path({str(env_path)!r}).write_text(os.environ.get('HOVERBOARD_STORE_SHOPIFY_ACCESS_TOKEN', 'missing'))\n"
        f"pathlib.Path({str(preview_path)!r}).write_text(json.dumps({{'blocked': False, 'effective_mode': 'dry-run'}}))\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("HOVERBOARD_STORE_SHOPIFY_ACCESS_TOKEN", "must-not-reach-child")
    invoke(tmp_path, [sys.executable, str(script_path)], preview_path, str(uuid.uuid4()))

    assert env_path.read_text() == "missing"
