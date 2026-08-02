from __future__ import annotations

import json
from pathlib import Path

import pytest

from orin_evidence_sync.cli import main
from orin_evidence_sync.service import EvidenceSyncError, build_artifacts, sync_run


def _run_dir(tmp_path: Path, *, run_id: str = "hb_20260802T120000Z_abcdef12") -> Path:
    run_dir = tmp_path / run_id
    run_dir.mkdir()
    (run_dir / "final_result.json").write_text(
        json.dumps(
            {
                "schema": "orin.final-result/v2",
                "client_id": "hoverboard_store",
                "run_id": run_id,
                "status": "completed",
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "events.jsonl").write_text('{"event":"done"}\n', encoding="utf-8")
    (run_dir / "stdout.log").write_text("safe output\n", encoding="utf-8")
    return run_dir


def test_builds_redacted_storage_records(tmp_path: Path) -> None:
    run_dir = _run_dir(tmp_path)
    artifacts = build_artifacts(run_dir)

    assert [artifact.kind for artifact in artifacts] == ["final_result", "events", "stdout"]
    assert all(artifact.object_path.startswith("hoverboard_store/") for artifact in artifacts)
    assert all(len(artifact.sha256) == 64 for artifact in artifacts)
    assert all("local_path" not in artifact.database_record() for artifact in artifacts)


def test_rejects_directory_identity_mismatch(tmp_path: Path) -> None:
    run_dir = _run_dir(tmp_path)
    result = json.loads((run_dir / "final_result.json").read_text(encoding="utf-8"))
    result["run_id"] = "hb_20260802T120001Z_deadbeef"
    (run_dir / "final_result.json").write_text(json.dumps(result), encoding="utf-8")

    with pytest.raises(EvidenceSyncError, match="does not match"):
        build_artifacts(run_dir)


def test_rejects_symlinked_evidence(tmp_path: Path) -> None:
    run_dir = _run_dir(tmp_path)
    outside = tmp_path / "outside.log"
    outside.write_text("not evidence", encoding="utf-8")
    (run_dir / "stderr.log").symlink_to(outside)

    with pytest.raises(EvidenceSyncError, match="unsafe evidence"):
        build_artifacts(run_dir)


def test_sync_is_idempotent_at_api_boundary(tmp_path: Path) -> None:
    run_dir = _run_dir(tmp_path)

    class FakeApi:
        def __init__(self) -> None:
            self.asserted = False

        def assert_run(self, *, client_id: str, run_id: str) -> None:
            self.asserted = client_id == "hoverboard_store" and run_id == run_dir.name

        def upload_immutable(self, _artifact: object) -> bool:
            return False

        def register_artifact(self, _artifact: object) -> bool:
            return False

    api = FakeApi()
    result = sync_run(api, run_dir)

    assert api.asserted is True
    assert result["artifact_count"] == 3
    assert result["uploaded_count"] == 0
    assert result["replayed_count"] == 3
    assert result["registered_count"] == 0


def test_cli_dry_run_needs_no_secret(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    run_dir = _run_dir(tmp_path)

    assert main(["--artifact-root", str(tmp_path), "--run-id", run_dir.name, "--dry-run"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "validated"
    assert result["results"][0]["artifact_count"] == 3
