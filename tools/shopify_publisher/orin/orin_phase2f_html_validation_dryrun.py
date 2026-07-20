#!/usr/bin/env python3
"""
ORIN Phase 2F — Selected-Job HTML Validation Dry-Run

Phase 2F validates the selected job's Writer HTML draft against the canonical
Hoverboard Store HTML contract (html_quality_check.py).

INPUT (from Phase 2C/2D/2A):
  /tmp/orin_selected_job_context.json        — canonical selected-job context
  /tmp/orin_selected_job_writer_plan.json    — writer plan from Phase 2C
  /tmp/orin_job21_writer_execution_preview.json — Phase 2D execution preview (contains output_path)
  /tmp/orin_selected_job_post_write_review.json — Post-write review result

OUTPUT:
  /tmp/orin_selected_job_html_validation.json  — validation result

PHASE RESPONSIBILITY:
  Validate HTML structure against canonical Hoverboard Store contract.
  Does NOT write HTML, update Shopify, or edit the queue.

MODE: Read-only — no production writes.

Usage:
  python3 tools/shopify_publisher/orin/orin_phase2f_html_validation_dryrun.py
  python3 tools/shopify_publisher/orin/orin_phase2f_html_validation_dryrun.py --as-of-date 2026-07-04
"""

import json
import subprocess
import hashlib
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from business_time import get_business_today_from_args

BASE_DIR = Path("/data/.openclaw/workspace")

CURRENT_DATE_STR = get_business_today_from_args(sys.argv[1:]).isoformat()

# Input paths
SELECTED_JOB_CONTEXT_PATH = Path("/tmp/orin_selected_job_context.json")
SELECTED_JOB_WRITER_PLAN_PATH = Path("/tmp/orin_selected_job_writer_plan.json")
WRITER_EXECUTION_PREVIEW_PATH = Path("/tmp/orin_job21_writer_execution_preview.json")
POST_WRITE_REVIEW_PATH = Path("/tmp/orin_selected_job_post_write_review.json")

# Output path
VALIDATION_OUTPUT_PATH = Path("/tmp/orin_selected_job_html_validation.json")

# Canonical Hoverboard Store HTML validator
HTML_QUALITY_CHECKER = BASE_DIR / "tools" / "shopify_publisher" / "html_quality_check.py"


def run_html_validation(draft_path: str) -> dict:
    """Run html_quality_check.py against the draft. Return structured result."""
    result = subprocess.run(
        [sys.executable, str(HTML_QUALITY_CHECKER), draft_path],
        capture_output=True,
        text=True,
        timeout=60,
    )
    output = result.stdout + result.stderr
    exit_code = result.returncode

    # Parse issues from output
    issues = []
    in_issues = False
    for line in output.splitlines():
        if "Issues found:" in line:
            in_issues = True
            try:
                count = int(line.split("Issues found:")[1].strip())
            except (ValueError, IndexError):
                count = None
            continue
        if in_issues and line.startswith("-"):
            issues.append(line.lstrip("- ").strip())
        if "STATUS:" in line:
            in_issues = False

    passed = exit_code == 0

    return {
        "script": "html_quality_check.py",
        "exit_code": exit_code,
        "passed": passed,
        "issues_count": len(issues),
        "issues": issues,
        "raw_output": output[:1000],
    }


