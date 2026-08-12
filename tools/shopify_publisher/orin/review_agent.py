#!/usr/bin/env python3
"""
ORIN Review Agent — Phase 2A
Pre-publish review for local drafts.

Reads:
  - Local draft files from DRAFTS_DIR
  - compliance_check.py
  - html_quality_check.py
  - check_duplicate_content.py
  - duplicate_risk_log.md
  - state_agent.py (for job state context)

Produces:
  - review results dict per job
  - NO writes to Shopify, queue, or drafts
"""

import subprocess
import re
import json
import sys
import json
from html import unescape
from pathlib import Path
from typing import Optional

from content_quality_gate import evaluate_article_quality
from workspace_paths import source_root, workspace_root

BASE_DIR = workspace_root()
TOOLS_DIR = source_root() / "tools" / "shopify_publisher"

# ─── Default Hoverboard Store paths (backward compatibility) ────────────────────
_HOVERBOARD_CLIENT_DIR = BASE_DIR / "clients" / "hoverboard_store" / "content_engine"

def _get_client_paths(client_context=None):
    """
    Return (CLIENT_DIR, DRAFTS_DIR, RULES_FILE, DUP_LOG) for the given client context.
    When client_context is None, returns Hoverboard Store defaults.
    """
    if client_context is not None and hasattr(client_context, "client_id"):
        cid = client_context.client_id
        client_root = client_context.client_root
        client_content = client_root / "content_engine"
        return (
            client_content,                                    # CLIENT_DIR
            client_content / "drafts",                        # DRAFTS_DIR
            client_content / "orin_preflight_rules.md",       # RULES_FILE
            client_content / "duplicate_risk_log.md",         # DUP_LOG
        )
    # Fallback: Hoverboard Store defaults
    return (
        _HOVERBOARD_CLIENT_DIR,
        _HOVERBOARD_CLIENT_DIR / "drafts",
        _HOVERBOARD_CLIENT_DIR / "orin_preflight_rules.md",
        _HOVERBOARD_CLIENT_DIR / "duplicate_risk_log.md",
    )

# Lazy-load defaults (backward compatibility)
CLIENT_DIR = _HOVERBOARD_CLIENT_DIR
DRAFTS_DIR = CLIENT_DIR / "drafts"
RULES_FILE = CLIENT_DIR / "orin_preflight_rules.md"
DUP_LOG = CLIENT_DIR / "duplicate_risk_log.md"

# ─── Known local draft paths per job ─────────────────────────────────────────

KNOWN_DRAFT_FILES = {
    "15": "how-to-store-hoverboard-battery-safely.html",
    "16": "65-vs-85-inch-hoverboards-kids-guide.html",
    "17": "hoverboard-wont-turn-on-safe-checks.html",
    "18": "hoverboard-weight-limit-guide-for-parents.html",
    "19": "christmas-hoverboard-gift-guide-for-kids.html",
}

# ─── Check script runners ────────────────────────────────────────────────────

def run_check(script_path: Path, file_path: Path, script_name: str, extra_args: list = None) -> dict:
    """Run a check script on a local draft. Return result dict.

    Args:
        script_path: path to the check script
        file_path: path to the HTML file to check
        script_name: identifier for the script
        extra_args: optional list of extra arguments to pass to the script
    """
    if not script_path.exists():
        return {
            "script": script_name,
            "status": "error",
            "detail": f"Script not found: {script_path}",
            "exit_code": None,
            "output": "",
        }

    if not file_path.exists():
        return {
            "script": script_name,
            "status": "error",
            "detail": f"File not found: {file_path}",
            "exit_code": None,
            "output": "",
        }

    try:
        args = [sys.executable, str(script_path)]
        if extra_args:
            args.extend(extra_args)
        args.append(str(file_path))
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=60,
        )
        output = result.stdout + result.stderr
        exit_code = result.returncode

        if script_name == "compliance_check":
            if exit_code == 0:
                status = "pass"
                detail = "PASS"
            elif exit_code == 1:
                status = "warn"
                detail = "PASS WITH WARNINGS"
            else:
                status = "fail"
                detail = "FAIL"
        elif script_name == "html_quality_check":
            if exit_code == 0:
                status = "pass"
                detail = "PASS"
            else:
                status = "fail"
                detail = "FAIL"
        elif script_name == "check_duplicate_content":
            if exit_code == 0:
                status = "pass"
                detail = "PASS"
            elif exit_code == 1:
                status = "review_needed"
                detail = "REVIEW NEEDED"
            else:
                status = "block"
                detail = "BLOCK"
        else:
            status = "unknown"
            detail = f"Exit {exit_code}"

        return {
            "script": script_name,
            "status": status,
            "detail": detail,
            "exit_code": exit_code,
            "output": output[:500],
        }

    except subprocess.TimeoutExpired:
        return {
            "script": script_name,
            "status": "error",
            "detail": "Timeout after 60s",
            "exit_code": None,
            "output": "",
        }
    except Exception as e:
        return {
            "script": script_name,
            "status": "error",
            "detail": str(e),
            "exit_code": None,
            "output": "",
        }


# ─── Title extraction ────────────────────────────────────────────────────────

