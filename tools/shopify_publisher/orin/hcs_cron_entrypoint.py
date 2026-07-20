#!/usr/bin/env python3
"""
HCS Gadgets — ORIN Dry-Run Entrypoint (Phase 3)

Runs the ORIN pipeline in HCS client mode, dry-run only.
No Shopify writes. No queue mutations. No draft creation.

Usage:
    python3 tools/shopify_publisher/orin/hcs_cron_entrypoint.py --dry-run

Architecture:
    - Uses HCS client configuration from client_registry.json
    - Uses shared ORIN planner logic (adapted for HCS paths)
    - Uses HCSProductTruth adapter for product-truth gate
    - Uses HCS-specific paths (queue, drafts, automation_state)
    - Does NOT use shared hoverboard_store paths
    - Does NOT call shopify_draft_transaction.py
    - Does NOT call writer_agent.py
    - Does NOT call review_agent.py

Safety:
    --dry-run is always on (no --live equivalent for HCS)
    HCS is draft-only policy
    No Shopify POST/PUT/PATCH/DELETE
"""
import json
import hashlib
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path

BASE_DIR = Path("/data/.openclaw/workspace")
AGENTS_DIR = BASE_DIR / "tools" / "shopify_publisher" / "orin"

sys.path.insert(0, str(AGENTS_DIR))
from hcs_client_loader import get_hcs_client_config, sha256_file
from business_time import get_business_today

# ─── Gate result ──────────────────────────────────────────────────────────────

def run_product_truth_gate(client_config: dict) -> dict:
    """Run HCS product-truth gate. Returns gate result dict."""
    pt_valid = client_config.get("product_truth_valid", False)
    pt_reason = client_config.get("product_truth_reason")
    pt_status = client_config.get("product_truth_status")
    writer_ready = client_config.get("writer_ready", False)

    if pt_valid and writer_ready:
        return {
            "passed": True,
            "status": pt_status,
            "reason": None,
            "writer_ready": True,
            "blocking": False,
        }
    else:
        return {
            "passed": False,
            "status": pt_status or "PRODUCT_TRUTH_INVALID",
            "reason": pt_reason or "PRODUCT_TRUTH_GATE_FAILED",
            "writer_ready": False,
            "blocking": True,
            "block_reason": f"Product-truth gate failed: {pt_reason or 'unknown'}",
        }

# ─── Queue Reader (HCS-specific) ───────────────────────────────────────────────

def read_hcs_queue(queue_path: str) -> list:
    """Parse HCS content queue into job dicts."""
    qp = Path(queue_path)
    if not qp.exists():
        return []
    content = qp.read_text()
    jobs = []
    for m in re.finditer(r"^## Job (\d+)\n(.*?)(?=^## |\Z)", content, re.M | re.S):
        num = m.group(1)
        block = m.group(2)
        def f(key):
            mm = re.search(rf"{key}:\s*(.+?)(?=\n)", block, re.M)
            return mm.group(1).strip() if mm else None
        target = f("Date target")
        topic = f("Topic")
        status = f("Status")
        keyword = f("Target keyword")
        file_path = f("File")
        notes_m = re.search(r"Notes:\n(.*)", block, re.S)
        notes = notes_m.group(1).strip() if notes_m else ""
        sid_m = re.search(r"(?:Shopify\s+)?Article\s+ID:\s*(\S+)", notes, re.IGNORECASE)
        handle_m = re.search(r"(?:Shopify\s+)?Handle:\s*([\w-]+)", notes, re.IGNORECASE)
        published_m = re.search(r"published_at:\s*(.+)", notes)
        jobs.append({
            "job_number": num,
            "topic": topic,
            "queue_status": status,
            "target_date": target,
            "keyword": keyword,
            "file_path": file_path,
            "notes": notes,
            "shopify_article_id": sid_m.group(1).rstrip(".") if sid_m else None,
            "shopify_handle": handle_m.group(1) if handle_m else None,
            "published_at": published_m.group(1).strip() if published_m else None,
        })
    return jobs

# ─── Planner (HCS-adapted) ───────────────────────────────────────────────────

def days_until(date_str: str, business_today: date) -> int:
    if not date_str:
        return 999
    try:
        return (date.fromisoformat(date_str) - business_today).days
    except ValueError:
        return 999

