#!/usr/bin/env python3
"""
HCS Gadgets — ORIN Phase 1B: Planner Agent Dry-Run

Read-only planning for HCS content queue.
Reads Phase 1A state and queue, decides next eligible job.
Writes preview to /tmp/hcs_phase1b_planner_preview.json

NEVER creates drafts, never touches Shopify, never updates queue.

Output: /tmp/hcs_phase1b_planner_preview.json
"""

import json
import re
from pathlib import Path
from datetime import datetime, date, timezone

# ─── PATHS ────────────────────────────────────────────────────────────────────

BASE_DIR    = Path("/data/.openclaw/workspace")
CLIENT_DIR  = BASE_DIR / "clients" / "hcs_gadgets" / "content_engine"
QUEUE_PATH  = CLIENT_DIR / "content_queue_3_months.md"
CONFIG_PATH = CLIENT_DIR / "hcs_client_config_draft.json"
STATE_JSON  = Path("/tmp/hcs_phase1a_state_preview.json")
JSON_OUTPUT = Path("/tmp/hcs_phase1b_planner_preview.json")

TODAY = date(2026, 7, 1)

# ─── HELPERS ──────────────────────────────────────────────────────────────────

def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"  [{ts}] {msg}")


def read_json(path):
    try:
        return json.loads(Path(path).read_text())
    except Exception:
        return None


def days_until(date_str):
    if not date_str or date_str.upper() == "TBD":
        return None
    try:
        return (date.fromisoformat(date_str) - TODAY).days
    except ValueError:
        return None


def parse_queue():
    """Parse content_queue_3_months.md and return list of job dicts."""
    if not QUEUE_PATH.exists():
        return []

    content = QUEUE_PATH.read_text()
    jobs = []

    for m in re.finditer(
        r"^## Job (\d+)\n(.*?)(?=^## |\Z)",
        content,
        re.M | re.S
    ):
        num   = m.group(1)
        block = m.group(2)

        def f(key):
            mm = re.search(rf"{key}:\s*(.+?)(?=\n)", block, re.M)
            return mm.group(1).strip() if mm else None

        target  = f("Date target")
        topic   = f("Topic")
        status  = f("Status")
        keyword = f("Target keyword")
        file_p  = f("File")

        notes_m = re.search(r"Notes:\n(.*)", block, re.S)
        notes   = notes_m.group(1).strip() if notes_m else ""

        sid_m    = re.search(r"Shopify article ID:\s*(\d+)", notes)
        handle_m = re.search(r"Shopify handle:\s*([\w-]+)", notes)
        pub_m    = re.search(r"published_at:\s*([\dT:+-]+)", notes)

        jobs.append({
            "job_number":         num,
            "topic":              topic,
            "queue_status":       status,
            "target_date":        target,        # may be "TBD"
            "keyword":            keyword,
            "file_path":          file_p,
            "notes":              notes,
            "shopify_article_id": sid_m.group(1) if sid_m else None,
            "shopify_handle":     handle_m.group(1) if handle_m else None,
            "published_at":       pub_m.group(1).strip() if pub_m else None,
        })

    return jobs


# ─── SKIP LOGIC ───────────────────────────────────────────────────────────────

SKIP_STATUSES = {"published_live", "draft_created", "needs_human_review"}

def should_skip(job):
    """Return reason if job should be skipped, else None."""
    status = job.get("queue_status", "").strip().lower()
    if status in SKIP_STATUSES:
        return f"queue_status={status}"
    # published_live check (explicit)
    if status == "published_live":
        return "already published_live"
    return None


# ─── DUE LOGIC ───────────────────────────────────────────────────────────────

def is_job_due(job):
    """
    Determine if a planned job is due.
    A job is 'due' if:
      - queue_status is 'planned'
      - target_date is set AND days_until <= 0
      - OR target_date is 'TBD' AND the planner decides to handle it as immediately actionable
        (for a brand-new client with no drafts, the first planned job can be treated
         as immediately actionable, but only if the date is TBD and the queue rules allow)
    Returns: "due_now" | "not_yet_due" | "date_tbd" | "no_target_date"
    """
    target = job.get("target_date", "").strip()

    if not target or target.upper() == "TBD":
        return "date_tbd"

    days = days_until(target)
    if days is None:
        return "no_target_date"

    if days <= 0:
        return "due_now"
    else:
        return "not_yet_due"


# ─── MAIN ─────────────────────────────────────────────────────────────────────

