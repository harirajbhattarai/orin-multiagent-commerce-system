from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID

import pytest

from orin_watchdog.models import WatchdogSnapshot
from orin_watchdog.service import evaluate, source_job_key


AFTER_DEADLINE = datetime(2026, 7, 30, 10, 20, tzinfo=UTC)
BEFORE_DEADLINE = datetime(2026, 7, 30, 10, 10, tzinfo=UTC)


def healthy_snapshot() -> WatchdogSnapshot:
    return WatchdogSnapshot(
        client_status="active",
        request_intake_enabled=True,
        automation_enabled=True,
        shopify_writes_enabled=False,
        max_concurrency=1,
        allowed_mode="dry-run",
        scheduler_state="healthy",
        scheduler_owner="openclaw:orin-hbstore-prod",
        job_id=UUID("11111111-1111-4111-8111-111111111111"),
        request_id=UUID("22222222-2222-4222-8222-222222222222"),
        job_status="completed",
        scheduled_for=datetime(2026, 7, 30, 10, tzinfo=UTC),
        attempt_count=1,
        job_error_code=None,
        run_id="hb_20260730T100001Z_abcdef12",
        run_status="completed",
        decision="READY_TO_CREATE_SELECTED_JOB_DRAFT",
        code_version="a" * 40,
        shopify_create_count=0,
        shopify_published=False,
        queue_changed=False,
        reconciliation_status="not_required",
        run_error_code=None,
        started_at=datetime(2026, 7, 30, 10, tzinfo=UTC),
        finished_at=datetime(2026, 7, 30, 10, 5, tzinfo=UTC),
    )


def test_healthy_terminal_run_is_observed_after_grace_period():
    result = evaluate(healthy_snapshot(), now=AFTER_DEADLINE)

    assert result.status == "healthy"
    assert result.code == "ORIN_SCHEDULED_RUN_OBSERVED"
    assert result.source_job_key == "scheduler:orin-hbstore-prod:2026-07-30"


def test_before_deadline_is_pending_without_false_alarm():
    snapshot = replace(
        healthy_snapshot(),
        client_status="maintenance",
        automation_enabled=False,
        scheduler_state="disabled",
        scheduler_owner=None,
        job_id=None,
        request_id=None,
        job_status=None,
        run_id=None,
        run_status=None,
        finished_at=None,
    )

    result = evaluate(snapshot, now=BEFORE_DEADLINE)

    assert result.status == "pending"
    assert result.code == "ORIN_WATCHDOG_BEFORE_DEADLINE"


def test_missing_daily_job_emits_missed_run_alert():
    snapshot = replace(
        healthy_snapshot(),
        job_id=None,
        request_id=None,
        job_status=None,
        run_id=None,
        run_status=None,
        finished_at=None,
    )

    result = evaluate(snapshot, now=AFTER_DEADLINE)

    assert result.status == "alert"
    assert result.code == "ORIN_SCHEDULED_RUN_MISSED"


@pytest.mark.parametrize("job_status", ["queued", "leased", "running"])
def test_nonterminal_job_after_grace_emits_stuck_alert(job_status: str):
    result = evaluate(
        replace(
            healthy_snapshot(),
            job_status=job_status,
            run_id=None,
            run_status=None,
            finished_at=None,
        ),
        now=AFTER_DEADLINE,
    )

    assert result.status == "alert"
    assert result.code == "ORIN_SCHEDULED_RUN_STUCK"


@pytest.mark.parametrize(
    ("job_status", "run_status"),
    [("blocked", "blocked"), ("failed", "failed"), ("cancelled", None)],
)
def test_terminal_failure_emits_failed_run_alert(
    job_status: str,
    run_status: str | None,
):
    result = evaluate(
        replace(
            healthy_snapshot(),
            job_status=job_status,
            run_status=run_status,
        ),
        now=AFTER_DEADLINE,
    )

    assert result.status == "alert"
    assert result.code == "ORIN_SCHEDULED_RUN_FAILED"


def test_closed_scheduler_after_deadline_emits_configuration_alert():
    result = evaluate(
        replace(
            healthy_snapshot(),
            client_status="maintenance",
            automation_enabled=False,
            scheduler_state="disabled",
            scheduler_owner=None,
        ),
        now=AFTER_DEADLINE,
    )

    assert result.status == "alert"
    assert result.code == "ORIN_SCHEDULER_NOT_ACTIVE"


@pytest.mark.parametrize(
    ("allowed_mode", "shopify_writes_enabled"),
    [("dry-run", True), ("hidden-draft", False)],
)
def test_inconsistent_mode_and_write_gate_emits_configuration_alert(
    allowed_mode: str,
    shopify_writes_enabled: bool,
):
    result = evaluate(
        replace(
            healthy_snapshot(),
            allowed_mode=allowed_mode,
            shopify_writes_enabled=shopify_writes_enabled,
        ),
        now=AFTER_DEADLINE,
    )

    assert result.status == "alert"
    assert result.code == "ORIN_SCHEDULER_NOT_ACTIVE"


def test_source_key_uses_london_date_across_utc_boundary():
    observed_at = datetime(2026, 7, 29, 23, 30, tzinfo=UTC)

    assert source_job_key(observed_at) == "scheduler:orin-hbstore-prod:2026-07-30"


def test_naive_time_is_rejected():
    with pytest.raises(ValueError, match="timezone-aware"):
        evaluate(healthy_snapshot(), now=datetime(2026, 7, 30, 12))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("shopify_create_count", 1),
        ("shopify_published", True),
        ("queue_changed", True),
        ("reconciliation_status", "needs_review"),
        ("code_version", None),
        ("code_version", "not-a-git-sha"),
    ],
)
def test_completed_dry_run_with_unsafe_receipt_emits_invariant_alert(
    field: str,
    value: object,
):
    result = evaluate(
        replace(healthy_snapshot(), **{field: value}),
        now=AFTER_DEADLINE,
    )

    assert result.status == "alert"
    assert result.code == "ORIN_SCHEDULED_RUN_INVARIANT_VIOLATION"


def test_hidden_draft_allows_at_most_one_unpublished_create():
    hidden_draft = replace(
        healthy_snapshot(),
        allowed_mode="hidden-draft",
        shopify_writes_enabled=True,
        shopify_create_count=1,
        reconciliation_status="reconciled",
    )

    assert evaluate(hidden_draft, now=AFTER_DEADLINE).status == "healthy"
    unsafe = evaluate(
        replace(hidden_draft, shopify_create_count=2),
        now=AFTER_DEADLINE,
    )
    assert unsafe.code == "ORIN_SCHEDULED_RUN_INVARIANT_VIOLATION"
