"""Versioned request and response models for the control API."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


@dataclass(frozen=True)
class Principal:
    user_id: UUID


class RunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: UUID
    mode: Literal["dry-run"] = "dry-run"


class RunRequestResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: UUID
    client_id: str
    request_id: UUID
    requested_mode: Literal["dry-run"]
    status: str
    scheduled_for: datetime
    created_at: datetime
    replayed: bool
