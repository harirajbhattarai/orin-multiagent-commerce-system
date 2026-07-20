#!/usr/bin/env python3
"""
ORIN Orchestrator — Phase 1E
Single wrapper that runs all agent dry-runs in order.

Agents called (in order):
  1. State Agent   (Phase 1A)
  2. Planner Agent (Phase 1B)
  3. Recovery Agent (Phase 1C)
  4. Reporter Agent (Phase 1D)

Produces:
  - Combined orchestrator decision dict
  - NO writes to Shopify, queue, or production state files
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from state_agent import today as get_today, days_until
from planner_agent import get_all_job_states, select_next_job
from recovery_agent import run_recovery_audit
from reporter_agent import build_report


def run_orchestrator(job_numbers=None):
    """
    Run all agents in sequence and return the orchestrator decision.
    """
    if job_numbers is None:
        job_numbers = [str(i) for i in range(15, 21)]

    today = get_today()

    # ── 1. State Agent ────────────────────────────────────────────────────
    all_states = get_all_job_states()
    states_15_20 = {n: s for n, s in all_states.items() if n in job_numbers}

    # ── 2. Planner Agent ──────────────────────────────────────────────────
    planner_decision = select_next_job(all_states)

    # ── 3. Recovery Agent ─────────────────────────────────────────────────
    recovery_result = run_recovery_audit(job_numbers=job_numbers)

    # ── 4. Reporter Agent ─────────────────────────────────────────────────
    full_report = build_report(job_numbers=job_numbers)

    # ── Orchestrator final decision ────────────────────────────────────────
    blocking_count = full_report["blocking_issues_count"]
    recovery_active = recovery_result["meta"]["active_count"]

    if planner_decision["planner_decision"] == "job_selected":
        orchestrator_status = "ACTIVE"
        safe_to_continue = True
    elif blocking_count == 0 and recovery_active == 0:
        orchestrator_status = "HEALTHY_WAITING"
        safe_to_continue = True
    elif recovery_active > 0:
        orchestrator_status = "RECOVERY_NEEDED"
        safe_to_continue = False
    else:
        orchestrator_status = "BLOCKED"
        safe_to_continue = False

    if orchestrator_status == "ACTIVE":
        recommended = (
            f"Proceed with Job {planner_decision['selected_job_number']}: "
            f"{planner_decision['selected_topic']}. "
            f"Run Writer Agent then Review Agent, then Publisher Agent. "
            f"Confirm all checks pass before Shopify push."
        )
    elif orchestrator_status == "RECOVERY_NEEDED":
        recommended = (
            f"{recovery_active} active recovery item(s) found. "
            f"Resolve before new work. Do not start Job 20 today."
        )
    elif orchestrator_status == "BLOCKED":
        recommended = (
            f"{blocking_count} blocking issue(s). "
            f"Resolve before continuing."
        )
    else:
        recommended = (
            f"Wait until Job 20 draft due date 2026-07-01. "
            f"All tracked jobs (15–19) are clean. "
            f"Manually trigger only after approval. Do not start Job 20 today."
        )

    return {
        "client": "hoverboard_store",
        "mode": "dry-run",
        "current_date": str(today),
        "health_status": orchestrator_status,
        "planner_decision": planner_decision["planner_decision"],
        "selected_job": planner_decision.get("selected_job_number"),
        "selected_topic": planner_decision.get("selected_topic"),
        "next_due_job": planner_decision.get("next_due_job"),
        "next_due_date": planner_decision.get("next_due_date"),
        "days_until_next_due": planner_decision.get("days_until_next_due"),
        "blocking_issues_count": blocking_count,
        "active_recovery_items_count": recovery_active,
        "historical_resolved_count": recovery_result["meta"]["historical_count"],
        "no_action_count": recovery_result["meta"]["no_action_count"],
        "safe_to_continue": safe_to_continue,
        "recommended_next_action": recommended,
        # Full agent outputs for reference
        "_states": states_15_20,
        "_planner_decision": planner_decision,
        "_recovery_result": recovery_result,
        "_full_report": full_report,
    }
