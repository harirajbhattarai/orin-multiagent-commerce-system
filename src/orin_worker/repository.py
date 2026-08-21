"""Narrow stored-function boundary for the ORIN worker."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import bindparam, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Engine

from orin_worker.models import ClaimedJob, CompletionRecord


class PostgresWorkerRepository:
    def __init__(
        self,
        engine: Engine,
        *,
        expected_role: str = "orin_worker",
        client_id: str | None = None,
    ) -> None:
        if client_id not in {"hoverboard_store", "hcs_gadgets"}:
            raise ValueError("worker database access requires an explicit supported client")
        expected_client_roles = {
            "hoverboard_store": {"orin_worker"},
            "hcs_gadgets": {"orin_hcs_worker", "orin_hcs_shopify_worker"},
        }[client_id]
        if expected_role not in expected_client_roles:
            raise ValueError(
                f"database role {expected_role} cannot serve client {client_id}"
            )
        self.engine = engine
        self.expected_role = expected_role
        self.client_id = client_id

    def _assert_narrow_role(self, connection: object) -> None:
        current_role = connection.execute(text("select current_user")).scalar_one()  # type: ignore[attr-defined]
        if current_role != self.expected_role:
            raise RuntimeError(
                f"database role mismatch: required={self.expected_role}, received={current_role}"
            )

    def claim_next(self, *, worker_id: str, lease_seconds: int) -> ClaimedJob | None:
        with self.engine.begin() as connection:
            self._assert_narrow_role(connection)
            if self.client_id == "hoverboard_store":
                statement = text(
                    """
                    select *
                    from orin_private.claim_next_job_for_client(
                      :worker_id, :client_id, :lease_seconds
                    )
                    """
                )
                parameters = {
                    "worker_id": worker_id,
                    "client_id": self.client_id,
                    "lease_seconds": lease_seconds,
                }
            elif self.expected_role == "orin_hcs_worker":
                statement = text(
                    """
                    select *
                    from orin_private.claim_next_dry_run_job_for_client(
                      :worker_id, :client_id, :lease_seconds
                    )
                    """
                )
                parameters = {
                    "worker_id": worker_id,
                    "client_id": self.client_id,
                    "lease_seconds": lease_seconds,
                }
            else:
                statement = text(
                    """
                    select *
                    from orin_private.claim_next_hcs_approved_draft_job_for_client(
                      :worker_id, :client_id, :lease_seconds
                    )
                    """
                )
                parameters = {
                    "worker_id": worker_id,
                    "client_id": self.client_id,
                    "lease_seconds": lease_seconds,
                }
            row = connection.execute(statement, parameters).first()
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

    def materialize_next_content_decision(self) -> None:
        """Turn at most one eligible dashboard decision into a gated job."""
        with self.engine.begin() as connection:
            self._assert_narrow_role(connection)
            if self.client_id == "hoverboard_store":
                statement = text(
                    """
                    select *
                    from orin_private.materialize_next_content_decision_for_client(
                      :client_id
                    )
                    """
                )
                parameters = {"client_id": self.client_id}
            elif self.expected_role == "orin_hcs_worker":
                statement = text(
                    """
                    select *
                    from orin_private.materialize_next_dry_run_decision_for_client(
                      :client_id
                    )
                    """
                )
                parameters = {"client_id": self.client_id}
            else:
                statement = text(
                    """
                    select *
                    from orin_private.materialize_next_hcs_approved_draft_decision_for_client(
                      :client_id
                    )
                    """
                )
                parameters = {"client_id": self.client_id}
            connection.execute(statement, parameters).first()

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

    def get_content_plan_snapshot(
        self, *, job_id: UUID, worker_id: str
    ) -> dict[str, Any]:
        with self.engine.begin() as connection:
            self._assert_narrow_role(connection)
            value = connection.execute(
                text(
                    """
                    select orin_private.get_content_plan_snapshot(
                      :job_id, :worker_id
                    )
                    """
                ),
                {"job_id": job_id, "worker_id": worker_id},
            ).scalar_one()
        if not isinstance(value, dict):
            raise RuntimeError("database returned an invalid content-plan snapshot")
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
            self._assert_narrow_role(connection)
            statement = text(
                """
                select *
                from orin_private.complete_job_with_review_draft(
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
            self._assert_narrow_role(connection)
            statement = text(
                """
                select *
                from orin_private.defer_job(
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