def run():
    print("\n" + "=" * 60)
    print("HCS GADGETS — ORIN Phase 1B: Planner Agent (Dry-Run)")
    print(f"Run date: {TODAY}")
    print("=" * 60)

    # ── Load Phase 1A state ───────────────────────────────────────────────
    log("Loading Phase 1A state...")
    state = read_json(STATE_JSON)
    if not state:
        log("  WARNING: Phase 1A state not found — running with no prior state")
        state = {}

    phase1a_passed = state.get("phase1a_passed", False)
    log(f"  Phase 1A passed: {phase1a_passed}")

    # ── Load client config ───────────────────────────────────────────────
    log("Loading HCS client config...")
    config = read_json(CONFIG_PATH)
    if not config:
        log("  WARNING: HCS client config not found")
        config = {}

    publish_mode = config.get("publish_mode", "unknown")
    log(f"  Publish mode: {publish_mode}")
    log(f"  Manual publish required: {config.get('manual_publish_required', 'unknown')}")

    # ── Load queue ───────────────────────────────────────────────────────
    log("Parsing content queue...")
    jobs = parse_queue()
    log(f"  Total jobs in queue: {len(jobs)}")

    # ── Classify all jobs ─────────────────────────────────────────────────
    published_live = [j for j in jobs if j.get("queue_status") == "published_live"]
    draft_created  = [j for j in jobs if j.get("queue_status") == "draft_created"]
    planned        = [j for j in jobs if j.get("queue_status") == "planned"]
    needs_human   = [j for j in jobs if j.get("queue_status") == "needs_human_review"]
    blocked        = [j for j in jobs if j.get("queue_status") == "blocked"]

    log(f"  published_live: {len(published_live)}")
    log(f"  draft_created:  {len(draft_created)}")
    log(f"  planned:        {len(planned)}")
    log(f"  needs_human:    {len(needs_human)}")
    log(f"  blocked:        {len(blocked)}")

    # ── Check for any active Shopify drafts ──────────────────────────────
    shopify_draft_count = state.get("shopify_inventory_summary", {}).get("draft_count", 0)
    log(f"  Shopify drafts in inventory: {shopify_draft_count}")

    # ── Skip Job 01 (published_live) ───────────────────────────────────
    job01 = next((j for j in jobs if j["job_number"] == "01"), None)
    job01_skipped = False
    job01_skip_reason = None
    if job01:
        reason = should_skip(job01)
        if reason:
            job01_skipped = True
            job01_skip_reason = reason
            log(f"  Job 01 skipped: {reason}")

    # ── Plan: collect non-skipped planned jobs sorted by job number ───────
    planned_sorted = sorted(
        [j for j in planned if not should_skip(j)],
        key=lambda j: j["job_number"]
    )

    # ── Check due status of planned jobs ────────────────────────────────
    planned_due_now     = []   # target_date is past or today
    planned_date_tbd    = []   # target_date is TBD
    planned_not_yet_due = []   # target_date is future

    for j in planned_sorted:
        due_status = is_job_due(j)
        j["due_status"] = due_status
        if due_status == "due_now":
            planned_due_now.append(j)
        elif due_status == "date_tbd":
            planned_date_tbd.append(j)
        else:
            planned_not_yet_due.append(j)

    log(f"  Planned (due_now):    {len(planned_due_now)}")
    log(f"  Planned (date_tbd):  {len(planned_date_tbd)}")
    log(f"  Planned (not_yet):   {len(planned_not_yet_due)}")

    # ── Determine planner decision ───────────────────────────────────────
    # Decision hierarchy:
    # 1. If Phase 1A failed → blocked
    # 2. If needs_human_review jobs exist → blocked (needs human decision first)
    # 3. If blocked jobs exist → blocked
    # 4. If any planned job is due_now → due_job_selected
    # 5. If all planned jobs have TBD dates → waiting_for_future_date (date not set)
    # 6. If all planned jobs are in the future → waiting_for_future_date
    # 7. If no planned jobs exist → no_planned_jobs

    planner_decision   = "no_planned_jobs"
    selected_job      = None
    block_reason      = None

    if not phase1a_passed:
        planner_decision = "blocked_state_mismatch"
        block_reason    = "Phase 1A did not pass — state mismatch exists"

    elif needs_human:
        planner_decision = "blocked_needs_human"
        block_reason    = f"Jobs require human decision: {[j['job_number'] for j in needs_human]}"

    elif blocked:
        planner_decision = "blocked_state_mismatch"
        block_reason    = f"Blocked jobs in queue: {[j['job_number'] for j in blocked]}"

    elif planned_due_now:
        # Pick lowest-numbered due job
        selected_job     = planned_due_now[0]
        planner_decision = "due_job_selected"
        log(f"  Selected due job: Job {selected_job['job_number']}")

    elif planned_date_tbd:
        # All planned jobs have TBD dates — ORIN cannot auto-create drafts
        # without an approved date. Stop safely.
        planner_decision = "waiting_for_future_date"
        candidates = ", ".join(f"Job {j['job_number']}" for j in planned_date_tbd)
        block_reason = (
            "All planned jobs have Date target: TBD. "
            "A planned job date must be set before ORIN can determine "
            "whether it is due. HCS is waiting for date assignment. "
            f"Candidates: {candidates}"
        )
        log(f"  {block_reason}")

    elif planned_not_yet_due:
        # All planned jobs are in the future
        next_job = planned_not_yet_due[0]
        planner_decision = "waiting_for_future_date"
        block_reason    = (
            f"Job {next_job['job_number']} is next planned but not yet due "
            f"(target: {next_job.get('target_date')}, "
            f"days: {days_until(next_job.get('target_date', ''))}d). "
            f"Waiting for due date."
        )
        log(f"  {block_reason}")

    else:
        planner_decision = "no_planned_jobs"
        block_reason    = "No planned jobs found in queue."
        log(f"  No planned jobs — pipeline stops safely.")

    # ── Build job summaries for report ───────────────────────────────────
    def job_summary(j):
        return {
            "job_number":  j["job_number"],
            "topic":       j.get("topic", "")[:60],
            "queue_status": j.get("queue_status"),
            "target_date":  j.get("target_date"),
            "keyword":      j.get("keyword"),
            "due_status":   j.get("due_status"),
            "days_until":   days_until(j.get("target_date", "")),
            "file_path":    j.get("file_path"),
            "skip_reason":  should_skip(j),
        }

    # ── Write JSON ────────────────────────────────────────────────────────
    result = {
        "meta": {
            "phase":      "1B",
            "client":     "hcs_gadgets",
            "mode":       "dry-run",
            "run_date":   str(TODAY),
        },
        "phase1a_passed":   phase1a_passed,
        "publish_mode":      publish_mode,
        "manual_publish":    config.get("manual_publish_required", True),
        "shopify_drafts":    shopify_draft_count,
        "queue_summary": {
            "total":           len(jobs),
            "published_live":  len(published_live),
            "draft_created":   len(draft_created),
            "planned":         len(planned),
            "needs_human":     len(needs_human),
            "blocked":         len(blocked),
        },
        "job01": {
            "skipped":      job01_skipped,
            "skip_reason":  job01_skip_reason,
        },
        "planner": {
            "planner_decision": planner_decision,
            "selected_job_number": selected_job["job_number"] if selected_job else None,
            "selected_topic":     selected_job.get("topic") if selected_job else None,
            "block_reason":       block_reason,
            "planned_due_now_count":    len(planned_due_now),
            "planned_date_tbd_count":    len(planned_date_tbd),
            "planned_not_yet_count":     len(planned_not_yet_due),
        },
        "planned_jobs": [job_summary(j) for j in planned_sorted],
        "phase1b_passed": planner_decision not in (
            "blocked_state_mismatch", "blocked_needs_human"
        ),
    }

    JSON_OUTPUT.write_text(json.dumps(result, indent=2, default=str))
    log(f"  JSON preview written to {JSON_OUTPUT}")

    # ── Print summary ────────────────────────────────────────────────────
    print()
    print("=" * 60)
    print("HCS Phase 1B SUMMARY")
    print("=" * 60)
    print(f"  Phase 1A passed:       {phase1a_passed}")
    print(f"  Publish mode:          {publish_mode}")
    print(f"  Shopify drafts:        {shopify_draft_count}")
    print(f"  Queue:                 {len(jobs)} total | {len(planned)} planned")
    print(f"  Job 01 skipped:        {'YES' if job01_skipped else 'NO'} — {job01_skip_reason or 'n/a'}")
    print(f"  Planned (due_now):     {len(planned_due_now)}")
    print(f"  Planned (date_tbd):    {len(planned_date_tbd)}")
    print(f"  Planned (not_yet):     {len(planned_not_yet_due)}")
    print(f"  Planner decision:      {planner_decision}")
    print(f"  Selected job:          {selected_job['job_number'] if selected_job else 'none'}")
    print(f"  Block reason:         {block_reason or 'none'}")
    print(f"  Phase 1B:             {'✅ PASSED' if result['phase1b_passed'] else '❌ BLOCKED'}")
    print("=" * 60)

    return result


if __name__ == "__main__":
    run()
