#!/usr/bin/env python3
"""
ORIN Canonical Queue Parser — Single Source of Truth for queue file parsing.

Replaces independent competing parsers in:
  - publisher_agent.py (get_queue_article_id, queue status regex)
  - writer_agent.py (_parse_queue — rigid field-order regex)

Canonical parser in state_agent.py (read_queue) is the reference implementation.
This module formalises it as an importable, tested API.

API:
  parse_queue_file(queue_path) -> dict[job_number, job_dict]
  get_queue_job(queue_path, job_number) -> job_dict | None

Regression tested against Jobs 15–21.
"""

import re
from pathlib import Path
from typing import Optional

# ─── Canonical heading regex ───────────────────────────────────────────────────
# Matches: ## Job 21
# Supports job numbers with or without "Job " prefix in search patterns.
HEADING_RE = re.compile(r"^## Job (\d+)\n(.*?)(?=^## Job |\Z)", re.M | re.S)

# ─── Field extractors ─────────────────────────────────────────────────────────

def _extract_field(block: str, key: str) -> Optional[str]:
    """Extract 'Key: value' from a job block. Returns None if not found."""
    # Try "Key: value" on its own line first (most common)
    m = re.search(rf"^{re.escape(key)}:\s*(.+?)(?:\n|$)", block, re.M)
    if m:
        return m.group(1).strip()
    return None

def _extract_shopify_id_from_notes(notes: str) -> Optional[str]:
    """Extract Shopify article ID from notes block."""
    # Supports: "Article ID: 123", "Shopify article ID: 123", "Shopify Article ID: 123"
    m = re.search(r"(?:Shopify\s+)?Article\s+ID:\s*(\S+)", notes, re.IGNORECASE)
    if m:
        val = m.group(1).rstrip(".")
        # Validate it's numeric
        if val.isdigit():
            return val
    return None

def _extract_handle_from_notes(notes: str) -> Optional[str]:
    """Extract Shopify handle from notes block."""
    # Supports: "Handle: some-handle", "Shopify handle: some-handle"
    m = re.search(r"(?:Shopify\s+)?[Hh]andle:\s*([\w-]+)", notes)
    if m:
        return m.group(1).strip()
    return None

# ─── Main parser ───────────────────────────────────────────────────────────────

def parse_queue_file(queue_path) -> dict:
    """
    Parse content_queue_3_months.md and return a dict keyed by job number string.

    Each job dict contains:
      job_number       — string, e.g. "21"
      job_label        — string, e.g. "Job 21"
      title            — Topic field
      target_keyword   — Target keyword field
      date_target      — Date target field
      cluster          — Cluster field
      decision         — Decision field
      status           — Status field (queue_status alias)
      queue_status     — same as status
      file_path        — File field (local draft path hint)
      shopify_article_id — extracted from notes
      shopify_handle   — extracted from notes
      notes            — raw notes block

    Returns:
      dict[str, dict]
    """
    content = Path(queue_path).read_text(encoding="utf-8")
    jobs = {}

    for m in HEADING_RE.finditer(content):
        num = m.group(1)          # "21"
        block = m.group(2)        # everything after "## Job 21\n"

        title        = _extract_field(block, "Topic")           or ""
        target_kw    = _extract_field(block, "Target keyword")  or ""
        date_target  = _extract_field(block, "Date target")     or ""
        cluster      = _extract_field(block, "Cluster")         or ""
        decision     = _extract_field(block, "Decision")        or ""
        status       = _extract_field(block, "Status")          or ""
        file_path    = _extract_field(block, "File")            or ""

        notes_raw = re.search(r"^Notes:\n(.*)", block, re.M | re.S)
        notes = notes_raw.group(1).strip() if notes_raw else ""

        shopify_article_id = _extract_shopify_id_from_notes(notes)
        shopify_handle     = _extract_handle_from_notes(notes)

        jobs[num] = {
            "job_number":         num,
            "job_label":          f"Job {num}",
            "title":              title,
            "target_keyword":     target_kw,
            "date_target":        date_target,
            "cluster":            cluster,
            "decision":           decision,
            "status":             status,
            "queue_status":       status,
            "file_path":          file_path,
            "shopify_article_id": shopify_article_id,
            "shopify_handle":     shopify_handle,
            "notes":              notes,
        }

    return jobs


def get_queue_job(queue_path, job_number) -> Optional[dict]:
    """
    Get a single job dict from the queue by job number.

    Args:
        queue_path:   path to content_queue_3_months.md
        job_number:   job number as string or int (e.g. "21" or 21)

    Returns:
        job dict or None if not found.
    """
    jobs = parse_queue_file(queue_path)
    return jobs.get(str(job_number))


# ─── Regression tests ─────────────────────────────────────────────────────────

_REGRESSION_CASES = [
    {
        "job": "20",
        "expected_status": "draft_created",
        "expected_article_id": "1006845985116",
        "expected_handle": "best-hoverboard-accessories-safer-riding-uk-2026",
    },
    {
        "job": "21",
        "expected_status": "planned",
        "expected_article_id": None,
        "expected_handle": None,
    },
]

def run_regressions(queue_path: str) -> dict:
    """Run regression tests against known jobs. Returns results dict."""
    results = {}
    for case in _REGRESSION_CASES:
        job_num = case["job"]
        job = get_queue_job(queue_path, job_num)
        if job is None:
            results[job_num] = {"parsed": False, "error": "job not found"}
            continue

        status_ok  = job.get("queue_status") == case["expected_status"]
        id_ok      = job.get("shopify_article_id") == case["expected_article_id"]
        handle_ok  = job.get("shopify_handle") == case["expected_handle"]

        results[job_num] = {
            "parsed":          True,
            "job_number":      job.get("job_number"),
            "job_label":       job.get("job_label"),
            "queue_status":    job.get("queue_status"),
            "shopify_article_id": job.get("shopify_article_id"),
            "shopify_handle":  job.get("shopify_handle"),
            "title":           job.get("title"),
            "status_match":    status_ok,
            "article_id_match": id_ok,
            "handle_match":     handle_ok,
            "all_ok":          status_ok and id_ok and handle_ok,
        }

    return results


if __name__ == "__main__":
    import json
    import sys

    queue_path = sys.argv[1] if len(sys.argv) > 1 else "clients/hoverboard_store/content_engine/content_queue_3_months.md"
    results = run_regressions(queue_path)
    print(json.dumps(results, indent=2, default=str))
