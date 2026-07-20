#!/usr/bin/env python3
"""
HCS Gadgets — ORIN Phase 1A: State Agent Dry-Run

Read-only state detection for HCS Gadgets content engine.
Reads queue, Shopify inventory, local drafts, and config.
Writes preview to /tmp/hcs_phase1a_state_preview.json

NEVER calls old/unsafe scripts:
  - hcs_publish_blog_draft.py
  - hcs_update_blog_draft.py
  - hcs_fetch_blogs.py (for writes)
  - tools/shopify_publisher/publish_blog_draft.py
  - tools/scheduler/next_blog_job.py
  - tools/scheduler/mark_job_done.py

Output: /tmp/hcs_phase1a_state_preview.json
"""

import json
import re
from pathlib import Path
from datetime import datetime, date, timezone

# ─── PATHS ────────────────────────────────────────────────────────────────────

BASE_DIR       = Path("/data/.openclaw/workspace")
CLIENT_DIR     = BASE_DIR / "clients" / "hcs_gadgets" / "content_engine"
QUEUE_PATH     = CLIENT_DIR / "content_queue_3_months.md"
INVENTORY_PATH = CLIENT_DIR / "shopify_inventory.json"
DRAFTS_DIR     = CLIENT_DIR / "drafts"
CONFIG_PATH    = CLIENT_DIR / "hcs_client_config_draft.json"
RULES_DIR      = CLIENT_DIR / "rules"

JSON_OUTPUT    = Path("/tmp/hcs_phase1a_state_preview.json")

TODAY = date(2026, 7, 1)

# ─── BLOCKED (unsafe legacy scripts — MUST NOT be called) ─────────────────────

UNSAFE_SCRIPTS = [
    "hcs_publish_blog_draft.py",
    "hcs_update_blog_draft.py",
    "hcs_fetch_blogs.py",
    "tools/shopify_publisher/publish_blog_draft.py",
    "tools/scheduler/next_blog_job.py",
    "tools/scheduler/mark_job_done.py",
]

# ─── HELPERS ──────────────────────────────────────────────────────────────────

def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"  [{ts}] {msg}")


def read_json(path):
    try:
        return json.loads(Path(path).read_text())
    except Exception as e:
        return None


def days_until(date_str):
    if not date_str:
        return 999
    try:
        return (date.fromisoformat(date_str) - TODAY).days
    except ValueError:
        return 999


# ─── PARSE QUEUE ───────────────────────────────────────────────────────────────

def parse_queue():
    """Parse content_queue_3_months.md and return list of job dicts."""
    if not QUEUE_PATH.exists():
        return []

    content = QUEUE_PATH.read_text()
    jobs = []

    # Match each job block
    for m in re.finditer(
        r"^## Job (\d+)\n(.*?)(?=^## |\Z)",
        content,
        re.M | re.S
    ):
        num  = m.group(1)
        block = m.group(2)

        def f(key):
            mm = re.search(rf"{key}:\s*(.+?)(?=\n)", block, re.M)
            return mm.group(1).strip() if mm else None

        target   = f("Date target")
        topic    = f("Topic")
        status   = f("Status")
        keyword  = f("Target keyword")
        file_p   = f("File")

        # Notes block
        notes_m  = re.search(r"Notes:\n(.*)", block, re.S)
        notes    = notes_m.group(1).strip() if notes_m else ""

        # Extract Shopify ID/handle from notes
        sid_m    = re.search(r"Shopify article ID:\s*(\d+)", notes)
        handle_m = re.search(r"Shopify handle:\s*([\w-]+)", notes)
        # Capture just the ISO timestamp — stop at first dot or text after timestamp
        pub_m    = re.search(r"published_at:\s*([\dT:+-]+)", notes)

        jobs.append({
            "job_number":          num,
            "topic":               topic,
            "queue_status":        status,
            "target_date":         target,
            "keyword":             keyword,
            "file_path":           file_p,
            "notes":               notes,
            "shopify_article_id":  sid_m.group(1) if sid_m else None,
            "shopify_handle":      handle_m.group(1) if handle_m else None,
            "published_at":        pub_m.group(1).strip() if pub_m else None,
        })

    return jobs


