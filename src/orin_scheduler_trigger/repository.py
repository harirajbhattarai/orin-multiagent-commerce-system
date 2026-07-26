"""Database capability wrapper for the hard-wired HBStore scheduler function."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Engine


@dataclass(frozen=True)
class ScheduledJob:
    job_id: UUID
    client_id: str
    request_id: UUID
    requested_mode: str
    job_status: str
    scheduled_for: datetime
    created_at: datetime
    replayed: bool


class SchedulerRepository:
    """Expose exactly one zero-argument database capability."""

    def __init__(self, engine: Engine, *, expected_role: str = "orin_scheduler") -> None:
        self.engine = engine
        self.expected_role = expected_role

    def trigger(self) -> ScheduledJob:
        with self.engine.begin() as connection:
            current_role = connection.execute(text("select current_user")).scalar_one()
            if current_role != self.expected_role:
                raise RuntimeError(
                    f"database role mismatch: required={self.expected_role}, received={current_role}"
                )
            row = connection.execute(
                text(
                    "select job_id, client_id, request_id, requested_mode, "
                    "job_status, scheduled_for, created_at, replayed "
                    "from orin_private.enqueue_hoverboard_scheduled_job()"
                )
            ).one()
        mapping = row._mapping
        return ScheduledJob(
            job_id=mapping["job_id"],
            client_id=mapping["client_id"],
            request_id=mapping["request_id"],
            requested_mode=mapping["requested_mode"],
            job_status=mapping["job_status"],
            scheduled_for=mapping["scheduled_for"],
            created_at=mapping["created_at"],
            replayed=mapping["replayed"],
        )

    def ping(self) -> None:
        with self.engine.connect() as connection:
            current_role = connection.execute(text("select current_user")).scalar_one()
            if current_role != self.expected_role:
                raise RuntimeError(
                    f"database role mismatch: required={self.expected_role}, received={current_role}"
                )

    def close(self) -> None:
        self.engine.dispose()
