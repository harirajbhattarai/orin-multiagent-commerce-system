#!/usr/bin/env python3
"""
ORIN Duplicate Decision Memory Agent — Phase 2B

Purpose:
  Reads Phase 2A review results and duplicate_risk_log.md,
  classifies each job's duplicate status into a memory record,
  and produces a preview JSON in /tmp (no production writes).

Memory record types:
  - self_match_info         : local draft vs own Shopify article — info only
  - global_site_warning     : checker warnings not involving current job — info only
  - human_duplicate_decision_required : real duplicate vs different article — BLOCKING
  - human_duplicate_decision_resolved : operator has decided — resolved

Strict rules:
  - NO writes to production duplicate_decisions.json
  - NO auto-approval of real duplicates
  - NO blocking decisions recorded without operator input
"""

import json
import re
import sys
from pathlib import Path

from workspace_paths import workspace_root
from datetime import datetime, date
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent))
from business_time import get_business_today

BASE_DIR = workspace_root()
_HOVERBOARD_CLIENT_DIR = BASE_DIR / "clients" / "hoverboard_store" / "content_engine"

def _get_client_duplicate_paths(client_context=None):
    """
    Return (CLIENT_DIR, DUP_LOG) for the given client context.
    When client_context is None, returns Hoverboard Store defaults.
    """
    if client_context is not None and hasattr(client_context, "client_id"):
        client_root = client_context.client_root
        client_content = client_root / "content_engine"
        return (
            client_content,
            client_content / "duplicate_risk_log.md",
        )
    return (
        _HOVERBOARD_CLIENT_DIR,
        _HOVERBOARD_CLIENT_DIR / "duplicate_risk_log.md",
    )

# Default (backward compatibility)
CLIENT_DIR = _HOVERBOARD_CLIENT_DIR
DUP_LOG = CLIENT_DIR / "duplicate_risk_log.md"
PHASE2A_REVIEW_JSON = Path("/tmp/orin_phase2a_review_preview.json")

# ─── Phase 2A review result reader ───────────────────────────────────────────

def load_phase2a_results(client_context=None) -> dict:
    """
    Load Phase 2A review preview JSON.
    client_context is unused for Phase 2A path — kept for API consistency.
    """
    if not PHASE2A_REVIEW_JSON.exists():
        return {"jobs": []}
    return json.loads(PHASE2A_REVIEW_JSON.read_text())


# ─── Duplicate log parser ────────────────────────────────────────────────────

def parse_duplicate_log(client_context=None) -> list:
    """
    Parse duplicate_risk_log.md into structured risk dicts.
    Returns list of dicts with: level, article_a, article_b, reasons.

    Args:
        client_context: optional ClientContext object. When provided, uses
                      client-specific duplicate_risk_log.md path.
    """
    _, DUP_LOG = _get_client_duplicate_paths(client_context)
    if not DUP_LOG.exists():
        return []

    content = DUP_LOG.read_text()
    risks = re.split(r'(?=## Risk \d+:)', content)

    parsed = []
    for risk in risks:
        if not risk.strip():
            continue

        level = None
        if "[BLOCK]" in risk:
            level = "BLOCK"
        elif "[REVIEW]" in risk:
            level = "REVIEW NEEDED"
        else:
            continue

        titles = re.findall(r'\*\*Article [AB]:\*\* ([^\n]+)', risk)
        slugs = re.findall(r'Slug: `([^`]+)`', risk)
        statuses = re.findall(r'Status: (\w+)', risk)

        reasons = []
        for line in risk.split("\n"):
            if line.strip().startswith("[BLOCK]") or line.strip().startswith("[REVIEW]"):
                reasons.append(line.strip())

        if len(titles) >= 2:
            parsed.append({
                "level": level,
                "article_a_title": titles[0].strip(),
                "article_b_title": titles[1].strip(),
                "article_a_slug": slugs[0].strip() if len(slugs) > 0 else "",
                "article_b_slug": slugs[1].strip() if len(slugs) > 1 else "",
                "article_a_status": statuses[0].strip() if len(statuses) > 0 else "",
                "article_b_status": statuses[1].strip() if len(statuses) > 1 else "",
                "reasons": reasons,
            })

    return parsed


