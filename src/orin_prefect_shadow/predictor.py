"""Pure, deterministic prediction logic for Prefect shadow runs."""

from __future__ import annotations

from datetime import date
from typing import Any


SHADOW_SNAPSHOT_SCHEMA = "orin.prefect-shadow-snapshot/v1"
FIXED_CLIENT_ID = "hoverboard_store"


class ShadowSnapshotError(ValueError):
    """Raised when the database projection violates the shadow contract."""


def _date(value: object, *, field: str) -> date:
    if not isinstance(value, str):
        raise ShadowSnapshotError(f"{field} must be an ISO date")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ShadowSnapshotError(f"{field} must be an ISO date") from exc


def _normalize_items(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    items = snapshot.get("items")
    if not isinstance(items, list):
        raise ShadowSnapshotError("items must be an array")
    seen: set[int] = set()
    normalized: list[dict[str, Any]] = []
    for raw in items:
        if not isinstance(raw, dict):
            raise ShadowSnapshotError("content-plan items must be objects")
        number = raw.get("item_number")
        if isinstance(number, bool) or not isinstance(number, int) or number < 1:
            raise ShadowSnapshotError("item_number must be a positive integer")
        if number in seen:
            raise ShadowSnapshotError("item_number values must be unique")
        seen.add(number)
        status = raw.get("status")
        if not isinstance(status, str) or not status:
            raise ShadowSnapshotError("item status is required")
        expected = raw.get("expected_draft_date")
        if expected is not None:
            _date(expected, field="expected_draft_date")
        normalized.append(dict(raw))
    return sorted(normalized, key=lambda item: item["item_number"])


def _gate_projection(snapshot: dict[str, Any]) -> dict[str, Any]:
    runtime = snapshot.get("runtime")
    scheduler = snapshot.get("scheduler")
    if not isinstance(runtime, dict) or not isinstance(scheduler, dict):
        raise ShadowSnapshotError("runtime and scheduler projections are required")
    blockers: list[str] = []
    if snapshot.get("client_status") != "active":
        blockers.append("client_not_active")
    if runtime.get("request_intake_enabled") is not True:
        blockers.append("request_intake_closed")
    if runtime.get("automation_enabled") is not True:
        blockers.append("automation_disabled")
    if runtime.get("allowed_mode") != "dry-run":
        blockers.append("dry_run_not_allowed")
    if snapshot.get("active_jobs") not in (0, None):
        blockers.append("active_job_exists")
    return {
        "would_accept_scheduler_request": not blockers,
        "blockers": blockers,
        "shopify_writes_observed": runtime.get("shopify_writes_enabled") is True,
        "scheduler_state": scheduler.get("state"),
        "scheduler_owner": scheduler.get("owner"),
    }


def _comparison(
    latest: object, *, as_of_date: date, selected_job_number: int | None
) -> dict[str, Any]:
    if not isinstance(latest, dict):
        return {"status": "not_comparable", "reason": "no_scheduler_dry_run"}
    business_date = latest.get("business_date")
    if business_date != as_of_date.isoformat():
        return {
            "status": "not_comparable",
            "reason": "different_business_date",
            "actual_business_date": business_date,
        }
    actual_decision = latest.get("decision")
    actual_job = latest.get("selected_job_number")
    if selected_job_number is None:
        matches = actual_decision == "no_job_due" and actual_job is None
    else:
        matches = (
            actual_decision == "READY_TO_CREATE_SELECTED_JOB_DRAFT"
            and actual_job == selected_job_number
        )
    return {
        "status": "match" if matches else "mismatch",
        "actual_run_id": latest.get("run_id"),
        "actual_decision": actual_decision,
        "actual_selected_job_number": actual_job,
    }


def predict_shadow_run(
    snapshot: dict[str, Any], *, as_of_date: date
) -> dict[str, Any]:
    """Predict the existing planner result without creating or changing work."""
    if snapshot.get("schema") != SHADOW_SNAPSHOT_SCHEMA:
        raise ShadowSnapshotError("unsupported shadow snapshot schema")
    if snapshot.get("client_id") != FIXED_CLIENT_ID:
        raise ShadowSnapshotError("shadow snapshot belongs to another client")

    items = _normalize_items(snapshot)
    planned = [item for item in items if item["status"] == "planned"]
    due = [
        item
        for item in planned
        if item.get("expected_draft_date") is not None
        and _date(item["expected_draft_date"], field="expected_draft_date")
        <= as_of_date
    ]
    selected = min(due, key=lambda item: item["item_number"]) if due else None
    future = [
        item
        for item in planned
        if item.get("expected_draft_date") is not None
        and _date(item["expected_draft_date"], field="expected_draft_date")
        > as_of_date
    ]
    next_due = (
        min(
            future,
            key=lambda item: (
                _date(item["expected_draft_date"], field="expected_draft_date"),
                item["item_number"],
            ),
        )
        if future
        else None
    )
    selected_number = selected["item_number"] if selected else None
    prediction = {
        "schema": "orin.prefect-shadow-prediction/v1",
        "mode": "shadow",
        "client_id": FIXED_CLIENT_ID,
        "as_of_date": as_of_date.isoformat(),
        "planner_decision": "job_selected" if selected else "no_job_due",
        "selected_job_number": selected_number,
        "selected_topic": selected.get("topic") if selected else None,
        "next_due_job_number": next_due.get("item_number") if next_due else None,
        "next_due_date": next_due.get("expected_draft_date") if next_due else None,
        "gate_projection": _gate_projection(snapshot),
        "observed_active_jobs": snapshot.get("active_jobs"),
        "observed_open_incidents": snapshot.get("open_incidents"),
    }
    prediction["comparison"] = _comparison(
        snapshot.get("latest_scheduler_dry_run"),
        as_of_date=as_of_date,
        selected_job_number=selected_number,
    )
    return prediction