def inspect_html_structure(content: str) -> dict:
    """Inspect HTML structure against canonical Hoverboard Store contract."""
    checks = {}

    # Wrapper checks
    checks["hs_article_wrapper"] = 'class="hs-article"' in content
    checks["hs_container"] = 'class="hs-container"' in content

    # H1
    h1_m = re.search(r"<h1[^>]*>(.*?)</h1>", content, re.DOTALL | re.IGNORECASE)
    checks["h1_present"] = bool(h1_m)
    checks["h1_text"] = h1_m.group(1).strip() if h1_m else ""

    # Meta section
    checks["hs_meta"] = 'class="hs-meta"' in content

    # Quick answer
    checks["hs_quick_answer"] = 'class="hs-quick-answer"' in content

    # Highlights
    checks["hs_highlights"] = 'class="hs-highlights"' in content

    # CTA
    checks["hs_cta"] = 'class="hs-cta"' in content

    # Byline text (not element — hs-byline is not in canonical contract)
    checks["byline_text_present"] = "By Hoverboard Store" in content

    # FAQ format (div.hs-faq-q, div.hs-faq-a — not h3/p)
    faq_items = len(re.findall(r'class="hs-faq-item"', content, re.I))
    faq_q_div = len(re.findall(r'<div\s+class="hs-faq-q"', content, re.I))
    faq_a_div = len(re.findall(r'<div\s+class="hs-faq-a"', content, re.I))
    faq_q_h3 = len(re.findall(r'<h3\s+class="hs-faq-q"', content, re.I))
    faq_a_p = len(re.findall(r'<p\s+class="hs-faq-a"', content, re.I))

    checks["faq_items_count"] = faq_items
    checks["faq_q_div_count"] = faq_q_div
    checks["faq_a_div_count"] = faq_a_div
    checks["faq_q_h3_count"] = faq_q_h3
    checks["faq_a_p_count"] = faq_a_p
    checks["faq_correct_format"] = (
        faq_q_div == faq_items and faq_a_div == faq_items and faq_q_h3 == 0 and faq_a_p == 0
    )

    # Manual FAQPage JSON-LD check
    checks["no_manual_faqpage_jsonld"] = not bool(
        re.search(r'"@type"\s*:\s*"FAQPage"', content, re.I)
    )

    # Invalid HTML
    checks["no_invalid_di_tag"] = not bool(re.search(r"<di(\s|>)", content, re.I))
    checks["no_invalid_closing_di"] = not bool(re.search(r"</di>", content, re.I))
    checks["no_empty_paragraphs"] = not bool(re.search(r"<p>\s*</p>", content, re.I))

    # Public metadata in body
    visible = re.sub(r"<[^>]+>", " ", content)
    visible = re.sub(r"\s+", " ", visible).strip()
    metadata_terms = ["SEO Title:", "Meta Title:", "Meta Description:", "URL Slug:"]
    checks["no_visible_metadata"] = not any(t in visible for t in metadata_terms)

    # Blocked author terms
    blocked = ["TOXIC", "AISEO", "ChatGPT", "OpenAI", "ORIN Test"]
    checks["no_blocked_author_terms"] = not any(t in visible for t in blocked)

    # Internal links
    hrefs = re.findall(r'href="([^"]+)"', content)
    external = [h for h in hrefs if h.startswith("http")]
    checks["external_href_count"] = len(external)
    checks["broken_placeholder_hrefs"] = [
        h for h in hrefs
        if any(p in h for p in ["#", "http://example.com", "https://example.com"])
    ]

    return checks


