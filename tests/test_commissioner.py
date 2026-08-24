from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from orin_commissioner.models import ClaimedCommissioning, CommissioningContext
from orin_commissioner.service import commission_once
from orin_commissioner.shopify import (
    PermanentCommissioningError,
    ShopifyIdentityReceipt,
    probe_shopify_identity,
)


class FakeRepository:
    def __init__(self, *, context: CommissioningContext | None = None) -> None:
        self.context = context
        self.claim = (
            ClaimedCommissioning(
                request_id=context.request_id,
                client_id=context.client_id,
                onboarding_request_id=context.onboarding_request_id,
                attempt_count=1,
                lease_expires_at=datetime.now(UTC) + timedelta(minutes=5),
            )
            if context
            else None
        )
        self.stages: list[tuple[str, dict[str, Any]]] = []
        self.finished: list[dict[str, Any]] = []
        self.renewed = True

    def claim_next(self, **_: Any) -> ClaimedCommissioning | None:
        return self.claim

    def get_context(self, **_: Any) -> CommissioningContext:
        assert self.context is not None
        return self.context

    def renew(self, **_: Any) -> bool:
        return self.renewed

    def boundary_snapshot(self, **_: Any) -> dict[str, Any]:
        return {
            "client_id": self.context.client_id if self.context else "client",
            "commissioning_request_id": str(self.context.request_id) if self.context else "request",
            "lease_owned": True,
            "active_request_count": 1,
            "exact_request_count": 1,
            "active_job_count": 0,
            "open_incident_count": 0,
            "shopify_writes_enabled": False,
            "approved_draft_writes_enabled": False,
            "scheduler_state": "disabled",
        }

    def record_stage(self, *, stage: str, evidence: dict[str, Any], **_: Any) -> None:
        self.stages.append((stage, evidence))

    def finish(self, **kwargs: Any) -> None:
        self.finished.append(kwargs)


def commissioning_context() -> CommissioningContext:
    return CommissioningContext(
        request_id=uuid4(),
        client_id="orin_oauth_test",
        onboarding_request_id=uuid4(),
        display_name="ORIN OAuth Test",
        owner_email="owner@example.com",
        store_domain="orin-oauth-test.myshopify.com",
        blog_gid="gid://shopify/Blog/123",
        blog_title="News",
        market_country="GB",
        timezone="Europe/London",
        brand_voice="Clear and useful.",
        content_categories=("Buying guides",),
        product_scope=({"name": "Electric scooters"},),
        access_token="secret-value",
        attempt_count=1,
        lease_expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )


def receipt(context: CommissioningContext) -> ShopifyIdentityReceipt:
    return ShopifyIdentityReceipt(
        store_domain=context.store_domain,
        shop_name=context.display_name,
        primary_domain="example.com",
        blog_gid=context.blog_gid,
        blog_title=context.blog_title,
        product_count=17,
    )


def test_commissioner_completes_all_read_only_proofs() -> None:
    context = commissioning_context()
    repository = FakeRepository(context=context)

    outcome = commission_once(
        repository,
        worker_id="commissioner-test",
        shopify_probe=lambda received: receipt(received),
    )

    assert outcome.status == "succeeded"
    assert [stage for stage, _ in repository.stages] == [
        "worker_setup",
        "dry_run_proof",
        "scheduler_proof",
        "watchdog_proof",
    ]
    assert repository.finished[-1]["succeeded"] is True
    assert repository.finished[-1]["evidence"] == {
        "client_id": "orin_oauth_test",
        "shopify_mutation_attempted": False,
        "recurring_content_schedule_enabled": False,
        "next_state": "pilot_pending",
    }
    assert "secret-value" not in json.dumps(repository.stages)
    assert "secret-value" not in json.dumps(repository.finished, default=str)


def test_commissioner_returns_no_request_without_writes() -> None:
    repository = FakeRepository()
    outcome = commission_once(repository, worker_id="commissioner-test")
    assert outcome.status == "no_request"
    assert repository.stages == []
    assert repository.finished == []


