#!/usr/bin/env python3
"""
ORIN Reporter Agent — Phase 1D
Consolidated reporting from all ORIN agents.

Reads:
  - state_agent (Phase 1A)
  - planner_agent (Phase 1B)
  - recovery_agent (Phase 1C)

Produces:
  - Consolidated report dict
  - Markdown report files
  - NO writes to Shopify or queue
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from state_agent import today as get_today, days_until
from planner_agent import get_all_job_states, select_next_job
from recovery_agent import run_recovery_audit


def build_report(job_numbers=None):
    """Build full ORIN status report."""
    if job_numbers is None:
        job_numbers = [str(i) for i in range(15, 21)]

    today = get_today()

    # ── Phase 1A: State ─────────────────────────────────────────────────────
    all_states = get_all_job_states()
    states_15_20 = {n: s for n, s in all_states.items() if n in job_numbers}

    # ── Phase 1B: Planner ───────────────────────────────────────────────────
    decision = select_next_job(all_states)

    # ── Phase 1C: Recovery ─────────────────────────────────────────────────
    recovery = run_recovery_audit(job_numbers=job_numbers)

    # ── Headline status ─────────────────────────────────────────────────────
    if decision["planner_decision"] == "job_selected":
        headline_status = "ACTIVE"
        headline_reason = (
            f"Job {decision['selected_job_number']} is due: "
            f"{decision['selected_topic']}. "
            f"Target date: {decision.get('next_due_date', '?')}."
        )
    elif decision["safe_to_continue"] is False and decision["blocking_issues_count"] > 0:
        headline_status = "BLOCKED"
        headline_reason = (
            f"{decision['blocking_issues_count']} blocking issue(s) found. "
            f"Resolve before continuing."
        )
    else:
        next_job = decision.get("next_due_job", "none")
        next_date = decision.get("next_due_date", "?")
        headline_status = "WAITING"
        headline_reason = (
            f"No job due. {next_job} due on {next_date}. "
            f"All tracked jobs are clean or not yet due."
        )

    # ── Handle protection summary ────────────────────────────────────────────
    from state_agent import read_approved_handles
    approved = read_approved_handles()
    from planner_agent import is_blocking

    handle_conflicts = []
    unresolved_mismatches = []
    for num, state in states_15_20.items():
        issues = state.get("issues", [])
        for issue in issues:
            t = issue.get("type", "")
            sev = issue.get("severity", "")
            if t == "approved_handle_conflicts_with_shopify_handle":
                handle_conflicts.append({"job": num, "issue": issue})
            elif t == "handle_mismatch_requires_decision" and sev in ("medium", "high"):
                unresolved_mismatches.append({"job": num, "issue": issue})

    # ── Job table ──────────────────────────────────────────────────────────
    job_rows = []
    for num in job_numbers:
        if num not in states_15_20:
            continue
        s = states_15_20[num]
        issues = s.get("issues", [])
        blocking = [i for i in issues if i.get("severity") in ("medium", "high")]
        info_notes = [i for i in issues if i.get("severity") == "info"]

        row = {
            "job_number": num,
            "topic": s.get("topic"),
            "queue_status": s.get("queue_status"),
            "detected_state": s.get("detected_state"),
            "target_date": s.get("target_date"),
            "expected_draft_date": s.get("expected_draft_date"),
            "days_until_draft": days_until(s.get("expected_draft_date")) if s.get("expected_draft_date") else None,
            "shopify_article_id": s.get("shopify_article_id"),
            "shopify_handle": s.get("shopify_handle"),
            "shopify_status": s.get("shopify_status"),
            "published_at": s.get("published_at"),
            "local_draft_exists": s.get("local_draft_exists"),
            "approved_handle": approved.get(num, {}).get("handle"),
            "blocking_issues": [i["type"] for i in blocking],
            "info_notes": [i["type"] for i in info_notes],
            "recommended_action": s.get("recommended_action"),
        }
        job_rows.append(row)

    # ── Phase readiness ────────────────────────────────────────────────────
    blocking_total = sum(
        1 for s in states_15_20.values()
        if is_blocking(s.get("issues", []))
    )
    recovery_active = recovery["meta"]["active_count"]
    phase_readiness = {
        "phase_1a_state_agent": True,   # always passes if this runs
        "phase_1b_planner": True,        # always passes if this runs
        "phase_1c_recovery": True,       # always passes if this runs
        "phase_1d_reporter": True,        # this is it
        "safe_for_phase_1e": (
            blocking_total == 0
            and recovery_active == 0
            and decision["planner_decision"] in ("no_job_due", "job_selected")
        ),
    }

    # ── Next safe action ────────────────────────────────────────────────────
    if decision["planner_decision"] == "job_selected":
        next_action = (
            f"Proceed with Job {decision['selected_job_number']}: "
            f"{decision['selected_topic']}. "
            f"Run Writer Agent then Review Agent, then Publisher Agent. "
            f"Confirm all checks pass before Shopify push."
        )
    elif recovery_active > 0:
        next_action = (
            f"Resolve {recovery_active} active recovery item(s) before new work. "
            f"Run Recovery Agent in live mode after approval."
        )
    elif blocking_total > 0:
        next_action = (
            f"Resolve {blocking_total} blocking issue(s) before new work. "
            f"Review handle conflicts or recovery items."
        )
    else:
        next_action = (
            f"Wait until Job 20 draft due date 2026-07-01. "
            f"All tracked jobs (15–19) are clean. "
            f"Manually trigger only after approval. Do not start Job 20 today."
        )

    return {
        "headline": {
            "status": headline_status,
            "reason": headline_reason,
        },
        "client": "hoverboard_store",
        "report_date": str(today),
        "jobs": job_rows,
        "planner": {
            "planner_decision": decision["planner_decision"],
            "selected_job": decision.get("selected_job_number"),
            "selected_topic": decision.get("selected_topic"),
            "next_due_job": decision.get("next_due_job"),
            "next_due_date": decision.get("next_due_date"),
            "days_until_next_due": decision.get("days_until_next_due"),
            "reason": decision["reason"],
            "skipped_count": len(decision.get("skipped_jobs", [])),
        },
        "recovery": {
            "active_recovery_items_count": recovery["meta"]["active_count"],
            "historical_resolved_items_count": recovery["meta"]["historical_count"],
            "no_action_count": recovery["meta"]["no_action_count"],
            "cron_loop_detected": bool(recovery["cron_loops_detected"]),
            "stale_in_progress": any(
                "stale_in_progress" in item.get("recovery_categories", [])
                for item in recovery.get("active_recovery_items", [])
            ),
        },
        "handle_protection": {
            "approved_handles_loaded": bool(approved),
            "total_approved_handles": len(approved),
            "any_handle_conflict": bool(handle_conflicts),
            "any_unresolved_mismatch": bool(unresolved_mismatches),
            "conflicts": handle_conflicts,
            "unresolved_mismatches": unresolved_mismatches,
        },
        "blocking_issues_count": blocking_total,
        "phase_readiness": phase_readiness,
        "next_safe_action": next_action,
    }
