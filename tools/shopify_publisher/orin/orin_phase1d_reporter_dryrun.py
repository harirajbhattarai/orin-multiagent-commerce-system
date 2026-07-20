#!/usr/bin/env python3
"""
ORIN Phase 1D — Reporter Agent Dry-Run

STRICT READ-ONLY: No writes to production files.
Output goes to /tmp only.

Usage:
  python3 tools/shopify_publisher/orin/orin_phase1d_reporter_dryrun.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from reporter_agent import build_report
from state_agent import today as get_today

REPORT_PATH = Path("/tmp/orin_phase1d_report_preview.json")


def main():
    print("=" * 70)
    print("ORIN Phase 1D — Reporter Agent Dry-Run")
    print(f"Run date: {get_today()}")
    print("Mode: READ-ONLY (no production writes)")
    print("=" * 70)
    print()

    # Build report for Jobs 15-20
    report = build_report(job_numbers=[str(i) for i in range(15, 21)])

    # Write preview JSON
    REPORT_PATH.write_text(json.dumps({
        "meta": {
            "phase": "1D",
            "mode": "dry-run",
            "run_date": report["report_date"],
            "note": "Preview only — not production orin_status.md"
        },
        **report,
    }, indent=2))
    print(f"Report preview written to: {REPORT_PATH}")
    print()

    # ── Headline ────────────────────────────────────────────────────────────
    print("## ORIN Headline Status")
    print()
    print(f"  Status:  {report['headline']['status']}")
    print(f"  Reason:  {report['headline']['reason']}")
    print()

    # ── Client / date ───────────────────────────────────────────────────────
    print(f"  Client:  {report['client']}")
    print(f"  Date:    {report['report_date']}")
    print()

    # ── Job table ───────────────────────────────────────────────────────────
    print("## Job Table: Jobs 15–20")
    print()
    header = (
        f"  {'Job':<6} {'Queue':<18} {'State':<30} {'Draft Due':<12} "
        f"{'Shopify ID':<16} {'Local':<6} {'Blk':<4} {'Info Notes'}"
    )
    print(header)
    print("  " + "-" * 90)
    for row in report["jobs"]:
        state = row["detected_state"][:28]
        draft = f"{row['expected_draft_date']} ({row['days_until_draft']}d)" if row["expected_draft_date"] else "—"
        sid = row["shopify_article_id"] or "—"
        sid_short = sid[-8:] if sid else "—"
        local = "yes" if row["local_draft_exists"] else "no"
        blk = str(len(row["blocking_issues"]))
        info = "; ".join(row["info_notes"]) if row["info_notes"] else "—"
        print(
            f"  Job {row['job_number']:<3} "
            f"{row['queue_status']:<18} "
            f"{state:<30} "
            f"{draft:<12} "
            f"{sid_short:<16} "
            f"{local:<6} "
            f"{blk:<4} "
            f"{info}"
        )
    print()

    # ── Planner summary ─────────────────────────────────────────────────────
    print("## Planner Summary")
    print()
    p = report["planner"]
    print(f"  Decision:          {p['planner_decision']}")
    print(f"  Selected job:     {p['selected_job'] or 'none'}")
    print(f"  Next due job:     {p['next_due_job'] or 'none'}")
    print(f"  Next due date:    {p['next_due_date'] or '?'}")
    print(f"  Days until:       {p['days_until_next_due']}")
    print(f"  Reason:           {p['reason']}")
    print()

    # ── Recovery summary ────────────────────────────────────────────────────
    print("## Recovery Summary")
    print()
    r = report["recovery"]
    print(f"  Active recovery items:   {r['active_recovery_items_count']}")
    print(f"  Historical resolved:      {r['historical_resolved_items_count']}")
    print(f"  No action needed:        {r['no_action_count']}")
    print(f"  Cron loop detected:       {'YES' if r['cron_loop_detected'] else 'no'}")
    print(f"  Stale in_progress:        {'YES' if r['stale_in_progress'] else 'no'}")
    print()

    # ── Handle protection ───────────────────────────────────────────────────
    print("## Handle Protection Summary")
    print()
    h = report["handle_protection"]
    print(f"  Approved handles loaded:    {'yes' if h['approved_handles_loaded'] else 'no'}")
    print(f"  Total approved handles:      {h['total_approved_handles']}")
    print(f"  Any handle conflict:         {'YES' if h['any_handle_conflict'] else 'no'}")
    print(f"  Any unresolved mismatch:     {'YES' if h['any_unresolved_mismatch'] else 'no'}")
    print()

    # ── Blocking issues ─────────────────────────────────────────────────────
    print(f"Blocking issues count: {report['blocking_issues_count']}")
    print()

    # ── Next safe action ────────────────────────────────────────────────────
    print("## Next Safe Action")
    print()
    print(f"  {report['next_safe_action']}")
    print()

    # ── Phase readiness ─────────────────────────────────────────────────────
    print("## Phase Readiness")
    print()
    pr = report["phase_readiness"]
    phases = [
        ("Phase 1A State Agent", pr["phase_1a_state_agent"]),
        ("Phase 1B Planner", pr["phase_1b_planner"]),
        ("Phase 1C Recovery", pr["phase_1c_recovery"]),
        ("Phase 1D Reporter", pr["phase_1d_reporter"]),
        ("Safe for Phase 1E Orchestrator Wrapper", pr["safe_for_phase_1e"]),
    ]
    all_passed = True
    for label, passed in phases:
        icon = "PASS" if passed else "FAIL"
        if not passed:
            all_passed = False
        print(f"  [{icon}] {label}")
    print()

    # ── Phase 1E readiness ──────────────────────────────────────────────────
    print("## Phase 1E Readiness")
    print()
    if pr["safe_for_phase_1e"]:
        print("  [PASS] Safe to proceed to Phase 1E Orchestrator Wrapper dry-run")
    else:
        print("  [FAIL] Not yet safe — resolve issues above first")
    print()

    print(f"Report preview file: {REPORT_PATH}")
    print("Dry-run complete — no production files modified.")


if __name__ == "__main__":
    main()