# ─── Memory record builders ──────────────────────────────────────────────────

def build_self_match_record(
    job_num: str,
    article_id: str,
    shopify_handle: str,
    local_file: str,
    reason: str,
) -> dict:
    """Build a self_match_info memory record."""
    return {
        "record_type": "self_match_info",
        "job_number": job_num,
        "article_id": article_id,
        "shopify_handle": shopify_handle,
        "local_file": local_file,
        "classification": "self_match_info",
        "reason": reason,
        "decided_by": "system",
        "severity": "info",
        "created_at": datetime.utcnow().isoformat() + "Z",
        "decision_status": None,
    }


def build_global_warning_record(
    job_num: str,
    topic: str,
    reason: str,
    related_risk_entries: list,
) -> dict:
    """Build a global_site_warning memory record."""
    return {
        "record_type": "global_site_warning",
        "job_number": job_num,
        "topic": topic,
        "classification": "global_site_warning",
        "reason": reason,
        "related_risk_log_entries": related_risk_entries,
        "severity": "info",
        "created_at": datetime.utcnow().isoformat() + "Z",
        "decision_status": None,
    }


def build_human_decision_required_record(
    job_num: str,
    current_job_title: str,
    current_job_handle: str,
    conflicting_article_id: str,
    conflicting_article_handle: str,
    conflicting_article_title: str,
    similarity_type: str,
    similarity_score: Optional[float],
    reason: str,
) -> dict:
    """Build a human_duplicate_decision_required memory record."""
    return {
        "record_type": "human_duplicate_decision_required",
        "job_number": job_num,
        "current_job_title": current_job_title,
        "current_job_handle": current_job_handle,
        "conflicting_article_id": conflicting_article_id,
        "conflicting_article_handle": conflicting_article_handle,
        "conflicting_article_title": conflicting_article_title,
        "similarity_type": similarity_type,
        "similarity_score": similarity_score,
        "classification": "human_duplicate_decision_required",
        "severity": "blocking",
        "decision_status": "pending",
        "created_at": datetime.utcnow().isoformat() + "Z",
        "decided_by": None,
        "decided_at": None,
        "reason": reason,
        "approved_action": None,
    }


# ─── Core classifier ─────────────────────────────────────────────────────────

