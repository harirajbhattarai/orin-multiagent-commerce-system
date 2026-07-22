"""Transactional PostgreSQL boundary for idempotent run requests."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    MetaData,
    SmallInteger,
    String,
    Table,
    and_,
    create_engine,
    func,
    literal,
    select,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID, insert
from sqlalchemy.engine import Engine

from orin_control.errors import (
    ClientAccessDenied,
    InsufficientRole,
    RequestConflict,
    RequestIntakeDisabled,
)
from orin_control.models import Principal, RunRequest


metadata = MetaData()

clients = Table(
    "clients",
    metadata,
    Column("client_id", String, primary_key=True),
    Column("status", String, nullable=False),
    schema="public",
)

client_members = Table(
    "client_members",
    metadata,
    Column("client_id", String, primary_key=True),
    Column("user_id", PG_UUID(as_uuid=True), primary_key=True),
    Column("role", String, nullable=False),
    schema="public",
)

client_runtime_settings = Table(
    "client_runtime_settings",
    metadata,
    Column("client_id", String, primary_key=True),
    Column("request_intake_enabled", Boolean, nullable=False),
    Column("automation_enabled", Boolean, nullable=False),
    Column("shopify_writes_enabled", Boolean, nullable=False),
    Column("max_concurrency", SmallInteger, nullable=False),
    Column("allowed_mode", String, nullable=False),
    schema="public",
)

content_jobs = Table(
    "content_jobs",
    metadata,
    Column("job_id", PG_UUID(as_uuid=True), primary_key=True),
    Column("client_id", String, nullable=False),
    Column("source_job_key", String, nullable=False),
    Column("request_id", PG_UUID(as_uuid=True), nullable=False),
    Column("requested_by", PG_UUID(as_uuid=True)),
    Column("requested_mode", String, nullable=False),
    Column("status", String, nullable=False),
    Column("scheduled_for", DateTime(timezone=True), nullable=False),
    Column("payload", JSONB, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    schema="public",
)


@dataclass(frozen=True)
class JobRecord:
    job_id: UUID
    client_id: str
    request_id: UUID
    requested_mode: Literal["dry-run"]
    status: str
    scheduled_for: datetime
    created_at: datetime
    replayed: bool


def normalize_database_url(database_url: str) -> str:
    if database_url.startswith("postgres://"):
        return "postgresql+psycopg://" + database_url.removeprefix("postgres://")
    if database_url.startswith("postgresql://"):
        return "postgresql+psycopg://" + database_url.removeprefix("postgresql://")
    if database_url.startswith("postgresql+psycopg://"):
        return database_url
    raise ValueError("ORIN_DATABASE_URL must be a PostgreSQL connection URL")


def create_database_engine(database_url: str, *, pool_size: int = 1) -> Engine:
    if pool_size != 1:
        raise ValueError("Phase 3 requires database pool size 1")
    return create_engine(
        normalize_database_url(database_url),
        pool_size=pool_size,
        max_overflow=0,
        pool_pre_ping=True,
        pool_recycle=300,
        hide_parameters=True,
        connect_args={
            "sslmode": "require",
            "connect_timeout": 10,
            "prepare_threshold": None,
        },
    )


class PostgresRunRequestRepository:
    def __init__(self, engine: Engine, *, expected_role: str = "orin_api") -> None:
        self.engine = engine
        self.expected_role = expected_role

    def _assert_narrow_role(self, connection: object) -> None:
        current_role = connection.execute(text("select current_user")).scalar_one()  # type: ignore[attr-defined]
        if current_role != self.expected_role:
            raise RuntimeError(
                f"database role mismatch: required={self.expected_role}, received={current_role}"
            )

    @staticmethod
    def _record(row: object, *, replayed: bool) -> JobRecord:
        mapping = row._mapping  # type: ignore[attr-defined]
        return JobRecord(
            job_id=mapping["job_id"],
            client_id=mapping["client_id"],
            request_id=mapping["request_id"],
            requested_mode=mapping["requested_mode"],
            status=mapping["status"],
            scheduled_for=mapping["scheduled_for"],
            created_at=mapping["created_at"],
            replayed=replayed,
        )

    @staticmethod
    def _job_columns() -> tuple[Column[object], ...]:
        return (
            content_jobs.c.job_id,
            content_jobs.c.client_id,
            content_jobs.c.request_id,
            content_jobs.c.requested_mode,
            content_jobs.c.status,
            content_jobs.c.scheduled_for,
            content_jobs.c.created_at,
        )

    def _existing(self, connection: object, *, client_id: str, request_id: UUID) -> object | None:
        return connection.execute(  # type: ignore[attr-defined]
            select(*self._job_columns(), content_jobs.c.source_job_key).where(
                and_(
                    content_jobs.c.client_id == client_id,
                    content_jobs.c.request_id == request_id,
                )
            )
        ).first()

    def request_run(self, *, principal: Principal, client_id: str, request: RunRequest) -> JobRecord:
        source_job_key = f"api:{request.request_id}"
        with self.engine.begin() as connection:
            self._assert_narrow_role(connection)
            access = connection.execute(
                select(
                    clients.c.status.label("client_status"),
                    client_members.c.role,
                    client_runtime_settings.c.request_intake_enabled,
                    client_runtime_settings.c.allowed_mode,
                )
                .select_from(
                    clients.join(
                        client_members,
                        clients.c.client_id == client_members.c.client_id,
                    ).join(
                        client_runtime_settings,
                        clients.c.client_id == client_runtime_settings.c.client_id,
                    )
                )
                .where(
                    and_(
                        clients.c.client_id == client_id,
                        client_members.c.user_id == principal.user_id,
                    )
                )
            ).first()

            if access is None:
                raise ClientAccessDenied("client not found")
            if access.role not in ("owner", "operator"):
                raise InsufficientRole("owner or operator role required")

            existing = self._existing(connection, client_id=client_id, request_id=request.request_id)
            if existing is not None:
                if (
                    existing._mapping["source_job_key"] != source_job_key
                    or existing._mapping["requested_mode"] != request.mode
                ):
                    raise RequestConflict("request UUID has different immutable inputs")
                return self._record(existing, replayed=True)

            if access.client_status != "active" or not access.request_intake_enabled:
                raise RequestIntakeDisabled("client request intake is disabled")
            if access.allowed_mode != request.mode:
                raise RequestIntakeDisabled("requested mode is not enabled")

            statement = (
                insert(content_jobs)
                .values(
                    client_id=client_id,
                    source_job_key=source_job_key,
                    request_id=request.request_id,
                    requested_by=principal.user_id,
                    requested_mode=request.mode,
                    status="queued",
                    scheduled_for=func.now(),
                    payload={},
                )
                .on_conflict_do_nothing(
                    index_elements=[content_jobs.c.client_id, content_jobs.c.request_id]
                )
                .returning(*self._job_columns())
            )
            inserted = connection.execute(statement).first()
            if inserted is not None:
                return self._record(inserted, replayed=False)

            raced = self._existing(connection, client_id=client_id, request_id=request.request_id)
            if raced is None:
                raise RuntimeError("idempotent insert lost without an existing row")
            if (
                raced._mapping["source_job_key"] != source_job_key
                or raced._mapping["requested_mode"] != request.mode
            ):
                raise RequestConflict("request UUID has different immutable inputs")
            return self._record(raced, replayed=True)

    def ping(self) -> None:
        with self.engine.connect() as connection:
            self._assert_narrow_role(connection)
            connection.execute(select(literal(1))).scalar_one()

    def close(self) -> None:
        self.engine.dispose()