def test_commissioner_fails_closed_on_identity_mismatch() -> None:
    context = commissioning_context()
    repository = FakeRepository(context=context)

    def mismatched(_: CommissioningContext) -> ShopifyIdentityReceipt:
        raise PermanentCommissioningError("different store")

    outcome = commission_once(
        repository, worker_id="commissioner-test", shopify_probe=mismatched
    )
    assert outcome.status == "failed"
    assert outcome.error_code == "ORIN_COMMISSIONING_CONFIGURATION_INVALID"
    assert repository.finished[-1]["succeeded"] is False
    assert repository.finished[-1]["evidence"]["shopify_mutation_attempted"] is False


def test_commissioner_fails_closed_when_boundary_is_not_unique() -> None:
    context = commissioning_context()
    repository = FakeRepository(context=context)
    original = repository.boundary_snapshot

    def unsafe(**kwargs: Any) -> dict[str, Any]:
        value = original(**kwargs)
        value["active_request_count"] = 2
        return value

    repository.boundary_snapshot = unsafe  # type: ignore[method-assign]
    outcome = commission_once(
        repository,
        worker_id="commissioner-test",
        shopify_probe=lambda received: receipt(received),
    )
    assert outcome.status == "failed"
    assert outcome.stage == "scheduler_proof"
    assert repository.finished[-1]["succeeded"] is False


class FakeResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *_: Any) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


def test_shopify_probe_uses_only_read_only_graphql() -> None:
    context = commissioning_context()
    captured: dict[str, Any] = {}

    def opener(request: Any, *, timeout: float) -> FakeResponse:
        captured["url"] = request.full_url
        captured["body"] = request.data.decode("utf-8")
        captured["timeout"] = timeout
        assert request.get_header("X-shopify-access-token") == "secret-value"
        return FakeResponse(
            {
                "data": {
                    "shop": {
                        "name": "ORIN OAuth Test",
                        "myshopifyDomain": context.store_domain,
                        "primaryDomain": {"host": "example.com"},
                    },
                    "blogs": {"nodes": [{"id": context.blog_gid, "title": "News"}]},
                    "productsCount": {"count": 17},
                }
            }
        )

    result = probe_shopify_identity(context, opener=opener)
    assert result.product_count == 17
    assert captured["url"].endswith("/admin/api/2026-07/graphql.json")
    assert "mutation" not in captured["body"].lower()
    assert "productsCount" in captured["body"]
    assert "secret-value" not in captured["body"]


def test_shopify_probe_rejects_cross_store_credential() -> None:
    context = commissioning_context()

    def opener(*_: Any, **__: Any) -> FakeResponse:
        return FakeResponse(
            {
                "data": {
                    "shop": {
                        "name": "Wrong",
                        "myshopifyDomain": "wrong-store.myshopify.com",
                        "primaryDomain": {"host": "wrong.example"},
                    },
                    "blogs": {"nodes": [{"id": context.blog_gid, "title": "News"}]},
                    "productsCount": {"count": 1},
                }
            }
        )

    with pytest.raises(PermanentCommissioningError, match="another store"):
        probe_shopify_identity(context, opener=opener)


def test_commissioner_migration_keeps_role_function_only() -> None:
    root = Path(__file__).resolve().parents[1]
    migration = (
        root
        / "supabase/migrations/20260824083857_trusted_client_commissioning_worker.sql"
    ).read_text(encoding="utf-8")
    compose = (root / "deploy/vps/compose.yml").read_text(encoding="utf-8")

    assert "create role orin_commissioner nologin" in migration
    assert "revoke all on all tables in schema public from orin_commissioner" in migration
    assert "grant execute on function orin_private.claim_next_client_commissioning" in migration
    assert "grant execute on function orin_private.get_client_commissioning_context" in migration
    assert "approved_draft_writes_enabled = false" in migration
    assert "shopify_writes_enabled = false" in migration
    assert "set state = 'disabled', scheduler_owner = null" in migration
    assert "docker.sock" not in compose
    commissioner_service = compose.split("  commissioner:", 1)[1].split("\n  watchdog:", 1)[0]
    assert "shopify_access_token" not in commissioner_service
    assert "writer_api_key" not in commissioner_service
    assert "prefect" not in commissioner_service.lower()
