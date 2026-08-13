from __future__ import annotations

import hashlib
from typing import Any

import pytest

from orin_shopify.hidden_draft import (
    BODY_CANONICALIZATION,
    CREATE_HIDDEN_DRAFT,
    FIND_MARKED_DRAFTS,
    VERIFY_HIDDEN_DRAFT,
    DraftReconciliationError,
    DraftSpec,
    HiddenDraftGateway,
    ShopifyRequestError,
    canonical_shopify_body_sha256,
    idempotency_marker,
)


IDEMPOTENCY_KEY = "hoverboard_store:aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
MARKER = idempotency_marker(IDEMPOTENCY_KEY)


def article(
    identifier: int,
    *,
    marker: str = MARKER,
    handle: str = "safe-handle",
    title: str = "Safe article",
    body: str = "<p>Safe body</p>",
    published_at: str | None = None,
) -> dict[str, Any]:
    return {
        "id": f"gid://shopify/Article/{identifier}",
        "handle": handle,
        "title": title,
        "body": body,
        "publishedAt": published_at,
        "metafield": {"value": marker},
    }


def spec() -> DraftSpec:
    return DraftSpec(
        blog_id="gid://shopify/Blog/123",
        title="Safe article",
        body_html="<p>Safe body</p>",
        handle="safe-handle",
        author_name="ORIN",
        idempotency_key=IDEMPOTENCY_KEY,
    )


class FakeTransport:
    def __init__(self, articles: list[dict[str, Any]] | None = None) -> None:
        self.articles = list(articles or [])
        self.create_calls: list[dict[str, Any]] = []
        self.fail_after_create = False

    def execute(self, document: str, variables: dict[str, Any]) -> dict[str, Any]:
        if document == FIND_MARKED_DRAFTS:
            return {
                "blog": {
                    "articles": {
                        "nodes": list(self.articles),
                        "pageInfo": {"hasNextPage": False, "endCursor": None},
                    }
                }
            }
        if document == CREATE_HIDDEN_DRAFT:
            self.create_calls.append(variables)
            new_article = article(
                9001,
                marker=variables["article"]["metafields"][0]["value"],
                handle=variables["article"]["handle"],
            )
            self.articles.append(new_article)
            if self.fail_after_create:
                raise ShopifyRequestError("connection closed after Shopify accepted the mutation")
            return {"articleCreate": {"article": new_article, "userErrors": []}}
        if document == VERIFY_HIDDEN_DRAFT:
            expected_id = variables["id"]
            return {"article": next(item for item in self.articles if item["id"] == expected_id)}
        raise AssertionError("unexpected GraphQL document")


def test_first_attempt_creates_exactly_one_explicit_hidden_draft():
    transport = FakeTransport()

    result = HiddenDraftGateway(transport).ensure(spec())

    assert result.numeric_article_id == 9001
    assert result.create_count == 1
    assert result.reconciliation_status == "reconciled"
    assert result.shopify_write_state == "article_observed"
    assert result.idempotency_marker == MARKER
    assert result.body_sha256 == hashlib.sha256(b"<p>Safe body</p>").hexdigest()
    assert result.canonical_body_sha256 == result.body_sha256
    assert result.body_canonicalization == BODY_CANONICALIZATION
    create_input = transport.create_calls[0]["article"]
    assert create_input["isPublished"] is False
    assert "publishDate" not in create_input
    assert create_input["metafields"] == [
        {
            "namespace": "orin_control",
            "key": "idempotency_key",
            "type": "single_line_text_field",
            "value": MARKER,
        }
    ]


def test_retry_finds_existing_marker_and_does_not_create():
    transport = FakeTransport([article(42)])

    result = HiddenDraftGateway(transport).ensure(spec())

    assert result.numeric_article_id == 42
    assert result.create_count == 1
    assert result.reconciliation_status == "reconciled"
    assert result.shopify_write_state == "article_observed"
    assert transport.create_calls == []


def test_crash_after_remote_create_is_reconciled_without_duplicate():
    transport = FakeTransport()
    transport.fail_after_create = True

    result = HiddenDraftGateway(transport).ensure(spec())

    assert result.numeric_article_id == 9001
    assert result.create_count == 1
    assert result.shopify_write_state == "article_observed"
    assert len(transport.articles) == 1
    assert len(transport.create_calls) == 1


def test_duplicate_markers_fail_closed_without_another_create():
    transport = FakeTransport([article(1), article(2)])

    with pytest.raises(DraftReconciliationError, match="multiple"):
        HiddenDraftGateway(transport).ensure(spec())

    assert transport.create_calls == []


def test_published_or_scheduled_marker_fails_closed():
    transport = FakeTransport([article(1, published_at="2026-07-23T10:00:00Z")])

    with pytest.raises(DraftReconciliationError, match="published or scheduled"):
        HiddenDraftGateway(transport).ensure(spec())

    assert transport.create_calls == []


