from __future__ import annotations

import hashlib

import pytest

from orin_shopify.reviewed_draft import (
    ReviewedDraftContractError,
    ShopifyRuntimeConfig,
    approved_review_draft_from_snapshot,
    ensure_approved_review_draft,
    load_shopify_runtime_config,
)


BODY = "<article><h1>Approved article</h1><p>Exact reviewed body.</p></article>"


def snapshot() -> dict:
    return {
        "schema": "orin.content-plan-snapshot/v1",
        "client_id": "hoverboard_store",
        "selected_item_id": "dededede-dede-4ede-8ede-dededededede",
        "selected_item_number": 33,
        "items": [],
        "approved_draft": {
            "draft_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
            "content_item_id": "dededede-dede-4ede-8ede-dededededede",
            "content_item_version": 5,
            "source_run_id": "hb_20260804T123458Z_729bc75f",
            "title": "Approved article",
            "body_html": BODY,
            "body_sha256": hashlib.sha256(BODY.encode()).hexdigest(),
            "handle": "approved-article",
        },
    }


def test_snapshot_returns_exact_hash_verified_review_draft():
    approved = approved_review_draft_from_snapshot(
        snapshot(), client_id="hoverboard_store"
    )

    assert approved.item_number == 33
    assert approved.content_item_version == 5
    assert approved.body_html == BODY
    assert approved.evidence()["body_sha256"] == hashlib.sha256(BODY.encode()).hexdigest()
    assert "body_html" not in approved.evidence()


def test_snapshot_rejects_tampered_html():
    value = snapshot()
    value["approved_draft"]["body_html"] += "<p>Regenerated.</p>"

    with pytest.raises(ReviewedDraftContractError, match="does not match"):
        approved_review_draft_from_snapshot(value, client_id="hoverboard_store")


def test_snapshot_rejects_draft_owned_by_another_item():
    value = snapshot()
    value["approved_draft"]["content_item_id"] = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"

    with pytest.raises(ReviewedDraftContractError, match="does not own"):
        approved_review_draft_from_snapshot(value, client_id="hoverboard_store")


def test_snapshot_rejects_noncanonical_handle():
    value = snapshot()
    value["approved_draft"]["handle"] = "Approved Article"

    with pytest.raises(ReviewedDraftContractError, match="not canonical"):
        approved_review_draft_from_snapshot(value, client_id="hoverboard_store")


def test_dry_run_snapshot_cannot_be_used_for_hidden_draft():
    value = snapshot()
    value["approved_draft"] = None

    with pytest.raises(ReviewedDraftContractError, match="no frozen"):
        approved_review_draft_from_snapshot(value, client_id="hoverboard_store")


def test_hcs_runtime_config_uses_only_hcs_environment(monkeypatch):
    monkeypatch.setenv("HCS_GADGETS_SHOPIFY_STORE_DOMAIN", "hcsgadgets-com.myshopify.com")
    monkeypatch.setenv("HCS_GADGETS_SHOPIFY_API_VERSION", "2026-07")
    monkeypatch.setenv("HCS_GADGETS_SHOPIFY_BLOG_ID", "89150259452")
    monkeypatch.setenv("HCS_GADGETS_SHOPIFY_ACCESS_TOKEN", "hcs-secret")
    monkeypatch.setenv("HOVERBOARD_STORE_SHOPIFY_ACCESS_TOKEN", "wrong-client-secret")

    config = load_shopify_runtime_config(client_id="hcs_gadgets")

    assert config.store_domain == "hcsgadgets-com.myshopify.com"
    assert config.access_token == "hcs-secret"
    assert config.blog_id == "gid://shopify/Blog/89150259452"
    assert config.author_name == "HCS Gadgets"


def test_hcs_hidden_draft_uses_hcs_author_and_stays_unpublished():
    value = snapshot()
    value["client_id"] = "hcs_gadgets"
    approved = approved_review_draft_from_snapshot(value, client_id="hcs_gadgets")
    observed = {}

    class Transport:
        def execute(self, document, variables):
            if "FindOrinDrafts" in document:
                return {
                    "blog": {
                        "articles": {
                            "nodes": [],
                            "pageInfo": {"hasNextPage": False, "endCursor": None},
                        }
                    }
                }
            if "CreateOrinHiddenDraft" in document:
                observed["article"] = variables["article"]
                return {
                    "articleCreate": {
                        "article": {"id": "gid://shopify/Article/9001"},
                        "userErrors": [],
                    }
                }
            return {
                "article": {
                    "id": "gid://shopify/Article/9001",
                    "handle": approved.handle,
                    "title": approved.title,
                    "body": approved.body_html,
                    "publishedAt": None,
                    "metafield": {
                        "value": "orin-v1:hcs_gadgets:11111111-1111-4111-8111-111111111111"
                    },
                }
            }

    result = ensure_approved_review_draft(
        approved,
        client_id="hcs_gadgets",
        request_id="11111111-1111-4111-8111-111111111111",
        config=ShopifyRuntimeConfig(
            store_domain="hcsgadgets-com.myshopify.com",
            access_token="not-used-by-injected-transport",
            api_version="2026-07",
            blog_id="gid://shopify/Blog/89150259452",
            author_name="HCS Gadgets",
        ),
        transport=Transport(),
    )

    assert observed["article"]["author"] == {"name": "HCS Gadgets"}
    assert observed["article"]["isPublished"] is False
    assert result.numeric_article_id == 9001
