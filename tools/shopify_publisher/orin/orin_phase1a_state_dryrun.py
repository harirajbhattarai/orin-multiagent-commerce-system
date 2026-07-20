#!/usr/bin/env python3
"""
ORIN Phase 1A — State Agent Dry-Run

STRICT READ-ONLY: No writes to production files.
Output goes to /tmp only.

Usage:
  python3 tools/shopify_publisher/orin/orin_phase1a_state_dryrun.py
  python3 tools/shopify_publisher/orin/orin_phase1a_state_dryrun.py --as-of-date 2026-07-04
"""

import json
import sys
from pathlib import Path

# Add tools dir to path so we can import state_agent
sys.path.insert(0, str(Path(__file__).parent))

from business_time import get_business_today_from_args

from state_agent import (
    build_job_states,
    to_markdown_table,
    BASE_DIR,
    CLIENT_DIR,
    today,
)

REPORT_PATH = Path("/tmp/orin_phase1a_job_state_preview.json")

def main():
    # Resolve business date (supports --as-of-date override)
    biz_today = get_business_today_from_args(sys.argv[1:])

    print("=" * 70)
    print("ORIN Phase 1A — State Agent Dry-Run")
    print(f"Run date: {biz_today}")
    print("Mode: READ-ONLY (no production writes)")
    print("=" * 70)
    print()

    # Jobs to audit
    job_numbers = [str(i) for i in range(15, 21)]

    print(f"Auditing Jobs: {', '.join(job_numbers)}")
    print()

    # Build state
    states = build_job_states(job_numbers)

    # Write preview JSON to /tmp
    REPORT_PATH.write_text(json.dumps({
        "meta": {
            "phase": "1A",
            "mode": "dry-run",
            "run_date": str(biz_today),
            "business_date_resolved": str(biz_today),
            "jobs_audited": job_numbers,
            "note": "Preview only — not production job_state.json"
        },
        "jobs": states
    }, indent=2))
    print(f"Preview state written to: {REPORT_PATH}")
    print()

    # Print markdown table
    print("## State Table: Jobs 15–20")
    print()
    print(to_markdown_table(states))
    print()

    # Summary
    clean = [s for s in states if s["detected_state"] == "clean_draft_created" and not s["issues_found"]]
    issues_list = [s for s in states if s["issues_found"]]
    waiting = [s for s in states if "waiting" in s["detected_state"]]
    due_now = [s for s in states if s["detected_state"] == "due_for_local_draft"]
    needs_push = [s for s in states if s["detected_state"] == "needs_shopify_push"]
    reconcile = [s for s in states if s["detected_state"] == "queue_needs_reconciliation"]

    print("## Summary")
    print()
    print(f"  Total jobs audited:    {len(states)}")
    print(f"  Clean draft_created:   {len(clean)}")
    print(f"  With issues:           {len(issues_list)}")
    print(f"  Waiting (not due):     {len(waiting)}")
    print(f"  Due now (local draft): {len(due_now)}")
    print(f"  Needs Shopify push:    {len(needs_push)}")
    print(f"  Queue needs recon:     {len(reconcile)}")
    print()

    if issues_list:
        print("## Issues Detail")
        print()
        for s in issues_list:
            print(f"  Job {s['job_number']} — {s['topic'][:50]}")
            for issue in s["issues_found"]:
                print(f"    [{issue['severity']}] {issue['type']}: {issue['detail']}")
            print()

    # Job 20 specific check
    job20 = next((s for s in states if s["job_number"] == "20"), None)
    if job20:
        print("## Job 20 Check")
        print()
        print(f"  Detected state: {job20['detected_state']}")
        print(f"  Expected draft date: {job20['expected_draft_date']}")
        print(f"  Days until draft: {job20['days_until_draft']}")
        print(f"  Due now: {'YES' if job20['detected_state'] == 'due_for_local_draft' else 'NO — wait'}")
        print()

    # Phase 1B readiness — only hard/medium issues block progression
    print("## Phase 1B Readiness")
    print()
    blocking_issues = [
        s for s in issues_list
        if any(i["severity"] in ("high", "medium") for i in s["issues_found"])
    ]
    if not blocking_issues and not due_now and not needs_push and not reconcile:
        print("  ✅ All audited jobs are clean or waiting — safe to proceed to Phase 1B Planner Agent")
    else:
        print("  ⚠️  Blocking issues found — resolve before Phase 1B:")
        if blocking_issues:
            for s in blocking_issues:
                for i in s["issues_found"]:
                    if i["severity"] in ("high", "medium"):
                        print(f"     Job {s['job_number']}: [{i['severity']}] {i['type']}")
        if needs_push:
            print(f"     Jobs needing Shopify push: {[s['job_number'] for s in needs_push]}")
        if reconcile:
            print(f"     Jobs needing queue reconciliation: {[s['job_number'] for s in reconcile]}")

    print()
    print(f"Preview state file: {REPORT_PATH}")
    print("Dry-run complete — no production files modified.")

if __name__ == "__main__":
    main()