# ─── PARSE SHOPIFY INVENTORY ─────────────────────────────────────────────────

def parse_shopify_inventory():
    """Return list of article dicts from shopify_inventory.json.
    
    Handles both the current dict format (with 'published' and 'drafts' keys)
    and legacy list format for backwards compatibility.
    """
    data = read_json(INVENTORY_PATH)
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        # Current format: { "published": [...], "drafts": [...], "total": N }
        published = data.get("published", [])
        drafts    = data.get("drafts", [])
        # Ensure each article has article_id field (use "id" as fallback)
        result = []
        for a in published:
            a2 = dict(a)
            a2.setdefault("article_id", a2.get("id"))
            a2.setdefault("published_at", a2.get("published_at"))
            result.append(a2)
        for a in drafts:
            a2 = dict(a)
            a2.setdefault("article_id", a2.get("id"))
            a2.setdefault("published_at", None)
            result.append(a2)
        return result
    return []


def shopify_published_articles(inventory):
    return [a for a in inventory if a.get("published_at")]

def shopify_draft_articles(inventory):
    return [a for a in inventory if not a.get("published_at")]


# ─── LOCAL DRAFTS ─────────────────────────────────────────────────────────────

def local_drafts():
    """Return list of local draft file paths (excluding .bak files)."""
    if not DRAFTS_DIR.exists():
        return []
    return sorted([
        f for f in DRAFTS_DIR.iterdir()
        if f.is_file() and not f.name.endswith(".bak")
    ])


# ─── DUPLICATE DETECTION ──────────────────────────────────────────────────────

def detect_duplicates(inventory):
    """Find duplicate handles and near-duplicate titles."""
    handles  = {}
    titles   = {}
    problems = []

    for a in inventory:
        aid = a.get("article_id") or a.get("id")
        h   = a.get("handle", "")
        t   = a.get("title", "")

        # Skip articles without handles ( shouldn't happen)
        if not h:
            continue

        # Duplicate handle
        if h in handles:
            problems.append({
                "type":         "duplicate_handle",
                "handle":       h,
                "article_ids":  [handles[h], aid],
                "titles":       [titles.get(h, ""), t],
            })
        else:
            handles[h] = aid
            titles[h]  = t

        # Near-duplicate handle (base match)
        base = re.sub(r"-\d+$", "", h)
        if base in handles and handles[base] != aid:
            problems.append({
                "type":         "near_duplicate_handle",
                "handle":       h,
                "base_handle":  base,
                "article_ids":  [handles[base], aid],
            })

    return problems


# ─── STALE / RISKY FILE DETECTION ─────────────────────────────────────────────

def detect_stale_files():
    """Flag stale backups and old script references."""
    issues = []

    # .bak files older than 30 days (created before 2026-06-01)
    if DRAFTS_DIR.exists():
        for f in DRAFTS_DIR.iterdir():
            if f.is_file() and ".bak." in f.name:
                m = re.search(r"\.bak\.(\d{8})-(\d{6})", f.name)
                if m:
                    bak_date_str = m.group(1)  # e.g. 20260601
                    try:
                        bak_date = date.fromisoformat(bak_date_str)
                        age_days = (TODAY - bak_date).days
                        if age_days > 30:
                            issues.append({
                                "type":   "stale_backup",
                                "file":   str(f.relative_to(BASE_DIR)),
                                "age_days": age_days,
                                "note":   "Backup older than 30 days — archive candidate",
                            })
                    except ValueError:
                        pass

    return issues


# ─── OLD SCRIPT SCAN ─────────────────────────────────────────────────────────

