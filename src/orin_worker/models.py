"""Worker database records."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal
from uuid import UUID


@dataclass(frozen=True)
class ClaimedJob:
    job_id: UUID
    client_id: str
    request_id: UUID
    requested_mode: Literal["dry-run", "hidden-draft"]
    attempt_count: int
    payload: dict[str, Any]
    lease_expires_at: datetime


@dataclass(frozen=True)
class CompletionRecord:
    run_id: str
    status: str
    replayed: bool
