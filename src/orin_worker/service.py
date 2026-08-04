"""Claim, execute, renew, and finalize one ORIN job."""

from __future__ import annotations

import re
import threading
from dataclasses import asdict, dataclass
from typing import Any, Callable, Protocol
from uuid import UUID

from orin_worker.models import ClaimedJob, CompletionRecord


class LeaseLostError(RuntimeError):
    """Raised when the worker no longer owns its database lease."""


class ResultContractError(RuntimeError):
    """Raised before persistence when runner output does not match the claim."""


class Repository(Protocol):
    def materialize_next_content_decision(self) -> None: ...
    def claim_next(self, *, worker_id: str, lease_seconds: int) -> ClaimedJob | None: ...
    def renew(self, *, job_id: UUID, worker_id: str, lease_seconds: int) -> bool: ...
    def complete(
        self,
        *,
        job_id: UUID,
        worker_id: str,
        final_result: dict[str, Any],
        review_draft: dict[str, Any] | None = None,
    ) -> CompletionRecord: ...
    def defer(
        self,
        *,
        job_id: UUID,
        worker_id: str,
        final_result: dict[str, Any],
    ) -> CompletionRecord: ...


@dataclass(frozen=True)
class WorkOutcome:
    status: str
    job_id: str | None
    run_id: str | None
    replayed: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class _LeaseHeartbeat:
    def __init__(
        self,
        repository: Repository,
        *,
        job_id: UUID,
        worker_id: str,
        lease_seconds: int,
        interval_seconds: float,
    ) -> None:
        self.repository = repository
        self.job_id = job_id
        self.worker_id = worker_id
        self.lease_seconds = lease_seconds
        self.interval_seconds = interval_seconds
        self._stop = threading.Event()
        self._lost = threading.Event()
        self._thread = threading.Thread(target=self._run, name="orin-lease-heartbeat", daemon=True)

    def _run(self) -> None:
        while not self._stop.wait(self.interval_seconds):
            try:
                renewed = self.repository.renew(
                    job_id=self.job_id,
                    worker_id=self.worker_id,
                    lease_seconds=self.lease_seconds,
                )
            except Exception:
                self._lost.set()
                return
            if not renewed:
                self._lost.set()
                return

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join()

    @property
    def lost(self) -> bool:
        return self._lost.is_set()


def _validate_result(job: ClaimedJob, result: dict[str, Any]) -> None:
    expected = {
        "schema": "orin.final-result/v2",
        "client_id": job.client_id,
        "request_id": str(job.request_id),
        "requested_mode": job.requested_mode,
        "shopify_published": False,
        "queue_changed": False,
    }
    actual = {key: result.get(key) for key in expected}
    if actual != expected:
        raise ResultContractError(
            f"runner result does not match the claimed job: expected={expected}, received={actual}"
        )
    if result.get("status") not in {"completed", "blocked", "failed"}:
        raise ResultContractError("runner returned an unsupported terminal status")
    if not result.get("run_id") or not result.get("decision"):
        raise ResultContractError("runner result is missing run identity or decision")
    create_count = result.get("shopify_create_count")
    article_id = result.get("shopify_article_id")
    article_handle = result.get("shopify_handle")
    reconciliation = result.get("reconciliation_status")
    replay_disposition = result.get("replay_disposition")
    write_state = result.get("shopify_write_state")
    if replay_disposition not in {"terminal", "retry", "reconcile"}:
        raise ResultContractError("runner result has an invalid replay disposition")
    if write_state not in {"not_attempted", "unknown", "article_observed"}:
        raise ResultContractError("runner result has an invalid Shopify write state")
    if replay_disposition != "terminal" and result.get("status") == "completed":
        raise ResultContractError("nonterminal replay state cannot report completed")
    if job.requested_mode == "dry-run":
        if (
            create_count != 0
            or article_id is not None
            or article_handle is not None
            or result.get("shopify_idempotency_marker") is not None
            or write_state != "not_attempted"
        ):
            raise ResultContractError("dry-run result claims a Shopify mutation")
        if replay_disposition == "reconcile":
            raise ResultContractError("dry-run result cannot require Shopify reconciliation")
        return
    expected_marker = f"orin-v1:{job.client_id}:{job.request_id}"
    if (
        result.get("effective_mode") != "hidden-draft"
        and not (
            result.get("status") == "failed"
            and article_id is None
            and result.get("effective_mode") == "none"
        )
    ):
        raise ResultContractError("hidden-draft result has an unsafe effective mode")
    if result.get("shopify_idempotency_marker") != expected_marker:
        raise ResultContractError("hidden-draft result has the wrong idempotency marker")
    if create_count not in {0, 1}:
        raise ResultContractError("hidden-draft result has an invalid Shopify create count")
    if write_state == "article_observed":
        if article_id is None or create_count != 1:
            raise ResultContractError("observed Shopify article evidence is incomplete")
        if reconciliation not in {"reconciled", "needs_review"}:
            raise ResultContractError("hidden-draft article has an invalid reconciliation state")
        if article_handle is not None and not re.fullmatch(
            r"[a-z0-9]+(?:-[a-z0-9]+)*", article_handle
        ):
            raise ResultContractError("hidden-draft result has an invalid Shopify handle")
    elif article_id is not None or article_handle is not None or create_count != 0:
        raise ResultContractError("hidden-draft result contradicts its Shopify write state")

    if (
        result.get("decision") == "APPROVED_REVIEW_DRAFT_CREATED_VERIFICATION_PASSED"
        and replay_disposition == "terminal"
        and not isinstance(article_handle, str)
    ):
        raise ResultContractError("approved review draft result is missing its Shopify handle")

    if replay_disposition == "terminal":
        if write_state == "unknown" or reconciliation == "needs_review":
            raise ResultContractError("unresolved Shopify state cannot be terminal")
        if article_id is not None and reconciliation != "reconciled":
            raise ResultContractError("terminal hidden-draft article is not reconciled")
    elif replay_disposition == "retry":
        if write_state != "not_attempted" or article_id is not None:
            raise ResultContractError("safe retry requires proof that Shopify was not attempted")
    elif write_state == "not_attempted":
        raise ResultContractError("reconciliation replay requires possible Shopify state")
    elif write_state == "unknown" and reconciliation not in {"needs_review", "failed"}:
        raise ResultContractError("unknown Shopify state requires unresolved reconciliation")


