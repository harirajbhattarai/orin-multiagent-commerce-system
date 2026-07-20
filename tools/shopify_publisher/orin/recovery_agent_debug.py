#!/usr/bin/env python3
"""
ORIN Recovery Agent — Phase 1C
Stuck-state detection and recovery categorisation.

Reads:
  - Queue file
  - Shopify inventory (normalised + raw)
  - Local draft filesystem
  - Cron runs log
  - State Agent logic (via state_agent.py)

Produces:
  - recovery_audit dict with active, historical, no_action categories
  - NO writes to queue, Shopify, or production state files
"""

import sys
import re
import json
from datetime import date, timedelta
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent))
from state_agent import (
    read_queue,
    read_shopify_inventory,
    read_approved_handles,
    local_file_for_job,
    resolve_shopify_article,
    detect_state,
    days_until,
    today,
    BASE_DIR,
    CLIENT_DIR,
    DRAFTS_DIR,
)

# ─── Cron log reader ──────────────────────────────────────────────────────────

def read_cron_runs():
    """Parse cron_runs.md into a list of run entries."""
    cron_path = CLIENT_DIR / "cron_runs.md"
    if not cron_path.exists():
        return []
    content = cron_path.read_text()

    entries = []
    # Split into individual run blocks
    blocks = re.split(r"\n(?=Last run:)", content.strip())
    for block in blocks:
        if not block.strip():
            continue
        entry = {"raw": block}
        m_job = re.search(r"^Job:\s*(.+?)$", block, re.M)
        m_result = re.search(r"^Result:\s*(.+?)$", block, re.M)
        m_date = re.search(r"^Last run:\s*(.+?)$", block, re.M)
        m_reason = re.search(r"^Reason:\s*(.+?)$", block, re.M)
        if m_job:
            entry["job"] = m_job.group(1).strip()
        if m_result:
            entry["result"] = m_result.group(1).strip()
        if m_date:
            entry["date"] = m_date.group(1).strip()
        if m_reason:
            entry["reason"] = m_reason.group(1).strip()
        entries.append(entry)
    return entries


def detect_cron_loops(cron_entries: list) -> dict:
    """
    Detect jobs that appear repeatedly with 'file already exists' result.
    Returns dict: job -> {count, entries, loop: bool}
    """
    job_runs = defaultdict(list)
    for e in cron_entries:
        if e.get("job"):
            job_runs[e["job"]].append(e)

    loops = {}
    for job, runs in job_runs.items():
        file_exists = [r for r in runs if r.get("result") == "file already exists"]
        if len(file_exists) >= 3:
            loops[job] = {
                "count": len(file_exists),
                "entries": file_exists,
                "loop": True,
            }
        else:
            loops[job] = {"count": len(file_exists), "loop": False}
    return loops


# ─── Recovery categorisation ───────────────────────────────────────────────────

CATEGORIES = [
    "queue_planned_local_exists_shopify_missing",   # 1
    "queue_planned_shopify_exists",                 # 2
    "local_file_exists_shopify_missing",            # 3
    "shopify_draft_exists_queue_not_updated",       # 4
    "cron_file_exists_loop",                        # 5
    "stale_in_progress",                            # 6
]