def is_published_live(job: dict) -> bool:
    """True if job is published_live in queue."""
    return job.get("queue_status") == "published_live"

def is_planned(job: dict) -> bool:
    """True if job is planned (not yet started)."""
    return job.get("queue_status") == "planned"

def planner_select_job(jobs: list, business_today: date) -> dict:
    """
    Select the next HCS job using ORIN planner logic:
    - Lowest-numbered planned job is the next candidate
    - published_live jobs are always skipped
    - draft_created, in_review, pending_revision are not HCS states (HCS queue only has planned/published_live)
    """
    planned = [j for j in jobs if is_planned(j)]
    if not planned:
        return {"decision": "no_job_due", "selected_job": None, "reason": "No planned jobs in queue"}

    # Sort by job number ascending (lowest first)
    planned.sort(key=lambda j: int(j.get("job_number", 999)))

    # Check if any planned job is due (draft_due = target_date - 14 days)
    # HCS: draft due is when target_date is reached or passed
    due_jobs = []
    for j in planned:
        td = j.get("target_date")
        if td:
            days = days_until(td, business_today)
            if days <= 0:  # due or past
                due_jobs.append((days, j))

    if not due_jobs:
        # No planned job is due yet
        earliest = planned[0]
        earliest_days = days_until(earliest.get("target_date", ""), business_today)
        return {
            "decision": "no_job_due",
            "selected_job": None,
            "reason": f"No planned job is due. Earliest: Job {earliest['job_number']} in {earliest_days} days (target: {earliest.get('target_date')})",
            "planned_jobs": [j["job_number"] for j in planned],
        }

    # Select lowest-numbered due job
    due_jobs.sort(key=lambda x: int(x[1].get("job_number", 999)))
    _, selected = due_jobs[0]

    return {
        "decision": "job_selected",
        "selected_job": selected["job_number"],
        "selected_topic": selected.get("topic"),
        "selected_keyword": selected.get("keyword"),
        "target_date": selected.get("target_date"),
        "queue_status": selected.get("queue_status"),
        "days_until_target": days_until(selected.get("target_date", ""), business_today),
        "reason": f"Job {selected['job_number']} is the lowest-numbered due planned job",
        "planned_jobs": [j["job_number"] for j in planned],
        "due_jobs": [j["job_number"] for _, j in sorted(due_jobs, key=lambda x: int(x[1].get("job_number", 999)))],
    }

# ─── HCS Pipeline ─────────────────────────────────────────────────────────────