def classify_job_duplicate(job_num: str, review_result: dict, risks: list) -> dict:
    """
    Given a Phase 2A review result dict and the parsed duplicate log risks,
    return the appropriate memory record dict.
    """
    dup_class = review_result.get("duplicate_classification", "")
    dup_detail = review_result.get("duplicate_detail", "")
    topic = review_result.get("topic", "")
    local_file = review_result.get("local_file_path", "")
    decision = review_result.get("review_decision", "")
    queue_status = review_result.get("queue_status", "")

    # Known Shopify mappings
    KNOWN_SHOPIFY = {
        "15": {"id": "1006811971932", "handle": "how-to-store-a-hoverboard-battery-safely-hoverboard-store"},
        "16": {"id": "1006814593372", "handle": "6-5-vs-8-5-inch-hoverboards-for-kids-simple-buying-guide-hoverboard-store"},
        "17": {"id": "1006818689372", "handle": "hoverboard-won-t-turn-on-safe-checks-before-you-replace-it"},
        "18": {"id": "1006819246428", "handle": "hoverboard-weight-limit-guide-for-parents"},
        "19": {"id": "1006822064476", "handle": "christmas-hoverboard-gift-guide-for-kids-uk"},
    }

    # ── Not due ─────────────────────────────────────────────────────────
    if decision == "skipped_not_due":
        return {
            "record_type": "skipped_not_due",
            "job_number": job_num,
            "reason": "Job not yet due; duplicate review skipped",
            "created_at": datetime.utcnow().isoformat() + "Z",
        }

    # ── No local file ───────────────────────────────────────────────────
    if decision == "no_local_file_to_review":
        return {
            "record_type": "no_local_file",
            "job_number": job_num,
            "reason": "No local draft file found; duplicate review skipped",
            "created_at": datetime.utcnow().isoformat() + "Z",
        }

    # ── Compliance or HTML blocked ──────────────────────────────────────
    blocking_issues = review_result.get("blocking_review_issues", [])
    if any("compliance" in b or "html_quality" in b for b in blocking_issues):
        return {
            "record_type": "blocked_by_compliance_or_html",
            "job_number": job_num,
            "reason": "Blocked by compliance or HTML quality issues, not duplicate",
            "created_at": datetime.utcnow().isoformat() + "Z",
        }

    # ── Self-match: local draft vs own Shopify article ──────────────────
    if dup_class == "self_match_info":
        shopify = KNOWN_SHOPIFY.get(job_num, {})
        article_id = shopify.get("id", "unknown")
        handle = shopify.get("handle", "")
        return build_self_match_record(
            job_num=job_num,
            article_id=article_id,
            shopify_handle=handle,
            local_file=local_file,
            reason=(
                f"Self-match: Phase 2A classified as {dup_class}. "
                f"Duplicate BLOCK is from local draft vs its own Shopify article "
                f"(article_id {article_id}). This is expected behaviour — "
                f"the article was already drafted and stored in Shopify as the same job. "
                f"Not a duplicate approval. "
                f"Detail: {dup_detail}"
            ),
        )

    # ── Global warning: not in any risk pair ───────────────────────────
    if dup_class == "global_site_warning":
        # Find any global risk entries for context
        related = []
        for risk in risks:
            reasons_str = " ".join(risk.get("reasons", []))
            related.append({
                "level": risk.get("level", ""),
                "article_a": risk.get("article_a_title", ""),
                "article_b": risk.get("article_b_title", ""),
                "reasons": risk.get("reasons", []),
            })

        return build_global_warning_record(
            job_num=job_num,
            topic=topic,
            reason=(
                f"Global site warning: Phase 2A classified as {dup_class}. "
                f"Job {job_num} ('{topic}') does not appear in any BLOCK or "
                f"REVIEW NEEDED risk pair in duplicate_risk_log.md. "
                f"The duplicate checker exit code reflects comparisons between "
                f"OTHER articles in the inventory. "
                f"Not a duplicate approval. "
                f"Detail: {dup_detail}"
            ),
            related_risk_entries=related[:3],  # limit to first 3 for preview
        )

    # ── Real duplicate vs different article — BLOCKING ──────────────────
    if dup_class == "current_job_real_duplicate":
        shopify = KNOWN_SHOPIFY.get(job_num, {})
        handle = shopify.get("handle", "")

        # Try to find the conflicting article from the duplicate log
        conflicting = None
        for risk in risks:
            # Check if this job's handle appears in the risk
            norm_handle = handle.lower().replace("-", "")
            a_slug_norm = risk.get("article_a_slug", "").lower().replace("-", "")
            b_slug_norm = risk.get("article_b_slug", "").lower().replace("-", "")

            is_a = a_slug_norm == norm_handle
            is_b = b_slug_norm == norm_handle

            if (is_a or is_b) and risk.get("level") in ("BLOCK", "REVIEW NEEDED"):
                other_title = risk.get("article_b_title") if is_a else risk.get("article_a_title")
                other_slug = risk.get("article_b_slug") if is_a else risk.get("article_a_slug")
                other_status = risk.get("article_b_status") if is_a else risk.get("article_a_status")

                # Extract similarity score from reasons
                score = None
                for reason in risk.get("reasons", []):
                    score_m = re.search(r'(?:similarity|overlap)[:\s]+(\d+\.?\d*)', reason)
                    if score_m:
                        score = float(score_m.group(1))
                        break

                conflicting = {
                    "article_title": other_title,
                    "article_slug": other_slug,
                    "article_status": other_status,
                    "similarity_type": "title+H1 similarity",
                    "similarity_score": score,
                }
                break

        if conflicting:
            return build_human_decision_required_record(
                job_num=job_num,
                current_job_title=topic,
                current_job_handle=handle,
                conflicting_article_id="unknown",  # ID not in slug
                conflicting_article_handle=conflicting["article_slug"],
                conflicting_article_title=conflicting["article_title"],
                similarity_type=conflicting["similarity_type"],
                similarity_score=conflicting["similarity_score"],
                reason=(
                    f"REAL DUPLICATE: Job {job_num} ('{topic}') is flagged as "
                    f"a duplicate against a DIFFERENT Shopify article. "
                    f"Conflicting article: '{conflicting['article_title']}' "
                    f"(slug: {conflicting['article_slug']}). "
                    f"Similarity: {conflicting['similarity_score'] or 'unknown'}. "
                    f"MUST NOT auto-approve. Operator decision required before proceeding. "
                    f"Approved actions: 'proceed_anyway', 'rewrite', 'merge', 'reject'."
                ),
            )
        else:
            # Fallback: couldn't find conflicting article in log
            return build_human_decision_required_record(
                job_num=job_num,
                current_job_title=topic,
                current_job_handle=handle,
                conflicting_article_id="unknown",
                conflicting_article_handle="unknown",
                conflicting_article_title="unknown",
                similarity_type="unknown",
                similarity_score=None,
                reason=(
                    f"REAL DUPLICATE (source unclear): Job {job_num} classified as "
                    f"{dup_class} but conflicting article not found in duplicate_risk_log.md. "
                    f"Operator review required before proceeding."
                ),
            )

    # ── Unclear classification ─────────────────────────────────────────
    return {
        "record_type": "unclear",
        "job_number": job_num,
        "duplicate_classification": dup_class,
        "duplicate_detail": dup_detail,
        "reason": f"Unclassified duplicate status: {dup_class} — {dup_detail}",
        "severity": "warning",
        "created_at": datetime.utcnow().isoformat() + "Z",
    }


