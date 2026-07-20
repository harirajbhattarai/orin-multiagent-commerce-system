#!/usr/bin/env python3
"""
ORIN Phase 2B — Duplicate Decision Memory Dry-Run

STRICT READ-ONLY: No writes to production duplicate_decisions.json.
Output goes to /tmp only.

Usage:
  python3 tools/shopify_publisher/orin/orin_phase2b_duplicate_memory_dryrun.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from business_time import get_business_today_from_args
from duplicate_decision_agent import build_duplicate_memory

PREVIEW_PATH = Path("/tmp/orin_phase2b_duplicate_decisions_preview.json")
JOBS_TO_REVIEW = [str(i) for i in range(15, 21)]  # Jobs 15-20


def main():
    biz_today = get_business_today_from_args(sys.argv[1:])
    print("=" * 70)
    print("ORIN Phase 2B — Duplicate Decision Memory Dry-Run")
    print(f"Run date: {biz_today}")
    print("Mode: READ-ONLY — no production duplicate_decisions.json written")
    print("=" * 70)
    print()

    # ── Build memory ────────────────────────────────────────────────────
    print("Building duplicate decision memory for Jobs 15-20...")
    result = build_duplicate_memory(JOBS_TO_REVIEW)

    # ── Write preview JSON ───────────────────────────────────────────────
    PREVIEW_PATH.write_text(json.dumps(result, indent=2))
    print(f"Preview written to: {PREVIEW_PATH}")
    print()

    # ── Summary ────────────────────────────────────────────────────────
    s = result["summary"]
    print("## Duplicate Decision Memory Summary")
    print()
    print(f"  Total jobs reviewed:    {s['total_jobs']}")
    print(f"  self_match_info:        {s['self_match_info_count']}  (info — not a duplicate approval)")
    print(f"  global_site_warning:     {s['global_site_warning_count']}  (info — not a duplicate approval)")
    print(f"  human_decision_required: {s['human_duplicate_decision_required_count']}  (BLOCKING)")
    print(f"  skipped/blocked:         {s['skipped_or_blocked_count']}")
    print()

    # ── Record table ────────────────────────────────────────────────────
    print("## Duplicate Memory Record Table: Jobs 15-20")
    print()
    header = f"  {'Job':<6} {'Record Type':<35} {'Severity':<10} {'Decision'}"
    print(header)
    print("  " + "-" * 80)
    for rec in result["records"]:
        rt = rec.get("record_type", "?")[:33]
        sev = rec.get("severity", rec.get("decision_status", "?"))[:9]
        num = rec.get("job_number", "?")
        decision = rec.get("decision_status") or rec.get("decided_by") or "pending"
        print(f"  Job {num:<3} {rt:<35} {sev:<10} {decision}")
    print()

    # ── Detailed self-match records ─────────────────────────────────────
    self_match = [r for r in result["records"] if r.get("record_type") == "self_match_info"]
    if self_match:
        print("## self_match_info Records")
        print()
        for r in self_match:
            print(f"  Job {r['job_number']}: {r.get('shopify_handle', '?')}")
            print(f"    Article ID: {r.get('article_id', '?')}")
            print(f"    Local file: {r.get('local_file', '?')}")
            print(f"    Reason: {r.get('reason', '')[:100]}...")
            print()
        print()

    # ── Detailed global warning records ─────────────────────────────────
    global_warn = [r for r in result["records"] if r.get("record_type") == "global_site_warning"]
    if global_warn:
        print("## global_site_warning Records")
        print()
        for r in global_warn:
            print(f"  Job {r['job_number']}: {r.get('topic', '?')}")
            print(f"    Reason: {r.get('reason', '')[:100]}")
            related = r.get("related_risk_log_entries", [])
            if related:
                print(f"    Related risk entries: {len(related)}")
            print()
        print()

    # ── Human decision required records ─────────────────────────────────
    human_req = [r for r in result["records"] if r.get("record_type") == "human_duplicate_decision_required"]
    if human_req:
        print("## HUMAN DECISION REQUIRED — BLOCKING")
        print()
        for r in human_req:
            print(f"  Job {r['job_number']}: {r.get('current_job_title', '?')}")
            print(f"    Conflicting article: {r.get('conflicting_article_title', '?')}")
            print(f"    Conflicting handle:  {r.get('conflicting_article_handle', '?')}")
            print(f"    Similarity: {r.get('similarity_type', '?')} {r.get('similarity_score', '')}")
            print(f"    Reason: {r.get('reason', '')[:120]}")
            print()
        print()
    else:
        print("## HUMAN DECISION REQUIRED")
        print("  None — no blocking duplicate decisions.")
        print()

    # ── Phase 2C readiness ──────────────────────────────────────────────
    print("## Phase 2C Readiness")
    print()
    if s["human_duplicate_decision_required_count"] == 0:
        print("  [PASS] No human duplicate decisions required.")
        print("         Jobs 15-19 are classified as self-match or global warnings.")
        print("         Safe to proceed to Phase 2C (Writer Agent dry-run).")
        print()
        print("  Phase 2B output:")
        print(f"    Preview: {PREVIEW_PATH}")
        print("    Production duplicate_decisions.json: NOT WRITTEN (dry-run)")
    else:
        print("  [FAIL] Human duplicate decisions required before Phase 2C.")
        print(f"         Jobs needing operator input: {[r['job_number'] for r in human_req]}")
        print()
        print("  Phase 2B cannot proceed until operator resolves these.")
        print("  Options: proceed_anyway / rewrite / merge / reject")

    print()
    print(f"Dry-run complete — duplicate_decisions.json NOT written to production.")
    print(f"Preview file: {PREVIEW_PATH}")


if __name__ == "__main__":
    main()
