"""Database capability wrapper for the hard-wired HBStore scheduler function."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import (
    DBAPIError,
    InterfaceError,
    OperationalError,
    TimeoutError as SQLAlchemyTimeoutError,
)


MAX_TRIGGER_ATTEMPTS = 2
POLICY_SQLSTATES = frozenset({"23505", "23514", "42501", "P0002"})
RETRYABLE_SQLSTATES = frozenset(
    {"40001", "40P01", "53300", "57P01", "57P02", "57P03"}
)


@dataclass(frozen=True)
class DatabaseFailure:
    response_code: str
    category: str
    retryable: bool
    sqlstate_class: str | None


class SchedulerDatabaseError(RuntimeError):
    """Stable, non-sensitive scheduler database failure."""

    def __init__(self, failure: DatabaseFailure, *, attempts: int) -> None:
        super().__init__(failure.response_code)
        self.response_code = failure.response_code
        self.category = failure.category
        self.retryable = failure.retryable
        self.sqlstate_class = failure.sqlstate_class
        self.attempts = attempts


def _sqlstate(error: BaseException) -> str | None:
    original = getattr(error, "orig", None)
    value = getattr(original, "sqlstate", None) or getattr(original, "pgcode", None)
    return value if isinstance(value, str) and len(value) == 5 else None


def classify_database_failure(error: BaseException) -> DatabaseFailure:
    """Map database failures to stable categories without leaking messages."""

    sqlstate = _sqlstate(error)
    sqlstate_class = sqlstate[:2] if sqlstate is not None else None
    connection_invalidated = bool(getattr(error, "connection_invalidated", False))

    if sqlstate in POLICY_SQLSTATES:
        return DatabaseFailure(
            response_code="ORIN_SCHEDULER_POLICY_BLOCKED",
            category="policy",
            retryable=False,
            sqlstate_class=sqlstate_class,
        )
    if (
        sqlstate_class == "08"
        or sqlstate in RETRYABLE_SQLSTATES
        or connection_invalidated
        or isinstance(error, (OperationalError, InterfaceError, SQLAlchemyTimeoutError))
    ):
        return DatabaseFailure(
            response_code="ORIN_SCHEDULER_DATABASE_UNAVAILABLE",
            category="transient_database",
            retryable=True,
            sqlstate_class=sqlstate_class,
        )
    return DatabaseFailure(
        response_code="ORIN_SCHEDULER_TRIGGER_BLOCKED",
        category="database",
        retryable=False,
        sqlstate_class=sqlstate_class,
    )


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
        attempts = 0
        while attempts < MAX_TRIGGER_ATTEMPTS:
            attempts += 1
            try:
                return self._trigger_once()
            except (DBAPIError, SQLAlchemyTimeoutError) as exc:
                failure = classify_database_failure(exc)
                if failure.retryable and attempts < MAX_TRIGGER_ATTEMPTS:
                    self.engine.dispose()
                    continue
                raise SchedulerDatabaseError(failure, attempts=attempts) from exc
        raise AssertionError("scheduler trigger retry loop exhausted unexpectedly")

    def _trigger_once(self) -> ScheduledJob:
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