def scan_for_unsafe_scripts():
    """Check if any HCS ORIN pipeline files reference old unsafe scripts."""
    problems = []
    orin_dir = Path("/data/.openclaw/workspace/tools/shopify_publisher/orin")
    if not orin_dir.exists():
        return problems

    this_file = Path(__file__).resolve()  # skip self

    for f in orin_dir.iterdir():
        if not f.is_file() or f.suffix != ".py":
            continue
        if f.resolve() == this_file:
            continue  # skip this file's own blocklist
        # Only scan HCS-specific ORIN files (skip hoverboard store ones)
        if "hcs" not in f.name.lower():
            continue
        content = f.read_text()
        for script in UNSAFE_SCRIPTS:
            if script in content:
                problems.append({
                    "type":  "unsafe_script_reference",
                    "file":  f.name,
                    "script": script,
                })
    return problems


# ─── MAIN ─────────────────────────────────────────────────────────────────────

def run():
    print("\n" + "=" * 60)
    print("HCS GADGETS — ORIN Phase 1A: State Agent (Dry-Run)")
    print(f"Run date: {TODAY}")
    print("=" * 60)

    # ── Parse queue ───────────────────────────────────────────────────────
    log("Parsing content queue...")
    queue_jobs = parse_queue()
    log(f"  {len(queue_jobs)} jobs found in queue")

    # Count by status
    status_counts = {}
    for j in queue_jobs:
        s = j.get("queue_status", "unknown")
        status_counts[s] = status_counts.get(s, 0) + 1
    log(f"  Queue status breakdown: {status_counts}")

    # ── Parse Shopify inventory ───────────────────────────────────────────
    log("Parsing Shopify inventory...")
    inventory = parse_shopify_inventory()
    log(f"  {len(inventory)} total articles in Shopify")

    pub_count   = len(shopify_published_articles(inventory))
    draft_count = len(shopify_draft_articles(inventory))
    log(f"  Published: {pub_count} | Drafts: {draft_count}")

    # Build lookup by article_id (support both 'article_id' and 'id' fields)
    by_id = {str(a.get("article_id") or a.get("id", "")): a for a in inventory if a.get("article_id") or a.get("id")}
    by_handle = {a["handle"]: a for a in inventory if a.get("handle")}

    # ── Verify Job 01 ───────────────────────────────────────────────────
    job01 = next((j for j in queue_jobs if j["job_number"] == "01"), None)
    job01_verified = False
    job01_problems = []

    if job01:
        expected_id     = job01.get("shopify_article_id")
        expected_handle = job01.get("shopify_handle")
        expected_pub   = job01.get("published_at")

        shopify_article = by_id.get(str(expected_id)) if expected_id else None

        if not expected_id:
            job01_problems.append("Queue Job 01 has no Shopify article ID")
        elif not shopify_article:
            job01_problems.append(f"Article ID {expected_id} not found in Shopify inventory")
        else:
            # Check handle match
            if shopify_article.get("handle") != expected_handle:
                job01_problems.append(
                    f"Handle mismatch: queue='{expected_handle}' "
                    f"vs shopify='{shopify_article.get('handle')}'"
                )
            # Check published_at match
            if shopify_article.get("published_at") != expected_pub:
                job01_problems.append(
                    f"published_at mismatch: queue='{expected_pub}' "
                    f"vs shopify='{shopify_article.get('published_at')}'"
                )

        if not job01_problems:
            job01_verified = True
            log(f"  Job 01 verified ✅ — article {expected_id} is published_live")
        else:
            for p in job01_problems:
                log(f"  Job 01 problem: {p}")

    # ── Detect Jobs 02-06 ────────────────────────────────────────────────
    jobs_02_06 = [j for j in queue_jobs if j["job_number"] in ("02","03","04","05","06")]
    jobs_02_06_detected = len(jobs_02_06)
    log(f"  Jobs 02–06 detected: {jobs_02_06_detected}")

    # ── Local drafts ─────────────────────────────────────────────────────
    log("Scanning local drafts...")
    drafts = local_drafts()
    draft_names = [f.name for f in drafts]
    log(f"  Local drafts found: {draft_names}")

    # Map queue file paths to local draft existence
    for j in queue_jobs:
        fp = j.get("file_path", "")
        if fp:
            rel = Path(fp).name
            j["local_draft_exists"] = any(
                dn == rel or dn.startswith(rel.replace(".html", ""))
                for dn in draft_names
            )
        else:
            j["local_draft_exists"] = False

    # ── Duplicate detection ──────────────────────────────────────────────
    log("Checking for duplicate handles/titles...")
    dup_problems = detect_duplicates(inventory)
    log(f"  Duplicate/near-duplicate issues found: {len(dup_problems)}")
    for dp in dup_problems:
        log(f"    [{dp['type']}] {dp.get('handle', '?')}")

    # ── Stale / risky files ──────────────────────────────────────────────
    log("Checking for stale/risky files...")
    stale = detect_stale_files()
    log(f"  Stale file issues: {len(stale)}")
    for s in stale:
        log(f"    [{s['type']}] {s['file']} ({s['age_days']} days old)")

    # ── Unsafe script scan ───────────────────────────────────────────────
    log("Scanning for unsafe script references...")
    unsafe_refs = scan_for_unsafe_scripts()
    log(f"  Unsafe script references found: {len(unsafe_refs)}")

    # ── Assemble result ──────────────────────────────────────────────────
    result = {
        "meta": {
            "phase":         "1A",
            "client":        "hcs_gadgets",
            "mode":          "dry-run",
            "run_date":      str(TODAY),
            "jobs_audited":  [j["job_number"] for j in queue_jobs],
        },
        "queue_summary": {
            "total_jobs":       len(queue_jobs),
            "status_counts":    status_counts,
            "planned_count":    status_counts.get("planned", 0),
            "draft_created":    status_counts.get("draft_created", 0),
            "published_live":   status_counts.get("published_live", 0),
        },
        "shopify_inventory_summary": {
            "total_articles":  len(inventory),
            "published_count": pub_count,
            "draft_count":     draft_count,
        },
        "job01_verification": {
            "job_number":       "01",
            "verified":          job01_verified,
            "problems":          job01_problems,
            "queue_status":      job01.get("queue_status") if job01 else None,
            "shopify_article_id": job01.get("shopify_article_id") if job01 else None,
            "shopify_handle":    job01.get("shopify_handle") if job01 else None,
            "published_at":      job01.get("published_at") if job01 else None,
        },
        "jobs_02_06_detected": jobs_02_06_detected,
        "local_drafts": draft_names,
        "duplicate_issues": dup_problems,
        "stale_files": stale,
        "unsafe_script_references": unsafe_refs,
        "phase1a_passed": job01_verified and len(job01_problems) == 0,
        "blocking_issues": job01_problems + [f"{dp['type']}: {dp.get('handle','?')}" for dp in dup_problems if dp.get("type") == "duplicate_handle"],
    }

    # ── Write JSON ───────────────────────────────────────────────────────
    JSON_OUTPUT.write_text(json.dumps(result, indent=2, default=str))
    log(f"  JSON preview written to {JSON_OUTPUT}")

    # ── Print summary ────────────────────────────────────────────────────
    print()
    print("=" * 60)
    print("HCS Phase 1A SUMMARY")
    print("=" * 60)
    print(f"  Queue jobs:          {len(queue_jobs)}")
    print(f"  Shopify articles:    {len(inventory)} (pub: {pub_count}, draft: {draft_count})")
    print(f"  Job 01 verified:     {'✅ YES' if job01_verified else '❌ NO'}")
    if job01_problems:
        for p in job01_problems:
            print(f"    Problem: {p}")
    print(f"  Jobs 02–06 found:    {jobs_02_06_detected}")
    print(f"  Local drafts:        {draft_names}")
    print(f"  Duplicate issues:    {len(dup_problems)}")
    print(f"  Stale file issues:   {len(stale)}")
    print(f"  Unsafe refs:         {len(unsafe_refs)}")
    print(f"  Phase 1A:            {'✅ PASSED' if result['phase1a_passed'] else '❌ BLOCKED'}")
    print("=" * 60)

    if not result["phase1a_passed"]:
        print("\n⚠️  Phase 1A BLOCKED — fix above issues before proceeding.")
        print("   Do NOT auto-fix. Report to user for manual resolution.")

    return result


if __name__ == "__main__":
    run()
