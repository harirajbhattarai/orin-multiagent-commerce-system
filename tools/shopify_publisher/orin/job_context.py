#!/usr/bin/env python3
"""
ORIN Job Context — Canonical Selected-Job Context Module

One canonical object holds the planner-selected job information.
Every downstream phase receives this context — not hardcoded job numbers.

Responsibilities:
  - Build the context from Phase 1A + Phase 1B results
  - Serialise to /tmp/orin_selected_job_context.json
  - Provide helpers for downstream phases to read the context

Context fields (required):
  job_number        — string e.g. "21"
  job_label         — string e.g. "Job 21"
  title             — article title
  topic             — job topic
  target_keyword    — SEO target keyword
  target_date       — YYYY-MM-DD due date
  expected_draft_date — YYYY-MM-DD when draft should be ready
  queue_status      — planned | draft_created | published_live | etc.
  local_draft_path  — absolute path to local draft or null
  shopify_article_id — Shopify Article ID or null
  shopify_handle    — Shopify handle or null
  published_at      — ISO timestamp or null

Context fields (optional):
  file_path         — queue's planned file path
  planner_decision  — job_selected | no_job_due | blocked
  planner_reason    — human-readable reason
  ALREADY_CREATED_classification — null | ALREADY_CREATED_QUEUE_ALREADY_CORRECT |
                                   ALREADY_CREATED_QUEUE_RECONCILIATION_REQUIRED

ALWAYS:
  - Job number is a string ("21") throughout
  - Dates are YYYY-MM-DD strings
  - None values are JSON null
"""

import json
import sys
from pathlib import Path
from datetime import date

sys.path.insert(0, str(Path(__file__).parent))
from business_time import get_business_today
from workspace_paths import workspace_root

BASE_DIR = workspace_root()
CONTEXT_PATH = Path("/tmp/orin_selected_job_context.json")


def build_job_context(
    job_number: str,
    job_data: dict,
    planner_decision: str = "job_selected",
    planner_reason: str = "",
) -> dict:
    """
    Build a canonical job context from queue job data.

    Args:
        job_number: string job number e.g. "21"
        job_data: dict from read_queue() for this job
        planner_decision: "job_selected" | "no_job_due" | etc.
        planner_reason: human-readable reason
    """
    today = get_business_today()

    # expected_draft_date = target_date - 14 days
    expected_draft_date = None
    if job_data.get("target_date"):
        try:
            td = date.fromisoformat(job_data["target_date"])
            edd = td - __import__("datetime").timedelta(days=14)
            expected_draft_date = edd.isoformat()
        except (ValueError, TypeError):
            pass

    ctx = {
        "job_number": job_number,
        "job_label": f"Job {job_number}",
        "title": job_data.get("topic", ""),
        "topic": job_data.get("topic", ""),
        "target_keyword": job_data.get("keyword", ""),
        "target_date": job_data.get("target_date"),
        "expected_draft_date": expected_draft_date,
        "queue_status": job_data.get("queue_status", "planned"),
        "local_draft_path": None,  # resolved below
        "shopify_article_id": job_data.get("shopify_id_from_notes")
                               or job_data.get("shopify_article_id"),
        "shopify_handle": job_data.get("shopify_handle_from_notes")
                          or job_data.get("shopify_handle"),
        "published_at": job_data.get("published_at"),
        "file_path": job_data.get("queue_file_path"),
        "notes": job_data.get("notes", ""),
        "planner_decision": planner_decision,
        "planner_reason": planner_reason,
        "ALREADY_CREATED_classification": None,
        # resolved fields
        "local_draft_exists": False,
        "shopify_draft_exists": False,
        "days_until_draft": None,
        "days_overdue": None,
    }

    # Resolve local draft existence
    if job_data.get("queue_file_path"):
        full = BASE_DIR / job_data["queue_file_path"]
        if full.exists():
            ctx["local_draft_path"] = str(full)
            ctx["local_draft_exists"] = True

    # Resolve overdue status
    if expected_draft_date:
        try:
            ed_date = date.fromisoformat(expected_draft_date)
            days_diff = (today - ed_date).days
            ctx["days_until_draft"] = -days_diff  # negative = overdue
            ctx["days_overdue"] = max(0, -days_diff)
        except (ValueError, TypeError):
            pass

    return ctx


