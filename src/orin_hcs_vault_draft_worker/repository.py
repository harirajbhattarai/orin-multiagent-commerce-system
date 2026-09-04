"""Function-only database boundary for HCS Vault-backed draft approvals."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import bindparam, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Engine

from orin_worker.models import ClaimedJob, CompletionRecord


class PostgresHCSVaultDraftRepository:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        self.client_id = "hcs_gadgets"
        self.expected_role = "orin_oauth_draft_worker"

    def _assert_role(self, connection: object) -> None:
        role = connection.execute(text("select current_user")).scalar_one()  # type: ignore[attr-defined]
        if role != self.expected_role:
            raise RuntimeError(
                f"database role mismatch: required={self.expected_role}, received={role}"
            )

    def materialize_next_content_decision(self) -> None:
        with self.engine.begin() as connection:
            self._assert_role(connection)
            connection.execute(
                text(
                    "select * from orin_private."
                    "materialize_next_hcs_vault_approved_draft_decision(:client_id)"
                ),
                {"client_id": self.client_id},
            ).first()

    def claim_next(self, *, worker_id: str, lease_seconds: int) -> ClaimedJob | None:
        with self.engine.begin() as connection:
            self._assert_role(connection)
            row = connection.execute(
                text(
                    """
                    select * from orin_private.claim_next_hcs_vault_approved_draft_job(
                      :worker_id, :client_id, :lease_seconds
                    )
                    """
                ),
                {
                    "worker_id": worker_id,
                    "client_id": self.client_id,
                    "lease_seconds": lease_seconds,
                },
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
                    text("select orin_private.renew_job_lease(:job_id, :worker_id, :lease_seconds)"),
                    {"job_id": job_id, "worker_id": worker_id, "lease_seconds": lease_seconds},
                ).scalar_one()
            )

    def get_context(self, *, job_id: UUID, worker_id: str) -> dict[str, Any]:
        with self.engine.begin() as connection:
            self._assert_role(connection)
            value = connection.execute(
                text("select orin_private.get_hcs_vault_approved_draft_context(:job_id, :worker_id)"),
                {"job_id": job_id, "worker_id": worker_id},
            ).scalar_one()
        if not isinstance(value, dict):
            raise RuntimeError("database returned an invalid HCS draft context")
        shopify = value.get("shopify")
        if not isinstance(shopify, dict) or "refresh_token" in shopify:
            raise RuntimeError("HCS draft context violated the credential boundary")
        return value

    def complete(
        self,
        *,
        job_id: UUID,
        worker_id: str,
        final_result: dict[str, Any],
        review_draft: dict[str, Any] | None = None,
    ) -> CompletionRecord:
        if review_draft is not None:
            raise RuntimeError("approval worker cannot persist a replacement review draft")
        with self.engine.begin() as connection:
            self._assert_role(connection)
            statement = text(
                "select * from orin_private.complete_hcs_vault_approved_draft_job("
                ":job_id, :worker_id, :result)"
            ).bindparams(bindparam("result", type_=JSONB))
            row = connection.execute(
                statement,
                {"job_id": job_id, "worker_id": worker_id, "result": final_result},
            ).one()
        value = row._mapping
        return CompletionRecord(value["run_id"], value["status"], value["replayed"])

    def defer(
        self, *, job_id: UUID, worker_id: str, final_result: dict[str, Any]
    ) -> CompletionRecord:
        with self.engine.begin() as connection:
            self._assert_role(connection)
            statement = text(
                "select * from orin_private.defer_hcs_vault_approved_draft_job("
                ":job_id, :worker_id, :result)"
            ).bindparams(bindparam("result", type_=JSONB))
            row = connection.execute(
                statement,
                {"job_id": job_id, "worker_id": worker_id, "result": final_result},
            ).one()
        value = row._mapping
        return CompletionRecord(value["run_id"], value["status"], value["replayed"])

    def ping(self) -> None:
        with self.engine.connect() as connection:
            self._assert_role(connection)
            connection.execute(text("select 1")).scalar_one()

    def close(self) -> None:
        self.engine.dispose()
