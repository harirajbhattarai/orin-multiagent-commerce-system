"""Function-only PostgreSQL boundary for the trusted commissioner."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import bindparam, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Engine

from orin_commissioner.models import ClaimedCommissioning, CommissioningContext


class PostgresCommissioningRepository:
    def __init__(self, engine: Engine, *, expected_role: str = "orin_commissioner") -> None:
        if expected_role != "orin_commissioner":
            raise ValueError("commissioner database role must be orin_commissioner")
        self.engine = engine
        self.expected_role = expected_role

    def _assert_role(self, connection: object) -> None:
        current_role = connection.execute(text("select current_user")).scalar_one()  # type: ignore[attr-defined]
        if current_role != self.expected_role:
            raise RuntimeError(
                f"database role mismatch: required={self.expected_role}, received={current_role}"
            )

    def ping(self) -> None:
        with self.engine.connect() as connection:
            self._assert_role(connection)
            connection.execute(text("select 1")).scalar_one()

    def claim_next(self, *, worker_id: str, lease_seconds: int) -> ClaimedCommissioning | None:
        with self.engine.begin() as connection:
            self._assert_role(connection)
            row = connection.execute(
                text(
                    """
                    select * from orin_private.claim_next_client_commissioning(
                      :worker_id, :lease_seconds
                    )
                    """
                ),
                {"worker_id": worker_id, "lease_seconds": lease_seconds},
            ).first()
        if row is None:
            return None
        value = row._mapping
        return ClaimedCommissioning(
            request_id=value["commissioning_request_id"],
            client_id=value["client_id"],
            onboarding_request_id=value["onboarding_request_id"],
            attempt_count=value["attempt_count"],
            lease_expires_at=value["lease_expires_at"],
        )

    def renew(self, *, request_id: UUID, worker_id: str, lease_seconds: int) -> bool:
        with self.engine.begin() as connection:
            self._assert_role(connection)
            return bool(
                connection.execute(
                    text(
                        """
                        select orin_private.renew_client_commissioning_lease(
                          :request_id, :worker_id, :lease_seconds
                        )
                        """
                    ),
                    {
                        "request_id": request_id,
                        "worker_id": worker_id,
                        "lease_seconds": lease_seconds,
                    },
                ).scalar_one()
            )

    def get_context(self, *, request_id: UUID, worker_id: str) -> CommissioningContext:
        with self.engine.begin() as connection:
            self._assert_role(connection)
            row = connection.execute(
                text(
                    """
                    select * from orin_private.get_client_commissioning_context(
                      :request_id, :worker_id
                    )
                    """
                ),
                {"request_id": request_id, "worker_id": worker_id},
            ).one()
        value = row._mapping
        scope = value["product_scope"]
        if not isinstance(scope, list) or not all(isinstance(item, dict) for item in scope):
            raise RuntimeError("commissioning context has an invalid product scope")
        categories = value["content_categories"]
        if not isinstance(categories, list) or not all(isinstance(item, str) for item in categories):
            raise RuntimeError("commissioning context has invalid content categories")
        return CommissioningContext(
            request_id=value["commissioning_request_id"],
            client_id=value["client_id"],
            onboarding_request_id=value["onboarding_request_id"],
            display_name=value["display_name"],
            owner_email=value["owner_email"],
            store_domain=value["shopify_store_domain"],
            blog_gid=value["shopify_blog_gid"],
            blog_title=value["shopify_blog_title"],
            market_country=value["market_country"],
            timezone=value["timezone"],
            brand_voice=value["brand_voice"],
            content_categories=tuple(categories),
            product_scope=tuple(scope),
            access_token=value["shopify_access_token"],
            attempt_count=value["attempt_count"],
            lease_expires_at=value["lease_expires_at"],
        )

    def boundary_snapshot(self, *, request_id: UUID, worker_id: str) -> dict[str, Any]:
        with self.engine.begin() as connection:
            self._assert_role(connection)
            value = connection.execute(
                text(
                    """
                    select orin_private.client_commissioning_boundary_snapshot(
                      :request_id, :worker_id
                    )
                    """
                ),
                {"request_id": request_id, "worker_id": worker_id},
            ).scalar_one()
        if not isinstance(value, dict):
            raise RuntimeError("commissioning boundary snapshot is invalid")
        return value

    def record_stage(
        self,
        *,
        request_id: UUID,
        worker_id: str,
        stage: str,
        summary: str,
        evidence: dict[str, Any],
    ) -> None:
        with self.engine.begin() as connection:
            self._assert_role(connection)
            statement = text(
                """
                select orin_private.record_client_commissioning_stage(
                  :request_id, :worker_id, :stage, :summary, :evidence
                )
                """
            ).bindparams(bindparam("evidence", type_=JSONB))
            connection.execute(
                statement,
                {
                    "request_id": request_id,
                    "worker_id": worker_id,
                    "stage": stage,
                    "summary": summary,
                    "evidence": evidence,
                },
            ).scalar_one_or_none()

    def finish(
        self,
        *,
        request_id: UUID,
        worker_id: str,
        succeeded: bool,
        error_code: str,
        evidence: dict[str, Any],
    ) -> None:
        with self.engine.begin() as connection:
            self._assert_role(connection)
            statement = text(
                """
                select orin_private.finish_client_commissioning(
                  :request_id, :worker_id, :succeeded, :error_code, :evidence
                )
                """
            ).bindparams(bindparam("evidence", type_=JSONB))
            connection.execute(
                statement,
                {
                    "request_id": request_id,
                    "worker_id": worker_id,
                    "succeeded": succeeded,
                    "error_code": error_code,
                    "evidence": evidence,
                },
            ).scalar_one_or_none()

    def close(self) -> None:
        self.engine.dispose()
