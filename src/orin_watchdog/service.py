"""Pure evaluation policy for the fixed daily scheduler watchdog."""

from __future__ import annotations

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from orin_watchdog.models import WatchdogResult, WatchdogSnapshot


CLIENT_ID = "hoverboard_store"
SCHEDULER_OWNER = "prefect:orin-hbstore-prod"
SCHEDULE_NAME = "orin-hbstore-prod"
LONDON = ZoneInfo("Europe/London")
EXPECTED_LOCAL_TIME = time(hour=11)
GRACE_PERIOD = timedelta(minutes=15)


def source_job_key(now: datetime) -> str:
    local_date = now.astimezone(LONDON).date()
    return f"scheduler:{SCHEDULE_NAME}:{local_date.isoformat()}"


def evaluate(snapshot: WatchdogSnapshot, *, now: datetime) -> WatchdogResult:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("watchdog time must be timezone-aware")
    local_now = now.astimezone(LONDON)
    expected_at = datetime.combine(local_now.date(), EXPECTED_LOCAL_TIME, tzinfo=LONDON)
    deadline_at = expected_at + GRACE_PERIOD
    key = source_job_key(now)

    def result(status: str, code: str) -> WatchdogResult:
        return WatchdogResult(
            status=status,
            code=code,
            client_id=CLIENT_ID,
            source_job_key=key,
            observed_at=now.isoformat(),
            expected_at=expected_at.isoformat(),
            deadline_at=deadline_at.isoformat(),
            job_id=str(snapshot.job_id) if snapshot.job_id else None,
            run_id=snapshot.run_id,
            job_status=snapshot.job_status,
            run_status=snapshot.run_status,
        )

    if local_now < deadline_at:
        return result("pending", "ORIN_WATCHDOG_BEFORE_DEADLINE")

    if (
        snapshot.client_status != "active"
        or not snapshot.request_intake_enabled
        or not snapshot.automation_enabled
        or snapshot.scheduler_state != "healthy"
        or snapshot.scheduler_owner != SCHEDULER_OWNER
        or snapshot.max_concurrency != 1
        or snapshot.allowed_mode not in {"dry-run", "hidden-draft"}
        or (
            snapshot.allowed_mode == "dry-run"
            and snapshot.shopify_writes_enabled
        )
        or (
            snapshot.allowed_mode == "hidden-draft"
            and not snapshot.shopify_writes_enabled
        )
    ):
        return result("alert", "ORIN_SCHEDULER_NOT_ACTIVE")

    if snapshot.job_id is None:
        return result("alert", "ORIN_SCHEDULED_RUN_MISSED")

    if snapshot.job_status in {"queued", "leased", "running"}:
        return result("alert", "ORIN_SCHEDULED_RUN_STUCK")

    if snapshot.job_status != "completed" or snapshot.run_status != "completed":
        return result("alert", "ORIN_SCHEDULED_RUN_FAILED")

    if snapshot.run_id is None or snapshot.finished_at is None:
        return result("alert", "ORIN_SCHEDULED_RUN_EVIDENCE_MISSING")

    if (
        snapshot.shopify_published is not False
        or snapshot.queue_changed is not False
        or snapshot.shopify_create_count is None
        or snapshot.shopify_create_count < 0
        or (
            snapshot.allowed_mode == "dry-run"
            and snapshot.shopify_create_count != 0
        )
        or (
            snapshot.allowed_mode == "hidden-draft"
            and snapshot.shopify_create_count > 1
        )
        or snapshot.reconciliation_status not in {"not_required", "reconciled"}
        or snapshot.code_version is None
        or len(snapshot.code_version) != 40
        or any(
            character not in "0123456789abcdef"
            for character in snapshot.code_version
        )
    ):
        return result("alert", "ORIN_SCHEDULED_RUN_INVARIANT_VIOLATION")

    return result("healthy", "ORIN_SCHEDULED_RUN_OBSERVED")
