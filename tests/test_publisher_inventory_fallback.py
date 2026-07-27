import json
import sys
from pathlib import Path


ORIN_TOOLS = (
    Path(__file__).resolve().parents[1]
    / "tools"
    / "shopify_publisher"
    / "orin"
)
sys.path.insert(0, str(ORIN_TOOLS))

import publisher_agent  # noqa: E402


def test_missing_shopify_config_uses_local_inventory_snapshot(
    monkeypatch,
    tmp_path,
):
    inventory_path = tmp_path / "shopify_inventory.json"
    expected_inventory = [
        {
            "id": 123,
            "handle": "existing-draft",
            "title": "Existing Draft",
        }
    ]
    inventory_path.write_text(
        json.dumps(expected_inventory),
        encoding="utf-8",
    )

    def raise_missing_config(*, limit, max_pages):
        assert limit == 250
        assert max_pages == 20
        raise RuntimeError("credential detail must not escape")

    monkeypatch.setattr(
        publisher_agent,
        "fetch_blog_articles_paginated",
        raise_missing_config,
    )
    monkeypatch.setattr(
        publisher_agent,
        "INVENTORY_PATH",
        inventory_path,
    )

    result = publisher_agent.refresh_shopify_inventory()

    assert result == {
        "inventory": expected_inventory,
        "live_fetch_success": False,
        "fallback_used": True,
        "inventory_available": True,
        "source": "local_snapshot",
        "error": "LIVE_FETCH_EXCEPTION:RuntimeError",
    }


def test_missing_live_and_local_inventory_blocks_safely(
    monkeypatch,
    tmp_path,
):
    def raise_missing_config(*, limit, max_pages):
        raise RuntimeError("credential detail must not escape")

    monkeypatch.setattr(
        publisher_agent,
        "fetch_blog_articles_paginated",
        raise_missing_config,
    )
    monkeypatch.setattr(
        publisher_agent,
        "INVENTORY_PATH",
        tmp_path / "missing.json",
    )

    result = publisher_agent.refresh_shopify_inventory()

    assert result == {
        "inventory": [],
        "live_fetch_success": False,
        "fallback_used": False,
        "inventory_available": False,
        "source": "unavailable",
        "error": "LIVE_FETCH_EXCEPTION:RuntimeError",
    }
