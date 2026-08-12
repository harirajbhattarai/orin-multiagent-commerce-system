"""Typed watchdog observation and result records."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any
from uuid import UUID


@dataclass(frozen=True)
class WatchdogSnapshot:
    client_status: str
    request_intake_enabled: bool
    automation_enabled: bool
    shopify_writes_enabled: bool
    approved_draft_writes_enabled: bool
    max_concurrency: int
    allowed_mode: str
    scheduler_state: str
    scheduler_owner: str | None
    job_id: UUID | None
    request_id: UUID | None
    job_status: str | None
    scheduled_for: datetime | None
    attempt_count: int | None
    job_error_code: str | None
    run_id: str | None
    run_status: str | None
    decision: str | None
    code_version: str | None
    shopify_create_count: int | None
    shopify_published: bool | None
    queue_changed: bool | None
    reconciliation_status: str | None
    run_error_code: str | None
    started_at: datetime | None
    finished_at: datetime | None


@dataclass(frozen=True)
class WatchdogResult:
    status: str
    code: str
    client_id: str
    source_job_key: str
    observed_at: str
    expected_at: str
    deadline_at: str
    job_id: str | None
    run_id: str | None
    job_status: str | None
    run_status: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
