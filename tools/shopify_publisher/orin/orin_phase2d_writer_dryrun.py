#!/usr/bin/env python3
"""
ORIN Phase 2D — Selected-Job Writer Execution Dry-Run

Phase 2D is the distinct Writer execution stage.
It receives the writer plan from Phase 2C and produces the local HTML draft.

INPUT (from Phase 2C):
  /tmp/orin_selected_job_context.json   — canonical selected-job context
  /tmp/orin_selected_job_writer_plan.json — writer plan from Phase 2C

OUTPUT:
  Local HTML draft at the path specified in writer_plan (or override).

Allowed:
  - Generate article HTML
  - Write to local file system (isolated /tmp/ or live drafts folder)
  - Use job_ctx + writer_plan for article identity

Forbidden:
  - Shopify writes
  - Queue edits
  - Publishing

Mode: Read-only plan inputs, write-only local draft output.

Usage:
  python3 tools/shopify_publisher/orin/orin_phase2d_writer_dryrun.py
  python3 tools/shopify_publisher/orin/orin_phase2d_writer_dryrun.py --as-of-date 2026-07-04
  python3 tools/shopify_publisher/orin/orin_phase2d_writer_dryrun.py --output /tmp/my_test/job_21_draft.html
"""

import json
import sys
import hashlib
import re
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from business_time import get_business_today_from_args
from writer_agent import WriterAgent
from handle_utils import is_canonical_shopify_handle, BLOCK_INVALID_PLANNED_HANDLE
from workspace_paths import workspace_root

BASE_DIR = workspace_root()

CURRENT_DATE_STR = get_business_today_from_args(sys.argv[1:]).isoformat()

# Input paths (produced by Phase 2C)
SELECTED_JOB_CONTEXT_PATH = Path("/tmp/orin_selected_job_context.json")
SELECTED_JOB_WRITER_PLAN_PATH = Path("/tmp/orin_selected_job_writer_plan.json")

# Default output path (isolated /tmp/ for dry-run)
DEFAULT_OUTPUT_PATH = Path("/tmp/orin_job21_writer_test/job_21_draft.html")

STATUS_REPORT_PATH = BASE_DIR / "clients" / "hoverboard_store" / "content_engine" / "orin_status_phase2d.md"


def parse_output_override():
    """Parse --output argument if provided."""
    args = sys.argv[1:]
    for i, arg in enumerate(args):
        if arg == "--output" and i + 1 < len(args):
            return Path(args[i + 1])
    return None


