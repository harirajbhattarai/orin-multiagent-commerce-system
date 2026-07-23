"""Regression checks for truthful ORIN cron reporting."""

import runpy
import sys
from pathlib import Path


ENTRYPOINT = Path(__file__).resolve().parent / "cron_entrypoint.py"
MODULE = runpy.run_path(str(ENTRYPOINT), run_name="orin_reporting_test")
build_report = MODULE["build_report"]


def load_entrypoint_with_args(*args):
    original_argv = sys.argv[:]
    try:
        sys.argv = [str(ENTRYPOINT), *args]
        return runpy.run_path(str(ENTRYPOINT), run_name="orin_cli_reporting_test")
    finally:
        sys.argv = original_argv


def test_no_mode_flag_defaults_to_dry_run():
    module = load_entrypoint_with_args()

    assert module["DRY_RUN"] is True
    assert module["LIVE_DRAFT"] is False
    assert module["REQUESTED_MODE"] == "dry-run"


def test_explicit_dry_run_takes_precedence_in_cli_parsing():
    module = load_entrypoint_with_args(
        "--live-draft",
        "--confirm-live-draft",
        "--dry-run",
    )

    assert module["DRY_RUN"] is True
    assert module["LIVE_DRAFT"] is True
    assert module["CONFIRM_LIVE_DRAFT"] is True
    assert module["REQUESTED_MODE"] == "live-draft"


def test_dry_run_report_is_truthful():
    report = build_report(
        {
            "blocked": False,
            "dry_run": True,
            "requested_mode": "dry-run",
            "live_draft_requested": False,
            "live_draft_confirmed": False,
            "shopify_touched": False,
            "queue_touched": False,
        },
        timestamp="2026-07-21T10:00:00+00:00",
    )

    assert report["mode"] == "dry-run"
    assert report["requested_mode"] == "dry-run"
    assert report["effective_mode"] == "dry-run"
    assert report["dry_run"] is True
    assert report["shopify_touched"] is False
    assert report["queue_touched"] is False


def test_needs_review_report_preserves_nonterminal_reconciliation_state():
    report = build_report(
        {
            "blocked": True,
            "dry_run": False,
            "requested_mode": "live-draft",
            "shopify_touched": True,
            "shopify_write_state": "article_observed",
            "replay_disposition": "reconcile",
            "transaction_result": {
                "decision": "DRAFT_CREATED_VERIFICATION_FAILED",
                "approved": False,
                "shopify_article_id": 9001,
                "shopify_create_count": 1,
                "shopify_write_state": "article_observed",
                "reconciliation_status": "needs_review",
            },
        },
        timestamp="2026-07-23T12:00:00+00:00",
    )

    assert report["blocked"] is True
    assert report["shopify_create_count"] == 1
    assert report["shopify_write_state"] == "article_observed"
    assert report["reconciliation_status"] == "needs_review"
    assert report["replay_disposition"] == "reconcile"


def test_live_draft_result_is_not_reported_as_dry_run():
    report = build_report(
        {
            "blocked": False,
            "dry_run": False,
            "requested_mode": "live-draft",
            "live_draft_requested": True,
            "live_draft_confirmed": True,
            "shopify_touched": True,
            "queue_touched": True,
            "transaction_result": {
                "decision": "DRAFT_CREATED_VERIFICATION_PASSED",
                "shopify_article_id": 12345,
            },
            "queue_commit_result": {"decision": "QUEUE_FINALISATION_APPROVED"},
        },
        timestamp="2026-07-21T10:00:00+00:00",
    )

    assert report["mode"] == "live-draft"
    assert report["requested_mode"] == "live-draft"
    assert report["effective_mode"] == "live-draft"
    assert report["dry_run"] is False
    assert report["shopify_touched"] is True
    assert report["queue_touched"] is True
    assert report["transaction_decision"] == "DRAFT_CREATED_VERIFICATION_PASSED"
    assert report["queue_commit_decision"] == "QUEUE_FINALISATION_APPROVED"
    assert report["shopify_article_id"] == 12345


def test_dry_run_takes_precedence_over_live_request():
    report = build_report(
        {
            "blocked": False,
            "dry_run": True,
            "requested_mode": "live-draft",
            "live_draft_requested": True,
            "live_draft_confirmed": True,
            "shopify_touched": False,
            "queue_touched": False,
        },
        timestamp="2026-07-21T10:00:00+00:00",
    )

    assert report["requested_mode"] == "live-draft"
    assert report["effective_mode"] == "dry-run"
    assert report["dry_run"] is True


def test_no_job_report_has_no_write_claims():
    report = build_report(
        {
            "blocked": False,
            "dry_run": False,
            "requested_mode": "live-draft",
            "live_draft_requested": True,
            "live_draft_confirmed": True,
            "planner_decision": "no_job_due",
            "selected_job": None,
            "shopify_touched": False,
            "queue_touched": False,
            "stop_reason": "No planned job is due.",
        },
        timestamp="2026-07-21T10:00:00+00:00",
    )

    assert report["effective_mode"] == "live-draft"
    assert report["planner_decision"] == "no_job_due"
    assert report["selected_job"] is None
    assert report["shopify_touched"] is False
    assert report["queue_touched"] is False
    assert report["next_action"] == "No planned job is due."