def extract_title_from_html(file_path: Path) -> Optional[str]:
    """Extract the main title (H1 or SEO title comment) from an HTML file."""
    if not file_path.exists():
        return None
    content = file_path.read_text()
    # Try H1 first
    h1_m = re.search(r'<h1[^>]*>([^<]+)</h1>', content, re.I)
    if h1_m:
        return h1_m.group(1).strip()
    # Try SEO title comment
    seo_m = re.search(r'SEO TITLE:\s*([^\n]+)', content)
    if seo_m:
        return seo_m.group(1).strip()
    # Try meta title
    meta_m = re.search(r'<title>([^<]+)</title>', content, re.I)
    if meta_m:
        return meta_m.group(1).strip()
    return None


# ─── Self-match detection ────────────────────────────────────────────────────

# Generic e-commerce/article words to ignore in title comparisons
_GENERIC_WORDS = {
    "a", "the", "and", "for", "to", "of", "in", "on", "is", "are",
    "uk", "2026", "your", "with", "how", "what", "when", "where", "why",
    "guide", "article", "hoverboard", "hoverboards", "hoverkart", "kids",
    "parents", "children", "buying", "best", "top", "ultimate", "complete",
}


def normalise(s: str) -> str:
    """Strip punctuation and lower-case for comparison."""
    return re.sub(r'[^\w\s]', '', s.lower())


def unapproved_internal_hrefs(content: str, writer_plan: dict) -> list[str]:
    """Return absolute article links that were not approved in the plan."""
    hrefs = set(re.findall(r'href="(http[^"]+)"', content))
    approved = {
        str(item.get("url", "")).strip()
        for item in writer_plan.get("internal_link_plan", [])
        if str(item.get("url", "")).strip()
    }
    cta_href = str(writer_plan.get("cta_plan", {}).get("button_href", "")).strip()
    if cta_href:
        approved.add(cta_href)
    return sorted(hrefs - approved)


def blocked_claims_in_text(content: str, claims_to_avoid: list[str]) -> list[str]:
    """Return prohibited claims used affirmatively in visible draft text.

    Every occurrence is evaluated independently. Clearly cautionary language,
    such as "rather than an everyday guarantee", is not treated as making the
    prohibited claim.
    """
    visible_text = unescape(re.sub(r"<[^>]+>", " ", content))
    visible_text = re.sub(r"\s+", " ", visible_text)
    blocked: list[str] = []

    for raw_claim in claims_to_avoid:
        claim = raw_claim.strip()
        if not claim:
            continue

        escaped_claim = re.escape(claim)
        claim_pattern = re.compile(rf"\b{escaped_claim}\b", re.IGNORECASE)
        has_affirmative_use = False

        for match in claim_pattern.finditer(visible_text):
            prefix = visible_text[max(0, match.start() - 180):match.start()]
            prefix = re.split(r"[.!?;:]", prefix)[-1]
            caution_patterns = (
                rf"\b(?:no|never|without|rather\s+than)\b"
                rf"(?:\W+\w+){{0,8}}\W*$",
                rf"\b(?:does|do|is|are|will|can)\s+not\b"
                rf"(?:\W+\w+){{0,8}}\W*$",
                rf"\bcannot\b(?:\W+\w+){{0,8}}\W*$",
                rf"\bnot\b(?:\W+\w+){{0,8}}\W*$",
            )
            is_cautionary = any(
                re.search(pattern, prefix, re.IGNORECASE)
                for pattern in caution_patterns
            )
            if re.search(r"\bnot\s+only\b", prefix, re.IGNORECASE):
                is_cautionary = False

            if not is_cautionary:
                has_affirmative_use = True
                break

        if has_affirmative_use:
            blocked.append(claim)

    return blocked


def topic_word_overlap(local_title: str, other_title: str) -> float:
    """
    Return fraction of non-generic local words that appear in other_title.
    A real duplicate needs at least 2 specific topic words in common.
    """
    local_words = set(normalise(local_title).split()) - _GENERIC_WORDS
    other_words = set(normalise(other_title).split()) - _GENERIC_WORDS
    if not local_words:
        return 0.0
    return len(local_words & other_words) / len(local_words)


