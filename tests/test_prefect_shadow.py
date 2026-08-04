from datetime import date

import pytest

from orin_prefect_shadow.predictor import ShadowSnapshotError, predict_shadow_run


def snapshot(*, items, latest=None, client_status="active", active_jobs=0):
    return {
        "schema": "orin.prefect-shadow-snapshot/v1",
        "client_id": "hoverboard_store",
        "client_status": client_status,
        "runtime": {
            "request_intake_enabled": True,
            "automation_enabled": True,
            "shopify_writes_enabled": False,
            "max_concurrency": 1,
            "allowed_mode": "dry-run",
        },
        "scheduler": {
            "state": "healthy",
            "owner": "openclaw:orin-hbstore-prod",
        },
        "active_jobs": active_jobs,
        "open_incidents": 0,
        "items": items,
        "latest_scheduler_dry_run": latest,
    }


def item(number, expected, *, status="planned", topic=None):
    return {
        "item_number": number,
        "expected_draft_date": expected,
        "status": status,
        "topic": topic or f"Topic {number}",
    }


def test_selects_lowest_numbered_due_planned_item():
    result = predict_shadow_run(
        snapshot(
            items=[
                item(42, "2026-08-04"),
                item(40, "2026-08-03"),
                item(39, "2026-08-01", status="draft_created"),
            ]
        ),
        as_of_date=date(2026, 8, 4),
    )
    assert result["planner_decision"] == "job_selected"
    assert result["selected_job_number"] == 40
    assert result["gate_projection"]["would_accept_scheduler_request"] is True


def test_reports_next_future_due_item_without_selecting_it():
    result = predict_shadow_run(
        snapshot(items=[item(42, "2026-08-09"), item(41, "2026-08-08")]),
        as_of_date=date(2026, 8, 4),
    )
    assert result["planner_decision"] == "no_job_due"
    assert result["selected_job_number"] is None
    assert result["next_due_job_number"] == 41
    assert result["next_due_date"] == "2026-08-08"


def test_closed_gates_are_reported_without_changing_planner_prediction():
    value = snapshot(
        items=[item(40, "2026-08-03")],
        client_status="maintenance",
        active_jobs=1,
    )
    value["runtime"]["request_intake_enabled"] = False
    value["runtime"]["automation_enabled"] = False
    result = predict_shadow_run(value, as_of_date=date(2026, 8, 4))
    assert result["selected_job_number"] == 40
    assert result["gate_projection"] == {
        "would_accept_scheduler_request": False,
        "blockers": [
            "client_not_active",
            "request_intake_closed",
            "automation_disabled",
            "active_job_exists",
        ],
        "shopify_writes_observed": False,
        "scheduler_state": "healthy",
        "scheduler_owner": "openclaw:orin-hbstore-prod",
    }


def test_matches_same_date_no_job_due_scheduler_receipt():
    latest = {
        "business_date": "2026-08-04",
        "run_id": "hb_example",
        "decision": "no_job_due",
        "selected_job_number": None,
    }
    result = predict_shadow_run(
        snapshot(items=[], latest=latest), as_of_date=date(2026, 8, 4)
    )
    assert result["comparison"]["status"] == "match"


def test_matches_same_date_selected_job_scheduler_receipt():
    latest = {
        "business_date": "2026-08-04",
        "run_id": "hb_example",
        "decision": "READY_TO_CREATE_SELECTED_JOB_DRAFT",
        "selected_job_number": 40,
    }
    result = predict_shadow_run(
        snapshot(items=[item(40, "2026-08-04")], latest=latest),
        as_of_date=date(2026, 8, 4),
    )
    assert result["comparison"]["status"] == "match"


def test_different_date_receipt_is_not_compared():
    latest = {
        "business_date": "2026-08-03",
        "decision": "no_job_due",
        "selected_job_number": None,
    }
    result = predict_shadow_run(
        snapshot(items=[], latest=latest), as_of_date=date(2026, 8, 4)
    )
    assert result["comparison"] == {
        "status": "not_comparable",
        "reason": "different_business_date",
        "actual_business_date": "2026-08-03",
    }


@pytest.mark.parametrize(
    "mutation",
    [
        {"schema": "wrong"},
        {"client_id": "another_client"},
        {"items": "not-an-array"},
        {"items": [item(1, "bad-date")]},
        {"items": [item(1, "2026-08-04"), item(1, "2026-08-05")]},
    ],
)
def test_rejects_malformed_or_cross_tenant_snapshots(mutation):
    value = snapshot(items=[])
    value.update(mutation)
    with pytest.raises(ShadowSnapshotError):
        predict_shadow_run(value, as_of_date=date(2026, 8, 4))
