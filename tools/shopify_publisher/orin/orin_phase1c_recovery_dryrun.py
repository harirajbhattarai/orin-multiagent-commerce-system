#!/usr/bin/env python3
"""
ORIN Phase 1C — Recovery Agent Dry-Run

STRICT READ-ONLY: No writes to production files.
Output goes to /tmp only.

Usage:
  python3 tools/shopify_publisher/orin/orin_phase1c_recovery_dryrun.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from business_time import get_business_today_from_args
from recovery_agent import run_recovery_audit, today, detect_cron_loops, read_cron_runs
from state_agent import today as state_today

REPORT_PATH = Path("/tmp/orin_phase1c_recovery_preview.json")


def fmt_table(items, columns):
    """Simple text table formatter."""
    col_widths = {c: max(len(str(row.get(c, ""))) for row in items) for c in columns}
    header = "  ".join(c.ljust(col_widths[c]) for c in columns)
    divider = "  ".join("-" * col_widths[c] for c in columns)
    rows = []
    for item in items:
        rows.append("  ".join(str(item.get(c, "")).ljust(col_widths[c]) for c in columns))
    return header + "\n" + divider + "\n" + "\n".join(rows)


def main():
    biz_today = get_business_today_from_args(sys.argv[1:])
    print("=" * 70)
    print("ORIN Phase 1C — Recovery Agent Dry-Run")
    print(f"Run date: {biz_today}")
    print("Mode: READ-ONLY (no production writes)")
    print("=" * 70)
    print()

    # Run audit for Jobs 15–20 only
    result = run_recovery_audit(job_numbers=[str(i) for i in range(15, 21)])

    # Write preview JSON
    REPORT_PATH.write_text(json.dumps({
        "meta": result["meta"],
        "cron_loops_detected": result["cron_loops_detected"],
        "active_recovery_items": [
            {k: v for k, v in item.items() if k != "issues"}
            for item in result["active_recovery_items"]
        ],
        "historical_resolved_items": [
            {k: v for k, v in item.items() if k != "issues"}
            for item in result["historical_resolved_items"]
        ],
        "no_action_needed_items": [
            {k: v for k, v in item.items() if k != "issues"}
            for item in result["no_action_needed_items"]
        ],
    }, indent=2))
    print(f"Recovery preview written to: {REPORT_PATH}")
    print()

    # ── Summary ─────────────────────────────────────────────────────────────
    m = result["meta"]
    print("## Summary")
    print()
    print(f"  Jobs audited:       {m['jobs_audited']}")
    print(f"  Active recovery:   {m['active_count']}")
    print(f"  Historical/resolved: {m['historical_count']}")
    print(f"  No action needed:  {m['no_action_count']}")
    print()

    # ── Active recovery items ───────────────────────────────────────────────
    print("## Active Recovery Items")
    print()
    active = result["active_recovery_items"]
    if active:
        for item in active:
            cats = ", ".join(item["recovery_categories"])
            print(f"  Job {item['job_number']} — {item['topic'][:50]}")
            print(f"    Categories: {cats}")
            print(f"    Queue: {item['queue_status']} | Shopify: {item['shopify_handle'] or 'none'} | Local: {'yes' if item['local_draft_exists'] else 'no'}")
            print(f"    Dry-run action: {item['dry_run_action']}")
            print()
    else:
        print("  None")
        print()

    # ── Historical resolved items ───────────────────────────────────────────
    print("## Historical / Resolved Items")
    print()
    hist = result["historical_resolved_items"]
    if hist:
        for item in hist:
            cats = ", ".join(item["recovery_categories"])
            print(f"  Job {item['job_number']} — {item['topic'][:50]}")
            print(f"    Was: {cats}")
            print(f"    Now: clean_draft_created — queue and Shopify are reconciled")
            print()
    else:
        print("  None")
        print()

    # ── No action needed ───────────────────────────────────────────────────
    print("## No Action Needed")
    print()
    no_act = result["no_action_needed_items"]
    if no_act:
        for item in no_act:
            print(
                f"  Job {item['job_number']} | "
                f"queue={item['queue_status']} | "
                f"state={item['detected_state']} | "
                f"action={item['dry_run_action']}"
            )
        print()
    else:
        print("  None")
        print()

    # ── Cron loops ─────────────────────────────────────────────────────────
    print("## Cron Loop Detection")
    print()
    loops = result["cron_loops_detected"]
    if loops:
        for job, info in loops.items():
            print(f"  Job {job}: {info['count']} consecutive 'file already exists' runs — LOOP DETECTED")
        print()
    else:
        print("  No cron loops detected")
        print()

    # ── Phase 1D readiness ─────────────────────────────────────────────────
    print("## Phase 1D Readiness")
    print()
    if result["active_recovery_items"]:
        print(f"  [FAIL] {len(result['active_recovery_items'])} active recovery item(s) found")
        print(f"         Resolve active recovery items before Phase 1D")
        for item in result["active_recovery_items"]:
            print(f"           Job {item['job_number']}: {item['recovery_categories']}")
    else:
        print(f"  [PASS] No active recovery needed")
        print(f"         Safe to proceed to Phase 1D Reporter Agent")

    print()
    print(f"Recovery preview file: {REPORT_PATH}")
    print("Dry-run complete — no production files modified.")


if __name__ == "__main__":
    main()