def work_once(
    repository: Repository,
    *,
    worker_id: str,
    execute: Callable[[ClaimedJob], dict[str, Any]],
    lease_seconds: int = 1200,
    heartbeat_interval_seconds: float = 60,
) -> WorkOutcome:
    if heartbeat_interval_seconds <= 0 or heartbeat_interval_seconds >= lease_seconds:
        raise ValueError("heartbeat interval must be positive and shorter than the lease")

    repository.materialize_next_content_decision()
    job = repository.claim_next(worker_id=worker_id, lease_seconds=lease_seconds)
    if job is None:
        return WorkOutcome(status="no_job_due", job_id=None, run_id=None, replayed=False)
    if job.requested_mode not in {"dry-run", "hidden-draft"} or job.payload != {}:
        raise ResultContractError("worker accepts only empty, supported-mode jobs")

    heartbeat = _LeaseHeartbeat(
        repository,
        job_id=job.job_id,
        worker_id=worker_id,
        lease_seconds=lease_seconds,
        interval_seconds=heartbeat_interval_seconds,
    )
    heartbeat.start()
    try:
        result = execute(job)
    finally:
        heartbeat.stop()

    if heartbeat.lost:
        raise LeaseLostError("database lease was lost before finalization")
    persisted_result = dict(result)
    review_draft = persisted_result.pop("_review_draft", None)
    _validate_result(job, persisted_result)
    if persisted_result["replay_disposition"] == "terminal":
        completion = repository.complete(
            job_id=job.job_id,
            worker_id=worker_id,
            final_result=persisted_result,
            review_draft=review_draft,
        )
    else:
        completion = repository.defer(
            job_id=job.job_id,
            worker_id=worker_id,
            final_result=persisted_result,
        )
    return WorkOutcome(
        status=completion.status,
        job_id=str(job.job_id),
        run_id=completion.run_id,
        replayed=completion.replayed,
    )


def work_forever(
    repository: Repository,
    *,
    worker_id: str,
    execute: Callable[[ClaimedJob], dict[str, Any]],
    stop_event: threading.Event,
    poll_interval_seconds: float = 15,
    error_backoff_seconds: float = 60,
    lease_seconds: int = 1200,
    heartbeat_interval_seconds: float = 60,
    on_outcome: Callable[[WorkOutcome], None] | None = None,
    on_error: Callable[[Exception], None] | None = None,
) -> None:
    """Run the fixed worker claim path until a local stop signal is received."""
    if poll_interval_seconds <= 0:
        raise ValueError("poll interval must be positive")
    if error_backoff_seconds <= 0:
        raise ValueError("error backoff must be positive")
    if heartbeat_interval_seconds <= 0 or heartbeat_interval_seconds >= lease_seconds:
        raise ValueError("heartbeat interval must be positive and shorter than the lease")

    while not stop_event.is_set():
        delay = poll_interval_seconds
        try:
            outcome = work_once(
                repository,
                worker_id=worker_id,
                execute=execute,
                lease_seconds=lease_seconds,
                heartbeat_interval_seconds=heartbeat_interval_seconds,
            )
        except Exception as exc:
            delay = error_backoff_seconds
            if on_error is not None:
                on_error(exc)
        else:
            if on_outcome is not None:
                on_outcome(outcome)
        stop_event.wait(delay)