# ─── Main entry point ────────────────────────────────────────────────────────

def build_duplicate_memory(job_numbers: list, client_context=None, phase2a_results=None) -> dict:
    """
    Build duplicate decision memory for specified jobs.
    Reads Phase 2A results and duplicate log, produces memory records.

    Args:
        client_context: optional ClientContext object. When provided, uses
                      client-specific duplicate_risk_log.md path.
        phase2a_results: optional dict with {"jobs": [...]} structure. When provided,
                        used directly instead of reading from the shared preview JSON.
                        This enables run-scoped Phase 2A→2B bridging without a
                        shared /tmp file.

    Returns a dict with meta and records list.
    """
    if phase2a_results is None:
        phase2a_results = load_phase2a_results(client_context)
    phase2a_by_job = {r["job_number"]: r for r in phase2a_results.get("jobs", [])}
    risks = parse_duplicate_log(client_context)

    records = []
    for num in job_numbers:
        review = phase2a_by_job.get(num, {})
        record = classify_job_duplicate(num, review, risks)
        record["job_number"] = num  # ensure consistent
        records.append(record)

    # Summary counts
    self_match = [r for r in records if r.get("record_type") == "self_match_info"]
    global_warn = [r for r in records if r.get("record_type") == "global_site_warning"]
    human_req = [r for r in records if r.get("record_type") == "human_duplicate_decision_required"]
    skipped = [r for r in records if r.get("record_type") in ("skipped_not_due", "no_local_file", "blocked_by_compliance_or_html")]

    return {
        "meta": {
            "phase": "2B",
            "mode": "dry-run",
            "run_date": get_business_today().isoformat(),
            "note": "Preview only — NOT written to production duplicate_decisions.json",
        },
        "summary": {
            "total_jobs": len(records),
            "self_match_info_count": len(self_match),
            "global_site_warning_count": len(global_warn),
            "human_duplicate_decision_required_count": len(human_req),
            "skipped_or_blocked_count": len(skipped),
        },
        "records": records,
    }
