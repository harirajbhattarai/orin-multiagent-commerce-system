import runpy
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