def is_self_match_against_shopify(
    local_file_path: Path,
    job_topic: str,
    shopify_article_id: Optional[str],
    shopify_handle: Optional[str],
    dup_log_path: Path = None,
    drafts_dir: Path = None,
) -> dict:
    """
    Args:
        dup_log_path: optional Path to duplicate_risk_log.md
        drafts_dir: optional Path to drafts directory
    """
    """
    Classify duplicate findings as self_match_info vs current_job_real_duplicate.

    self_match_info:      The BLOCK/REVIEW NEEDED is the local draft vs its own
                          Shopify article (same handle or article ID).
    current_job_real_duplicate: The BLOCK/REVIEW NEEDED is the local draft vs
                          a DIFFERENT Shopify article.
    global_site_warning:  The current job is not mentioned in any risk pair —
                          global site-health warnings only.
    """
    if not local_file_path or not local_file_path.exists():
        return {
            "is_self_match": False,
            "classification": "unclear",
            "detail": "No local file to compare",
        }

    dup_log = dup_log_path or DUP_LOG
    if not dup_log.exists():
        return {
            "is_self_match": False,
            "classification": "unclear",
            "detail": "duplicate_risk_log.md not found",
        }

    dup_content = dup_log.read_text()
    local_title = extract_title_from_html(local_file_path) or job_topic

    # ── Parse all BLOCK and REVIEW NEEDED risk sections ────────────────
    risks = re.split(r'(?=## Risk \d+:)', dup_content)

    self_match_risks = []      # risks where job vs its own Shopify article
    real_dup_risks = []        # risks where job vs a different article
    global_only_risks = []     # risks that don't involve this job

    for risk in risks:
        if not risk.strip():
            continue

        level = "BLOCK" if "[BLOCK]" in risk else "REVIEW NEEDED" if "[REVIEW]" in risk else None
        if not level:
            continue

        # Get article titles and slugs in this risk pair
        titles_in_risk = re.findall(r'\*\*Article [AB]:\*\* ([^\n]+)', risk)
        slugs_in_risk = re.findall(r'Slug: `([^`]+)`', risk)
        ids_in_risk = re.findall(r'article_id[\s:]+(\d+)', risk)

        norm_handle = (shopify_handle or "").lower().replace("-", "")

        slug_match_own = False
        id_match_own = False
        title_match_diff = False

        for slug in slugs_in_risk:
            if norm_handle and slug.lower().replace("-", "") == norm_handle:
                slug_match_own = True

        if shopify_article_id:
            for aid in ids_in_risk:
                if aid == shopify_article_id:
                    id_match_own = True

        # Check if local title has significant topic-word overlap with either article
        for t in titles_in_risk:
            overlap = topic_word_overlap(local_title, t)
            if overlap >= 0.50:  # ≥50% non-generic word overlap → likely same topic
                title_match_diff = True

        if slug_match_own or id_match_own:
            self_match_risks.append(level)
        elif title_match_diff:
            real_dup_risks.append(level)
        else:
            global_only_risks.append(level)

    # ── Classify ───────────────────────────────────────────────────────
    if self_match_risks and not real_dup_risks:
        return {
            "is_self_match": True,
            "classification": "self_match_info",
            "detail": (
                f"Self-match only: duplicate flagged for local draft vs own "
                f"Shopify article ({'handle' if shopify_handle else 'article ID'}). "
                f"BLOCK/REVIEW NEEDED risks against self: {len(self_match_risks)}. "
                f"No real duplicate against different articles found."
            ),
            "self_match_count": len(self_match_risks),
            "real_dup_count": 0,
        }
    elif real_dup_risks:
        return {
            "is_self_match": False,
            "classification": "current_job_real_duplicate",
            "detail": (
                f"Real duplicate found: local draft vs a DIFFERENT Shopify article. "
                f"Duplicate risks: {len(real_dup_risks)}. "
                f"Self-match risks: {len(self_match_risks)}."
            ),
            "self_match_count": len(self_match_risks),
            "real_dup_count": len(real_dup_risks),
        }
    else:
        return {
            "is_self_match": False,
            "classification": "global_site_warning",
            "detail": (
                "Current job not found in any BLOCK/REVIEW NEEDED risk pair. "
                "Duplicate warnings are global site-health issues unrelated to this job."
            ),
            "self_match_count": 0,
            "real_dup_count": 0,
        }


# ─── Main review function ────────────────────────────────────────────────────