def write_job_context(ctx: dict, path: Path = None) -> None:
    """Serialise job context to JSON file for downstream phases."""
    p = path or CONTEXT_PATH
    p.write_text(json.dumps(ctx, indent=2, default=str))


def read_job_context(path: Path = None) -> dict:
    """Load job context from JSON file."""
    p = path or CONTEXT_PATH
    if not p.exists():
        return None
    return json.loads(p.read_text())


def resolve_local_draft_path(ctx: dict) -> str | None:
    """
    Resolve the local draft path for a job context.
    Returns the planned file path from queue if no local draft exists.
    """
    if ctx.get("local_draft_path"):
        return ctx["local_draft_path"]
    # Fall back to queue file_path
    fp = ctx.get("file_path")
    if fp:
        full = BASE_DIR / fp
        if full.exists():
            return str(full)
    return None


def resolve_planned_handle(ctx: dict) -> str | None:
    """
    Resolve the planned URL slug/handle for a job.
    Uses shopify_handle if available; otherwise generates from topic.
    Uses canonical handle normalisation from handle_utils.
    """
    if ctx.get("shopify_handle"):
        return ctx["shopify_handle"]
    topic = ctx.get("title", "")
    # Use shared canonical handle utility — single source of truth
    from handle_utils import normalise_shopify_handle
    return normalise_shopify_handle(topic)


def is_already_created(ctx: dict) -> tuple[bool, str | None]:
    """
    Check if the selected job already has a Shopify draft.

    Returns (is_already_created, classification).
    classification:
      ALREADY_CREATED_QUEUE_ALREADY_CORRECT — Shopify draft exists, queue already draft_created
      ALREADY_CREATED_QUEUE_RECONCILIATION_REQUIRED — Shopify draft exists, queue still planned
      None — no Shopify draft found
    """
    if not ctx.get("shopify_article_id"):
        return False, None

    if not ctx.get("shopify_draft_exists"):
        # Verify by checking local inventory
        inv_path = BASE_DIR / "clients" / "hoverboard_store" / "content_engine" / "shopify_inventory.json"
        if inv_path.exists():
            import json as _json
            inv = _json.loads(inv_path.read_text())
            article_ids = [str(a["id"]) for a in inv]
            if ctx["shopify_article_id"] in article_ids:
                ctx["shopify_draft_exists"] = True

    if not ctx.get("shopify_draft_exists"):
        return False, None

    # Shopify draft confirmed
    if ctx.get("queue_status") == "draft_created":
        return True, "ALREADY_CREATED_QUEUE_ALREADY_CORRECT"
    else:
        return True, "ALREADY_CREATED_QUEUE_RECONCILIATION_REQUIRED"


def classify_selected_job(ctx: dict) -> str:
    """
    Classify the selected job's current state.
    Returns a short classification string.
    """
    if ctx.get("shopify_article_id") and ctx.get("shopify_draft_exists"):
        if ctx.get("queue_status") == "draft_created":
            return "ALREADY_CREATED_QUEUE_ALREADY_CORRECT"
        return "ALREADY_CREATED_QUEUE_RECONCILIATION_REQUIRED"

    if ctx.get("local_draft_exists"):
        if ctx.get("shopify_article_id"):
            return "LOCAL_DRAFT_EXISTS_SHOPIFY_MISSING"
        return "LOCAL_DRAFT_EXISTS_SHOPIFY_PLANNED"

    if ctx.get("queue_status") == "planned":
        dd = ctx.get("expected_draft_date")
        if dd:
            from datetime import date as _date
            try:
                ed = _date.fromisoformat(dd)
                if (get_business_today() - ed).days > 0:
                    return "PLANNED_OVERDUE_NO_DRAFT"
            except ValueError:
                pass
        return "PLANNED_NOT_YET_DUE"

    return "UNKNOWN_STATE"


if __name__ == "__main__":
    # Diagnostic: print current job context if file exists
    ctx = read_job_context()
    if ctx:
        print(json.dumps(ctx, indent=2))
    else:
        print("No job context found at", CONTEXT_PATH)
