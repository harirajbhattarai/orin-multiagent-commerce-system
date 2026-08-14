import importlib
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
ORIN_TOOLS = REPO_ROOT / "tools" / "shopify_publisher" / "orin"


def _load_hcs_client_loader(monkeypatch, runtime_root: Path):
    monkeypatch.syspath_prepend(str(ORIN_TOOLS))
    monkeypatch.setenv("ORIN_WORKSPACE_ROOT", str(runtime_root))
    sys.modules.pop("workspace_paths", None)
    sys.modules.pop("hcs_client_loader", None)
    return importlib.import_module("hcs_client_loader")


def test_hcs_loader_uses_private_queue_projection_and_scoped_runtime(
    tmp_path, monkeypatch
):
    runtime_root = tmp_path / "runtime"
    product_truth = (
        runtime_root
        / "clients"
        / "hcs_gadgets"
        / "content_engine"
        / "automation_state"
        / "product_truth"
    )
    product_truth.mkdir(parents=True)
    normalised = product_truth / "product_truth_normalised.json"
    normalised.write_text(
        '{"freshness_status":"PRODUCT_TRUTH_FRESH",'
        '"writer_ready":true,"validation_status":"PRODUCT_TRUTH_FRESH",'
        '"client_id":"hcs_gadgets",'
        '"source_store":"hcsgadgets-com.myshopify.com"}',
        encoding="utf-8",
    )
    (product_truth / "product_truth_link_map.json").write_text(
        "{}", encoding="utf-8"
    )
    private_run = tmp_path / "evidence" / "run"
    private_run.mkdir(parents=True)
    projection = private_run / "content_queue_projection.md"
    projection.write_text("# private database projection\n", encoding="utf-8")

    monkeypatch.setenv("ORIN_DURABLE_DB_MODE", "1")
    monkeypatch.setenv("ORIN_RUN_ARTIFACT_DIR", str(private_run))
    monkeypatch.setenv("ORIN_CONTENT_QUEUE_PATH", str(projection))
    loader = _load_hcs_client_loader(monkeypatch, runtime_root)

    config = loader.get_hcs_client_config()

    assert config["loaded"] is True
    assert config["writer_ready"] is True
    assert config["queue_path"] == str(projection)
    assert config["product_truth_normalised"] == str(normalised)
    assert config["product_truth_adapter"].startswith(str(REPO_ROOT))
    assert not config["queue_path"].startswith(str(runtime_root))


def test_hcs_route_runs_from_immutable_source_not_runtime():
    entrypoint = (ORIN_TOOLS / "cron_entrypoint.py").read_text(encoding="utf-8")

    assert "cwd=str(source_root())" in entrypoint
    assert "cwd=str(BASE_DIR)" not in entrypoint.split(
        "if CLIENT_ROUTE == \"hcs_gadgets\":", 1
    )[1].split("# Default route", 1)[0]


def test_hcs_runtime_path_cannot_escape_client_subtree(tmp_path, monkeypatch):
    loader = _load_hcs_client_loader(monkeypatch, tmp_path / "runtime")

    with pytest.raises(RuntimeError, match="escapes the dedicated client subtree"):
        loader._runtime_path("clients/hoverboard_store/content_engine")
