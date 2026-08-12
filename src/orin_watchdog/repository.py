"""Read-only database projection for the fixed HBStore watchdog."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Engine

from orin_watchdog.models import WatchdogSnapshot


class WatchdogRepository:
    def __init__(self, engine: Engine, *, expected_role: str = "orin_watchdog") -> None:
        self.engine = engine
        self.expected_role = expected_role

    def snapshot(self, *, client_id: str, source_job_key: str) -> WatchdogSnapshot:
        with self.engine.connect() as connection:
            current_role = connection.execute(text("select current_user")).scalar_one()
            if current_role != self.expected_role:
                raise RuntimeError(
                    f"database role mismatch: required={self.expected_role}, received={current_role}"
                )
            row = connection.execute(
                text(
                    """
                    select
                      client.status as client_status,
                      settings.request_intake_enabled,
                      settings.automation_enabled,
                      settings.shopify_writes_enabled,
                      settings.approved_draft_writes_enabled,
                      settings.max_concurrency,
                      settings.allowed_mode,
                      health.state as scheduler_state,
                      health.scheduler_owner,
                      job.job_id,
                      job.request_id,
                      job.status as job_status,
                      job.scheduled_for,
                      job.attempt_count,
                      job.last_error_code as job_error_code,
                      run.run_id,
                      run.status as run_status,
                      run.decision,
                      run.code_version,
                      run.shopify_create_count,
                      run.shopify_published,
                      run.queue_changed,
                      run.reconciliation_status,
                      run.error_code as run_error_code,
                      run.started_at,
                      run.finished_at
                    from public.clients client
                    join public.client_runtime_settings settings using (client_id)
                    join public.scheduler_health health using (client_id)
                    left join public.content_jobs job
                      on job.client_id = client.client_id
                     and job.source_job_key = :source_job_key
                    left join public.runs run
                      on run.client_id = job.client_id
                     and run.request_id = job.request_id
                    where client.client_id = :client_id
                    """
                ),
                {"client_id": client_id, "source_job_key": source_job_key},
            ).one()
        return WatchdogSnapshot(**dict(row._mapping))

    def ping(self) -> None:
        with self.engine.connect() as connection:
            current_role = connection.execute(text("select current_user")).scalar_one()
            if current_role != self.expected_role:
                raise RuntimeError(
                    f"database role mismatch: required={self.expected_role}, received={current_role}"
                )

    def close(self) -> None:
        self.engine.dispose()
