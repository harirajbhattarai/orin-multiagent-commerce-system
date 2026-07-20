#!/usr/bin/env python3
"""
ORIN Planner Agent — Phase 1B
Job selection logic for Hoverboard Store content queue.

Reads:
  - Queue file (via state_agent.read_queue)
  - Shopify inventory (via state_agent.read_shopify_inventory)
  - Approved handles (via state_agent.read_approved_handles)
  - Local draft filesystem

Produces:
  - planner_decision dict
  - NO writes to queue, Shopify, or production state files
"""

import sys
from pathlib import Path
from datetime import date, timedelta

# Import state_agent functions for shared reads
sys.path.insert(0, str(Path(__file__).parent))
from state_agent import (
    read_queue,
    read_shopify_inventory,
    read_approved_handles,
    local_file_for_job,
    resolve_shopify_article,
    detect_state,
    days_until,
    today,
    BASE_DIR,
)


def get_all_job_states():
    """Build full state for all jobs in queue using State Agent logic."""
    queue = read_queue()
    shopify_inv = read_shopify_inventory()
    approved = read_approved_handles()

    states = {}
    for num, job in queue.items():
        local_exists, local_path = local_file_for_job(job)
        shopify_info = resolve_shopify_article(job, shopify_inv, approved)
        local_info = {"exists": local_exists, "path": local_path}
        state_name, issues, action = detect_state(job, shopify_info, local_info, approved)
        states[num] = {
            **job,
            "shopify_article_id": shopify_info["shopify_article_id"],
            "shopify_handle": shopify_info["shopify_handle"],
            "shopify_status": shopify_info["shopify_status"],
            "published_at": shopify_info["published_at"],
            "local_draft_exists": local_exists,
            "local_file_path": local_path,
            "detected_state": state_name,
            "issues": issues,
            "recommended_action": action,
        }
    return states


def is_blocking(issues: list) -> bool:
    """Return True if any issue is medium or high severity."""
    return any(i.get("severity") in ("medium", "high") for i in issues)


def is_due(job_state: dict) -> bool:
    """Return True if expected_draft_date <= today."""
    dd = job_state.get("expected_draft_date")
    if not dd:
        return False
    return days_until(dd) <= 0


def select_next_job(all_states: dict) -> dict:
    """
    Select the lowest-numbered planned job that:
      - is due (expected_draft_date <= today)
      - has no blocking issues
    Returns dict with decision metadata.
    """
    planned_candidates = []
    skipped = []

    for num, state in sorted(all_states.items(), key=lambda x: int(x[0])):
        queue_status = state.get("queue_status", "")
        issues = state.get("issues", [])
        state_name = state.get("detected_state", "")
        due = is_due(state)
        blocking = is_blocking(issues)

        if queue_status != "planned":
            skipped.append({
                "job_number": num,
                "topic": state.get("topic"),
                "reason": f"queue_status={queue_status}",
                "detected_state": state_name,
                "blocking": False,
            })
            continue

        if blocking:
            skipped.append({
                "job_number": num,
                "topic": state.get("topic"),
                "reason": f"blocking_issues={[i['type'] for i in issues if i.get('severity') in ('medium','high')]}",
                "detected_state": state_name,
                "blocking": True,
            })
            continue

        if not due:
            skipped.append({
                "job_number": num,
                "topic": state.get("topic"),
                "reason": f"not_due (draft due: {state.get('expected_draft_date')}, days_until: {days_until(state.get('expected_draft_date'))})",
                "detected_state": state_name,
                "blocking": False,
            })
            continue

        # Candidate
        planned_candidates.append((int(num), state))

    if not planned_candidates:
        # Find next due job for reporting
        future_due = []
        for num, state in sorted(all_states.items(), key=lambda x: int(x[0])):
            if state.get("queue_status") == "planned" and not is_blocking(state.get("issues", [])):
                dd = state.get("expected_draft_date")
                if dd:
                    future_due.append((num, state, dd))
        if future_due:
            future_due.sort(key=lambda x: x[2])
            next_num, next_state, next_dd = future_due[0]
            return {
                "planner_decision": "no_job_due",
                "selected_job_number": None,
                "selected_topic": None,
                "reason": "No planned job is due. All candidates are either not yet due or have blocking issues.",
                "next_due_job": f"Job {next_num}",
                "next_due_date": next_dd,
                "days_until_next_due": days_until(next_dd),
                "skipped_jobs": skipped,
                "blocking_issues_count": len([s for s in skipped if s["blocking"]]),
                "safe_to_continue": False,
                "all_states": all_states,
            }

        return {
            "planner_decision": "no_job_due",
            "selected_job_number": None,
            "selected_topic": None,
            "reason": "No planned jobs found in queue.",
            "next_due_job": None,
            "next_due_date": None,
            "days_until_next_due": None,
            "skipped_jobs": skipped,
            "blocking_issues_count": len([s for s in skipped if s["blocking"]]),
            "safe_to_continue": False,
            "all_states": all_states,
        }

    # Select lowest numbered due job
    planned_candidates.sort(key=lambda x: x[0])
    selected_num, selected_state = planned_candidates[0]

    return {
        "planner_decision": "job_selected",
        "selected_job_number": selected_num,
        "selected_topic": selected_state.get("topic"),
        "reason": f"Job {selected_num} is planned, due (expected_draft_date={selected_state.get('expected_draft_date')}), and has no blocking issues.",
        "next_due_job": f"Job {selected_num}",
        "next_due_date": selected_state.get("expected_draft_date"),
        "days_until_next_due": days_until(selected_state.get("expected_draft_date")),
        "skipped_jobs": skipped,
        "blocking_issues_count": len([s for s in skipped if s["blocking"]]),
        "safe_to_continue": True,
        "all_states": all_states,
    }
