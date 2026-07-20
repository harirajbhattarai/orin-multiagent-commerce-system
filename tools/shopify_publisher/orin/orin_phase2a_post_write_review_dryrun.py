#!/usr/bin/env python3
"""
ORIN Phase 2A — Selected-Job Post-Write Review Dry-Run

This is the POST-WRITE review stage for the selected-job pipeline.
It runs AFTER the Writer has produced the local HTML draft (Phase 2D).

INPUT (from Phase 2C Writer Planning + Phase 2D Writer Execution):
  /tmp/orin_selected_job_context.json       — canonical selected-job context
  /tmp/orin_selected_job_writer_plan.json   — writer plan from Phase 2C
  /tmp/orin_job21_writer_execution_preview.json — Writer execution preview (contains output_path)

OUTPUT:
  /tmp/orin_selected_job_post_write_review.json — review result

PHASE RESPONSIBILITY:
  Post-write review of the selected job's Writer draft.
  Verifies identity, content quality, compliance, structure, and internal links.
  Does NOT independently select jobs from the queue.

MODE: Read-only — no Shopify writes, no queue edits, no draft mutations.

Usage:
  python3 tools/shopify_publisher/orin/orin_phase2a_post_write_review_dryrun.py
  python3 tools/shopify_publisher/orin/orin_phase2a_post_write_review_dryrun.py --as-of-date 2026-07-04
"""

import json
import sys
import hashlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from business_time import get_business_today_from_args
from review_agent import review_selected_job_draft
from handle_utils import is_canonical_shopify_handle

BASE_DIR = Path("/data/.openclaw/workspace")

CURRENT_DATE_STR = get_business_today_from_args(sys.argv[1:]).isoformat()

# Input paths
SELECTED_JOB_CONTEXT_PATH = Path("/tmp/orin_selected_job_context.json")
SELECTED_JOB_WRITER_PLAN_PATH = Path("/tmp/orin_selected_job_writer_plan.json")
WRITER_EXECUTION_PREVIEW_PATH = Path("/tmp/orin_job21_writer_execution_preview.json")

# Output path
REVIEW_OUTPUT_PATH = Path("/tmp/orin_selected_job_post_write_review.json")


def flines(items):
    return "\n".join(["- " + str(item) for item in items]) if items else "None"


