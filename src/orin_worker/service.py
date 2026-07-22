"""Claim, execute, renew, and finalize one ORIN job."""

from __future__ import annotations

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
    def claim_next(self, *, worker_id: str, lease_seconds: int) -> ClaimedJob | None: ...
    def renew(self, *, job_id: UUID, worker_id: str, lease_seconds: int) -> bool: ...
    def complete(
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
        "schema": "orin.final-result/v1",
        "client_id": job.client_id,
        "request_id": str(job.request_id),
        "requested_mode": "dry-run",
        "shopify_create_count": 0,
        "shopify_published": False,
        "queue_changed": False,
    }
    actual = {key: result.get(key) for key in expected}
    if actual != expected:
        raise ResultContractError(
            f"runner result does not match the claimed dry-run job: expected={expected}, received={actual}"
        )
    if result.get("status") not in {"completed", "blocked", "failed"}:
        raise ResultContractError("runner returned an unsupported terminal status")
    if not result.get("run_id") or not result.get("decision"):
        raise ResultContractError("runner result is missing run identity or decision")


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

    job = repository.claim_next(worker_id=worker_id, lease_seconds=lease_seconds)
    if job is None:
        return WorkOutcome(status="no_job_due", job_id=None, run_id=None, replayed=False)
    if job.requested_mode != "dry-run" or job.payload != {}:
        raise ResultContractError("Phase 3B worker accepts only empty dry-run jobs")

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
    _validate_result(job, result)
    completion = repository.complete(
        job_id=job.job_id,
        worker_id=worker_id,
        final_result=result,
    )
    return WorkOutcome(
        status=completion.status,
        job_id=str(job.job_id),
        run_id=completion.run_id,
        replayed=completion.replayed,
    )
