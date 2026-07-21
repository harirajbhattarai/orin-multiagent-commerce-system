#!/usr/bin/env python3
"""
ORIN State Agent — Phase 1A
Read-only state detection for Hoverboard Store content jobs.

Reads:
  - Queue file
  - Shopify inventory (normalised + raw)
  - Local draft filesystem
  - ORIN preflight rules

Produces:
  - job_state dict with detected state per job
  - issues list
  - NO writes to queue, Shopify, or production state files
"""

import json
import re
import os
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent))
from business_time import get_business_today
from workspace_paths import workspace_root

BASE_DIR = workspace_root()
CLIENT_DIR = BASE_DIR / "clients" / "hoverboard_store" / "content_engine"
DRAFTS_DIR = CLIENT_DIR / "drafts"
RULES_FILE = CLIENT_DIR / "orin_preflight_rules.md"
QUEUE_FILE = CLIENT_DIR / "content_queue_3_months.md"
SHOPIFY_INV = CLIENT_DIR / "shopify_inventory.json"
SHOPIFY_RAW = CLIENT_DIR / "shopify_inventory_raw.json"
APPROVED_HANDLES_FILE = CLIENT_DIR / "orin_preflight_rules.md"

# ─── Date helpers ─────────────────────────────────────────────────────────────

def today() -> date:
    """Return the ORIN business date (Europe/London). Respects --as-of-date if set."""
    return get_business_today()

def draft_due_date(target_date_str: str) -> str:
    """target_date minus 14 days."""
    td = date.fromisoformat(target_date_str)
    dd = td - timedelta(days=14)
    return dd.isoformat()

def days_until(d: str) -> int:
    return (date.fromisoformat(d) - today()).days

# ─── Queue reader ─────────────────────────────────────────────────────────────

def read_queue() -> dict:
    """Parse content_queue_3_months.md into a dict keyed by job number."""
    content = QUEUE_FILE.read_text()
    jobs = {}
    for m in re.finditer(r"^## Job (\d+)\n(.*?)(?=^## |\Z)", content, re.M | re.S):
        num = m.group(1)
        block = m.group(2)
        def f(key):
            m = re.search(rf"{key}:\s*(.+?)(?=\n)", block, re.M)
            return m.group(1).strip() if m else None
        target = f("Date target")
        topic = f("Topic")
        status = f("Status")
        keyword = f("Target keyword")
        file_path = f("File")
        notes_raw = re.search(r"Notes:\n(.*)", block, re.S)
        notes = notes_raw.group(1).strip() if notes_raw else ""

        # Extract any Shopify ID from notes — supports both "Article ID:" and "Shopify article ID:"
        shopify_id_note = re.search(r"(?:Shopify\s+)?Article\s+ID:\s*(\S+)", notes, re.IGNORECASE)
        shopify_handle_note = re.search(r"(?:Shopify\s+)?Handle:\s*([\w-]+)", notes, re.IGNORECASE)

        jobs[num] = {
            "job_number": num,
            "topic": topic,
            "queue_status": status,
            "target_date": target,
            "expected_draft_date": draft_due_date(target) if target else None,
            "keyword": keyword,
            "queue_file_path": file_path,
            "notes": notes,
            "shopify_id_from_notes": shopify_id_note.group(1).rstrip(".") if shopify_id_note else None,
            "shopify_handle_from_notes": shopify_handle_note.group(1).strip() if shopify_handle_note else None,
        }
    return jobs

# ─── Shopify inventory reader ─────────────────────────────────────────────────

def read_shopify_inventory() -> dict:
    """Read normalised shopify_inventory.json into a dict keyed by article ID string."""
    articles = json.loads(SHOPIFY_INV.read_text())
    by_id = {}
    by_handle = {}
    for a in articles:
        sid = str(a["id"])
        by_id[sid] = a
        by_handle[a["handle"]] = a
    return {"by_id": by_id, "by_handle": by_handle, "all": articles}

