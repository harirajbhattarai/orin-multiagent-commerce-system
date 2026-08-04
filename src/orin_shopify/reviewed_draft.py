"""Bind one immutable database review draft to one Shopify hidden draft."""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

from orin_control.secrets import read_private_secret
from orin_shopify.hidden_draft import (
    DraftResult,
    DraftSpec,
    GraphQLHTTPTransport,
    GraphQLTransport,
    HiddenDraftGateway,
)


MAX_APPROVED_DRAFT_BYTES = 500_000
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_HANDLE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class ReviewedDraftContractError(ValueError):
    """The claimed job is not bound to one valid immutable review draft."""


@dataclass(frozen=True)
class ApprovedReviewDraft:
    draft_id: str
    content_item_id: str
    content_item_version: int
    source_run_id: str
    item_number: int
    title: str
    body_html: str
    body_sha256: str
    handle: str

    def evidence(self) -> dict[str, Any]:
        value = asdict(self)
        value.pop("body_html")
        value["body_bytes"] = len(self.body_html.encode("utf-8"))
        return value


@dataclass(frozen=True)
class ShopifyRuntimeConfig:
    store_domain: str
    access_token: str
    api_version: str
    blog_id: str


def _required_text(value: object, *, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ReviewedDraftContractError(f"approved review draft {label} is required")
    return value


def approved_review_draft_from_snapshot(
    snapshot: dict[str, Any], *, client_id: str
) -> ApprovedReviewDraft:
    """Validate the worker-only snapshot and return its exact frozen draft."""
    if snapshot.get("client_id") != client_id:
        raise ReviewedDraftContractError("content-plan snapshot belongs to another client")
    approved = snapshot.get("approved_draft")
    if not isinstance(approved, dict):
        raise ReviewedDraftContractError("hidden-draft job has no frozen approved review draft")

    selected_item_id = _required_text(snapshot.get("selected_item_id"), label="selected item ID")
    selected_number = snapshot.get("selected_item_number")
    if isinstance(selected_number, bool) or not isinstance(selected_number, int) or selected_number < 1:
        raise ReviewedDraftContractError("approved review draft item number is invalid")

    draft_id = _required_text(approved.get("draft_id"), label="ID")
    content_item_id = _required_text(approved.get("content_item_id"), label="content item ID")
    source_run_id = _required_text(approved.get("source_run_id"), label="source run ID")
    try:
        UUID(draft_id)
        UUID(content_item_id)
    except ValueError as exc:
        raise ReviewedDraftContractError("approved review draft identity is invalid") from exc
    if content_item_id != selected_item_id:
        raise ReviewedDraftContractError("approved review draft does not own the selected content item")

    version = approved.get("content_item_version")
    if isinstance(version, bool) or not isinstance(version, int) or version < 2:
        raise ReviewedDraftContractError("approved review draft version is invalid")

    title = _required_text(approved.get("title"), label="title")
    body_html = _required_text(approved.get("body_html"), label="body")
    body_bytes = body_html.encode("utf-8")
    if len(body_bytes) > MAX_APPROVED_DRAFT_BYTES:
        raise ReviewedDraftContractError("approved review draft body exceeds the safe size limit")
    body_sha256 = _required_text(approved.get("body_sha256"), label="body hash")
    if not _SHA256.fullmatch(body_sha256):
        raise ReviewedDraftContractError("approved review draft body hash is invalid")
    if hashlib.sha256(body_bytes).hexdigest() != body_sha256:
        raise ReviewedDraftContractError("approved review draft body hash does not match its HTML")

    handle = _required_text(approved.get("handle"), label="Shopify handle")
    if len(handle) > 255 or not _HANDLE.fullmatch(handle):
        raise ReviewedDraftContractError("approved review draft Shopify handle is not canonical")

    return ApprovedReviewDraft(
        draft_id=draft_id,
        content_item_id=content_item_id,
        content_item_version=version,
        source_run_id=source_run_id,
        item_number=selected_number,
        title=title,
        body_html=body_html,
        body_sha256=body_sha256,
        handle=handle,
    )


def load_shopify_runtime_config() -> ShopifyRuntimeConfig:
    """Load the narrow hidden-draft credential contract without exposing secrets."""
    store_domain = os.environ.get("HOVERBOARD_STORE_SHOPIFY_STORE_DOMAIN", "")
    api_version = os.environ.get("HOVERBOARD_STORE_SHOPIFY_API_VERSION", "")
    blog_id = os.environ.get("HOVERBOARD_STORE_SHOPIFY_BLOG_ID", "")
    direct_token = os.environ.get("HOVERBOARD_STORE_SHOPIFY_ACCESS_TOKEN", "")
    token_file = os.environ.get("HOVERBOARD_STORE_SHOPIFY_ACCESS_TOKEN_FILE", "")
    if (
        not store_domain
        or "/" in store_domain
        or not re.fullmatch(r"[0-9]{4}-[0-9]{2}", api_version)
        or not blog_id.isascii()
        or not blog_id.isdecimal()
        or bool(direct_token) == bool(token_file)
    ):
        raise ReviewedDraftContractError("Shopify hidden-draft configuration is incomplete or invalid")
    access_token = (
        direct_token
        if direct_token
        else read_private_secret(Path(token_file), label="Shopify access token")
    )
    return ShopifyRuntimeConfig(
        store_domain=store_domain,
        access_token=access_token,
        api_version=api_version,
        blog_id=f"gid://shopify/Blog/{int(blog_id)}",
    )


def ensure_approved_review_draft(
    approved: ApprovedReviewDraft,
    *,
    client_id: str,
    request_id: str,
    config: ShopifyRuntimeConfig | None = None,
    transport: GraphQLTransport | None = None,
) -> DraftResult:
    """Create or reconcile exactly one unpublished copy of the approved HTML."""
    runtime = config or load_shopify_runtime_config()
    graphql = transport or GraphQLHTTPTransport(
        store_domain=runtime.store_domain,
        access_token=runtime.access_token,
        api_version=runtime.api_version,
    )
    result = HiddenDraftGateway(graphql).ensure(
        DraftSpec(
            blog_id=runtime.blog_id,
            title=approved.title,
            body_html=approved.body_html,
            handle=approved.handle,
            author_name="Hoverboard Store",
            idempotency_key=f"{client_id}:{request_id}",
        )
    )
    if result.body_sha256 != approved.body_sha256:
        raise ReviewedDraftContractError("verified Shopify body hash differs from the approved draft")
    return result
