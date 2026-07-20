#!/usr/bin/env python3
"""
ORIN Phase 1B — Planner Agent Dry-Run

STRICT READ-ONLY: No writes to production files.
Output goes to /tmp only.

Usage:
  python3 tools/shopify_publisher/orin/orin_phase1b_planner_dryrun.py
  python3 tools/shopify_publisher/orin/orin_phase1b_planner_dryrun.py --as-of-date 2026-07-04
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from business_time import get_business_today_from_args
from planner_agent import select_next_job, get_all_job_states, days_until
from state_agent import today

REPORT_PATH = Path("/tmp/orin_phase1b_planner_preview.json")


def main():
    # Resolve business date (supports --as-of-date override)
    biz_today = get_business_today_from_args(sys.argv[1:])

    print("=" * 70)
    print("ORIN Phase 1B — Planner Agent Dry-Run")
    print(f"Run date: {biz_today}")
    print("Mode: READ-ONLY (no production writes)")
    print("=" * 70)
    print()

    # Build all job states using State Agent
    all_states = get_all_job_states()
    decision = select_next_job(all_states)

    # Build clean serialisable decision (all_states becomes summary)
    clean_decision = {k: v for k, v in decision.items() if k != "all_states"}
    clean_decision["all_jobs_summary"] = {
        num: {
            "queue_status": s.get("queue_status"),
            "detected_state": s.get("detected_state"),
            "expected_draft_date": s.get("expected_draft_date"),
            "days_until_draft": (
                days_until(s.get("expected_draft_date"))
                if s.get("expected_draft_date") else None
            ),
            "blocking_issues": [
                i["type"] for i in s.get("issues", [])
                if i.get("severity") in ("medium", "high")
            ],
            "recommended_action": s.get("recommended_action"),
        }
        for num, s in sorted(all_states.items(), key=lambda x: int(x[0]))
    }

    REPORT_PATH.write_text(json.dumps({
        "meta": {
            "phase": "1B",
            "mode": "dry-run",
            "run_date": str(biz_today),
            "business_date_resolved": str(biz_today),
            "note": "Preview only — not production job_state.json"
        },
        "planner": clean_decision,
    }, indent=2))
    print(f"Planner preview written to: {REPORT_PATH}")
    print()

    # ── Planner decision ────────────────────────────────────────────────────
    print("## Planner Decision")
    print()
    print(f"  Decision:       {decision['planner_decision']}")
    print(f"  Selected job:   {decision.get('selected_job_number') or 'none'}")
    print(f"  Topic:         {decision.get('selected_topic') or '—'}")
    print(f"  Reason:        {decision['reason']}")
    print()

    # ── Next due ────────────────────────────────────────────────────────────
    if decision.get("next_due_job"):
        print("## Next Due Job")
        print()
        print(f"  Job:           {decision['next_due_job']}")
        print(f"  Date:          {decision['next_due_date']}")
        print(f"  Days until:    {decision['days_until_next_due']}")
        print()

    # ── Skipped jobs ────────────────────────────────────────────────────────
    skipped = decision.get("skipped_jobs", [])
    print("## Skipped Jobs")
    print()
    if skipped:
        for s in skipped:
            tag = "BLOCKING" if s["blocking"] else "not due / not planned"
            topic_short = (s["topic"] or "?")[:50]
            print(f"  Job {s['job_number']} [{tag}]: {topic_short}")
            print(f"    Reason: {s['reason']}")
        print()
    else:
        print("  None")
        print()

    # ── Blocking issues ─────────────────────────────────────────────────────
    blocking_count = decision.get("blocking_issues_count", 0)
    print(f"Blocking issues count: {blocking_count}")
    print()

    # ── Phase 1C readiness ─────────────────────────────────────────────────
    print("## Phase 1C Readiness")
    print()
    if decision["safe_to_continue"]:
        print(f"  [PASS] Planner selected Job {decision['selected_job_number']}")
        print(f"         Safe to proceed to Phase 1C Recovery Agent")
    else:
        if blocking_count == 0:
            print(f"  [PASS] No job due but no blocking issues")
            print(f"         Safe to proceed to Phase 1C Recovery Agent")
            print(f"         Recovery Agent will audit stuck states and reconcile queue")
            print(f"         even with no new work queued.")
        else:
            print(f"  [FAIL] Blocking issues remain: {blocking_count}")
            print(f"         Resolve blocking issues before Phase 1C")

    print()
    print(f"Planner preview file: {REPORT_PATH}")
    print("Dry-run complete — no production files modified.")


if __name__ == "__main__":
    main()
