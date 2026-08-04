from __future__ import annotations

import pytest

from orin_runner.content_plan import (
    ContentPlanSnapshotError,
    render_content_plan_markdown,
    validate_content_plan_snapshot,
)


def snapshot() -> dict[str, object]:
    return {
        "schema": "orin.content-plan-snapshot/v1",
        "client_id": "hoverboard_store",
        "selected_item_number": 31,
        "items": [
            {
                "content_item_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
                "item_number": 31,
                "target_date": "2026-08-01",
                "expected_draft_date": "2026-07-18",
                "cluster": "Buyer Guide",
                "decision": "create_new",
                "status": "planned",
                "topic": "A database-owned topic",
                "target_keyword": "database owned topic",
                "draft_path": "clients/hoverboard_store/content_engine/drafts/db-topic.html",
                "notes": "- Keep this safe.",
                "shopify_article_id": None,
                "shopify_handle": None,
                "version": 1,
            }
        ],
    }


def test_snapshot_renders_canonical_read_only_projection():
    rendered = render_content_plan_markdown(snapshot(), client_id="hoverboard_store")

    assert "Generated from the authoritative database content plan." in rendered
    assert "## Job 31" in rendered
    assert "Status: planned" in rendered
    assert "Topic: A database-owned topic" in rendered
    assert "- Keep this safe." in rendered


def test_selected_in_progress_item_is_planned_only_in_compatibility_projection():
    value = snapshot()
    value["items"][0]["status"] = "in_progress"  # type: ignore[index]

    rendered = render_content_plan_markdown(value, client_id="hoverboard_store")

    assert "Status: planned" in rendered
    assert value["items"][0]["status"] == "in_progress"  # type: ignore[index]


def test_snapshot_rejects_cross_tenant_data():
    with pytest.raises(ContentPlanSnapshotError, match="another client"):
        validate_content_plan_snapshot(snapshot(), client_id="hcs_gadgets")


def test_snapshot_rejects_duplicate_item_numbers():
    value = snapshot()
    value["items"] = [value["items"][0], dict(value["items"][0])]  # type: ignore[index]

    with pytest.raises(ContentPlanSnapshotError, match="unique"):
        validate_content_plan_snapshot(value, client_id="hoverboard_store")


def test_snapshot_rejects_incomplete_planned_item():
    value = snapshot()
    value["items"][0]["topic"] = ""  # type: ignore[index]

    with pytest.raises(ContentPlanSnapshotError, match="requires a topic"):
        validate_content_plan_snapshot(value, client_id="hoverboard_store")