def read_shopify_raw() -> list:
    """Return all articles from shopify_inventory_raw.json."""
    raw = json.loads(SHOPIFY_RAW.read_text())
    articles = []
    for blog in raw.get("blogs", []):
        for a in blog.get("articles", []):
            articles.append(a)
    return articles

# ─── Local filesystem check ───────────────────────────────────────────────────

def local_file_for_job(job: dict) -> tuple:
    """
    Returns (exists: bool, path: str or None)
    Tries the queue file path first, then glob for similar names.
    """
    qp = job.get("queue_file_path")
    if qp:
        full = BASE_DIR / qp
        if full.exists():
            return True, str(full)
        # Try just filename match in drafts dir
        filename = full.name
        matches = list(DRAFTS_DIR.glob(filename))
        if matches:
            return True, str(matches[0])
        matches = list(DRAFTS_DIR.glob(filename.replace(".html", "*.html")))
        if matches:
            return True, str(matches[0])

    # Fuzzy match by job number and topic keywords
    topic = (job.get("topic") or "").lower()
    num = job.get("job_number", "")

    # Known cross-reference for jobs with known local files
    known_local_files = {
        "15": "how-to-store-a-hoverboard-battery-safely-hoverboard-store.html",
        "16": "6-5-vs-8-5-inch-hoverboards-for-kids-simple-buying-guide-hoverboard-store.html",
        "17": "hoverboard-wont-turn-on-safe-checks-before-replace-it.html",
        "18": "hoverboard-weight-limit-guide-for-parents.html",
        "19": "christmas-hoverboard-gift-guide-for-kids.html",
    }
    if num in known_local_files:
        p = DRAFTS_DIR / known_local_files[num]
        if p.exists():
            return True, str(p)

    return False, None

# ─── Approved handle reader ───────────────────────────────────────────────────

def read_approved_handles() -> dict:
    """Parse orin_preflight_rules.md for approved handles."""
    if not APPROVED_HANDLES_FILE.exists():
        return {}
    content = APPROVED_HANDLES_FILE.read_text()
    handles = {}
    # Match table rows: Job ID | Article ID | Approved Handle
    for m in re.finditer(r"\|\s*Job (\d+)[^|]*\|\s*`?([^`]+)`?\s*\|\s*`([^`]+)`", content):
        job_num = m.group(1)
        article_id = m.group(2).strip()
        handle = m.group(3).strip()
        handles[job_num] = {"article_id": article_id, "handle": handle}
    return handles

# ─── Shopify ID resolution ────────────────────────────────────────────────────

def resolve_shopify_article(job: dict, shopify_inv: dict, approved_handles: dict) -> dict:
    """
    Find the matching Shopify article for a job.
    Priority:
      1. Article ID found in queue notes
      2. Article ID from approved_handles
      3. Handle match via approved_handles
      4. Manual known mapping (fallback for dry-run)
    """
    num = job["job_number"]

    # Known Shopify IDs from the inventory audit
    KNOWN_IDS = {
        "15": "1006811971932",
        "16": "1006814593372",
        "17": "1006818689372",
        "18": "1006819246428",
        "19": "1006822064476",
    }

    # Try queue notes first
    if job.get("shopify_id_from_notes"):
        sid = job["shopify_id_from_notes"].rstrip(".")
        if sid in shopify_inv["by_id"]:
            a = shopify_inv["by_id"][sid]
            return {
                "shopify_article_id": sid,
                "shopify_handle": a["handle"],
                "shopify_status": "published" if a.get("published_at") else "draft",
                "published_at": a.get("published_at"),
            }

    # Try known IDs
    if num in KNOWN_IDS:
        sid = KNOWN_IDS[num]
        if sid in shopify_inv["by_id"]:
            a = shopify_inv["by_id"][sid]
            return {
                "shopify_article_id": sid,
                "shopify_handle": a["handle"],
                "shopify_status": "published" if a.get("published_at") else "draft",
                "published_at": a.get("published_at"),
            }

    return {
        "shopify_article_id": None,
        "shopify_handle": None,
        "shopify_status": None,
        "published_at": None,
    }

# ─── Local URL slug extractor ─────────────────────────────────────────────────