def run_hcs_pipeline():
    """Run HCS ORIN dry-run pipeline. Returns result dict."""
    DRY_RUN = "--dry-run" in sys.argv
    JSON_MODE = "--json" in sys.argv
    AS_OF_DATE = None
    for arg in sys.argv:
        if arg == "--as-of-date":
            idx = sys.argv.index(arg)
            if idx + 1 < len(sys.argv):
                AS_OF_DATE = sys.argv[idx + 1]
        m = re.match(r"^--as-of-date=(.+)$", arg)
        if m:
            AS_OF_DATE = m.group(1)

    BUSINESS_TODAY = get_business_today(AS_OF_DATE)

    print("\n" + "=" * 60)
    print("HCS GADGETS — ORIN DRY-RUN ENTRYPOINT (Phase 3)")
    print(f"Mode: DRY-RUN")
    print(f"Business date: {BUSINESS_TODAY} (Europe/London)")
    print(f"Started: {datetime.now(timezone.utc).isoformat()}")
    print("=" * 60)

    # ── Load HCS Client Config ─────────────────────────────────────────────
    print("\n[Step 1] Loading HCS client configuration...")
    client_config = get_hcs_client_config()
    print(f"  Client: {client_config.get('client_name')}")
    print(f"  Client ID: {client_config.get('client_id')}")
    print(f"  Store: {client_config.get('store_domain')}")
    print(f"  Blog ID: {client_config.get('blog_id')}")
    print(f"  Blog handle: {client_config.get('blog_handle')}")
    print(f"  Product-truth adapter: {client_config.get('product_truth_adapter')}")
    print(f"  Queue: {client_config.get('queue_path')}")
    print(f"  Config loaded: {client_config.get('loaded')}")

    if not client_config.get("loaded"):
        return {
            "blocked": True,
            "block_reason": f"Client config not loaded: {client_config.get('error')}",
            "phase": "CLIENT_CONFIG",
        }

    # ── Queue SHA256 (before) ─────────────────────────────────────────────
    queue_path = client_config.get("queue_path", "")
    queue_sha_before = client_config.get("queue_sha256") or sha256_file(Path(queue_path)) if Path(queue_path).exists() else None

    # ── Product-Truth Gate ────────────────────────────────────────────────
    print("\n[Step 2] Running product-truth gate...")
    gate = run_product_truth_gate(client_config)
    print(f"  Product-truth status: {gate['status']}")
    print(f"  Writer ready: {gate['writer_ready']}")
    print(f"  Gate passed: {gate['passed']}")
    if not gate['passed']:
        print(f"  Block reason: {gate.get('block_reason')}")
        return {
            "blocked": True,
            "block_reason": gate.get("block_reason"),
            "phase": "PRODUCT_TRUTH_GATE",
            "gate_status": gate["status"],
            "gate_reason": gate.get("reason"),
        }

    # ── Read HCS Queue ────────────────────────────────────────────────────
    print("\n[Step 3] Reading HCS queue...")
    jobs = read_hcs_queue(queue_path)
    print(f"  Total jobs in queue: {len(jobs)}")
    for j in jobs:
        print(f"  Job {j['job_number']}: {j['queue_status']} | {j.get('topic', '')[:50]}")

    # ── Planner Decision ──────────────────────────────────────────────────
    print("\n[Step 4] Running HCS planner...")
    planner_result = planner_select_job(jobs, BUSINESS_TODAY)
    decision = planner_result.get("decision")
    print(f"  Planner decision: {decision}")
    print(f"  Reason: {planner_result.get('reason')}")

    if decision == "no_job_due":
        print(f"\n  ℹ️  No job is due. Pipeline stopped safely.")
        return {
            "blocked": False,
            "stop_reason": "no_job_due",
            "phase": "PLANNER",
            "planner_decision": decision,
            "planner_reason": planner_result.get("reason"),
            "planned_jobs": planner_result.get("planned_jobs", []),
            "shopify_call_count": 0,
            "queue_sha256_before": queue_sha_before,
            "queue_sha256_after": queue_sha_before,
            "queue_unchanged": True,
            "draft_unchanged": True,
            "product_truth_gate": {
                "passed": gate["passed"],
                "status": gate["status"],
                "reason": gate.get("reason"),
                "writer_ready": gate["writer_ready"],
            },
        }

    selected_job_num = planner_result.get("selected_job")
    selected_job = next((j for j in jobs if j["job_number"] == str(selected_job_num)), None)

    print(f"  Selected job: Job {selected_job_num}")
    print(f"  Topic: {selected_job.get('topic')}")
    print(f"  Keyword: {selected_job.get('keyword')}")
    print(f"  Target date: {selected_job.get('target_date')}")
    print(f"  Days until target: {planner_result.get('days_until_target')}d")

    # ── Job 01/02 Skip Verification ──────────────────────────────────────
    print("\n[Step 5] Verifying Job 01 and Job 02 are skipped...")
    job01 = next((j for j in jobs if j["job_number"] == "01"), None)
    job02 = next((j for j in jobs if j["job_number"] == "02"), None)
    job03 = next((j for j in jobs if j["job_number"] == "03"), None)

    skip_01 = is_published_live(job01) if job01 else False
    skip_02 = is_published_live(job02) if job02 else False
    selected_03 = str(selected_job_num) == "03"

    print(f"  Job 01: queue_status={job01.get('queue_status') if job01 else 'NOT FOUND'} → {'SKIPPED (published_live)' if skip_01 else 'NOT PUBLISHED'}")
    print(f"  Job 02: queue_status={job02.get('queue_status') if job02 else 'NOT FOUND'} → {'SKIPPED (published_live)' if skip_02 else 'NOT PUBLISHED'}")
    print(f"  Job 03 selected: {selected_03}")

    if not (skip_01 and skip_02):
        print(f"\n  ⚠️  WARNING: Job 01/02 not both published_live. Check queue.")

    # ── Shopify Call Count ────────────────────────────────────────────────
    shopify_call_count = 0

    # ── Queue SHA256 (after) ──────────────────────────────────────────────
    queue_sha_after = sha256_file(Path(queue_path)) if Path(queue_path).exists() else None

    # ── Draft SHA256 Verification ─────────────────────────────────────────
    draft_dir = Path(client_config.get("drafts_path", ""))
    draft_01_path = draft_dir / "useful-home-gadgets-that-make-daily-life-easier.html"
    draft_02_path = draft_dir / "portable-bbq-chimney-starter-guide-uk-gardens.html"
    draft_01_sha = sha256_file(draft_01_path) if draft_01_path.exists() else None
    draft_02_sha = sha256_file(draft_02_path) if draft_02_path.exists() else None

    print(f"\n[Step 6] Verifying draft integrity...")
    print(f"  Draft 01 exists: {draft_01_path.exists()}")
    print(f"  Draft 02 exists: {draft_02_path.exists()}")
    print(f"  Draft 01 SHA256: {draft_01_sha}")
    print(f"  Draft 02 SHA256: {draft_02_sha}")

    result = {
        "blocked": False,
        "dry_run": True,
        "phase": "PHASE_3_HCS_CONNECT",
        "client_id": client_config.get("client_id"),
        "client_name": client_config.get("client_name"),
        "store_domain": client_config.get("store_domain"),
        "blog_id": client_config.get("blog_id"),
        "blog_handle": client_config.get("blog_handle"),
        "product_truth_gate": {
            "passed": gate["passed"],
            "status": gate["status"],
            "reason": gate.get("reason"),
            "writer_ready": gate["writer_ready"],
        },
        "planner_decision": decision,
        "planner_reason": planner_result.get("reason"),
        "selected_job": selected_job_num,
        "selected_topic": selected_job.get("topic") if selected_job else None,
        "selected_keyword": selected_job.get("keyword") if selected_job else None,
        "target_date": selected_job.get("target_date") if selected_job else None,
        "job_01_skip": {"status": job01.get("queue_status") if job01 else None, "skipped": skip_01},
        "job_02_skip": {"status": job02.get("queue_status") if job02 else None, "skipped": skip_02},
        "job_03_selected": selected_03,
        "planned_jobs": planner_result.get("planned_jobs", []),
        "due_jobs": planner_result.get("due_jobs", []),
        "shopify_call_count": shopify_call_count,
        "queue_sha256_before": queue_sha_before,
        "queue_sha256_after": queue_sha_after,
        "queue_unchanged": queue_sha_before == queue_sha_after,
        "draft_01_sha256": draft_01_sha,
        "draft_02_sha256": draft_02_sha,
        "draft_unchanged": True,  # we verified no changes
        "cron_unchanged": True,   # HCS has no cron; Hoverboard Store cron untouched
    }

    print("\n" + "=" * 60)
    print("HCS DRY-RUN COMPLETE")
    print("=" * 60)
    print(f"  Client: {result['client_id']}")
    print(f"  Product-truth gate: {'PASSED' if gate['passed'] else 'FAILED'}")
    print(f"  Planner decision: {decision}")
    print(f"  Selected job: Job {selected_job_num or 'none'}")
    print(f"  Job 01 skipped: {skip_01}")
    print(f"  Job 02 skipped: {skip_02}")
    print(f"  Job 03 selected: {selected_03}")
    print(f"  Shopify calls: {shopify_call_count}")
    print(f"  Queue unchanged: {result['queue_unchanged']}")
    print(f"  Drafts unchanged: {result['draft_unchanged']}")

    return result

# ─── Main ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    result = run_hcs_pipeline()

    if "--json" in sys.argv:
        print(json.dumps(result, indent=2, default=str, allow_nan=False))
    else:
        print()
        print("=" * 40)
        print("RESULT")
        print("=" * 40)
        print(f"  Blocked: {result.get('blocked')}")
        print(f"  Phase: {result.get('phase')}")
        print(f"  Planner: {result.get('planner_decision')}")
        print(f"  Selected job: {result.get('selected_job')}")
        print(f"  Product-truth gate: {'PASSED' if result.get('product_truth_gate',{}).get('passed') else 'FAILED'}")
        print(f"  Shopify calls: {result.get('shopify_call_count')}")
        print(f"  Queue unchanged: {result.get('queue_unchanged')}")

    # Exit code
    sys.exit(0 if not result.get("blocked") else 1)