def run_validation():
    # ── Load inputs ─────────────────────────────────────────────────────────
    job_ctx = None
    writer_plan = None
    writer_preview = None
    post_write_review = None

    for path, label, dest in [
        (SELECTED_JOB_CONTEXT_PATH, "job context", "job_ctx"),
        (SELECTED_JOB_WRITER_PLAN_PATH, "writer plan", "writer_plan"),
        (WRITER_EXECUTION_PREVIEW_PATH, "writer execution preview", "writer_preview"),
        (POST_WRITE_REVIEW_PATH, "post-write review", "post_write_review"),
    ]:
        if path.exists():
            try:
                dest_ref = {"job_ctx": lambda: None, "writer_plan": lambda: None,
                            "writer_preview": lambda: None, "post_write_review": lambda: None}
                setattr(sys.modules[__name__], label.replace(" ", "_"), 
                       json.loads(path.read_text()))
            except Exception:
                pass

    # Load using local vars
    job_ctx = json.loads(SELECTED_JOB_CONTEXT_PATH.read_text()) if SELECTED_JOB_CONTEXT_PATH.exists() else None
    writer_plan = json.loads(SELECTED_JOB_WRITER_PLAN_PATH.read_text()) if SELECTED_JOB_WRITER_PLAN_PATH.exists() else None
    writer_preview = json.loads(WRITER_EXECUTION_PREVIEW_PATH.read_text()) if WRITER_EXECUTION_PREVIEW_PATH.exists() else None
    post_write_review = json.loads(POST_WRITE_REVIEW_PATH.read_text()) if POST_WRITE_REVIEW_PATH.exists() else None

    # ── Derive draft path ────────────────────────────────────────────────────
    if writer_preview:
        draft_path = writer_preview.get("output_path", "")
    else:
        draft_path = (writer_plan or {}).get("proposed_local_file_path", "")

    draft_path_obj = Path(draft_path)

    # ── Pre-validation invariants ─────────────────────────────────────────────
    errors = []
    ctx_job = str((job_ctx or {}).get("job_number", ""))
    plan_job = str((writer_plan or {}).get("job_number", ""))

    if job_ctx and writer_plan and ctx_job != plan_job:
        errors.append(f"BLOCK_JOB_CONTEXT_MISMATCH: job_ctx ({ctx_job}) != writer_plan ({plan_job})")

    if not draft_path:
        errors.append("draft_path not determined")
    elif not draft_path_obj.exists():
        errors.append(f"draft file not found: {draft_path}")

    if errors:
        result = {
            "phase": "2F",
            "phase_name": "HTML Validation",
            "run_date": CURRENT_DATE_STR,
            "job_number": ctx_job or plan_job or "unknown",
            "validation_passed": False,
            "errors": errors,
            "draft_path": draft_path or "none",
        }
        VALIDATION_OUTPUT_PATH.write_text(json.dumps(result, indent=2, default=str))
        print("ERRORS:", errors)
        return result

    # ── Read draft ──────────────────────────────────────────────────────────
    content = draft_path_obj.read_text(encoding="utf-8")
    sha256_before = hashlib.sha256(content.encode()).hexdigest()

    # ── Run canonical HTML validator ─────────────────────────────────────────
    validator_result = run_html_validation(draft_path)

    # ── Inspect HTML structure ───────────────────────────────────────────────
    structure = inspect_html_structure(content)

    # ── Compile results ──────────────────────────────────────────────────────
    result = {
        "phase": "2F",
        "phase_name": "HTML Validation",
        "run_date": CURRENT_DATE_STR,
        "job_number": ctx_job,
        "title": (writer_plan or {}).get("title", "unknown"),
        "approved_handle": (writer_plan or {}).get("approved_handle", ""),
        "draft_path": draft_path,
        "draft_sha256": sha256_before,
        "draft_not_mutated": True,  # validation is read-only
        "validation_passed": validator_result["passed"],
        "validator_exit_code": validator_result["exit_code"],
        "validator_issues_count": validator_result["issues_count"],
        "validator_issues": validator_result["issues"],
        "structure_checks": structure,
        "post_write_review_decision": (post_write_review or {}).get("review_decision", "N/A"),
        "post_write_review_blockers": (post_write_review or {}).get("blockers", []),
        "safe_for_publisher_preflight": (
            validator_result["passed"]
            and structure["hs_article_wrapper"]
            and structure["hs_container"]
            and structure["h1_present"]
            and structure["faq_correct_format"]
        ),
        "errors": errors,
    }

    # ── Write output ────────────────────────────────────────────────────────
    VALIDATION_OUTPUT_PATH.write_text(json.dumps(result, indent=2, default=str))

    # ── Print summary ───────────────────────────────────────────────────────
    print("=" * 70)
    print("ORIN Phase 2F — Selected-Job HTML Validation Dry-Run")
    print(f"Run date: {CURRENT_DATE_STR}")
    print("=" * 70)
    print()
    print(f"Selected job: {ctx_job} — {result['title']}")
    print(f"Draft: {draft_path}")
    print(f"SHA256: {sha256_before}")
    print()
    print("=== Canonical HTML Validator Result ===")
    print(f"  html_quality_check.py exit code: {validator_result['exit_code']}")
    print(f"  Passed: {validator_result['passed']}")
    print(f"  Issues: {validator_result['issues_count']}")
    if validator_result["issues"]:
        for issue in validator_result["issues"]:
            print(f"    - {issue}")
    print()
    print("=== Structure Checks ===")
    for check, value in structure.items():
        status = "PASS" if value else "FAIL"
        print(f"  [{status}] {check}: {value}")
    print()
    print(f"safe_for_publisher_preflight: {result['safe_for_publisher_preflight']}")
    print()
    print(f"Validation output: {VALIDATION_OUTPUT_PATH}")
    print("Dry-run complete — no production files modified.")

    return result


if __name__ == "__main__":
    result = run_validation()
    sys.exit(0 if result.get("validation_passed") else 1)
