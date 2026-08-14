import importlib
import runpy
import sys
from datetime import date
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


def test_database_bound_hcs_item_bypasses_legacy_calendar(monkeypatch):
    monkeypatch.syspath_prepend(str(ORIN_TOOLS))
    monkeypatch.setenv("ORIN_DURABLE_DB_MODE", "1")
    module = runpy.run_path(str(ORIN_TOOLS / "hcs_cron_entrypoint.py"))
    select_job = module["planner_select_job"]
    jobs = [
        {
            "job_number": "1",
            "topic": "Approved database concept",
            "keyword": "approved concept",
            "queue_status": "planned",
            "target_date": "2026-08-28",
        }
    ]

    result = select_job(
        jobs,
        date(2026, 8, 14),
        durable_selected_job="1",
    )

    assert result["decision"] == "job_selected"
    assert result["selected_job"] == "1"
    assert result["days_until_target"] == 14
    assert result["durable_selected_job"] == "1"


def test_database_bound_hcs_item_fails_closed_without_database_mode(monkeypatch):
    monkeypatch.syspath_prepend(str(ORIN_TOOLS))
    monkeypatch.delenv("ORIN_DURABLE_DB_MODE", raising=False)
    module = runpy.run_path(str(ORIN_TOOLS / "hcs_cron_entrypoint.py"))

    result = module["planner_select_job"](
        [{"job_number": "1", "queue_status": "planned"}],
        date(2026, 8, 14),
        durable_selected_job="1",
    )

    assert result == {
        "decision": "blocked",
        "block_reason": "DURABLE_SELECTION_REQUIRES_DATABASE_MODE",
    }


def test_hcs_normaliser_adds_bound_metadata_and_schema(monkeypatch):
    monkeypatch.syspath_prepend(str(ORIN_TOOLS))
    from writer_agent import _normalise_hcs_model_output

    body = """<article class="hcs-article">
<section class="hcs-faq"><div class="hcs-faq-item">
<h3>What should a buyer compare?</h3><p>Compare the listing and manual.</p>
</div></section></article>"""
    output = _normalise_hcs_model_output(
        body,
        meta_title="Adult Scooter Suspension Guide",
        meta_description="Compare adult scooter suspension details using listings and manuals before choosing a model that suits your intended use.",
        approved_handle="adult-scooter-suspension-guide",
        target_keyword="adult electric scooter suspension guide",
        cluster="buying-guide",
        job_number="1",
        title="Adult Electric Scooter Suspension: What UK Buyers Should Compare",
        site_url="https://hcsgadgets.com",
        blog_handle="gadget-blog",
        byline="HCS Gadgets",
    )

    assert "Meta Title: Adult Scooter Suspension Guide" in output
    assert output.count('<script type="application/ld+json">') == 2
    assert '"@type":"BlogPosting"' in output
    assert '"@type":"FAQPage"' in output
    assert "https://hcsgadgets.com/blogs/gadget-blog/adult-scooter-suspension-guide" in output


def test_hcs_visible_quality_ignores_json_ld_arrays(monkeypatch):
    monkeypatch.syspath_prepend(str(ORIN_TOOLS))
    from hcs_writer_adapter import _visible_article_html, check_content_quality

    html = """<article class="hcs-article">
<section class="hcs-content"><h2>First check</h2><p>Compare the listing.</p>
<h2>Second check</h2><p>Read the manufacturer manual.</p></section>
<script type="application/ld+json">{"mainEntity":[{"name":"Question"}]}</script>
</article>"""

    passed, failures = check_content_quality(_visible_article_html(html))

    assert passed is True
    assert failures == []
