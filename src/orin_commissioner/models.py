"""Immutable commissioning worker contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID


@dataclass(frozen=True)
class ClaimedCommissioning:
    request_id: UUID
    client_id: str
    onboarding_request_id: UUID
    attempt_count: int
    lease_expires_at: datetime


@dataclass(frozen=True)
class CommissioningContext:
    request_id: UUID
    client_id: str
    onboarding_request_id: UUID
    display_name: str
    owner_email: str
    store_domain: str
    blog_gid: str
    blog_title: str
    market_country: str
    timezone: str
    brand_voice: str
    content_categories: tuple[str, ...]
    product_scope: tuple[dict[str, Any], ...]
    attempt_count: int
    lease_expires_at: datetime
    access_token: str = field(repr=False)


@dataclass(frozen=True)
class CommissioningOutcome:
    status: str
    request_id: str | None
    client_id: str | None
    stage: str | None
    error_code: str | None = None

    def to_dict(self) -> dict[str, str | None]:
        return {
            "status": self.status,
            "request_id": self.request_id,
            "client_id": self.client_id,
            "stage": self.stage,
            "error_code": self.error_code,
        }
