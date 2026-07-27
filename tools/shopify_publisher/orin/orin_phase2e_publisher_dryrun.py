#!/usr/bin/env python3
"""
ORIN Phase 2E Publisher Dry-Run
Wrapper script for publisher_agent.py

Accepts --job-context <path> to evaluate the correct selected job.

Usage:
  python3 orin_phase2e_publisher_dryrun.py --job-context /tmp/orin_selected_job_context.json

Generates: orin_status_phase2e.md + /tmp/orin_phase2e_publisher_preview.json
"""

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from workspace_paths import workspace_root, writable_report_path

AGENT_SCRIPT = Path(__file__).resolve().parent / "publisher_agent.py"
BASE_DIR = workspace_root()
REPORT_PATH = writable_report_path(
    artifact_name="orin_status_phase2e.md",
    workspace_relative_path=(
        "clients/hoverboard_store/content_engine/orin_status_phase2e.md"
    ),
)
JSON_PATH = Path("/tmp/orin_phase2e_publisher_preview.json")
JOB_CONTEXT_ARG = "--job-context"
WRITER_EXECUTION_ARG = "--writer-execution"


def run():
    print("=" * 60)
    print("ORIN PHASE 2E — PUBLISHER DRY-RUN")
    print(f"Started: {datetime.now(timezone.utc).isoformat()}")
    print("=" * 60)

    # ── Resolve selected job from job context ─────────────────────────────
    job_label = None
    draft_path = None
    expected_slug = None
    job_context_path = None

    if JOB_CONTEXT_ARG in sys.argv:
        idx = sys.argv.index(JOB_CONTEXT_ARG)
        job_context_path = Path(sys.argv[idx + 1])
        if job_context_path.exists():
            ctx = json.loads(job_context_path.read_text())
            job_label = ctx.get("job_number")  # e.g. "21"
            job_label = f"Job {job_label}" if job_label else None
            draft_path = ctx.get("local_draft_path")  # absolute path or None
            expected_slug = ctx.get("shopify_handle")  # e.g. "hoverkart-compatibility-checklist-uk-2026"
            print(f"  Selected job: {job_label}")
            print(f"  Draft path:   {draft_path or '(none — new planned job)'}")
            print(f"  Expected slug: {expected_slug or '(none)'}")
        else:
            print(f"  WARNING: job context not found: {job_context_path}")
    else:
        # Legacy positional args for backward compat
        job_label = sys.argv[1] if len(sys.argv) > 1 else "Job 20"
        draft_path = sys.argv[2] if len(sys.argv) > 2 else None
        print(f"  Using legacy positional args: {job_label}")

    if not job_label:
        print("ERROR: No job selected. Pass --job-context <path>")
        sys.exit(1)

    # Build publisher_agent.py call
    pub_args = [sys.executable, str(AGENT_SCRIPT)]
    if job_context_path:
        pub_args.extend([JOB_CONTEXT_ARG, str(job_context_path)])
        # PHASE G.1 FIX: Also pass Writer execution preview so Publisher can resolve
        # draft path automatically without manual context patching
        job_num = ctx.get("job_number") if job_context_path.exists() else None
        if job_num:
            writer_exec_path = Path(f"/tmp/orin_job{job_num}_writer_execution_preview.json")
            if writer_exec_path.exists():
                pub_args.extend([WRITER_EXECUTION_ARG, str(writer_exec_path)])
                print(f"  Writer execution preview: {writer_exec_path}")
    else:
        pub_args.append(job_label)
        if draft_path:
            pub_args.append(draft_path)
    pub_args.append("--json")

    print()
    print(f"  Calling publisher_agent: {pub_args[2:]}")
    print()

    # Run the publisher agent dry-run
    result = subprocess.run(
        pub_args,
        capture_output=True,
        text=True,
        cwd=str(BASE_DIR),
    )

    output = result.stdout + result.stderr
    print(output)

    try:
        agent_results = json.loads(result.stdout)
    except json.JSONDecodeError:
        print("❌ Failed to parse agent output")
        sys.exit(1)

    # ── Build Phase 2E report ─────────────────────────────────────────────
    checks = agent_results.get("checks", {})
    pv = agent_results.get("payload_preview") or {}

    expected_slug_report = expected_slug or "(none — new planned job)"
    expected_status_report = (
        checks.get("queue_status", {}).get("expected", "planned")
    )

    report = f"""# ORIN Phase 2E — Publisher Agent Dry-Run Report

## Phase Identification

- **Phase:** 2E — Publisher Agent (dry-run)
- **Publisher evaluated job:** {job_label}
- **Target job (from agent):** {agent_results.get('target_job')}
- **Mode:** DRY-RUN — no Shopify API calls, no queue updates, no publishing
- **Timestamp:** {agent_results.get('timestamp')}
- **Job context:** {str(job_context_path) if job_context_path else 'legacy positional args'}

## Pre-Flight Checks

| Check | Expected | Found | Result |
|---|---|---|---|
| Queue status | {expected_status_report} | {checks.get('queue_status', {}).get('found', 'N/A')} | {'✅ PASS' if checks.get('queue_status', {}).get('pass') else '❌ FAIL'} |
| Local draft exists | yes | {'yes' if checks.get('local_draft_exists') else 'no'} | {'✅ PASS' if checks.get('local_draft_exists') else '❌ FAIL'} |
| Slug | {expected_slug_report} | {checks.get('slug', {}).get('found', 'N/A')} | {'✅ PASS' if checks.get('slug', {}).get('pass') else '❌ FAIL'} |
| Shopify handle duplicate | none | {'exists' if checks.get('shopify_handle_duplicate', {}).get('found') else 'not found'} | {'❌ FAIL — BLOCK' if checks.get('shopify_handle_duplicate', {}).get('found') else '✅ PASS'} |
| Shopify similar title | none | {checks.get('shopify_similar_title', {}).get('count', 'N/A')} found | {'⚠️ REVIEW' if checks.get('shopify_similar_title', {}).get('count', 0) > 0 else '✅ PASS'} |
| Compliance | pass | {checks.get('compliance', {}).get('issues_found', 'N/A')} issues | {'❌ FAIL' if not checks.get('compliance', {}).get('pass') else '✅ PASS'} |
| HTML quality | pass | {'issues' if checks.get('html_quality', {}).get('issues') else 'clean'} | {'❌ FAIL' if not checks.get('html_quality', {}).get('pass') else '❌ FAIL'} |

## Shopify Duplicate Check Details

### Handle Check
{'❌ EXISTING ARTICLE FOUND — BLOCK' if checks.get('shopify_handle_duplicate', {}).get('found') else '✅ No article with this handle exists in Shopify inventory'}

### Similar Title Check
{checks.get('shopify_similar_title', {}).get('count', 0)} article(s) with overlapping title terms:
{chr(10).join([f"- `{a}`" for a in checks.get('shopify_similar_title', {}).get('articles', [])]) if checks.get('shopify_similar_title', {}).get('articles') else 'None'}

*Note: Similar titles are not automatic blockers — context determines whether overlap is acceptable.*

## Compliance Check

- **Issues found:** {checks.get('compliance', {}).get('issues_found', 0)}
- **Result:** {'✅ PASS' if checks.get('compliance', {}).get('pass') else '❌ FAIL — review flagged language before push'}

## HTML Quality Check

- **Issues:** {len(checks.get('html_quality', {}).get('issues', []))}
- **Warnings:** {len(checks.get('html_quality', {}).get('warnings', []))}
- **Result:** {'✅ PASS' if checks.get('html_quality', {}).get('pass') else '❌ FAIL'}

{chr(10).join([f'  - ⚠️ {w}' for w in checks.get('html_quality', {}).get('warnings', [])]) if checks.get('html_quality', {}).get('warnings') else ''}

## Payload Preview

| Field | Value |
|---|---|
| **Title** | {pv.get('title', 'N/A')} |
| **Handle / Slug** | {pv.get('handle', 'N/A')} |
| **Author** | {pv.get('author', 'N/A')} |
| **Blog target** | {pv.get('blog_target', 'N/A')} |
| **Body HTML length** | {pv.get('body_html_length', 'N/A')} |
| **Tags** | {pv.get('tags', [])} |
| **Published** | {pv.get('published')} |
| **Published_at** | {pv.get('published_at')} |
| **Expected action** | {pv.get('expected_action')} |
| **Queue update after push** | {pv.get('queue_update_after_push')} |

## Phase 2E Decision

**Decision:** {agent_results.get('decision', 'N/A')}

- Shopify API called: ❌ NO (dry-run)
- Queue updated: ❌ NO
- Shopify touched: {agent_results.get('shopify_touched', False)}
- Queue touched: {agent_results.get('queue_touched', False)}
- Draft created: {agent_results.get('draft_created', False)}

## Summary

| | |
|---|---|
| Phase 2E passed | {'YES ✅' if agent_results.get('passed') else 'NO ❌'} |
| Safe for manual Shopify draft push | {'YES ✅' if agent_results.get('passed') else 'NO ❌'} |
| Next step | Manual approval → Shopify draft push |

---

*Generated: {datetime.now(timezone.utc).isoformat()}*
*Mode: DRY-RUN — no live Shopify changes*
"""

    # Persist the canonical machine-readable decision first. The Markdown
    # projection is useful evidence, but a report-path failure must not erase
    # an already-computed publisher decision from the supervising pipeline.
    with open(JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(agent_results, f, indent=2, default=str)

    # Write report
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write(report)

    print(f"\n📄 Report written: {REPORT_PATH}")
    print(f"📄 JSON written:   {JSON_PATH}")

    # Exit 0 if agent returned a decision (even passed=False).
    # Cron entrypoint handles the decision, not just the exit code.
    # Exit 1 only for actual errors (parse failure, no job, etc.)
    decision = agent_results.get("decision", "")
    agent_passed = agent_results.get("passed", False)
    is_soft_block = (
        decision == "BLOCK — local draft not found"
    )
    return agent_passed or is_soft_block

if __name__ == "__main__":
    result = run()
    sys.exit(0 if result else 1)
