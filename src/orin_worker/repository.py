"""Narrow stored-function boundary for the ORIN worker."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import bindparam, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Engine

from orin_worker.models import ClaimedJob, CompletionRecord


class PostgresWorkerRepository:
    def __init__(self, engine: Engine, *, expected_role: str = "orin_worker") -> None:
        self.engine = engine
        self.expected_role = expected_role

    def _assert_narrow_role(self, connection: object) -> None:
        current_role = connection.execute(text("select current_user")).scalar_one()  # type: ignore[attr-defined]
        if current_role != self.expected_role:
            raise RuntimeError(
                f"database role mismatch: required={self.expected_role}, received={current_role}"
            )

    def claim_next(self, *, worker_id: str, lease_seconds: int) -> ClaimedJob | None:
        with self.engine.begin() as connection:
            self._assert_narrow_role(connection)
            row = connection.execute(
                text(
                    """
                    select *
                    from orin_private.claim_next_job(:worker_id, :lease_seconds)
                    """
                ),
                {"worker_id": worker_id, "lease_seconds": lease_seconds},
            ).first()
        if row is None:
            return None
        value = row._mapping
        return ClaimedJob(
            job_id=value["job_id"],
            client_id=value["client_id"],
            request_id=value["request_id"],
            requested_mode=value["requested_mode"],
            attempt_count=value["attempt_count"],
            payload=value["payload"],
            lease_expires_at=value["lease_expires_at"],
        )

    def renew(self, *, job_id: UUID, worker_id: str, lease_seconds: int) -> bool:
        with self.engine.begin() as connection:
            self._assert_narrow_role(connection)
            return bool(
                connection.execute(
                    text(
                        """
                        select orin_private.renew_job_lease(
                          :job_id, :worker_id, :lease_seconds
                        )
                        """
                    ),
                    {
                        "job_id": job_id,
                        "worker_id": worker_id,
                        "lease_seconds": lease_seconds,
                    },
                ).scalar_one()
            )

    def complete(
        self,
        *,
        job_id: UUID,
        worker_id: str,
        final_result: dict[str, Any],
    ) -> CompletionRecord:
        with self.engine.begin() as connection:
            self._assert_narrow_role(connection)
            statement = text(
                """
                select *
                from orin_private.complete_job(
                  :job_id, :worker_id, :final_result
                )
                """
            ).bindparams(bindparam("final_result", type_=JSONB))
            row = connection.execute(
                statement,
                {
                    "job_id": job_id,
                    "worker_id": worker_id,
                    "final_result": final_result,
                },
            ).one()
        value = row._mapping
        return CompletionRecord(
            run_id=value["run_id"],
            status=value["status"],
            replayed=value["replayed"],
        )

    def ping(self) -> None:
        with self.engine.connect() as connection:
            self._assert_narrow_role(connection)
            connection.execute(text("select 1")).scalar_one()

    def close(self) -> None:
        self.engine.dispose()