def test_marker_with_different_handle_fails_closed():
    transport = FakeTransport([article(1, handle="another-handle")])

    with pytest.raises(DraftReconciliationError, match="different article handle"):
        HiddenDraftGateway(transport).ensure(spec())

    assert transport.create_calls == []


def test_marker_with_different_title_fails_closed():
    transport = FakeTransport([article(1, title="Regenerated title")])

    with pytest.raises(DraftReconciliationError, match="title differs"):
        HiddenDraftGateway(transport).ensure(spec())

    assert transport.create_calls == []


def test_marker_with_different_body_fails_closed():
    transport = FakeTransport([article(1, body="<p>Regenerated body</p>")])

    with pytest.raises(DraftReconciliationError, match="body differs") as failure:
        HiddenDraftGateway(transport).ensure(spec())

    assert failure.value.article_id == "gid://shopify/Article/1"
    assert transport.create_calls == []


def test_shopify_list_serializer_newline_reconciles_without_duplicate():
    approved = "<ul><li><strong>Fit.</strong> Check the rider.</li></ul>"
    serialized = "<ul><li>\n<strong>Fit.</strong> Check the rider.</li></ul>"
    expected = spec()
    expected = DraftSpec(
        blog_id=expected.blog_id,
        title=expected.title,
        body_html=approved,
        handle=expected.handle,
        author_name=expected.author_name,
        idempotency_key=expected.idempotency_key,
    )
    transport = FakeTransport([article(42, body=serialized)])

    result = HiddenDraftGateway(transport).ensure(expected)

    assert result.numeric_article_id == 42
    assert result.body_sha256 == hashlib.sha256(serialized.encode()).hexdigest()
    assert result.canonical_body_sha256 == canonical_shopify_body_sha256(approved)
    assert transport.create_calls == []


def test_shopify_list_anchor_serializer_newline_reconciles_without_duplicate():
    approved = '<ul><li><a href="/collections/scooters">Browse scooters</a>.</li></ul>'
    serialized = '<ul><li>\n<a href="/collections/scooters">Browse scooters</a>.</li></ul>'
    expected = spec()
    expected = DraftSpec(
        blog_id=expected.blog_id,
        title=expected.title,
        body_html=approved,
        handle=expected.handle,
        author_name=expected.author_name,
        idempotency_key=expected.idempotency_key,
    )
    transport = FakeTransport([article(44, body=serialized)])

    result = HiddenDraftGateway(transport).ensure(expected)

    assert result.numeric_article_id == 44
    assert result.body_sha256 == hashlib.sha256(serialized.encode()).hexdigest()
    assert result.canonical_body_sha256 == canonical_shopify_body_sha256(approved)
    assert transport.create_calls == []


def test_shopify_faq_div_serializer_newlines_reconcile_without_duplicate():
    approved = (
        '<section class="hs-faq">\n'
        '<div class="hs-faq-item"><div class="hs-faq-q">Question?</div>'
        '<div class="hs-faq-a">Answer.</div></div>\n'
        '</section>'
    )
    serialized = (
        '<section class="hs-faq">\n'
        '<div class="hs-faq-item">\n<div class="hs-faq-q">Question?</div>\n'
        '<div class="hs-faq-a">Answer.</div>\n</div>\n'
        '</section>'
    )
    expected = spec()
    expected = DraftSpec(
        blog_id=expected.blog_id,
        title=expected.title,
        body_html=approved,
        handle=expected.handle,
        author_name=expected.author_name,
        idempotency_key=expected.idempotency_key,
    )
    transport = FakeTransport([article(45, body=serialized)])

    result = HiddenDraftGateway(transport).ensure(expected)

    assert result.numeric_article_id == 45
    assert result.body_sha256 == hashlib.sha256(serialized.encode()).hexdigest()
    assert result.canonical_body_sha256 == canonical_shopify_body_sha256(approved)
    assert transport.create_calls == []


def test_shopify_apostrophe_entity_decoding_reconciles_without_duplicate():
    approved = "<p>Follow the manufacturer&#39;s instructions.</p>"
    serialized = "<p>Follow the manufacturer's instructions.</p>"
    expected = spec()
    expected = DraftSpec(
        blog_id=expected.blog_id,
        title=expected.title,
        body_html=approved,
        handle=expected.handle,
        author_name=expected.author_name,
        idempotency_key=expected.idempotency_key,
    )
    transport = FakeTransport([article(43, body=serialized)])

    result = HiddenDraftGateway(transport).ensure(expected)

    assert result.numeric_article_id == 43
    assert result.body_sha256 == hashlib.sha256(serialized.encode()).hexdigest()
    assert result.canonical_body_sha256 == canonical_shopify_body_sha256(approved)
    assert transport.create_calls == []


def test_canonicalization_does_not_ignore_inline_or_text_changes():
    transport = FakeTransport([article(42, body="<p>Safe <strong>body</strong></p>")])

    with pytest.raises(DraftReconciliationError, match="body differs"):
        HiddenDraftGateway(transport).ensure(spec())

    assert transport.create_calls == []
