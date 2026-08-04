from __future__ import annotations

import hashlib

import pytest

from orin_shopify.reviewed_draft import (
    ReviewedDraftContractError,
    approved_review_draft_from_snapshot,
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