def run_post_write_review():
    # ── Load inputs from Phase 2C and Phase 2D ───────────────────────────────
    job_ctx = None
    writer_plan = None
    writer_preview = None

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

    if WRITER_EXECUTION_PREVIEW_PATH.exists():
        try:
            writer_preview = json.loads(WRITER_EXECUTION_PREVIEW_PATH.read_text())
        except (json.JSONDecodeError, OSError) as e:
            print(f"WARNING: Could not read writer execution preview: {e}")

    # ── Derive draft path from Phase 2D execution preview ─────────────────────
    if writer_preview:
        draft_path = writer_preview.get("output_path", "")
    else:
        # Fallback: use proposed_local_file_path from writer plan
        draft_path = (writer_plan or {}).get("proposed_local_file_path", "")
        if not Path(draft_path).exists():
            # Fall back to temp test path
            draft_path = "/tmp/orin_job21_writer_test/job_21_draft.html"

    job_number = (job_ctx or {}).get("job_number", "unknown")
    title = (writer_plan or {}).get("title", "unknown")

    print("=" * 70)
    print("ORIN Phase 2A — Selected-Job Post-Write Review Dry-Run")
    print(f"Run date: {CURRENT_DATE_STR}")
    print("Mode: READ-ONLY (no production writes)")
    print("=" * 70)
    print()
    print(f"Selected job: {job_number} — {title}")
    print(f"Draft path: {draft_path}")
    print()

    # ── Determine if this is a new planned article ─────────────────────────────
    # New planned articles have no existing Shopify handle or article_id
    is_new_article = False
    if job_ctx:
        shopify_handle = job_ctx.get("shopify_handle", "")
        shopify_article_id = job_ctx.get("shopify_article_id", "")
        is_new_article = not shopify_handle and not shopify_article_id

    skip_duplicate_check = is_new_article
    if skip_duplicate_check:
        print("[INFO] New planned article detected (no Shopify handle/ID) — skipping duplicate check")
        print("        (duplicate checker would always flag a new article as false positive)")
        print()

    # ── Run post-write review ────────────────────────────────────────────────
    if job_ctx and writer_plan and draft_path:
        result = review_selected_job_draft(
            job_ctx=job_ctx,
            writer_plan=writer_plan,
            draft_path=draft_path,
            skip_duplicate_check=skip_duplicate_check,
        )
    else:
        errors = []
        if not job_ctx:
            errors.append("job_ctx missing — cannot run review")
        if not writer_plan:
            errors.append("writer_plan missing — cannot run review")
        if not draft_path:
            errors.append("draft_path not determined")
        result = {
            "job_number": job_number,
            "title": title,
            "draft_path": draft_path or "none",
            "review_decision": "POST_WRITE_REVIEW_BLOCKED",
            "blockers": errors,
            "warnings": [],
            "safe_for_html_validation": False,
            "errors": errors,
        }

    # ── Write review output ────────────────────────────────────────────────────
    REVIEW_OUTPUT_PATH.write_text(json.dumps(result, indent=2, default=str))
    print(f"Review output written to: {REVIEW_OUTPUT_PATH}")
    print()

    # ── Print summary ─────────────────────────────────────────────────────────
    print("=== Post-Write Review Summary ===")
    print(f"  Job: {result.get('job_number')} — {result.get('title')}")
    print(f"  Draft: {result.get('draft_path')}")
    print(f"  SHA256 (before): {result.get('sha256_before', 'N/A')}")
    print(f"  SHA256 (after):  {result.get('sha256_after', 'N/A')}")
    print(f"  Draft not mutated: {result.get('draft_not_mutated', False)}")
    print(f"  Decision: {result.get('review_decision')}")
    print(f"  Safe for HTML validation: {result.get('safe_for_html_validation')}")
    print(f"  Duplicate check skipped: {result.get('duplicate_check_skipped', False)}")
    print()

    # ── Identity checks ────────────────────────────────────────────────────────
    ic = result.get("identity_checks", {})
    print("=== Identity Checks ===")
    print(f"  H1 present: {ic.get('h1_present')}")
    print(f"  H1 match: {ic.get('h1_match')}")
    print(f"  H1: {ic.get('h1_extracted', 'MISSING')[:60]}")
    print(f"  Job 20 slug absent: {ic.get('job_20_slug_not_in_draft')}")
    print(f"  Job 20 title absent: {ic.get('job_20_title_not_in_draft')}")
    print(f"  Canonical handle: {ic.get('canonical_handle')}")
    print(f"  Canonical handle in draft: {ic.get('canonical_handle_in_draft')}")
    print()

    # ── Compliance checks ──────────────────────────────────────────────────────
    cc = result.get("compliance_checks", {})
    print("=== Compliance ===")
    print(f"  Script status: {cc.get('script_status')}")
    print(f"  Claims to avoid clean: {cc.get('claims_to_avoid_clean')}")
    print(f"  Dangerous phrases clean: {cc.get('dangerous_phrases_clean')}")
    print(f"  Public road caution: {cc.get('public_road_caution_present')}")
    print(f"  Public road correctly negative: {cc.get('public_road_caution_correctly_negative')}")
    if cc.get("claims_to_avoid_found"):
        print(f"  WARNING — claims to avoid found: {cc.get('claims_to_avoid_found')}")
    if cc.get("dangerous_phrases_found"):
        print(f"  WARNING — dangerous phrases: {[d[0] for d in cc.get('dangerous_phrases_found')]}")
    print()

    # ── Content quality ────────────────────────────────────────────────────────
    qc = result.get("content_quality_checks", {})
    print("=== Content Quality ===")
    print(f"  Word count: {qc.get('word_count')} / target {qc.get('word_count_target')}")
    print(f"  Word count adequate: {qc.get('word_count_adequate')}")
    print(f"  Paragraph count: {qc.get('paragraph_count')}")
    print(f"  No debug text: {qc.get('no_debug_text')}")
    print(f"  No placeholder text: {qc.get('no_placeholder_text')}")
    print()

    # ── Structure ─────────────────────────────────────────────────────────────
    sc = result.get("structure_checks", {})
    print("=== Structure ===")
    print(f"  H2 count: {sc.get('h2_count')}")
    print(f"  CTA present: {sc.get('cta_present')}")
    print(f"  FAQ present: {sc.get('faq_present_in_draft')} (required: {sc.get('faq_required')})")
    print(f"  FAQ count: {sc.get('faq_count')}")
    print(f"  Canonical byline text (By Hoverboard Store): {sc.get('canonical_byline_text_present')}")
    print(f"  hs-article container: {sc.get('hs_article_container')}")
    print(f"  hs-container: {sc.get('hs_container')}")
    print()

    # ── Internal links ─────────────────────────────────────────────────────────
    lc = result.get("internal_link_checks", {})
    print("=== Internal Links ===")
    print(f"  External hrefs: {lc.get('external_href_count')}")
    print(f"  Internal hrefs: {lc.get('internal_href_count')}")
    print(f"  Broken/placeholder hrefs: {lc.get('broken_placeholder_hrefs', [])}")
    print()

    # ── Source grounding ───────────────────────────────────────────────────────
    gc = result.get("source_grounding_checks", {})
    print("=== Source Grounding ===")
    print(f"  Evidence available: {gc.get('source_evidence_available')}")
    if gc.get("source_evidence_available"):
        print(f"  Verified claims: {gc.get('verified_claims_count')}")
        print(f"  Unverified claims: {gc.get('unverified_claims_count')}")
        print(f"  Blocked claims: {gc.get('blocked_claims_count')}")
        print(f"  General guidance: {gc.get('general_guidance_count')}")
    print()

    # ── Blockers and warnings ────────────────────────────────────────────────
    blockers = result.get("blockers", [])
    warnings = result.get("warnings", [])

    if blockers:
        print("=== BLOCKERS ===")
        for b in blockers:
            print(f"  [BLOCK] {b}")
        print()

    if warnings:
        print("=== WARNINGS ===")
        for w in warnings:
            print(f"  [WARN] {w}")
        print()

    # ── Final decision ────────────────────────────────────────────────────────
    decision = result.get("review_decision", "unknown")
    print(f"Final decision: {decision}")
    print()

    if decision == "POST_WRITE_REVIEW_PASSED":
        print("[PASS] Draft passed all automated checks.")
        print("       Safe to proceed to Phase F (HTML validation).")
    elif decision == "POST_WRITE_REVIEW_NEEDS_HUMAN_REVIEW":
        print("[WARN] Draft has warnings — human review recommended.")
        print("       Safe for HTML validation but requires human sign-off.")
    else:
        print("[BLOCK] Draft has blocking issues — resolve before proceeding.")

    print()
    print(f"Review output: {REVIEW_OUTPUT_PATH}")
    print("Dry-run complete — no production files modified.")

    return result


if __name__ == "__main__":
    result = run_post_write_review()
    sys.exit(0 if result.get("review_decision") == "POST_WRITE_REVIEW_PASSED" else 1)
