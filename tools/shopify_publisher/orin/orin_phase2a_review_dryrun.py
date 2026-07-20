#!/usr/bin/env python3
"""
ORIN Phase 2A — Review Agent Dry-Run

STRICT READ-ONLY: No writes to production files.
Runs compliance, HTML quality, and duplicate checks on local drafts.
Output goes to /tmp only.

Usage:
  python3 tools/shopify_publisher/orin/orin_phase2a_review_dryrun.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from business_time import get_business_today_from_args
from review_agent import review_jobs

REPORT_PATH = Path("/tmp/orin_phase2a_review_preview.json")


def main():
    biz_today = get_business_today_from_args(sys.argv[1:])
    print("=" * 70)
    print("ORIN Phase 2A — Review Agent Dry-Run")
    print(f"Run date: {biz_today}")
    print("Mode: READ-ONLY (no production writes)")
    print("Checks: compliance + HTML quality + duplicate")
    print("=" * 70)
    print()

    # Review Jobs 15-20
    print("Reviewing Jobs 15-20...")
    print()

    results = review_jobs([str(i) for i in range(15, 21)])

    # Write preview JSON
    # Strip verbose output fields for clean preview
    clean_results = []
    for r in results:
        clean = {k: v for k, v in r.items()
                 if k not in ("compliance_result", "html_quality_result",
                               "duplicate_script_result")}
        clean_results.append(clean)

    REPORT_PATH.write_text(json.dumps({
        "meta": {
            "phase": "2A",
            "mode": "dry-run",
            "run_date": str(biz_today),
            "note": "Preview only — not production review log"
        },
        "jobs": clean_results,
    }, indent=2))
    print(f"Review preview written to: {REPORT_PATH}")
    print()

    # ── Summary ──────────────────────────────────────────────────────────
    pass_ready = [r for r in results if r["review_decision"] == "pass_ready_for_next_step"]
    blocked_comp = [r for r in results if r["review_decision"] == "blocked_compliance"]
    blocked_html = [r for r in results if r["review_decision"] == "blocked_html_quality"]
    dup_decision = [r for r in results if r["review_decision"] == "needs_human_duplicate_decision"]
    no_file = [r for r in results if r["review_decision"] == "no_local_file_to_review"]
    not_due = [r for r in results if r["review_decision"] == "skipped_not_due"]

    print("## Review Summary")
    print()
    print(f"  Total jobs reviewed:  {len(results)}")
    print(f"  Pass (ready):        {len(pass_ready)}")
    print(f"  Blocked compliance:  {len(blocked_comp)}")
    print(f"  Blocked HTML:        {len(blocked_html)}")
    print(f"  Needs dup decision:  {len(dup_decision)}")
    print(f"  No local file:       {len(no_file)}")
    print(f"  Not due:             {len(not_due)}")
    print()

    # ── Review table ──────────────────────────────────────────────────────
    print("## Review Table: Jobs 15-20")
    print()
    header = f"  {'Job':<6} {'Decision':<30} {'Comp':<6} {'HTML':<6} {'Dup':<6} {'Flag':<5} {'Issues'}"
    print(header)
    print("  " + "-" * 85)
    for r in results:
        comp = r.get("compliance_result", {})
        html = r.get("html_quality_result", {})
        dup = r.get("duplicate_script_result", {})

        comp_s = comp.get("status", "?")[:4] if comp else "N/A"
        html_s = html.get("status", "?")[:4] if html else "N/A"
        dup_s = dup.get("status", "?")[:4] if dup else "N/A"

        flag = "YES" if r["current_job_duplicate_flagged"] else "no"
        decision = r["review_decision"][:28]

        blocking = r.get("blocking_review_issues", [])
        issues = "; ".join(blocking) if blocking else "none"
        issues = issues[:50]

        print(
            f"  Job {r['job_number']:<3} "
            f"{decision:<30} "
            f"{comp_s:<6} {html_s:<6} {dup_s:<6} "
            f"{flag:<5} "
            f"{issues}"
        )
    print()

    # ── Detailed results for pass + blocked ──────────────────────────────
    if pass_ready:
        print("## Pass Ready for Next Step")
        for r in pass_ready:
            dup_res = r.get("duplicate_script_result", {})
            dup_warns = r.get("global_duplicate_warnings_count", 0)
            info = r.get("info_review_notes", [])
            print(f"  Job {r['job_number']}: {r['topic'][:50]}")
            if info:
                for note in info:
                    print(f"    Info: {note}")
            print(f"    Global duplicate warnings: {dup_warns}")
            print()

    if blocked_comp:
        print("## Blocked — Compliance")
        for r in blocked_comp:
            print(f"  Job {r['job_number']}: {r['topic'][:50]}")
            for issue in r.get("blocking_review_issues", []):
                print(f"    {issue}")
            print()

    if blocked_html:
        print("## Blocked — HTML Quality")
        for r in blocked_html:
            print(f"  Job {r['job_number']}: {r['topic'][:50]}")
            for issue in r.get("blocking_review_issues", []):
                print(f"    {issue}")
            print()

    if dup_decision:
        print("## Needs Human Duplicate Decision")
        for r in dup_decision:
            print(f"  Job {r['job_number']}: {r['topic'][:50]}")
            print(f"    Current job flagged in duplicate_risk_log.md: YES")
            for issue in r.get("blocking_review_issues", []):
                print(f"    {issue}")
            print()

    # ── Job 20 status ─────────────────────────────────────────────────────
    job20 = next((r for r in results if r["job_number"] == "20"), None)
    if job20:
        print("## Job 20 Status")
        print()
        print(f"  Decision:   {job20['review_decision']}")
        print(f"  Local file: {'exists' if job20['local_file_exists'] else 'not found'}")
        print(f"  Shopify:    {job20.get('queue_status', '?')}")
        print()

    # ── Phase 2B readiness ────────────────────────────────────────────────
    print("## Phase 2B Readiness")
    print()
    if pass_ready and not (blocked_comp or blocked_html or dup_decision):
        print("  [PASS] Jobs 15-19 reviewed with no blockers")
        print("         Safe to proceed to Phase 2B (duplicate decision memory)")
        if dup_decision:
            print(f"         Note: {len(dup_decision)} job(s) need human duplicate decision")
    else:
        print("  [FAIL] Blocking issues found — resolve before Phase 2B")
        if blocked_comp:
            print(f"         Compliance blockers: {[r['job_number'] for r in blocked_comp]}")
        if blocked_html:
            print(f"         HTML quality blockers: {[r['job_number'] for r in blocked_html]}")
        if dup_decision:
            print(f"         Duplicate decision needed: {[r['job_number'] for r in dup_decision]}")

    print()
    print(f"Review preview file: {REPORT_PATH}")
    print("Dry-run complete — no production files modified.")


if __name__ == "__main__":
    main()