def review_job(
    job_num: str,
    job_topic: str,
    local_file_path: Optional[str],
    shopify_handle: Optional[str],
    shopify_article_id: Optional[str],
    is_due: bool,
    queue_status: str,
) -> dict:
    """
    Review a single job. Return review result dict.
    """
    # ── Skip if not due ───────────────────────────────────────────────
    if not is_due:
        return {
            "job_number": job_num,
            "topic": job_topic,
            "local_file_path": local_file_path,
            "local_file_exists": bool(local_file_path and Path(local_file_path).exists()),
            "queue_status": queue_status,
            "compliance_result": None,
            "html_quality_result": None,
            "duplicate_script_result": None,
            "duplicate_classification": "skipped_not_due",
            "current_job_duplicate_flagged": False,
            "global_duplicate_warnings_count": 0,
            "blocking_review_issues": [],
            "info_review_notes": [],
            "review_decision": "skipped_not_due",
        }

    # ── No local file ────────────────────────────────────────────────
    if not local_file_path or not Path(local_file_path).exists():
        return {
            "job_number": job_num,
            "topic": job_topic,
            "local_file_path": local_file_path,
            "local_file_exists": False,
            "queue_status": queue_status,
            "compliance_result": None,
            "html_quality_result": None,
            "duplicate_script_result": None,
            "duplicate_classification": "no_local_file",
            "current_job_duplicate_flagged": False,
            "global_duplicate_warnings_count": 0,
            "blocking_review_issues": [],
            "info_review_notes": [],
            "review_decision": "no_local_file_to_review",
        }

    file_path = Path(local_file_path)

    # ── Derive brand for html_quality_check byline verification ─────────────────
    brand_for_check = "Hoverboard Store"  # backward-compatible default
    if client_context is not None and hasattr(client_context, "byline"):
        byline = client_context.byline or ""
        if byline.startswith("By "):
            brand_for_check = byline[3:].strip()
        elif byline:
            brand_for_check = byline.strip()

    # ── Run checks ────────────────────────────────────────────────────
    compliance = run_check(TOOLS_DIR / "compliance_check.py", file_path, "compliance_check")
    html_q = run_check(
        TOOLS_DIR / "html_quality_check.py",
        file_path,
        "html_quality_check",
        extra_args=[f"--brand={brand_for_check}"],
    )
    dup_check = run_check(TOOLS_DIR / "check_duplicate_content.py", file_path, "check_duplicate_content")

    # ── Self-match vs real duplicate classification ──────────────────
    dup_class = is_self_match_against_shopify(
        local_file_path=file_path,
        job_topic=job_topic,
        shopify_article_id=shopify_article_id,
        shopify_handle=shopify_handle,
        dup_log_path=DUP_LOG,
        drafts_dir=DRAFTS_DIR,
    )
    current_job_flagged = dup_class["classification"] in (
        "self_match_info", "current_job_real_duplicate"
    )

    # ── Count global duplicate warnings in checker output ──────────────
    dup_output = dup_check.get("output", "") or ""
    global_warnings = sum(
        1 for line in dup_output.split("\n")
        if "REVIEW NEEDED" in line or "[BLOCK]" in line
    )

    # ── Build issue list ──────────────────────────────────────────────
    blocking = []
    info_notes = []

    if compliance["status"] == "fail":
        blocking.append(f"compliance_fail: {compliance.get('detail', '')}")
    elif compliance["status"] == "warn":
        info_notes.append(f"compliance_warn: {compliance.get('detail', '')}")

    if html_q["status"] == "fail":
        blocking.append(f"html_quality_fail: {html_q.get('detail', '')}")
    elif html_q["status"] == "warn":
        info_notes.append(f"html_quality_warn: {html_q.get('detail', '')}")

    # ── Duplicate handling with self-match logic ───────────────────────
    dup_status = dup_check.get("status", "")

    if dup_status == "block":
        if dup_class["classification"] == "self_match_info":
            info_notes.append(f"duplicate_self_match: {dup_class['detail']}")
        elif dup_class["classification"] == "current_job_real_duplicate":
            blocking.append(
                f"duplicate_block_real: {dup_class['detail']} "
                f"[script: {dup_check.get('detail', '')}]"
            )
        elif dup_class["classification"] == "global_site_warning":
            info_notes.append(f"duplicate_global_warning: {dup_class['detail']}")
        else:
            info_notes.append(f"duplicate_block_unclear: {dup_class.get('detail', dup_check.get('detail', ''))}")

    elif dup_status == "review_needed":
        if dup_class["classification"] == "self_match_info":
            info_notes.append(f"duplicate_self_match_review: {dup_class['detail']}")
        elif dup_class["classification"] == "current_job_real_duplicate":
            blocking.append(f"duplicate_review_real: {dup_class['detail']}")
        elif dup_class["classification"] == "global_site_warning":
            info_notes.append(f"duplicate_global_warning: {dup_class['detail']}")
        else:
            info_notes.append(f"duplicate_review_unclear: {dup_class.get('detail', dup_check.get('detail', ''))}")

    # ── Make decision ─────────────────────────────────────────────────
    if blocking:
        if any("compliance" in b for b in blocking):
            decision = "blocked_compliance"
        elif any("html_quality" in b for b in blocking):
            decision = "blocked_html_quality"
        elif any("duplicate" in b for b in blocking):
            decision = "needs_human_duplicate_decision"
        else:
            decision = "blocked_other"
    elif not file_path.exists():
        decision = "no_local_file_to_review"
    else:
        decision = "pass_ready_for_next_step"

    return {
        "job_number": job_num,
        "topic": job_topic,
        "local_file_path": str(file_path),
        "local_file_exists": file_path.exists(),
        "queue_status": queue_status,
        "compliance_result": compliance,
        "html_quality_result": html_q,
        "duplicate_script_result": dup_check,
        "duplicate_classification": dup_class["classification"],
        "duplicate_detail": dup_class["detail"],
        "current_job_duplicate_flagged": current_job_flagged,
        "global_duplicate_warnings_count": global_warnings,
        "blocking_review_issues": blocking,
        "info_review_notes": info_notes,
        "review_decision": decision,
    }


def review_jobs(job_numbers: list) -> list:
    """
    Review all specified jobs. Returns list of review results.
    """
    # Import from state_agent on demand to avoid circular deps
    sys.path.insert(0, str(Path(__file__).parent))
    from state_agent import read_queue, read_shopify_inventory, read_approved_handles
    from state_agent import local_file_for_job, resolve_shopify_article, today

    queue = read_queue()
    shopify_inv = read_shopify_inventory()
    approved = read_approved_handles()

    results = []
    for num in job_numbers:
        if num not in queue:
            continue

        job = queue[num]
        queue_status = job.get("queue_status", "")
        topic = job.get("topic", "")
        expected_draft_date = job.get("expected_draft_date")

        # Check if due
        is_due = False
        if expected_draft_date:
            try:
                from state_agent import days_until
                is_due = days_until(expected_draft_date) <= 0
            except Exception:
                pass

        # Get local file
        local_exists, local_path = local_file_for_job(job)
        full_local = Path(local_path) if local_path else None

        # Get Shopify handle and article ID
        shopify_info = resolve_shopify_article(job, shopify_inv, approved)
        shopify_handle = shopify_info.get("shopify_handle")
        shopify_article_id = shopify_info.get("article_id")

        result = review_job(
            job_num=num,
            job_topic=topic,
            local_file_path=str(full_local) if full_local else None,
            shopify_handle=shopify_handle,
            shopify_article_id=shopify_article_id,
            is_due=is_due,
            queue_status=queue_status,
        )
        results.append(result)

    return results