def run_writer_execution_dry_run():
    writer = WriterAgent(str(BASE_DIR), CURRENT_DATE_STR)

    # ── Read inputs from Phase 2C ──────────────────────────────────────────
    job_ctx = None
    writer_plan = None

    if SELECTED_JOB_CONTEXT_PATH.exists():
        try:
            job_ctx = json.loads(SELECTED_JOB_CONTEXT_PATH.read_text())
        except (json.JSONDecodeError, OSError) as e:
            print(f"WARNING: Could not read selected job context: {e}")

    if SELECTED_JOB_WRITER_PLAN_PATH.exists():
        try:
            writer_plan = json.loads(SELECTED_JOB_WRITER_PLAN_PATH.read_text())
        except (json.JSONDecodeError, OSError) as e:
            print(f"WARNING: Could not read writer plan: {e}")

    # ── Parse output override ──────────────────────────────────────────────
    output_override = parse_output_override()
    output_path = output_override or DEFAULT_OUTPUT_PATH

    # ── Pre-execution invariant checks ──────────────────────────────────────
    errors = []

    if job_ctx is None:
        errors.append("job_ctx is None — Phase 2C may not have run, or context file missing")
    if writer_plan is None:
        errors.append("writer_plan is None — Phase 2C may not have produced a plan")

    if job_ctx and writer_plan:
        # Invariant 1: job number match
        ctx_job = str(job_ctx.get("job_number", ""))
        plan_job = str(writer_plan.get("job_number", ""))
        if ctx_job != plan_job:
            errors.append(
                f"BLOCK_JOB_CONTEXT_MISMATCH: "
                f"job_ctx job ({ctx_job}) != writer_plan job ({plan_job})"
            )

        # Invariant 2: canonical handle
        handle = writer_plan.get("approved_handle", "")
        if not is_canonical_shopify_handle(handle):
            errors.append(
                f"{BLOCK_INVALID_PLANNED_HANDLE}: "
                f"handle is not canonical: {repr(handle)}"
            )

    if errors:
        for err in errors:
            print(f"ERROR: {err}")
        return {"success": False, "errors": errors}

    # ── Execute: write the HTML draft ──────────────────────────────────────
    job_number = job_ctx.get("job_number", "unknown")
    title = writer_plan.get("title", "unknown")

    print(f"Phase 2D: Writing draft for {job_number} — {title}")
    print(f"  Output path: {output_path}")
    print(f"  Using writer plan from: {SELECTED_JOB_WRITER_PLAN_PATH}")
    print(f"  Using job context from: {SELECTED_JOB_CONTEXT_PATH}")

    write_result = writer.write_selected_job_draft(
        job_ctx=job_ctx,
        writer_plan=writer_plan,
        output_path_override=str(output_path),
    )

    # ── Read back and compute stats ─────────────────────────────────────────
    if output_path.exists():
        content = output_path.read_text(encoding="utf-8")
        sha256 = hashlib.sha256(content.encode("utf-8")).hexdigest()
        word_count = len(content.split())
        h1_matches = re.findall(r"<h1[^>]*>(.*?)</h1>", content, re.DOTALL)
        h2_matches = re.findall(r"<h2[^>]*>(.*?)</h2>", content, re.DOTALL)
        faq_items = re.findall(r'class="hs-faq-item"', content)
        h1 = h1_matches[0].strip() if h1_matches else "MISSING"
        h1_source = "generated from writer_plan title" if h1 == title else f"WARNING: H1='{h1}' != title='{title}'"
    else:
        content = ""
        sha256 = "file-not-written"
        word_count = 0
        h1 = "MISSING"
        h2_matches = []
        faq_items = []
        h1_source = "output file not created"

    result = {
        "success": True,
        "phase": "2D",
        "phase_name": "Writer Execution",
        "run_date": CURRENT_DATE_STR,
        "job_ctx_job": job_ctx.get("job_number") if job_ctx else None,
        "writer_plan_job": writer_plan.get("job_number") if writer_plan else None,
        "write_result_job": write_result.get("job_number"),
        "title": write_result.get("title"),
        "approved_handle": write_result.get("approved_handle"),
        "output_path": str(output_path),
        "file_written": output_path.exists(),
        "file_size_bytes": write_result.get("file_size_bytes"),
        "word_count": word_count,
        "word_count_target": write_result.get("word_count_target"),
        "sha256": sha256,
        "h1": h1,
        "h1_source": h1_source,
        "h1_count": len(h1_matches),
        "h2_count": len(h2_matches),
        "faq_count": len(faq_items),
        "internal_link_count": write_result.get("internal_link_count"),
        "article_structure": {
            "hs_article": '<div class="hs-article">' in content,
            "hs_container": '<div class="hs-container">' in content,
            "hs_quick_answer": 'class="hs-quick-answer"' in content,
            "hs_highlights": 'class="hs-highlights"' in content,
            "hs_meta": 'class="hs-meta">' in content,
            "hs_cta": 'class="hs-cta">' in content,
        },
        "canonical_handle": is_canonical_shopify_handle(write_result.get("approved_handle", "")),
        "invariant_checks_passed": True,
        "errors": [],
    }

    # ── Leakage check ───────────────────────────────────────────────────────
    if content:
        job20_terms = [
            "best-hoverboard-accessories-safer-riding",
            "Best Hoverboard Accessories for Safer Riding",
            "Job 20",
            "job_20",
        ]
        leakage = {term: term in content for term in job20_terms}
        result["leakage_check"] = leakage
        result["job20_leaks"] = sum(leakage.values())
    else:
        result["leakage_check"] = {}
        result["job20_leaks"] = None

    # ── Print summary ───────────────────────────────────────────────────────
    print()
    print("=== Phase 2D Writer Execution Summary ===")
    print(f"Job: {write_result.get('job_number')} — {write_result.get('title')}")
    print(f"Output: {result['output_path']}")
    print(f"File written: {result['file_written']}")
    print(f"Word count: {result['word_count']} / target {result['word_count_target']}")
    print(f"SHA256: {result['sha256']}")
    print(f"H1: {result['h1']}")
    print(f"H2 count: {result['h2_count']}")
    print(f"FAQ items: {result['faq_count']}")
    print(f"Canonical handle: {result['canonical_handle']}")
    print(f"Job 20 leaks: {result['job20_leaks']}")
    if result['errors']:
        for e in result['errors']:
            print(f"ERROR: {e}")

    print()
    print("Phase 2D Writer Execution Complete.")

    return result


if __name__ == "__main__":
    result = run_writer_execution_dry_run()
    sys.exit(0 if result.get("success") else 1)
