"""Commission one no-code client while every execution gate remains closed."""

from __future__ import annotations

from typing import Any, Callable, Protocol
from uuid import UUID

from orin_commissioner.models import (
    ClaimedCommissioning,
    CommissioningContext,
    CommissioningOutcome,
)
from orin_commissioner.shopify import PermanentCommissioningError, probe_shopify_identity


class Repository(Protocol):
    def claim_next(self, *, worker_id: str, lease_seconds: int) -> ClaimedCommissioning | None: ...
    def renew(self, *, request_id: UUID, worker_id: str, lease_seconds: int) -> bool: ...
    def get_context(self, *, request_id: UUID, worker_id: str) -> CommissioningContext: ...
    def boundary_snapshot(self, *, request_id: UUID, worker_id: str) -> dict[str, Any]: ...
    def record_stage(
        self,
        *,
        request_id: UUID,
        worker_id: str,
        stage: str,
        summary: str,
        evidence: dict[str, Any],
    ) -> None: ...
    def finish(
        self,
        *,
        request_id: UUID,
        worker_id: str,
        succeeded: bool,
        error_code: str,
        evidence: dict[str, Any],
    ) -> None: ...


def _require_closed_snapshot(snapshot: dict[str, Any]) -> None:
    expected = {
        "lease_owned": True,
        "active_request_count": 1,
        "exact_request_count": 1,
        "active_job_count": 0,
        "open_incident_count": 0,
        "shopify_writes_enabled": False,
        "approved_draft_writes_enabled": False,
        "scheduler_state": "disabled",
    }
    actual = {key: snapshot.get(key) for key in expected}
    if actual != expected:
        raise PermanentCommissioningError("commissioning boundary snapshot is unsafe")


def commission_once(
    repository: Repository,
    *,
    worker_id: str,
    lease_seconds: int = 300,
    shopify_probe: Callable[[CommissioningContext], Any] = probe_shopify_identity,
) -> CommissioningOutcome:
    claim = repository.claim_next(worker_id=worker_id, lease_seconds=lease_seconds)
    if claim is None:
        return CommissioningOutcome("no_request", None, None, None)

    current_stage = "worker_setup"
    try:
        context = repository.get_context(request_id=claim.request_id, worker_id=worker_id)
        if context.request_id != claim.request_id or context.client_id != claim.client_id:
            raise PermanentCommissioningError("commissioning context identity mismatch")
        if not context.content_categories or not context.product_scope:
            raise PermanentCommissioningError("commissioning content boundary is incomplete")
        repository.record_stage(
            request_id=claim.request_id,
            worker_id=worker_id,
            stage="worker_setup",
            summary="Isolated client profile, credential boundary, and content scope verified.",
            evidence={
                "client_id": context.client_id,
                "store_domain": context.store_domain,
                "blog_gid": context.blog_gid,
                "content_category_count": len(context.content_categories),
                "product_scope_count": len(context.product_scope),
                "attempt": claim.attempt_count,
            },
        )

        current_stage = "dry_run_proof"
        receipt = shopify_probe(context)
        repository.record_stage(
            request_id=claim.request_id,
            worker_id=worker_id,
            stage="dry_run_proof",
            summary="Shopify store, target blog, and catalogue were verified through read-only GraphQL.",
            evidence=receipt.evidence(),
        )

        if not repository.renew(
            request_id=claim.request_id,
            worker_id=worker_id,
            lease_seconds=lease_seconds,
        ):
            raise RuntimeError("commissioning lease was lost")

        current_stage = "scheduler_proof"
        scheduler_snapshot = repository.boundary_snapshot(
            request_id=claim.request_id, worker_id=worker_id
        )
        _require_closed_snapshot(scheduler_snapshot)
        repository.record_stage(
            request_id=claim.request_id,
            worker_id=worker_id,
            stage="scheduler_proof",
            summary="Exclusive request identity and lease were verified; recurring content scheduling remains disabled.",
            evidence=scheduler_snapshot,
        )

        current_stage = "watchdog_proof"
        watchdog_snapshot = repository.boundary_snapshot(
            request_id=claim.request_id, worker_id=worker_id
        )
        _require_closed_snapshot(watchdog_snapshot)
        repository.record_stage(
            request_id=claim.request_id,
            worker_id=worker_id,
            stage="watchdog_proof",
            summary="A second independent boundary check observed no jobs, incidents, scheduler owner, or Shopify write access.",
            evidence=watchdog_snapshot,
        )
        repository.finish(
            request_id=claim.request_id,
            worker_id=worker_id,
            succeeded=True,
            error_code="",
            evidence={
                "client_id": claim.client_id,
                "shopify_mutation_attempted": False,
                "recurring_content_schedule_enabled": False,
                "next_state": "pilot_pending",
            },
        )
        return CommissioningOutcome(
            "succeeded", str(claim.request_id), claim.client_id, "complete"
        )
    except Exception as exc:
        error_code = (
            "ORIN_COMMISSIONING_CONFIGURATION_INVALID"
            if isinstance(exc, PermanentCommissioningError)
            else "ORIN_COMMISSIONING_PROBE_FAILED"
        )
        repository.finish(
            request_id=claim.request_id,
            worker_id=worker_id,
            succeeded=False,
            error_code=error_code,
            evidence={
                "client_id": claim.client_id,
                "failed_stage": current_stage,
                "failure_type": type(exc).__name__,
                "shopify_mutation_attempted": False,
            },
        )
        return CommissioningOutcome(
            "failed", str(claim.request_id), claim.client_id, current_stage, error_code
        )