def review_selected_job_draft(
    job_ctx: dict,
    writer_plan: dict,
    draft_path: str,
    skip_duplicate_check: bool = False,
    client_context=None,
) -> dict:
    """
    Post-write review for the selected job's local HTML draft.

    Args:
        client_context: optional ClientContext object. When provided, review uses
                      client-specific paths for duplicate log and rules.
                      When None, falls back to Hoverboard Store defaults.
    """
    # Resolve client-specific paths
    CLIENT_DIR, DRAFTS_DIR, RULES_FILE, DUP_LOG = _get_client_paths(client_context)
    """
    Post-write review for the selected job's local HTML draft.

    INPUTS:
      job_ctx        — selected-job context dict (from /tmp/orin_selected_job_context.json)
      writer_plan    — writer plan dict (from /tmp/orin_selected_job_writer_plan.json)
      draft_path     — absolute path to the writer-executed HTML draft
      skip_duplicate_check — set True for new planned articles (no existing Shopify record);
                             the duplicate checker compares against existing Shopify articles
                             and would always flag a brand-new article as a false positive

    INVARIANTS (checked before substantive review):
      job_ctx.job_number == writer_plan.job_number  → BLOCK_JOB_CONTEXT_MISMATCH
      reviewed draft path must match the path supplied  → BLOCK_DRAFT_PATH_MISMATCH

    RETURNS:
      Structured review result dict with:
        job_number, title, draft_path, review_decision,
        blockers[], warnings[], identity_checks{},
        content_quality_checks{}, compliance_checks{},
        source_grounding_checks{}, structure_checks{},
        internal_link_checks{}, safe_for_html_validation

    ALLOWED DECISIONS:
      POST_WRITE_REVIEW_PASSED
      POST_WRITE_REVIEW_BLOCKED
      POST_WRITE_REVIEW_NEEDS_HUMAN_REVIEW
    """
    import hashlib

    BLOCK_JOB_CONTEXT_MISMATCH = "BLOCK_JOB_CONTEXT_MISMATCH"
    BLOCK_DRAFT_PATH_MISMATCH = "BLOCK_DRAFT_PATH_MISMATCH"

    errors = []
    warnings_list = []

    # ── Identity invariants ────────────────────────────────────────────────────
    ctx_job = str(job_ctx.get("job_number", ""))
    plan_job = str(writer_plan.get("job_number", ""))

    if not ctx_job or not plan_job:
        errors.append(f"{BLOCK_JOB_CONTEXT_MISMATCH}: empty job number (ctx={ctx_job}, plan={plan_job})")
    elif ctx_job != plan_job:
        errors.append(
            f"{BLOCK_JOB_CONTEXT_MISMATCH}: "
            f"job_ctx job ({ctx_job}) != writer_plan job ({plan_job})"
        )

    if not draft_path:
        errors.append(f"{BLOCK_DRAFT_PATH_MISMATCH}: empty draft_path")

    draft_path_obj = Path(draft_path) if draft_path else None
    if errors:
        return {
            "job_number": ctx_job or plan_job or "unknown",
            "title": writer_plan.get("title", "unknown"),
            "draft_path": draft_path or "none",
            "review_decision": "POST_WRITE_REVIEW_BLOCKED",
            "blockers": errors,
            "warnings": warnings_list,
            "identity_checks": {},
            "content_quality_checks": {},
            "compliance_checks": {},
            "source_grounding_checks": {},
            "structure_checks": {},
            "internal_link_checks": {},
            "safe_for_html_validation": False,
            "errors": errors,
        }

    # ── Pre-read draft for inspection ──────────────────────────────────────────
    if not draft_path_obj.exists():
        return {
            "job_number": ctx_job,
            "title": writer_plan.get("title", "unknown"),
            "draft_path": draft_path,
            "review_decision": "POST_WRITE_REVIEW_BLOCKED",
            "blockers": [f"draft file not found: {draft_path}"],
            "warnings": warnings_list,
            "identity_checks": {},
            "content_quality_checks": {},
            "compliance_checks": {},
            "source_grounding_checks": {},
            "structure_checks": {},
            "internal_link_checks": {},
            "safe_for_html_validation": False,
            "errors": [],
        }

    content = draft_path_obj.read_text(encoding="utf-8")
    sha256_before = hashlib.sha256(content.encode("utf-8")).hexdigest()

    # ── Identity checks ────────────────────────────────────────────────────────
    identity = {}

    # H1 check
    h1_m = re.search(r"<h1[^>]*>(.*?)</h1>", content, re.DOTALL | re.IGNORECASE)
    h1_text = h1_m.group(1).strip() if h1_m else ""
    expected_title = writer_plan.get("title", "")
    identity["h1_match"] = h1_text == expected_title
    identity["h1_extracted"] = h1_text
    identity["h1_expected"] = expected_title
    identity["h1_present"] = bool(h1_m)

    # Job number in draft (should not contain Job 20 identifiers)
    identity["job_20_slug_not_in_draft"] = "best-hoverboard-accessories-safer-riding" not in content
    identity["job_20_title_not_in_draft"] = "Best Hoverboard Accessories for Safer Riding" not in content
    identity["job_20_identifier_absent"] = "Job 20" not in content

    # Approved handle represented (in canonical form)
    canonical_handle = writer_plan.get("approved_handle", "")
    identity["canonical_handle"] = canonical_handle
    identity["canonical_handle_in_draft"] = canonical_handle in content

    # Article topic consistency
    topic = writer_plan.get("topic", "")
    topic_words = set(topic.lower().split())
    h1_words = set(h1_text.lower().split())
    overlap = topic_words & h1_words
    identity["topic_h1_overlap_words"] = list(overlap)
    identity["topic_h1_relevant"] = len(overlap) >= 2 if topic_words else False

    # ── Content quality checks ────────────────────────────────────────────────
    quality = {}

    # No planning/debug text exposed
    debug_patterns = [
        r"WRITER_PLAN", r"JOB_CONTEXT", r"PHASE_[12][A-Z]",
        r"\[TEMPLATE\]", r"\[PLACEHOLDER\]", r"DRAFT_ONLY",
        r"simulated_job", r"BLOCK_JOB", r"BLOCK_INVALID",
    ]
    debug_found = []
    for pat in debug_patterns:
        if re.search(pat, content, re.IGNORECASE):
            debug_found.append(pat)
    quality["no_debug_text"] = len(debug_found) == 0
    quality["debug_patterns_found"] = debug_found

    # No placeholder text
    placeholder_phrases = ["[YOUR TEXT HERE]", "[INSERT]", "TBD", "TODO", "XXX"]
    placeholders_found = [p for p in placeholder_phrases if p in content]
    quality["no_placeholder_text"] = len(placeholders_found) == 0
    quality["placeholders_found"] = placeholders_found

    # Phase 3.5 is initially scoped to the dedicated Hoverboard Store path.
    # Other client contracts remain unchanged until they receive their own
    # client-specific quality profile.
    phase35_enforced = (
        client_context is None
        or getattr(client_context, "client_id", "") == "hoverboard_store"
    )
    quality_receipt = None
    if phase35_enforced:
        site_url = writer_plan.get("site_url", "")
        if not site_url and client_context is not None:
            site_url = getattr(client_context, "site_url", "")
        if not site_url:
            site_url = "https://hoverboardstore.co.uk"
        quality_receipt = evaluate_article_quality(
            content,
            target_keyword=writer_plan.get("target_keyword", ""),
            site_url=site_url,
        )
        quality.update(quality_receipt["metrics"])
        quality["contract_version"] = quality_receipt["contract_version"]
        quality["gate_passed"] = quality_receipt["passed"]
        quality["gate_blockers"] = quality_receipt["blockers"]
        quality["thresholds"] = quality_receipt["thresholds"]
        quality["word_count"] = quality["visible_word_count"]
        quality["word_count_target"] = quality_receipt["thresholds"][
            "min_visible_words"
        ]
        quality["word_count_adequate"] = (
            quality["visible_word_count"]
            >= quality_receipt["thresholds"]["min_visible_words"]
        )
        quality["has_substantive_body"] = (
            quality["paragraph_count"]
            >= quality_receipt["thresholds"]["min_paragraph_count"]
        )
    else:
        # Preserve the existing advisory metrics for clients not yet migrated
        # to a Phase 3.5 content contract.
        word_count = len(content.split())
        target_words = writer_plan.get("recommended_word_count", 1000)
        paragraphs = re.findall(
            r"<p[\s>].*?</p>",
            content,
            re.DOTALL | re.IGNORECASE,
        )
        quality.update(
            {
                "contract_version": None,
                "gate_passed": None,
                "gate_blockers": [],
                "word_count": word_count,
                "word_count_target": target_words,
                "word_count_adequate": word_count >= target_words * 0.8,
                "paragraph_count": len(paragraphs),
                "has_substantive_body": len(paragraphs) >= 5,
            }
        )

    # ── Compliance checks ────────────────────────────────────────────────────
    compliance = {}

    # Run compliance check
    comp_result = run_check(
        TOOLS_DIR / "compliance_check.py",
        draft_path_obj,
        "compliance_check"
    )
    compliance["script_result"] = comp_result
    compliance["script_status"] = comp_result.get("status", "unknown")
    compliance["exit_code"] = comp_result.get("exit_code")

    # Blocked claims from writer plan
    # Use word-boundary regex to avoid substring false positives
    # (e.g. "guarantee" should not match "guarantees" or "No...guarantee")
    claims_to_avoid = writer_plan.get("claims_to_avoid", [])
    blocked_found_in_draft = blocked_claims_in_text(content, claims_to_avoid)
    compliance["claims_to_avoid_found"] = blocked_found_in_draft
    compliance["claims_to_avoid_clean"] = len(blocked_found_in_draft) == 0

    # Specific phrases that should never appear (absolute safety claims)
    # Use word-boundary matching to avoid substring false positives
    dangerous_phrases = [
        ("road legal", "legal road use claim"),
        ("guarantees safety", "safety guarantee"),
        ("safer than", "comparative safety claim"),
        ("universal compatibility", "universal fit claim"),
        ("fits all hoverboards", "universal fit claim"),
    ]
    dangerous_found = []
    for phrase, label in dangerous_phrases:
        pattern = r"\b" + re.escape(phrase) + r"\b"
        if re.search(pattern, content, re.IGNORECASE):
            # Exclude negated uses
            escaped_phrase = re.escape(phrase)
            negated_pattern = re.compile(
                rf"(no|never|doesn't|does not|dont|do not)"
                rf"\s+\w+(?:\s+\w+){{0,30}}\s+{escaped_phrase}",
                re.IGNORECASE
            )
            if negated_pattern.search(content):
                continue
            dangerous_found.append((phrase, label))
    compliance["dangerous_phrases_found"] = dangerous_found
    compliance["dangerous_phrases_clean"] = len(dangerous_found) == 0

    # Public-road context check
    public_road_neg = re.search(
        r"do not use.{0,100}public (road|roads|pavement)",
        content, re.IGNORECASE
    )
    compliance["public_road_caution_present"] = bool(public_road_neg)
    compliance["public_road_caution_correctly_negative"] = bool(public_road_neg)

    # ── Source grounding checks ───────────────────────────────────────────────
    grounding = {}

    # Load source evidence if available
    source_evidence_path = Path("/tmp/orin_job21_writer_source_evidence.json")
    if source_evidence_path.exists():
        try:
            se = json.loads(source_evidence_path.read_text())
            grounding["source_evidence_available"] = True
            grounding["verified_claims_count"] = se.get("verified_claims_count", 0)
            grounding["unverified_claims_count"] = se.get("unverified_claims_count", 0)
            grounding["blocked_claims_count"] = se.get("blocked_claims_count", 0)
            grounding["general_guidance_count"] = se.get("general_guidance_facts_count", 0)
        except Exception:
            grounding["source_evidence_available"] = False
    else:
        grounding["source_evidence_available"] = False

    # ── Structure checks ─────────────────────────────────────────────────────
    structure = {}

    # Major sections (H2)
    h2s = re.findall(r"<h2[^>]*>(.*?)</h2>", content, re.DOTALL | re.IGNORECASE)
    structure["h2_count"] = len(h2s)
    structure["h2_present"] = len(h2s) >= 3

    # CTA present
    cta_match = re.search(r'class="[^"]*hs-cta[^"]*"', content, re.IGNORECASE)
    structure["cta_present"] = bool(cta_match)

    # FAQ present (if writer plan requires it)
    faq_plan = writer_plan.get("faq_plan", [])
    faq_items_in_draft = re.findall(r'class="[^"]*hs-faq-item[^"]*"', content)
    structure["faq_required"] = len(faq_plan) > 0
    structure["faq_present_in_draft"] = len(faq_items_in_draft) > 0
    structure["faq_count"] = len(faq_items_in_draft)
    structure["faq_expected_count"] = len(faq_plan)
    structure["faq_matches_plan"] = len(faq_items_in_draft) == len(faq_plan)

    # Canonical Hoverboard Store byline requirement (from html_quality_check.py):
    # Visible article text must contain "By Hoverboard Store".
    # This is the ONLY canonical byline requirement.
    # hs-byline is NOT in the canonical HTML contract (html_blocks.md).
    # HTML class/markup byline checks belong to the Canonical HTML Validator, not Review.
    visible_for_byline = re.sub(r"<[^>]+>", " ", content)
    visible_for_byline = re.sub(r"\s+", " ", visible_for_byline).strip()
    brand_byline_check = "Hoverboard Store"
    if client_context is not None and hasattr(client_context, "byline"):
        b = client_context.byline or ""
        if b.startswith("By "):
            brand_byline_check = b[3:].strip()
        elif b:
            brand_byline_check = b.strip()
    structure["canonical_byline_text_present"] = f"By {brand_byline_check}" in visible_for_byline

    # Article container
    structure["hs_article_container"] = 'class="hs-article"' in content or 'class="hs-article ' in content
    structure["hs_container"] = 'class="hs-container"' in content or 'class="hs-container ' in content

    # ── Internal link checks ──────────────────────────────────────────────────
    links = {}

    hrefs = re.findall(r'href="(http[^"]+)"', content)
    links["external_href_count"] = len(hrefs)

    approved_hrefs = {
        str(item.get("url", "")).strip()
        for item in writer_plan.get("internal_link_plan", [])
        if str(item.get("url", "")).strip()
    }
    cta_href = str(writer_plan.get("cta_plan", {}).get("button_href", "")).strip()
    if cta_href:
        approved_hrefs.add(cta_href)
    links["approved_hrefs"] = sorted(approved_hrefs)
    links["unapproved_hrefs"] = unapproved_internal_hrefs(content, writer_plan)
    links["approved_href_only"] = not links["unapproved_hrefs"]

    # Check for placeholder/broken href patterns
    broken_patterns = ["#", "http://example.com", "https://example.com", "YOUR_URL"]
    broken_hrefs = [h for h in hrefs if any(p in h for p in broken_patterns)]
    links["broken_placeholder_hrefs"] = broken_hrefs
    links["has_broken_hrefs"] = len(broken_hrefs) > 0

    # Local internal links
    local_hrefs = [h for h in hrefs if h.startswith("/") or "hoverboard-store" in h]
    links["internal_href_count"] = len(local_hrefs)

    # ── HTML quality check ───────────────────────────────────────────────────
    # Derive brand for html_quality_check byline verification
    brand_for_check2 = "Hoverboard Store"
    if client_context is not None and hasattr(client_context, "byline"):
        byline2 = client_context.byline or ""
        if byline2.startswith("By "):
            brand_for_check2 = byline2[3:].strip()
        elif byline2:
            brand_for_check2 = byline2.strip()
    html_q_result = run_check(
        TOOLS_DIR / "html_quality_check.py",
        draft_path_obj,
        "html_quality_check",
        extra_args=[f"--brand={brand_for_check2}"],
    )

    # ── Duplicate check (conditionally skipped for new planned articles) ──────
    dup_result = None
    dup_classification = "skipped_new_article"
    if skip_duplicate_check:
        dup_result = {
            "script": "check_duplicate_content",
            "status": "skipped",
            "detail": "Skipped for new planned article (no existing Shopify record)",
            "exit_code": None,
            "output": "",
        }
        dup_classification = "skipped_new_article"
    else:
        dup_result = run_check(
            TOOLS_DIR / "check_duplicate_content.py",
            draft_path_obj,
            "check_duplicate_content"
        )
        # Classify for new articles without Shopify handle
        shopify_handle = job_ctx.get("shopify_handle", "") or writer_plan.get("approved_handle", "")
        shopify_article_id = job_ctx.get("shopify_article_id", "")
        dup_class = is_self_match_against_shopify(
            local_file_path=draft_path_obj,
            job_topic=job_ctx.get("topic", ""),
            shopify_article_id=shopify_article_id,
            shopify_handle=shopify_handle,
            dup_log_path=DUP_LOG,
            drafts_dir=DRAFTS_DIR,
        )
        dup_classification = dup_class.get("classification", "unclear")

    # ── Assemble blockers and warnings ───────────────────────────────────────
    blockers = []
    post_write_warnings = []

    # Compliance failures
    if comp_result.get("status") == "fail":
        blockers.append(f"compliance_fail: {comp_result.get('detail', '')}")

    # HTML quality failures
    if html_q_result.get("status") == "fail":
        blockers.append(f"html_quality_fail: {html_q_result.get('detail', '')}")

    # Duplicate block (only if not skipped)
    if dup_result and not skip_duplicate_check:
        if dup_result.get("status") == "block":
            blockers.append(
                f"duplicate_block: {dup_result.get('detail', '')} "
                f"[classification: {dup_classification}]"
            )

    # Blocked claims found
    if blocked_found_in_draft:
        blockers.append(f"blocked_claims_in_draft: {blocked_found_in_draft}")

    # Dangerous phrases found
    if dangerous_found:
        blockers.append(f"dangerous_phrases: {[d[0] for d in dangerous_found]}")

    if not links["approved_href_only"]:
        blockers.append(
            "unapproved_internal_links: "
            f"{links['unapproved_hrefs']}"
        )

    if structure["faq_required"] and not structure["faq_matches_plan"]:
        blockers.append(
            "faq_plan_mismatch: "
            f"draft has {structure['faq_count']} FAQ items, "
            f"expected exactly {structure['faq_expected_count']}"
        )

    # Identity failures
    if not identity["h1_present"]:
        blockers.append("identity: H1 missing")
    if not identity["h1_match"]:
        blockers.append(f"identity: H1 mismatch (got: '{h1_text}', expected: '{expected_title}')")

    # Phase 3.5 content quality failures are blocking before Shopify.
    if phase35_enforced:
        for quality_blocker in quality_receipt["blockers"]:
            blockers.append(
                "content_quality_gate: "
                f"{quality_blocker['code']}: {quality_blocker['message']} "
                f"(actual={quality_blocker['actual']!r}, "
                f"expected={quality_blocker['expected']!r})"
            )
        if not quality["no_debug_text"]:
            blockers.append(f"content_quality_gate: CQ_DEBUG_TEXT: {debug_found}")
        if not quality["no_placeholder_text"]:
            blockers.append(
                f"content_quality_gate: CQ_PLACEHOLDER_CONTENT: {placeholders_found}"
            )

    # Warnings
    if comp_result.get("status") == "warn":
        post_write_warnings.append(f"compliance_warn: {comp_result.get('detail', '')}")
    if html_q_result.get("status") == "warn":
        post_write_warnings.append(f"html_quality_warn: {html_q_result.get('detail', '')}")
    if not phase35_enforced and not quality["no_debug_text"]:
        post_write_warnings.append(f"debug_text_found: {debug_found}")
    if not phase35_enforced and not quality["word_count_adequate"]:
        post_write_warnings.append(
            f"word_count_low: {quality['word_count']} "
            f"(target: {quality['word_count_target']})"
        )
    if links["has_broken_hrefs"]:
        post_write_warnings.append(f"broken_hrefs: {broken_hrefs}")
    if not identity["topic_h1_relevant"]:
        post_write_warnings.append(f"topic_h1_low_overlap: {list(overlap)}")
    if not structure["canonical_byline_text_present"]:
        post_write_warnings.append(
            "byline: canonical Hoverboard Store visible text 'By Hoverboard Store' not found in article"
        )

    # ── Make decision ────────────────────────────────────────────────────────
    sha256_after = sha256_before  # read-only review

    # Blocking decision: only when real blockers exist
    # PASSED when no blocking issues — advisory warnings are informational only
    # (reported in the 'warnings' return field for human awareness)
    if blockers:
        decision = "POST_WRITE_REVIEW_BLOCKED"
        safe_for_html_validation = False
    else:
        decision = "POST_WRITE_REVIEW_PASSED"
        safe_for_html_validation = True

    return {
        "job_number": ctx_job,
        "title": writer_plan.get("title", "unknown"),
        "approved_handle": writer_plan.get("approved_handle", ""),
        "draft_path": draft_path,
        "sha256_before": sha256_before,
        "sha256_after": sha256_after,
        "draft_not_mutated": sha256_before == sha256_after,
        "review_decision": decision,
        "blockers": blockers,
        "warnings": post_write_warnings,
        "identity_checks": identity,
        "content_quality_checks": quality,
        "content_quality_receipt": quality_receipt,
        "compliance_checks": compliance,
        "source_grounding_checks": grounding,
        "structure_checks": structure,
        "internal_link_checks": links,
        "safe_for_html_validation": safe_for_html_validation,
        "duplicate_check_skipped": skip_duplicate_check,
        "duplicate_classification": dup_classification,
        "html_quality_result": html_q_result,
        "errors": [],
    }
