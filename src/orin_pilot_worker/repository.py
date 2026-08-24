"""Function-only database boundary for generic OAuth pilot dry-runs."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import bindparam, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Engine

from orin_worker.models import ClaimedJob, CompletionRecord


class PostgresPilotRepository:
    """Repository intentionally unable to read Vault or Shopify credentials."""

    def __init__(self, engine: Engine, *, expected_role: str = "orin_pilot_worker") -> None:
        if expected_role != "orin_pilot_worker":
            raise ValueError("generic pilot worker requires the orin_pilot_worker role")
        self.engine = engine
        self.expected_role = expected_role

    def _assert_role(self, connection: object) -> None:
        role = connection.execute(text("select current_user")).scalar_one()  # type: ignore[attr-defined]
        if role != self.expected_role:
            raise RuntimeError(
                f"database role mismatch: required={self.expected_role}, received={role}"
            )

    def materialize_next_content_decision(self) -> None:
        # Generic pilot jobs are prepared through the separate operator-only
        # commissioning function. The worker never interprets arbitrary tenant
        # decisions or opens gates by itself.
        return None

    def claim_next(self, *, worker_id: str, lease_seconds: int) -> ClaimedJob | None:
        with self.engine.begin() as connection:
            self._assert_role(connection)
            row = connection.execute(
                text(
                    """
                    select *
                    from orin_private.claim_next_generic_pilot_job(
                      :worker_id, :lease_seconds
                    )
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
            self._assert_role(connection)
            return bool(
                connection.execute(
                    text(
                        "select orin_private.renew_job_lease(:job_id, :worker_id, :lease_seconds)"
                    ),
                    {
                        "job_id": job_id,
                        "worker_id": worker_id,
                        "lease_seconds": lease_seconds,
                    },
                ).scalar_one()
            )

    def get_context(self, *, job_id: UUID, worker_id: str) -> dict[str, Any]:
        with self.engine.begin() as connection:
            self._assert_role(connection)
            value = connection.execute(
                text(
                    "select orin_private.get_generic_pilot_context(:job_id, :worker_id)"
                ),
                {"job_id": job_id, "worker_id": worker_id},
            ).scalar_one()
        if not isinstance(value, dict):
            raise RuntimeError("database returned an invalid pilot context")
        forbidden = {"shopify_access_token", "shopify_refresh_token", "credential"}
        if any(key in value for key in forbidden):
            raise RuntimeError("pilot context exposed a forbidden credential field")
        return value

    def complete(
        self,
        *,
        job_id: UUID,
        worker_id: str,
        final_result: dict[str, Any],
        review_draft: dict[str, Any] | None = None,
    ) -> CompletionRecord:
        with self.engine.begin() as connection:
            self._assert_role(connection)
            statement = text(
                """
                select *
                from orin_private.complete_generic_pilot_job(
                  :job_id, :worker_id, :final_result, :review_draft
                )
                """
            ).bindparams(
                bindparam("final_result", type_=JSONB),
                bindparam("review_draft", type_=JSONB),
            )
            row = connection.execute(
                statement,
                {
                    "job_id": job_id,
                    "worker_id": worker_id,
                    "final_result": final_result,
                    "review_draft": review_draft,
                },
            ).one()
        value = row._mapping
        return CompletionRecord(
            run_id=value["run_id"],
            status=value["status"],
            replayed=value["replayed"],
        )

    def defer(
        self,
        *,
        job_id: UUID,
        worker_id: str,
        final_result: dict[str, Any],
    ) -> CompletionRecord:
        with self.engine.begin() as connection:
            self._assert_role(connection)
            statement = text(
                """
                select * from orin_private.defer_generic_pilot_job(
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
            self._assert_role(connection)
            connection.execute(text("select 1")).scalar_one()

    def close(self) -> None:
        self.engine.dispose()
