import runpy
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "tools"
    / "shopify_publisher"
    / "orin"
    / "workspace_paths.py"
)
MODULE = runpy.run_path(str(MODULE_PATH))
writable_report_path = MODULE["writable_report_path"]
writable_output_path = MODULE["writable_output_path"]


def test_durable_report_uses_private_run_evidence(tmp_path, monkeypatch):
    monkeypatch.setenv("ORIN_RUN_ARTIFACT_DIR", str(tmp_path))
    monkeypatch.setenv("ORIN_WORKSPACE_ROOT", "/runtime")

    result = writable_report_path(
        artifact_name="orin_status_phase2e.md",
        workspace_relative_path=(
            "clients/hoverboard_store/content_engine/orin_status_phase2e.md"
        ),
    )

    assert result == tmp_path / "orin_status_phase2e.md"


def test_report_falls_back_to_workspace_without_durable_run(tmp_path, monkeypatch):
    monkeypatch.delenv("ORIN_RUN_ARTIFACT_DIR", raising=False)
    monkeypatch.setenv("ORIN_WORKSPACE_ROOT", str(tmp_path))

    result = writable_report_path(
        artifact_name="orin_status_phase2c.md",
        workspace_relative_path=(
            "clients/hoverboard_store/content_engine/orin_status_phase2c.md"
        ),
    )

    assert result == (
        tmp_path
        / "clients"
        / "hoverboard_store"
        / "content_engine"
        / "orin_status_phase2c.md"
    )


def test_durable_report_rejects_relative_artifact_directory(monkeypatch):
    monkeypatch.setenv("ORIN_RUN_ARTIFACT_DIR", "relative/evidence")

    with pytest.raises(RuntimeError, match="must be absolute"):
        writable_report_path(
            artifact_name="orin_status_phase2e.md",
            workspace_relative_path=(
                "clients/hoverboard_store/content_engine/orin_status_phase2e.md"
            ),
        )


def test_transaction_evidence_uses_private_run_directory(tmp_path):
    repository_root = Path(__file__).resolve().parents[1]
    agents_dir = (
        repository_root / "tools" / "shopify_publisher" / "orin"
    )
    environment = os.environ.copy()
    environment["ORIN_RUN_ARTIFACT_DIR"] = str(tmp_path)
    environment["PYTHONPATH"] = os.pathsep.join(
        [str(agents_dir), str(repository_root / "src")]
    )

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import json; "
                "from shopify_draft_transaction import _EVIDENCE_BASE; "
                "from live_draft_gate import _check_verification_capability; "
                "print(json.dumps({'base': str(_EVIDENCE_BASE), "
                "'capability': _check_verification_capability()}))"
            ),
        ],
        cwd=repository_root,
        env=environment,
        capture_output=True,
        text=True,
        check=True,
    )

    diagnostic = json.loads(result.stdout)
    assert diagnostic["base"] == str(tmp_path / "shopify_transaction")
    assert diagnostic["capability"] == [True, []]