def extract_url_slug(html_path: str) -> Optional[str]:
    """Extract url_slug from HTML comment block."""
    if not html_path or not Path(html_path).exists():
        return None
    content = Path(html_path).read_text()
    m = re.search(r"(?i)URL slug:\s*(.+?)(?:\n|$)", content)
    return m.group(1).strip() if m else None

# ─── State detector ───────────────────────────────────────────────────────────

DETECTION_RULES = [
    ("clean_draft_created",         # queue=draft_created, Shopify exists, not published
        lambda j, s, l, a:
            j["queue_status"] == "draft_created"
            and s["shopify_article_id"] is not None
            and s["shopify_status"] == "draft"),

    ("queue_needs_reconciliation",   # queue=planned, Shopify draft exists
        lambda j, s, l, a:
            j["queue_status"] == "planned"
            and s["shopify_article_id"] is not None
            and s["shopify_status"] == "draft"),

    ("needs_shopify_push",           # queue=planned, local file exists, no Shopify draft
        lambda j, s, l, a:
            j["queue_status"] == "planned"
            and l["exists"]
            and s["shopify_article_id"] is None),

    ("due_for_local_draft",         # queue=planned, no local file, draft due
        lambda j, s, l, a:
            j["queue_status"] == "planned"
            and not l["exists"]
            and j.get("expected_draft_date")
            and days_until(j["expected_draft_date"]) <= 0),

    ("waiting_not_due",              # queue=planned, no local file, draft not due
        lambda j, s, l, a:
            j["queue_status"] == "planned"
            and not l["exists"]
            and j.get("expected_draft_date")
            and days_until(j["expected_draft_date"]) > 0),

    ("queue_planned_no_file_no_shopify",  # queue=planned, nothing exists yet
        lambda j, s, l, a:
            j["queue_status"] == "planned"
            and not l["exists"]
            and s["shopify_article_id"] is None),
]

def detect_state(job: dict, shopify_info: dict, local_info: dict, approved: dict) -> tuple:
    """Returns (detected_state, issues_list)."""
    num = job["job_number"]
    state = None
    issues = []

    for state_name, check_fn in DETECTION_RULES:
        if check_fn(job, shopify_info, local_info, approved):
            state = state_name
            break

    if not state:
        state = "unknown"

    # Issue: handle mismatch / resolution
    if shopify_info.get("shopify_handle") and local_info.get("path"):
        local_slug = extract_url_slug(local_info["path"])
        shopify_handle = shopify_info["shopify_handle"]
        approved_handle = approved.get(num, {}).get("handle")

        if approved_handle and approved_handle != shopify_handle:
            # Approved handle explicitly conflicts with Shopify handle — BLOCK
            issues.append({
                "type": "approved_handle_conflicts_with_shopify_handle",
                "severity": "high",
                "detail": (
                    f"Approved handle ('{approved_handle}') differs from "
                    f"Shopify handle ('{shopify_handle}'). "
                    f"STOP — resolve conflict before updating Shopify."
                )
            })
        elif local_slug and local_slug != shopify_handle and approved_handle == shopify_handle:
            # Local slug differs from Shopify handle, but approved_handle == Shopify handle
            # This is resolved — non-blocking
            issues.append({
                "type": "handle_mismatch_resolved_by_approved_handle",
                "severity": "info",
                "detail": (
                    f"Local url_slug ('{local_slug}') differs from Shopify handle "
                    f"('{shopify_handle}'), but approved_handle is set to Shopify handle "
                    f"and is locked. Non-blocking — Shopify handle will be preserved."
                )
            })
        elif local_slug and not approved_handle:
            # No approved handle and slug differs from Shopify — BLOCK
            issues.append({
                "type": "handle_mismatch_requires_decision",
                "severity": "medium",
                "detail": (
                    f"Local url_slug ('{local_slug}') differs from Shopify handle "
                    f"('{shopify_handle}'). No approved_handle set. "
                    f"STOP — require explicit operator decision."
                )
            })

    # Issue: local file exists but queue still planned (possible cron loop residue)
    if local_info["exists"] and job["queue_status"] == "planned":
        issues.append({
            "type": "local_file_without_queue_update",
            "severity": "low",
            "detail": "Local draft file exists but queue status is still 'planned' — possible stale cron state"
        })

    # Recommended next action
    action = recommend_action(state, issues, job)

    return state, issues, action