def run_recovery_audit(job_numbers: list = None) -> dict:
    """
    Main audit: categorise every job into active, historical, or no_action.
    """
    import traceback as _tb; [open("/tmp/phase1c_error.log","w").write(_tb.format_exc()) or None for _ in [None]]
    queue = read_queue()
    shopify_inv = read_shopify_inventory()
    approved = read_approved_handles()
    cron_entries = read_cron_runs()
    cron_loops = detect_cron_loops(cron_entries)

    active = []
    historical = []
    no_action = []

    jobs_to_check = job_numbers if job_numbers else list(queue.keys())

    for num in sorted(jobs_to_check, key=int):
        if num not in queue:
            continue
        job = queue[num]
        queue_status = job.get("queue_status", "")
        local_exists, local_path = local_file_for_job(job)
        shopify_info = resolve_shopify_article(job, shopify_inv, approved)
        local_info = {"exists": local_exists, "path": local_path}
        state_name, issues, action = detect_state(job, shopify_info, local_info, approved)
        approved_handle_info = approved.get(num, {})

        item = {
            "job_number": num,
            "topic": job.get("topic"),
            "queue_status": queue_status,
            "detected_state": state_name,
            "local_draft_exists": local_exists,
            "local_file_path": local_path,
            "shopify_article_id": shopify_info["shopify_article_id"],
            "shopify_handle": shopify_info["shopify_handle"],
            "shopify_status": shopify_info["shopify_status"],
            "published_at": shopify_info["published_at"],
            "approved_handle": approved_handle_info.get("handle"),
            "issues": issues,
            "recommended_action": action,
            "recovery_categories": [],
            "is_historical": False,
            "is_active": False,
            "dry_run_action": None,  # what would be done (not performed)
        }

        # ── Category 1: queue planned + local file + no Shopify ────────────
        if (queue_status == "planned"
                and local_exists
                and not shopify_info["shopify_article_id"]):
            item["recovery_categories"].append("queue_planned_local_exists_shopify_missing")
            item["dry_run_action"] = (
                "Local draft exists but Shopify draft missing. "
                "Would push to Shopify via Publisher Agent (handle-preservation check required). "
                "NOT PERFORMED — dry-run only."
            )
            item["is_active"] = True

        # ── Category 2: queue planned + Shopify draft exists ──────────────
        if (queue_status == "planned"
                and shopify_info["shopify_article_id"]):
            item["recovery_categories"].append("queue_planned_shopify_exists")
            item["dry_run_action"] = (
                "Shopify draft exists but queue not updated. "
                "Would reconcile queue: update status to draft_created and record metadata. "
                "NOT PERFORMED — dry-run only."
            )
            item["is_active"] = True

        # ── Category 3: local file exists + no Shopify article ─────────────
        if (local_exists
                and not shopify_info["shopify_article_id"]):
            item["recovery_categories"].append("local_file_exists_shopify_missing")
            item["dry_run_action"] = (
                "Local draft exists but no Shopify article found. "
                "Would push to Shopify via Publisher Agent. "
                "NOT PERFORMED — dry-run only."
            )
            item["is_active"] = True

        # ── Category 4: Shopify draft exists + queue not draft_created ────
        if (shopify_info["shopify_article_id"]
                and queue_status not in ("draft_created", "published_live", "published")):
            item["recovery_categories"].append("shopify_draft_exists_queue_not_updated")
            item["dry_run_action"] = (
                f"Shopify draft exists but queue status is '{queue_status}'. "
                "Would reconcile: update queue status and record Shopify metadata. "
                "NOT PERFORMED — dry-run only."
            )
            item["is_active"] = True

        # ── Category 5: cron file-exists loop ──────────────────────────────
        if num in cron_loops and cron_loops[num]["loop"]:
            item["recovery_categories"].append("cron_file_exists_loop")
            loop_info = cron_loops[num]
            item["dry_run_action"] = (
                f"Cron attempted Job {num} {loop_info['count']} times consecutively "
                f"with 'file already exists'. Would inspect job state, confirm queue and Shopify "
                f"are clean, and mark loop as resolved. NOT PERFORMED — dry-run only."
            )
            # Check if this is already resolved (queue=clean and Shopify=clean)
            if state_name == "clean_draft_created":
                item["is_historical"] = True
                item["recovery_categories"].append("cron_loop_resolved")
            else:
                item["is_active"] = True

        # ── Category 6: stale in_progress (>7 days) ───────────────────────
        if queue_status == "in_progress":
            # Try to detect staleness from notes/timestamps
            notes = job.get("notes", "")
            m_updated = re.search(r"updated[_-]at:\s*(.+?)(?:\n|$)", notes, re.I)
            if m_updated:
                try:
                    updated_date = date.fromisoformat(m_updated.group(1).strip()[:10])
                    if (today() - updated_date).days > 7:
                        item["recovery_categories"].append("stale_in_progress")
                        item["dry_run_action"] = (
                            f"Job {num} stuck in 'in_progress' for "
                            f"{(today() - updated_date).days} days (>7 day threshold). "
                            f"Would flag for human review. NOT PERFORMED — dry-run only."
                        )
                        item["is_active"] = True
                except ValueError:
                    pass

        # ── No recovery needed ─────────────────────────────────────────────
        if not item["recovery_categories"]:
            item["recovery_categories"].append("no_recovery_needed")
            item["dry_run_action"] = "No recovery action needed — job state is clean or waiting."
            item["is_active"] = False
            item["is_historical"] = False
            no_action.append(item)
        elif item["is_historical"] and not item["is_active"]:
            historical.append(item)
        else:
            active.append(item)

    return {
        "active_recovery_items": active,
        "historical_resolved_items": historical,
        "no_action_needed_items": no_action,
        "cron_loops_detected": {
            job: info for job, info in cron_loops.items()
            if info["loop"]
        },
        "meta": {
            "jobs_audited": len(jobs_to_check),
            "active_count": len(active),
            "historical_count": len(historical),
            "no_action_count": len(no_action),
            "run_date": str(today()),
        }
    }
