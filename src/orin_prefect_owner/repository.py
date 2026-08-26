"""Narrow repositories for fixed Prefect scheduler enqueue boundaries."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import psycopg


@dataclass(frozen=True)
class CommissioningJob:
    job_id: UUID
    client_id: str
    request_id: UUID
    requested_mode: str
    job_status: str
    scheduled_for: datetime
    created_at: datetime
    replayed: bool

    def as_json(self) -> dict[str, Any]:
        value = asdict(self)
        value["job_id"] = str(self.job_id)
        value["request_id"] = str(self.request_id)
        value["scheduled_for"] = self.scheduled_for.isoformat()
        value["created_at"] = self.created_at.isoformat()
        return value


class OwnerRepository:
    def __init__(self, database_url_file: Path, *, expected_role: str) -> None:
        self.database_url_file = database_url_file
        self.expected_role = expected_role

    def enqueue(self) -> CommissioningJob:
        database_url = self.database_url_file.read_text(encoding="utf-8").strip()
        if not database_url:
            raise RuntimeError("owner database URL file is empty")
        with psycopg.connect(database_url, autocommit=True) as connection:
            with connection.cursor() as cursor:
                cursor.execute("select current_user")
                current_role = cursor.fetchone()[0]
                if current_role != self.expected_role:
                    raise RuntimeError(
                        "database role mismatch: "
                        f"required={self.expected_role}, received={current_role}"
                    )
                cursor.execute(
                    "select job_id, client_id, request_id, requested_mode, "
                    "job_status, scheduled_for, created_at, replayed "
                    "from orin_private.enqueue_hoverboard_prefect_commissioning_job()"
                )
                row = cursor.fetchone()
        if row is None:
            raise RuntimeError("commissioning function returned no receipt")
        return CommissioningJob(*row)


class DailyOwnerRepository:
    """Execute only the fixed, zero-argument daily Prefect boundary."""

    def __init__(self, database_url_file: Path, *, expected_role: str) -> None:
        self.database_url_file = database_url_file
        self.expected_role = expected_role

    def enqueue(self) -> CommissioningJob:
        database_url = self.database_url_file.read_text(encoding="utf-8").strip()
        if not database_url:
            raise RuntimeError("owner database URL file is empty")
        with psycopg.connect(database_url, autocommit=True) as connection:
            with connection.cursor() as cursor:
                cursor.execute("select current_user")
                current_role = cursor.fetchone()[0]
                if current_role != self.expected_role:
                    raise RuntimeError(
                        "database role mismatch: "
                        f"required={self.expected_role}, received={current_role}"
                    )
                cursor.execute(
                    "select job_id, client_id, request_id, requested_mode, "
                    "job_status, scheduled_for, created_at, replayed "
                    "from orin_private.enqueue_hoverboard_prefect_scheduled_job()"
                )
                row = cursor.fetchone()
        if row is None:
            raise RuntimeError("daily scheduler function returned no receipt")
        return CommissioningJob(*row)


class HcsDailyOwnerRepository:
    """Execute only the fixed, zero-argument HCS daily boundary."""

    def __init__(self, database_url_file: Path, *, expected_role: str) -> None:
        self.database_url_file = database_url_file
        self.expected_role = expected_role

    def enqueue(self) -> CommissioningJob:
        database_url = self.database_url_file.read_text(encoding="utf-8").strip()
        if not database_url:
            raise RuntimeError("HCS owner database URL file is empty")
        with psycopg.connect(database_url, autocommit=True) as connection:
            with connection.cursor() as cursor:
                cursor.execute("select current_user")
                current_role = cursor.fetchone()[0]
                if current_role != self.expected_role:
                    raise RuntimeError(
                        "database role mismatch: "
                        f"required={self.expected_role}, received={current_role}"
                    )
                cursor.execute(
                    "select job_id, client_id, request_id, requested_mode, "
                    "job_status, scheduled_for, created_at, replayed "
                    "from orin_private.enqueue_hcs_prefect_scheduled_job()"
                )
                row = cursor.fetchone()
        if row is None:
            raise RuntimeError("HCS daily scheduler function returned no receipt")
        return CommissioningJob(*row)


class TenantDailyOwnerRepository:
    """Run the zero-argument shared tenant scheduler boundary."""

    def __init__(self, database_url_file: Path, *, expected_role: str) -> None:
        self.database_url_file = database_url_file
        self.expected_role = expected_role

    def enqueue(self) -> CommissioningJob | None:
        database_url = self.database_url_file.read_text(encoding="utf-8").strip()
        if not database_url:
            raise RuntimeError("tenant scheduler database URL file is empty")
        with psycopg.connect(database_url, autocommit=True) as connection:
            with connection.cursor() as cursor:
                cursor.execute("select current_user")
                current_role = cursor.fetchone()[0]
                if current_role != self.expected_role:
                    raise RuntimeError(
                        "database role mismatch: "
                        f"required={self.expected_role}, received={current_role}"
                    )
                cursor.execute(
                    "select job_id, client_id, request_id, requested_mode, "
                    "job_status, scheduled_for, created_at, replayed "
                    "from orin_private.enqueue_due_tenant_prefect_jobs()"
                )
                row = cursor.fetchone()
        return None if row is None else CommissioningJob(*row)