def recommend_action(state: str, issues: list, job: dict) -> str:
    issue_types = [i["type"] for i in issues]
    severities = {i["type"]: i["severity"] for i in issues}

    if "approved_handle_conflicts_with_shopify_handle" in issue_types:
        return "STOP — approved handle conflicts with Shopify handle. Resolve before any update."
    if "handle_mismatch_requires_decision" in issue_types:
        return "STOP — operator must decide approved handle before any Shopify update"
    if "handle_mismatch_resolved_by_approved_handle" in issue_types:
        return "No action needed — draft is clean; Shopify handle locked via approved_handle"
    if state == "clean_draft_created":
        return "No action needed — draft is clean"
    if state == "queue_needs_reconciliation":
        return "Reconcile queue: update queue_status to draft_created and record Shopify metadata"
    if state == "needs_shopify_push":
        return "Push local draft to Shopify via Publisher Agent (handle-preservation check required)"
    if state == "due_for_local_draft":
        return "Create local draft via Writer Agent"
    if state == "waiting_not_due":
        return "Wait — draft not yet due"
    if state == "queue_planned_no_file_no_shopify":
        dd = job.get("expected_draft_date", "?")
        return f"Wait — draft date is {dd}"
    return f"Manual review required (state: {state})"

# ─── Main state builder ──────────────────────────────────────────────────────

def build_job_states(job_numbers: list) -> list:
    """Build full state dict for specified job numbers."""
    queue = read_queue()
    shopify_inv = read_shopify_inventory()
    approved_handles = read_approved_handles()

    results = []
    for num in job_numbers:
        if num not in queue:
            continue
        job = queue[num]
        local_exists, local_path = local_file_for_job(job)
        shopify_info = resolve_shopify_article(job, shopify_inv, approved_handles)
        local_info = {"exists": local_exists, "path": local_path}
        state, issues, action = detect_state(job, shopify_info, local_info, approved_handles)

        approved = approved_handles.get(num, {})
        results.append({
            "job_number": num,
            "topic": job["topic"],
            "queue_status": job["queue_status"],
            "target_date": job["target_date"],
            "expected_draft_date": job["expected_draft_date"],
            "days_until_draft": days_until(job["expected_draft_date"]) if job.get("expected_draft_date") else None,
            "local_draft_exists": local_exists,
            "local_file_path": local_path,
            "shopify_article_id": shopify_info["shopify_article_id"],
            "shopify_handle": shopify_info["shopify_handle"],
            "shopify_status": shopify_info["shopify_status"],
            "published_at": shopify_info["published_at"],
            "approved_handle": approved.get("handle"),
            "detected_state": state,
            "issues_found": issues,
            "recommended_next_action": action,
        })

    return results

def to_markdown_table(rows: list) -> str:
    lines = []
    header = (
        "| Job | Queue | State | Shopify ID | Shopify Handle | "
        "Local File | Draft Due | Issues | Next Action |"
    )
    divider = header.replace("|", "|").replace("—", "-")
    # rebuild divider
    divider = "|---|---|---|---|---|---|---|---|---|"
    lines.append(header)
    lines.append(divider)
    for r in rows:
        issues_s = "; ".join([i["type"] for i in r["issues_found"]]) or "none"
        draft = r["expected_draft_date"] or "?"
        lines.append(
            f"| Job {r['job_number']} | {r['queue_status']} | "
            f"{r['detected_state']} | {r['shopify_article_id'] or '—'} | "
            f"{r['shopify_handle'] or '—'} | "
            f"{'yes' if r['local_draft_exists'] else 'no'} | "
            f"{draft} ({r['days_until_draft']}d) | "
            f"{issues_s} | {r['recommended_next_action']} |"
        )
    return "\n".join(lines)
