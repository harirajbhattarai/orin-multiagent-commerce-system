#!/usr/bin/env python3
"""
ORIN Cron Entrypoint — Phase 3B

One safe cron entrypoint that runs the full ORIN pipeline in order:
  Phase 1A → Phase 1B → Phase 1C → Phase 2D (Writer) → Phase 2A-INLINE → Phase 2B-INLINE → Phase 2E/2G

Safety defaults:
  --dry-run    : Default, including when no mode flag is supplied. No Shopify writes.
  --live-draft : Requests a hidden Shopify draft and requires --confirm-live-draft.
                 The live-draft gate must still approve before any Shopify write.

NEVER:
  - Call old publish_blog_draft.py, update_blog_draft.py, or next_blog_job.py
  - Set published_at on any article
  - Auto-publish anything
  - Update queue status

If any phase returns a blocking decision, the pipeline stops safely.

Usage:
  python3 tools/shopify_publisher/orin/cron_entrypoint.py --dry-run
  python3 tools/shopify_publisher/orin/cron_entrypoint.py --job 20 --dry-run --json
"""

import sys
import json
import hashlib
import subprocess
import re
import os
import uuid as _uuid_lib
from pathlib import Path
from datetime import datetime, date, timezone

AGENTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(AGENTS_DIR))
from workspace_paths import workspace_root

# Default to the repository/workspace containing this script. An explicit
# override is available for controlled deployments and tests; production code
# must not silently import from a different live workspace.
BASE_DIR = workspace_root()
CLIENT_DIR = BASE_DIR / "clients" / "hoverboard_store" / "content_engine"
QUEUE_PATH = CLIENT_DIR / "content_queue_3_months.md"

from business_time import get_business_today
from job_context import build_job_context, write_job_context, read_job_context, CONTEXT_PATH as JOB_CONTEXT_PATH
from shopify_draft_transaction import run_safe_draft_transaction
from queue_state_manager import commit_transaction_result, TRANSACTION_APPROVED_DRAFT_CREATED, \
    TRANSACTION_BLOCKED_VERIFICATION_FAILED
from writer_agent import WriterAgent
from topic_identity_gate import run_topic_identity_gate, TOPIC_IDENTITY_BLOCK

JSON_OUTPUT_PATH = Path("/tmp/orin_phase3b_cron_entrypoint_preview.json")

# Old unsafe scripts — BLOCKED (pipeline must never call these)
BLOCKED_SCRIPT_PATTERNS = [
    "next_blog_job",
    "publish_blog_draft",
    "update_blog_draft",
    "mark_job_done",
]

# Phase wrappers and their /tmp JSON output paths
PHASE_WRAPPERS = {
    "1A": {
        "wrapper": "orin_phase1a_state_dryrun.py",
        "json_path": "/tmp/orin_phase1a_job_state_preview.json",
    },
    "1B": {
        "wrapper": "orin_phase1b_planner_dryrun.py",
        "json_path": "/tmp/orin_phase1b_planner_preview.json",
    },
    "1C": {
        "wrapper": "orin_phase1c_recovery_dryrun.py",
        "json_path": "/tmp/orin_phase1c_recovery_preview.json",
    },
    "2B": {
        "wrapper": "orin_phase2b_duplicate_memory_dryrun.py",
        "json_path": "/tmp/orin_phase2b_duplicate_decisions_preview.json",
    },
    "2D": {
        # Writer planning wrapper (Phase 2C in canonical naming)
        "wrapper": "orin_phase2c_writer_planning_dryrun.py",
        "json_path": "/tmp/orin_phase2c_writer_plan_preview.json",
    },
    "2E": {
        "wrapper": "orin_phase2e_publisher_dryrun.py",
        "json_path": "/tmp/orin_phase2e_publisher_preview.json",
    },
}

# NOTE on Phase 2A and Phase 2B:
# These are NOT called via run_phase_wrapper() for the selected job.
# The batch wrappers (orin_phase2a_review_dryrun.py, orin_phase2b_duplicate_memory_dryrun.py)
# only process jobs 15-20. For the selected job (any number), both phases run INLINE
# directly in this file using review_selected_job_draft() and build_duplicate_memory().
# This ensures the actual current writer HTML is always reviewed, not a stale artefact.

# ─── CLI ──────────────────────────────────────────────────────────────────────

LIVE_DRAFT = "--live-draft" in sys.argv
CONFIRM_LIVE_DRAFT = "--confirm-live-draft" in sys.argv
# No mode flag is a dry-run. An explicit --dry-run also takes precedence when
# both dry-run and live-draft flags are supplied.
DRY_RUN = "--dry-run" in sys.argv or not LIVE_DRAFT
REQUESTED_MODE = "live-draft" if LIVE_DRAFT else "dry-run"
JSON_MODE = "--json" in sys.argv
JOB_FILTER = None
AS_OF_DATE = None  # resolved business date override
CLIENT_ROUTE = None  # 'hcs_gadgets' | 'hoverboard_store' | None (default=Hoverboard)
for arg in sys.argv:
    m = re.match(r"^--client=(\w+)$", arg)
    if m:
        CLIENT_ROUTE = m.group(1)
    m_job = re.match(r"^--job=(\d+)$", arg)
    if m_job:
        JOB_FILTER = m_job.group(1)
    if arg == "--as-of-date":
        idx = sys.argv.index(arg)
        if idx + 1 < len(sys.argv):
            AS_OF_DATE = sys.argv[idx + 1]
    m2 = re.match(r"^--as-of-date=(.+)$", arg)
    if m2:
        AS_OF_DATE = m2.group(1)

# Resolve business date once at startup (production or override)
BUSINESS_TODAY = get_business_today(AS_OF_DATE)

# ─── CLIENT ROUTING ────────────────────────────────────────────────────────────
# Route HCS Gadgets to isolated HCS pipeline (no Hoverboard Store module coupling).
# Unknown client_id fails closed. HCS is always dry-run.
if CLIENT_ROUTE == "hcs_gadgets":
    import subprocess
    _hcs_script = AGENTS_DIR / "hcs_cron_entrypoint.py"
    if not _hcs_script.exists():
        print(f"ERROR: HCS entrypoint not found: {_hcs_script}")
        sys.exit(1)
    _hcs_args = [sys.executable, str(_hcs_script), "--dry-run"]
    if JSON_MODE:
        _hcs_args.append("--json")
    _hcs_result = subprocess.run(_hcs_args, capture_output=True, text=True, cwd=str(BASE_DIR))
    if JSON_MODE:
        print(_hcs_result.stdout)
    else:
        print(_hcs_result.stdout)
        if _hcs_result.stderr:
            print(_hcs_result.stderr)
    sys.exit(_hcs_result.returncode)

# Default route: Hoverboard Store (existing behaviour, unchanged)
if CLIENT_ROUTE is not None and CLIENT_ROUTE != "hoverboard_store":
    print(f"ERROR: Unknown client_id: {CLIENT_ROUTE!r}")
    print(f"Available: hoverboard_store, hcs_gadgets")
    sys.exit(1)

# ─── SAFETY GATES ─────────────────────────────────────────────────────────────
# Live-draft confirmation intent is enforced by Gate v2 (live_draft_gate.py).
# Gate v2 H1 check: --live-draft AND --confirm-live-draft must both be present.
# Without --confirm-live-draft, Gate v2 returns BLOCK_LIVE_DRAFT_CONFIRMATION_REQUIRED.
# No pre-flight sys.exit() blocks are needed here — Gate v2 is the single source of truth.

if LIVE_DRAFT and CONFIRM_LIVE_DRAFT and DRY_RUN:
    print("[SAFETY GATE] --dry-run takes precedence; Shopify transaction will be skipped.")
    print()
elif LIVE_DRAFT and CONFIRM_LIVE_DRAFT:
    print("[SAFETY GATE] --confirm-live-draft detected. Proceeding with live-draft safety check...")
    print("[SAFETY GATE] No job will be pushed unless all live-draft gate checks approve.")
    print()

# ─── HELPERS ──────────────────────────────────────────────────────────────────

def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"  [{ts}] {msg}")


def writer_output_path(planned_draft_path, job_num, pipeline_run_id):
    """Keep database-backed worker output in its private evidence directory."""
    if os.environ.get("ORIN_DURABLE_DB_MODE") != "1":
        return planned_draft_path or f"/tmp/orin_job{job_num}_writer_exec.html"

    artifact_dir = os.environ.get("ORIN_RUN_ARTIFACT_DIR", "")
    artifact_root = Path(artifact_dir)
    if not artifact_dir or not artifact_root.is_absolute():
        raise RuntimeError(
            "durable database mode requires an absolute ORIN_RUN_ARTIFACT_DIR"
        )
    return str(artifact_root / f"writer_output_{pipeline_run_id}.html")


def run_phase_wrapper(phase_key, extra_args=None):
    """
    Run a phase dry-run wrapper script.
    Reads the /tmp JSON preview written by the wrapper.
    Returns (parsed_json, error). Errors are non-blocking (logged, not fatal).
    """
    info = PHASE_WRAPPERS.get(phase_key, {})
    wrapper = info.get("wrapper", "")
    json_path = info.get("json_path", "")
    wrapper_path = AGENTS_DIR / wrapper

    log(f"Running Phase {phase_key} ({wrapper})...")
    args = [sys.executable, str(wrapper_path)] + (extra_args or [])

    # Propagate business date to subprocess via env var
    env = os.environ.copy()
    env["ORIN_BUSINESS_DATE"] = BUSINESS_TODAY.isoformat()

    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(BASE_DIR),
            env=env,
        )
    except subprocess.TimeoutExpired:
        return None, f"Phase {phase_key}: timeout after 120s"
    except Exception as e:
        return None, f"Phase {phase_key}: {e}"

    if result.returncode != 0:
        stderr_tail = result.stderr[-300:] if result.stderr else "(no stderr)"
        log(f"  ⚠️  Phase {phase_key} exited with code {result.returncode}: {stderr_tail}")
        # Phase scripts (esp. Phase 2E) write preview BEFORE deciding exit code.
        # A non-zero exit may mean "decision=BLOCKED" rather than "script crashed".
        # If preview exists and is valid JSON, use it — the decision is in the preview.
        if not Path(json_path).exists():
            return None, f"Phase {phase_key} exit {result.returncode}"

    # Read the /tmp JSON preview (works for both exit 0 and exit 1 with valid preview)
    if Path(json_path).exists():
        try:
            data = json.loads(Path(json_path).read_text())
            log(f"  ✅ Phase {phase_key} preview loaded from {json_path}")
            return data, None
        except json.JSONDecodeError as e:
            return None, f"Phase {phase_key}: JSON read error: {e}"
    else:
        return None, f"Phase {phase_key}: no preview at {json_path}"


def read_queue():
    """Read queue file and return list of job dicts."""
    if not QUEUE_PATH.exists():
        return []
    content = QUEUE_PATH.read_text()
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


def days_until(date_str):
    if not date_str:
        return 999
    try:
        return (date.fromisoformat(date_str) - BUSINESS_TODAY).days
    except ValueError:
        return 999


def pipeline_blocked(reason):
    """Print blocking reason and return blocking dict."""
    print(f"\n🛑 PIPELINE BLOCKED: {reason}")
    return {
        "blocked": True,
        "block_reason": reason,
        "phase": None,
        "dry_run": DRY_RUN,
        "requested_mode": REQUESTED_MODE,
        "live_draft_requested": LIVE_DRAFT,
        "live_draft_confirmed": CONFIRM_LIVE_DRAFT,
        "shopify_touched": False,
        "queue_touched": False,
    }


def check_no_blocked_scripts():
    """
    Verify the entrypoint's run_phase_wrapper() and subprocess calls do NOT
    invoke blocked scripts. Only inspects actual call sites.
    """
    src = Path(__file__).read_text()
    problems = []
    # Only look at lines with actual call patterns
    for i, line in enumerate(src.split("\n"), 1):
        # Only inspect lines that call subprocess or run_phase
        if not ("subprocess" in line or "run_phase_wrapper" in line or "run_phase" in line):
            continue
        stripped = line.strip()
        # Skip comment-only lines
        if stripped.startswith("#"):
            continue
        # Flag if a blocked pattern appears in a call line
        for pattern in BLOCKED_SCRIPT_PATTERNS:
            if pattern in line:
                problems.append(f"Line {i}: {stripped[:80]}")
    return problems


# ─── MAIN PIPELINE ────────────────────────────────────────────────────────────

def run_pipeline():
    """Run full ORIN pipeline. Returns result dict."""
    print("\n" + "=" * 60)
    print("ORIN CRON ENTRYPOINT — Phase 3B")
    print(f"Mode: {'DRY-RUN' if DRY_RUN else 'LIVE-DRAFT'}")
    print(f"Business date: {BUSINESS_TODAY} (Europe/London)")
    print(f"Started: {datetime.now(timezone.utc).isoformat()}")
    print("=" * 60)

    # ── Safety: no blocked scripts in pipeline code ─────────────────────
    print("\n[SAFETY] Checking pipeline code for blocked script calls...")
    problems = check_no_blocked_scripts()
    if problems:
        print(f"ERROR: Blocked script references found:")
        for p in problems:
            print(f"  {p}")
        return pipeline_blocked(f"Blocked script references: {problems}")
    print("  ✅ No blocked script references in pipeline code")

    # ── Phase 1A: State Agent ────────────────────────────────────────────
    print()
    phase1a, err1a = run_phase_wrapper("1A")
    if err1a:
        log(f"  ⚠️  Phase 1A error (non-blocking): {err1a}")
        phase1a = {"jobs": [], "meta": {"phase": "1A", "error": err1a}}
    else:
        log(f"  Phase 1A complete — {len(phase1a.get('jobs', []))} jobs analysed")

    # ── Phase 1B: Planner Agent ──────────────────────────────────────────
    print()
    phase1b, err1b = run_phase_wrapper("1B")
    if err1b:
        return pipeline_blocked(f"Phase 1B failed: {err1b}")

    planner = phase1b.get("planner", {})
    planner_decision = planner.get("planner_decision", "")
    selected_job = planner.get("selected_job_number")
    print(f"  Planner decision: {planner_decision}")
    print(f"  Selected job: {selected_job or 'none'}")

    if planner_decision == "no_job_due":
        msg = "No planned job is due. Pipeline stopped safely — nothing to do."
        print(f"\nℹ️  {msg}")
        return {
            "blocked": False,
            "block_reason": None,
            "stop_reason": msg,
            "phase": "1B",
            "planner_decision": planner_decision,
            "dry_run": DRY_RUN,
            "requested_mode": REQUESTED_MODE,
            "live_draft_requested": LIVE_DRAFT,
            "live_draft_confirmed": CONFIRM_LIVE_DRAFT,
            "shopify_touched": False,
            "queue_touched": False,
            "selected_job": None,
            "next_action": "No action required; no planned job is due.",
        }

    if not selected_job:
        return pipeline_blocked(
            f"Phase 1B: no job selected (decision={planner_decision})"
        )

    job_num = selected_job
    queue = read_queue()
    job = next((j for j in queue if str(j["job_number"]) == str(job_num)), None)
    if not job:
        return pipeline_blocked(f"Job {job_num} not found in queue")

    print(f"  Selected: Job {job_num} — {job.get('topic')}")
    print(f"  Target date: {job.get('target_date')} ({days_until(job.get('target_date', ''))}d)")
    print(f"  Queue status: {job.get('queue_status')}")
    print(f"  Local file: {job.get('file_path') or 'none'}")

    # ── Pipeline run identity — artefact isolation ─────────────────────────────────
    # Generate a unique run ID for this pipeline invocation.
    # Every /tmp artefact written in this run carries this run_id.
    # Downstream consumers verify artefact.pipeline_run_id matches current pipeline_run_id.
    # Stale artefacts from previous runs have mismatched run_ids and are rejected.
    # This eliminates any dependency on manual /tmp cleanup between runs.
    pipeline_run_id = f"job{job_num}_{int(datetime.now(timezone.utc).timestamp())}_{_uuid_lib.uuid4().hex[:8]}"
    print(f"  Pipeline run ID: {pipeline_run_id}")

    # ── Build Canonical Selected-Job Context ──────────────────────────────
    # Every downstream phase receives this context.
    planner_reason = planner.get("reason", "")
    job_ctx = build_job_context(
        job_number=str(job_num),
        job_data=job,
        planner_decision=planner_decision,
        planner_reason=planner_reason,
    )
    write_job_context(job_ctx, JOB_CONTEXT_PATH)
    print(f"  Job context written: {JOB_CONTEXT_PATH}")
    print(f"  Classification: {job_ctx.get('ALREADY_CREATED_classification') or job_ctx.get('detected_state', '?')}")

    # ── Phase 1C: Recovery Agent ─────────────────────────────────────────
    print()
    phase1c, err1c = run_phase_wrapper("1C", [str(job_num)])
    if err1c:
        log(f"  ⚠️  Phase 1C error (non-blocking): {err1c}")
        phase1c = {"active_recovery_items": [], "meta": {"phase": "1C", "error": err1c}}
    active_items = phase1c.get("active_recovery_items", [])
    log(f"  Phase 1C complete — {len(active_items)} active recovery items")

    # ── Phase 2C: Writer Planning ─────────────────────────────────────────
    # Runs BEFORE Phase 2A review so the writer creates the draft first.
    # Circular dependency fixed: review requires draft, but writer creates draft.
    print()
    phase2c_writer, err2c = run_phase_wrapper("2D")  # 2D = writer_planning wrapper
    if err2c:
        log(f"  ⚠️  Phase 2C Writer Planning error (non-blocking): {err2c}")
        phase2c_writer = {"writer_decision": "error", "error": err2c}
    writer_decision = phase2c_writer.get("writer_decision", "unknown")
    log(f"  Phase 2C complete — writer decision: {writer_decision}")

    # Update job context with writer's planned draft path (from dynamic writer plan)
    writer_plan = phase2c_writer.get("writer_plan", {})
    # Phase 2C writes writer_plan to /tmp/orin_selected_job_writer_plan.json
    # (not the wrapper's json_path). Read it directly so inline Phase 2D works.
    _wp_path = Path("/tmp/orin_selected_job_writer_plan.json")
    if _wp_path.exists():
        try:
            writer_plan = json.loads(_wp_path.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    planned_draft_path = writer_plan.get("proposed_local_file_path")
    if planned_draft_path:
        job_ctx["local_draft_path"] = planned_draft_path
        from pathlib import Path as _Path
        if _Path(planned_draft_path).exists():
            job_ctx["local_draft_exists"] = True
        write_job_context(job_ctx, JOB_CONTEXT_PATH)
        log(f"  Job context updated with writer planned path: {planned_draft_path}")

    # ── Phase 2D: Writer Execution + Topic Identity Gate ─────────────────
    # Production rule: writer output → topic identity gate → Phase 2A.
    # Inline execution (no separate phase wrapper): writer planning (Phase 2C)
    # created the writer_plan; now execute it to produce the HTML draft.
    # topic_identity_gate runs BEFORE Phase 2A review so contamination is
    # caught before any downstream phase runs.
    print()
    log("Running Phase 2D: Writer Execution + Topic Identity Gate...")
    writer_agent = WriterAgent(str(BASE_DIR), BUSINESS_TODAY.isoformat())
    exec_output_path = writer_output_path(
        planned_draft_path,
        job_num,
        pipeline_run_id,
    )
    try:
        exec_stats = writer_agent.write_selected_job_draft(
            job_ctx=job_ctx,
            writer_plan=writer_plan,
            output_path_override=exec_output_path,
        )
        log(f"  Writer execution: {exec_output_path}")
    except Exception as e:
        log(f"  ⚠️  Writer execution error: {e}")
        exec_stats = {}

    # Write the execution preview JSON so downstream phases can load it
    exec_preview_path = Path(f"/tmp/orin_job{job_num}_writer_execution_preview.json")
    exec_html = ""
    if Path(exec_output_path).exists():
        exec_html = Path(exec_output_path).read_text(encoding="utf-8")
    sha256_hex = hashlib.sha256(exec_html.encode()).hexdigest() if exec_html else ""
    exec_preview = {
        "job_number": str(job_num),
        "pipeline_run_id": pipeline_run_id,
        "title": writer_plan.get("title", job.get("topic", "")),
        "approved_handle": writer_plan.get("approved_handle", job.get("shopify_handle", "")),
        "output_path": exec_output_path,
        "sha256": sha256_hex,
        "word_count": len(exec_html.split()),
        "file_written": Path(exec_output_path).exists(),
    }
    exec_preview_path.write_text(json.dumps(exec_preview, indent=2), encoding="utf-8")
    log(f"  Execution preview written: {exec_preview_path}")

    # ── Topic Identity Gate ──────────────────────────────────────────────
    topic_lower = job.get("topic", "").lower()
    if any(k in topic_lower for k in ["hoverkart", "kart"]):
        cluster = "Hoverkart"
    elif any(k in topic_lower for k in ["accessori", "helmet", "pad", "bag"]):
        cluster = "Accessories"
    elif any(k in topic_lower for k in ["safe", "checklist", "law"]):
        cluster = "Safety"
    elif any(k in topic_lower for k in ["wont turn", "not charging", "beeping", "flashing", "troubleshoot"]):
        cluster = "Troubleshooting"
    elif any(k in topic_lower for k in ["best", "guide", "choose", "vs"]):
        cluster = "Buyer Guide"
    elif any(k in topic_lower for k in ["clean", "store", "maintenance", "battery care"]):
        cluster = "Maintenance"
    elif any(k in topic_lower for k in ["gift", "christmas", "birthday"]):
        cluster = "Seasonal"
    else:
        cluster = "default"
    approved_h2_plan = [
        {"id": h.get("id", ""), "h2": h.get("h2", "")}
        for h in writer_plan.get("h2_outline", [])
    ]
    gate_result = run_topic_identity_gate(
        job_id=str(job_num),
        expected_topic=job.get("topic", ""),
        target_keyword=job.get("target_keyword", ""),
        cluster=cluster,
        approved_h2_plan=approved_h2_plan,
        output_html=exec_html,
    )
    gate_decision = gate_result.get("decision", "")
    log(f"  Topic identity gate: {gate_decision}")
    if gate_decision == TOPIC_IDENTITY_BLOCK:
        blockers = gate_result.get("blockers", [])
        checks = gate_result.get("checks", [])
        log(f"  BLOCK — topic identity gate failed: {blockers}")
        return pipeline_blocked(
            f"Phase 2D Topic Identity Gate BLOCKED. "
            f"Job {job_num} contamination detected. "
            f"Blockers: {blockers}. "
            f"Checks: {checks}. "
            f"Pipeline stopped before Phase 2A."
        )
    log(f"  Topic identity gate PASSED — continuing to Phase 2A")

    # ═══════════════════════════════════════════════════════════════════════
    # PHASE 2A: POST-WRITE REVIEW — INLINE (not via batch wrapper)
    #
    # The batch wrapper (orin_phase2a_review_dryrun.py) only covers jobs 15-20.
    # For the selected job (any number, including jobs 21+), the review runs
    # HERE inline using review_selected_job_draft().
    #
    # The review operates on the EXACT same HTML file just produced by writer
    # execution — not a stale or cached artefact.
    #
    # BLOCK if:
    #   - writer HTML does not exist at exec_output_path
    #     → PIPELINE_ARTIFACT_IDENTITY_BLOCK
    #   - review returns POST_WRITE_REVIEW_BLOCKED
    #   - review returns POST_WRITE_REVIEW_NEEDS_HUMAN_REVIEW
    #
    # The result is written to a job-scoped artefact with pipeline_run_id
    # so Phase H can load it without stale-artifact risk.
    # ═══════════════════════════════════════════════════════════════════════
    print()
    log("Running Phase 2A: Post-Write Review (INLINE — reviews actual writer HTML)...")

    # BLOCK if writer HTML was not produced
    if not exec_output_path or not Path(exec_output_path).exists():
        log(f"  BLOCK — no writer HTML at: {exec_output_path}")
        return pipeline_blocked(
            f"PIPELINE_ARTIFACT_IDENTITY_BLOCK: "
            f"Phase 2A cannot review missing writer HTML: {exec_output_path}. "
            f"Pipeline stopped."
        )

    # Load writer plan for review
    _inline_wp = {}
    _inline_wp_path = Path("/tmp/orin_selected_job_writer_plan.json")
    if _inline_wp_path.exists():
        try:
            _inline_wp = json.loads(_inline_wp_path.read_text())
        except (json.JSONDecodeError, OSError):
            pass

    # Load job context for review
    _inline_jc = {}
    if Path("/tmp/orin_selected_job_context.json").exists():
        try:
            _inline_jc = json.loads(Path("/tmp/orin_selected_job_context.json").read_text())
        except (json.JSONDecodeError, OSError):
            pass

    # Call review_selected_job_draft() directly — reviews the actual current HTML
    from review_agent import review_selected_job_draft
    # For new planned articles: skip duplicate check (no existing Shopify record)
    _is_new = not bool(job.get("shopify_handle")) and not bool(job.get("shopify_article_id"))
    _inline_review = review_selected_job_draft(
        job_ctx=_inline_jc,
        writer_plan=_inline_wp,
        draft_path=exec_output_path,
        skip_duplicate_check=_is_new,
    )

    # Write job-scoped review artefact (with pipeline_run_id for isolation)
    _review_artefact_path = Path(f"/tmp/orin_selected_job_post_write_review_{pipeline_run_id}.json")
    _review_artefact_path.write_text(json.dumps(_inline_review, indent=2, default=str), encoding="utf-8")
    log(f"  Phase 2A review artefact: {_review_artefact_path}")

    # Extract review decision
    phase2a_review_decision = _inline_review.get("review_decision", "")
    phase2a_blockers = _inline_review.get("blockers", [])
    log(f"  Phase 2A review decision: {phase2a_review_decision}")

    # BLOCK on review failure:
    # - POST_WRITE_REVIEW_BLOCKED: explicit blocking issues found
    # - POST_WRITE_REVIEW_NEEDS_HUMAN_REVIEW with non-empty blockers: compliance/safety issues
    # NOT blocking:
    # - POST_WRITE_REVIEW_NEEDS_HUMAN_REVIEW with empty blockers: advisory warnings only
    #   (e.g. word count low) — pipeline continues with warning logged
    if phase2a_review_decision == "POST_WRITE_REVIEW_BLOCKED":
        return pipeline_blocked(
            f"Phase 2A BLOCKED: {phase2a_review_decision}. "
            f"Blockers: {phase2a_blockers}. "
            f"Pipeline stopped before Shopify transaction."
        )
    if phase2a_review_decision == "POST_WRITE_REVIEW_NEEDS_HUMAN_REVIEW" and phase2a_blockers:
        # Non-empty blockers means real compliance/safety issues
        return pipeline_blocked(
            f"Phase 2A BLOCKED: {phase2a_review_decision}. "
            f"Blockers: {phase2a_blockers}. "
            f"Pipeline stopped before Shopify transaction."
        )
    if phase2a_review_decision == "POST_WRITE_REVIEW_NEEDS_HUMAN_REVIEW" and not phase2a_blockers:
        # Advisory warnings only — pipeline continues but transaction is not authorised
        log(f"  WARNING: Phase 2A returned NEEDS_HUMAN_REVIEW (advisory only): {phase2a_review_decision}")
        log(f"  Warnings: {_inline_review.get('warnings', [])}")
        log(f"  Pipeline continues but Shopify transaction requires human sign-off before live run.")

    log(f"  ✅ Phase 2A PASS — continuing pipeline")
    review_decision = phase2a_review_decision
    issues = phase2a_blockers

    # ═══════════════════════════════════════════════════════════════════════
    # PHASE 2B: DUPLICATE DECISION MEMORY — INLINE (not via batch wrapper)
    #
    # The batch wrapper (orin_phase2b_duplicate_memory_dryrun.py) only covers
    # jobs 15-20. For the selected job, duplicate check runs HERE inline
    # using build_duplicate_memory() for the single selected job.
    #
    # BLOCK if:
    #   - human_duplicate_decision_required (real duplicate)
    #   - no_local_file or skipped_not_due record type
    #     → PIPELINE_ARTIFACT_IDENTITY_BLOCK
    # ═══════════════════════════════════════════════════════════════════════
    print()
    log("Running Phase 2B: Duplicate Decision Memory (INLINE)...")

    _dup_artefact_path = Path(f"/tmp/orin_phase2b_duplicate_decisions_{pipeline_run_id}.json")

    from duplicate_decision_agent import build_duplicate_memory
    _inline_dup_result = build_duplicate_memory([str(job_num)])
    _dup_artefact_path.write_text(json.dumps(_inline_dup_result, indent=2, default=str), encoding="utf-8")
    log(f"  Phase 2B duplicate artefact: {_dup_artefact_path}")

    _inline_dup_records = _inline_dup_result.get("records", [])
    _inline_dup_record = next(
        (r for r in _inline_dup_records if str(r.get("job_number")) == str(job_num)),
        {}
    )
    _inline_record_type = _inline_dup_record.get("record_type", "")

    # ── Phase 2B severity contract — FAIL-CLOSED allowlist ────────────────────────
    # Every known record_type has an explicit defined outcome.
    # Unknown / empty / malformed record_type → BLOCK before Shopify.
    #
    # Blocking: human_duplicate_decision_required | no_local_file |
    #           skipped_not_due | blocked_by_compliance_or_html
    # Warn:    unclear (only when human_decision_count=0) | global_site_warning
    # Pass:    self_match_info

    BLOCKING_TYPES = frozenset([
        "human_duplicate_decision_required",  # real duplicate vs different article
        "no_local_file",                      # missing local draft file
        "skipped_not_due",                   # job not yet due
        "blocked_by_compliance_or_html",      # blocked upstream in Phase 2A
    ])
    WARN_TYPES = frozenset([
        "unclear",          # ambiguous; warn and continue only if no human decisions pending
        "global_site_warning",  # site-level warning unrelated to this job
    ])
    PASS_TYPES = frozenset([
        "self_match_info",   # local draft matches own Shopify article — expected
    ])

    _dup_summary = _inline_dup_result.get("summary", {})
    _human_decision_count = _dup_summary.get("human_duplicate_decision_required_count", 0)

    if _inline_record_type in BLOCKING_TYPES:
        _block_reason = {
            "human_duplicate_decision_required": (
                f"Phase 2B BLOCKED: real duplicate requires human decision. "
                f"Conflicting: {_inline_dup_record.get('conflicting_article_title', '?')}. "
                f"Pipeline stopped."
            ),
            "no_local_file": (
                f"PIPELINE_ARTIFACT_IDENTITY_BLOCK: "
                f"Phase 2B cannot check duplicate — input unavailable: "
                f"record_type=no_local_file, draft={exec_output_path}. Pipeline stopped."
            ),
            "skipped_not_due": (
                f"PIPELINE_ARTIFACT_IDENTITY_BLOCK: "
                f"Phase 2B cannot check duplicate — input unavailable: "
                f"record_type=skipped_not_due, draft={exec_output_path}. Pipeline stopped."
            ),
            "blocked_by_compliance_or_html": (
                f"Phase 2B BLOCKED: job blocked by compliance or HTML quality issues "
                f"upstream in Phase 2A. Pipeline stopped."
            ),
        }.get(_inline_record_type, f"Phase 2B BLOCKED: record_type={_inline_record_type}. Pipeline stopped.")
        return pipeline_blocked(_block_reason)

    if _inline_record_type in WARN_TYPES:
        if _inline_record_type == "unclear" and _human_decision_count > 0:
            return pipeline_blocked(
                f"Phase 2B BLOCKED: record_type=unclear but "
                f"human_duplicate_decision_required_count={_human_decision_count} > 0 "
                f"(real duplicate in batch). Pipeline stopped."
            )
        log(f"  Phase 2B record type: {_inline_record_type}")
        log(f"  ⚠️  Phase 2B WARN — {_inline_record_type} (human_decision_count={_human_decision_count})")
        record_type = _inline_record_type
        phase2b_record = _inline_dup_record
    elif _inline_record_type in PASS_TYPES:
        log(f"  Phase 2B record type: {_inline_record_type}")
        log(f"  ✅ Phase 2B PASS — {_inline_record_type}")
        record_type = _inline_record_type
        phase2b_record = _inline_dup_record
    else:
        # Fail-closed: unknown / empty / None record_type
        return pipeline_blocked(
            f"Phase 2B BLOCKED: unrecognized record_type={_inline_record_type!r}. "
            f"Pipeline stopped before Shopify."
        )

    # ── Phase 2E/2G: Publisher Agent (hardened preflight) ──────────────────
    print()
    phase2e, err2e = run_phase_wrapper("2E", ["--job-context", str(JOB_CONTEXT_PATH)])
    if err2e:
        return pipeline_blocked(f"Phase 2E/2G Publisher Agent failed: {err2e}")

    publisher_passed = phase2e.get("passed", False)
    publisher_decision = phase2e.get("decision", "")
    publisher_job = phase2e.get("publisher_job_number")

    # ALREADY_CREATED invariant: Phase 2E must evaluate the selected job
    if publisher_job and str(publisher_job) != str(job_num):
        return pipeline_blocked(
            f"Phase 2E BLOCKED — publisher_route=BLOCK_AND_STOP "
            f"JOB_CONTEXT_MISMATCH: Phase 2E evaluated Job {publisher_job} "
            f"but selected job is Job {job_num}."
        )

    already_created_classification = phase2e.get("already_created_classification")
    if already_created_classification:
        job_ctx["ALREADY_CREATED_classification"] = already_created_classification
        write_job_context(job_ctx, JOB_CONTEXT_PATH)
        print(f"  ALREADY_CREATED classification: {already_created_classification}")

    print(f"  Publisher decision: {publisher_decision}")
    print(f"  Publisher passed: {publisher_passed}")
    print(f"  Publisher evaluated: Job {publisher_job or 'unknown'}")

    # ── Publisher Route Classification ─────────────────────────────────
    NEW_DRAFT_DECISIONS = frozenset(["READY_TO_CREATE_SELECTED_JOB_DRAFT"])
    ALREADY_CREATED_CORRECT = frozenset(["ALREADY_CREATED_QUEUE_ALREADY_CORRECT"])
    QUEUE_RECONCILIATION_DECISIONS = frozenset(["ALREADY_CREATED_QUEUE_RECONCILIATION_REQUIRED"])
    BLOCKING_DECISIONS = frozenset([
        "BLOCKED_DUPLICATE_SHOPIFY_TITLE", "BLOCKED_DUPLICATE_SHOPIFY_HANDLE",
        "BLOCKED_NEAR_HANDLE_CONFLICT", "BLOCKED_NEAR_TITLE_CONFLICT",
        "BLOCK_JOB_CONTEXT_MISMATCH", "BLOCK_DRAFT_PATH_MISMATCH",
        "BLOCK_HANDLE_CONTEXT_MISMATCH", "BLOCK_LOCAL_DRAFT_MUTATED_AFTER_WRITER",
        "BLOCK_SELF_MATCH_IDENTITY_MISMATCH", "BLOCK_REVIEW_GATE",
        "BLOCK_HTML_VALIDATION_GATE", "BLOCK_COMPLIANCE",
        "BLOCK_QUEUE_STATUS_MISMATCH", "BLOCK_DRAFT_NOT_FOUND",
        "BLOCK_SLUG_MISMATCH", "BLOCK_HTML_QUALITY",
    ])
    if publisher_decision in NEW_DRAFT_DECISIONS:
        publisher_route = "NEW_DRAFT_CREATION_ROUTE"
    elif publisher_decision in ALREADY_CREATED_CORRECT:
        publisher_route = "SAFE_STOP_ALREADY_CORRECT"
    elif publisher_decision in QUEUE_RECONCILIATION_DECISIONS:
        publisher_route = "QUEUE_RECONCILIATION_ROUTE"
    elif publisher_decision in BLOCKING_DECISIONS:
        publisher_route = "BLOCK_AND_STOP"
    else:
        publisher_route = "BLOCK_UNKNOWN_PUBLISHER_DECISION"

    print(f"  Publisher route: {publisher_route}")

    # ── DRY-RUN STOP ──────────────────────────────────────────────────────
    if not publisher_passed:
        return pipeline_blocked(
            f"Phase 2E/2G BLOCKED: publisher_route={publisher_route} "
            f"decision={publisher_decision}"
        )

    print(f"  ✅ Phase 2E/2G PASS — preflight all checks passed")

    # ═══════════════════════════════════════════════════════════════════════
    # INLINE HTML VALIDATION (Phase 2F-equivalent)
    #
    # Runs inline after Phase 2A review passes.
    # Uses a job-scoped artefact path with pipeline_run_id to prevent stale-artifact risk.
    # The artefact is verified to belong to the current job before use.
    # ═══════════════════════════════════════════════════════════════════════
    _hv_artefact_path = Path(f"/tmp/orin_selected_job_html_validation_{pipeline_run_id}.json")
    if not _hv_artefact_path.exists():
        _hv_passed = False
        _hv_issues = []
        _hv_safe = False
        if exec_output_path and Path(exec_output_path).exists():
            _hv_html = Path(exec_output_path).read_text(encoding="utf-8")
            _hv_words = len(_hv_html.split())
            _hv_has_h1 = bool(re.search(r"<h1", _hv_html, re.IGNORECASE))
            _hv_has_h2 = bool(re.search(r"<h2", _hv_html, re.IGNORECASE))
            _hv_has_content = _hv_words >= 100
            _hv_safe = True
            if not _hv_has_h1:
                _hv_issues.append("missing_h1: article has no <h1>")
            if not _hv_has_h2:
                _hv_issues.append("missing_h2: article has no <h2>")
            if not _hv_has_content:
                _hv_issues.append(f"insufficient_content: only {_hv_words} words")
            _hv_passed = len(_hv_issues) == 0
        else:
            _hv_issues.append(f"no_draft_file: HTML file not written at {exec_output_path}")
            _hv_passed = False
        _hv_result = {
            "job_number": str(job_num),
            "pipeline_run_id": pipeline_run_id,
            "passed": _hv_passed,
            "validation_passed": _hv_passed,
            "safe_for_publisher_preflight": _hv_safe,
            "issues": _hv_issues,
            "validator_issues": _hv_issues,
            "word_count": (
                len(Path(exec_output_path).read_text(encoding="utf-8").split())
                if Path(exec_output_path).exists() else 0
            ),
            "note": "inline_html_validation_job_scoped",
        }
        _hv_artefact_path.write_text(json.dumps(_hv_result, indent=2), encoding="utf-8")
        log(f"  Inline HTML validation: {'PASS' if _hv_passed else 'FAIL'} — {', '.join(_hv_issues) or 'ok'}")
        log(f"  HTML validation artefact: {_hv_artefact_path}")

    # ── DRY-RUN STOP ──────────────────────────────────────────────────────
    if DRY_RUN and not (LIVE_DRAFT and CONFIRM_LIVE_DRAFT):
        print()
        print("=" * 60)
        print("DRY-RUN COMPLETE — no Shopify writes made")
        print("=" * 60)
        return {
            "blocked": False,
            "dry_run": True,
            "requested_mode": REQUESTED_MODE,
            "live_draft_requested": LIVE_DRAFT,
            "live_draft_confirmed": CONFIRM_LIVE_DRAFT,
            "shopify_touched": False,
            "queue_touched": False,
            "selected_job": job_num,
            "selected_topic": job.get("topic"),
            "queue_status": job.get("queue_status"),
            "target_date": job.get("target_date"),
            "review_decision": review_decision,
            "publisher_passed": publisher_passed,
            "publisher_decision": publisher_decision,
            "publisher_route": publisher_route,
            "pipeline_phases_completed": ["1A", "1B", "1C", "2D-WRITER", "2A-POST-WRITE-INLINE", "2B-INLINE", "2E"],
            "pipeline_run_id": pipeline_run_id,
            "writer_output_path": exec_output_path,
            "next_action": (
                f"Publisher route: {publisher_route}. "
                f"Queue status: {job.get('queue_status')}. "
                f"Run with --live-draft --confirm-live-draft to push (when enabled)."
            ),
        }

    # ═══════════════════════════════════════════════════════════════════════
    # PHASE H: LIVE-DRAFT GATE v2
    #
    # Gate runs AFTER Publisher preflight + routing, BEFORE any Shopify write.
    # Artefacts are loaded from job-scoped paths with pipeline_run_id.
    # Any stale artefact (wrong job number) is detected and rejected.
    # ═══════════════════════════════════════════════════════════════════════
    if LIVE_DRAFT and CONFIRM_LIVE_DRAFT:
        from live_draft_gate import run_gate, _check_verification_capability

        _gate_ctx_job = {
            "job_number": job.get("job_number"),
            "topic": job.get("topic"),
            "queue_status": job.get("queue_status"),
            "target_date": job.get("target_date"),
            "shopify_handle": job.get("shopify_handle"),
        }

        # Load writer plan
        _gate_writer_plan = {}
        if Path("/tmp/orin_selected_job_writer_plan.json").exists():
            _gate_writer_plan = json.loads(Path("/tmp/orin_selected_job_writer_plan.json").read_text())

        # Load writer execution preview
        _gate_writer_exec = {}
        _gate_exec_preview_path = Path(f"/tmp/orin_job{job_num}_writer_execution_preview.json")
        if _gate_exec_preview_path.exists():
            _gate_writer_exec = json.loads(_gate_exec_preview_path.read_text())

        # ── Load Phase 2A review artefact — job-scoped path required ──────────
        _gate_review = {}
        _gate_review_src = "not found"
        _gate_review_scoped = Path(f"/tmp/orin_selected_job_post_write_review_{pipeline_run_id}.json")
        if _gate_review_scoped.exists():
            _raw = json.loads(_gate_review_scoped.read_text())
            if _raw.get("job_number") == str(job_num):
                _gate_review = _raw
                _gate_review_src = str(_gate_review_scoped)
            else:
                _gate_review_src = f"STALE REJECTED: {_gate_review_scoped} (job {_raw.get('job_number')} != {job_num})"
                log(f"  WARNING: Stale review artefact rejected: job {_raw.get('job_number')} != {job_num}")
        else:
            _gate_review_src = f"not found: {_gate_review_scoped}"

        # ── Load HTML validation artefact — job-scoped path required ───────────
        _gate_html = {}
        _gate_html_src = "not found"
        _gate_html_scoped = Path(f"/tmp/orin_selected_job_html_validation_{pipeline_run_id}.json")
        if _gate_html_scoped.exists():
            _raw = json.loads(_gate_html_scoped.read_text())
            if _raw.get("job_number") == str(job_num):
                _gate_html = _raw
                _gate_html_src = str(_gate_html_scoped)
            else:
                _gate_html_src = f"STALE REJECTED: {_gate_html_scoped} (job {_raw.get('job_number')} != {job_num})"
                log(f"  WARNING: Stale HTML validation artefact rejected: job {_raw.get('job_number')} != {job_num}")
        else:
            _gate_html_src = f"not found: {_gate_html_scoped}"

        log(f"  Phase H review artefact: {_gate_review_src}")
        log(f"  Phase H HTML artefact:  {_gate_html_src}")

        # Build gate context
        gate_ctx = {
            "selected_job_context": _gate_ctx_job,
            "writer_plan": _gate_writer_plan,
            "writer_execution": _gate_writer_exec,
            "post_write_review": _gate_review,
            "html_validation": _gate_html,
            "publisher_preflight": {
                "publisher_job_number": publisher_job,
                "decision": publisher_decision,
                "passed": publisher_passed,
                "payload_preview": {
                    "handle": job.get("shopify_handle"),
                },
            },
            "publisher_route": publisher_route,
            "live_draft_requested": LIVE_DRAFT,
            "live_draft_confirmed": CONFIRM_LIVE_DRAFT,
            "business_date": BUSINESS_TODAY,
        }

        # ── H11: Verification capability check ─────────────────────────────
        _body_hash_available, _capability_failures = _check_verification_capability()
        if not _body_hash_available:
            log(f"  [H11 CAPABILITY CHECK] Verification capability not connected: {_capability_failures}")
        else:
            log(f"  [H11 CAPABILITY CHECK] Verification capability CONNECTED")
        gate_ctx["body_hash_verification_available"] = _body_hash_available

        gate_result = run_gate(**gate_ctx)
        gate_decision = gate_result.get("decision", "")
        gate_approved = gate_result.get("approved", False)
        log(f"  Gate decision: {gate_decision}")
        log(f"  Gate approved: {gate_approved}")

        if not gate_approved:
            blockers_list = gate_result.get("blockers", [])
            return pipeline_blocked(
                f"Phase H Live-Draft Gate BLOCKED: {gate_decision}. "
                f"Blockers: {blockers_list}. "
                f"Message: {gate_result.get('message', '')}"
            )

        # Gate approved — but DRY-RUN takes absolute precedence
        if DRY_RUN:
            print()
            log("  DRY-RUN: Shopify transaction SKIPPED (DRY_RUN flag set)")
            return {
                "blocked": False,
                "dry_run": True,
                "requested_mode": REQUESTED_MODE,
                "live_draft_requested": LIVE_DRAFT,
                "live_draft_confirmed": CONFIRM_LIVE_DRAFT,
                "phase_h_stop": False,
                "gate_approved": True,
                "gate_decision": gate_decision,
                "shopify_touched": False,
                "queue_touched": False,
                "selected_job": job_num,
                "selected_topic": job.get("topic"),
                "queue_status": job.get("queue_status"),
                "publisher_passed": publisher_passed,
                "publisher_decision": publisher_decision,
                "publisher_route": publisher_route,
                "gate_result": gate_result,
                "transaction_result": {"decision": "dry_run_skipped", "approved": False, "shopify_article_id": None},
                "queue_commit_result": {"decision": "dry_run_skipped", "approved": False},
                "pipeline_phases_completed": ["1A", "1B", "1C", "2D-WRITER", "2A-POST-WRITE-INLINE", "2B-INLINE", "2E", "H"],
                "pipeline_run_id": pipeline_run_id,
                "writer_output_path": exec_output_path,
                "next_action": (
                    f"Gate approved (decision={gate_decision}). "
                    f"DRY-RUN: transaction skipped. "
                    f"Run without --dry-run to execute live Shopify transaction."
                ),
            }

        print()
        log("  Gate approved — running live Shopify transaction...")

        transaction_result = run_safe_draft_transaction(
            selected_job_context={
                "job_number": job.get("job_number"),
                "topic": job.get("topic"),
                "queue_status": job.get("queue_status"),
                "target_date": job.get("target_date"),
                "shopify_handle": job.get("shopify_handle"),
            },
            writer_plan=_gate_writer_plan,
            writer_execution=_gate_writer_exec,
            post_write_review=_gate_review,
            html_validation=_gate_html,
            publisher_preflight={
                "publisher_job_number": publisher_job,
                "decision": publisher_decision,
                "passed": publisher_passed,
                "payload_preview": {
                    "handle": job.get("shopify_handle"),
                },
            },
            publisher_route=publisher_route,
            live_draft_gate_result=gate_result,
        )
        transaction_decision = transaction_result.get("decision", "")
        transaction_approved = transaction_result.get("approved", False)
        log(f"  Transaction decision: {transaction_decision}")
        log(f"  Transaction approved: {transaction_approved}")
        if transaction_result.get("shopify_article_id"):
            log(f"  Shopify article ID: {transaction_result['shopify_article_id']}")
        if transaction_result.get("blockers"):
            log(f"  Transaction blockers: {transaction_result['blockers']}")

        # Supabase-backed runs treat the database job/run records as transaction
        # truth. The Markdown queue remains readable input and is never mutated.
        if os.environ.get("ORIN_DURABLE_DB_MODE") == "1":
            commit_result = {
                "decision": "DATABASE_AUTHORITATIVE_NO_QUEUE_COMMIT",
                "approved": True,
                "blockers": [],
            }
        else:
            commit_result = commit_transaction_result(
                queue_path=str(QUEUE_PATH),
                transaction_result=transaction_result,
                dry_run=DRY_RUN,
            )
        commit_decision = commit_result.get("decision", "")
        commit_approved = commit_result.get("approved", False)
        log(f"  Queue commit decision: {commit_decision}")
        log(f"  Queue commit approved: {commit_approved}")
        if commit_result.get("blockers"):
            log(f"  Queue commit blockers: {commit_result['blockers']}")

        shopify_write_state = transaction_result.get(
            "shopify_write_state",
            "article_observed"
            if transaction_result.get("shopify_article_id") is not None
            else "not_attempted",
        )
        reconciliation_status = transaction_result.get(
            "reconciliation_status", "not_started"
        )
        shopify_touched = shopify_write_state == "article_observed"
        queue_touched = commit_decision in (
            "QUEUE_FINALISATION_APPROVED",
            "QUEUE_NEEDS_HUMAN_REVIEW_COMMITTED",
        )
        blocked = not transaction_approved or not commit_approved
        replay_disposition = (
            "reconcile"
            if reconciliation_status == "needs_review"
            or shopify_write_state == "unknown"
            else "terminal"
        )

        return {
            "blocked": blocked,
            "dry_run": False,
            "requested_mode": REQUESTED_MODE,
            "live_draft_requested": LIVE_DRAFT,
            "live_draft_confirmed": CONFIRM_LIVE_DRAFT,
            "phase_h_stop": False,
            "gate_approved": True,
            "gate_decision": gate_decision,
            "shopify_touched": shopify_touched,
            "shopify_write_state": shopify_write_state,
            "replay_disposition": replay_disposition,
            "queue_touched": queue_touched,
            "selected_job": job_num,
            "selected_topic": job.get("topic"),
            "queue_status": job.get("queue_status"),
            "publisher_passed": publisher_passed,
            "publisher_decision": publisher_decision,
            "publisher_route": publisher_route,
            "gate_result": gate_result,
            "transaction_result": transaction_result,
            "queue_commit_result": commit_result,
            "pipeline_phases_completed": ["1A", "1B", "1C", "2D-WRITER", "2A-POST-WRITE-INLINE", "2B-INLINE", "2E", "H", "I-TX", "I7"],
            "pipeline_run_id": pipeline_run_id,
            "writer_output_path": exec_output_path,
            "next_action": (
                f"Transaction: {transaction_decision} ({transaction_approved}). "
                f"Queue commit: {commit_decision} ({commit_approved}). "
                f"Article ID: {transaction_result.get('shopify_article_id', 'none')}."
            ),
        }

    # ── INCOMPLETE LIVE-DRAFT REQUEST ──────────────────────────────────────
    return pipeline_blocked(
        "Live-draft request blocked: --confirm-live-draft is required."
    )


# ─── REPORT WRITER ────────────────────────────────────────────────────────────

def build_report(result, *, timestamp=None):
    """Build a truthful report from the effective result and request intent."""
    dry_run = bool(result.get("dry_run", DRY_RUN))
    requested_mode = result.get("requested_mode", REQUESTED_MODE)
    effective_mode = "dry-run" if dry_run else "live-draft"
    blocked = bool(result.get("blocked", False))
    transaction_result = result.get("transaction_result") or {}
    queue_commit_result = result.get("queue_commit_result") or {}

    default_next_action = (
        result.get("stop_reason")
        or ("Resolve the blocking reason before retrying." if blocked else None)
        or ("Dry-run complete; review evidence before requesting a live draft." if dry_run else None)
        or "Review the transaction and queue-commit evidence."
    )

    report = {
        "pipeline": "ORIN Cron Entrypoint Phase 3B",
        "mode": effective_mode,
        "requested_mode": requested_mode,
        "effective_mode": effective_mode,
        "timestamp": timestamp or datetime.now(timezone.utc).isoformat(),
        "dry_run": dry_run,
        "live_draft_requested": bool(result.get("live_draft_requested", LIVE_DRAFT)),
        "live_draft_confirmed": bool(result.get("live_draft_confirmed", CONFIRM_LIVE_DRAFT)),
        "shopify_touched": result.get("shopify_touched", False),
        "queue_touched": result.get("queue_touched", False),
        "blocked": blocked,
        "block_reason": result.get("block_reason"),
        "stop_reason": result.get("stop_reason"),
        "planner_decision": result.get("planner_decision"),
        "selected_job": result.get("selected_job"),
        "selected_topic": result.get("selected_topic"),
        "publisher_passed": result.get("publisher_passed"),
        "publisher_decision": result.get("publisher_decision"),
        "review_decision": result.get("review_decision"),
        "pipeline_run_id": result.get("pipeline_run_id", ""),
        "writer_output_path": result.get("writer_output_path"),
        "transaction_decision": transaction_result.get("decision"),
        "queue_commit_decision": queue_commit_result.get("decision"),
        "shopify_article_id": transaction_result.get("shopify_article_id"),
        "shopify_create_count": transaction_result.get("shopify_create_count", 0),
        "shopify_write_state": transaction_result.get(
            "shopify_write_state",
            result.get("shopify_write_state", "not_attempted"),
        ),
        "shopify_idempotency_marker": transaction_result.get("shopify_idempotency_marker"),
        "reconciliation_status": transaction_result.get("reconciliation_status", "not_required"),
        "replay_disposition": result.get("replay_disposition", "terminal"),
        "next_action": result.get("next_action", default_next_action),
        "pipeline_phases": [
            "Phase 1A: State Agent (read-only, via orin_phase1a_state_dryrun.py)",
            "Phase 1B: Planner Agent (read-only, via orin_phase1b_planner_dryrun.py)",
            "Phase 1C: Recovery Agent (read-only, via orin_phase1c_recovery_dryrun.py)",
            "Phase 2D-WRITER: Writer Planning + Execution (via orin_phase2c_writer_planning_dryrun.py + inline WriterAgent)",
            "Phase 2A-POST-WRITE-INLINE: Post-write review (inline review_selected_job_draft())",
            "Phase 2B-INLINE: Duplicate Decision Memory (inline build_duplicate_memory())",
            "Phase 2E/2G: Publisher Agent preflight (read-only, via orin_phase2e_publisher_dryrun.py)",
            "Phase H: Live-Draft Gate v2 (via live_draft_gate.py)",
            "Phase I: Shopify draft transaction (via shopify_draft_transaction.py)",
        ],
        "blocked_scripts_check": BLOCKED_SCRIPT_PATTERNS,
        "never_calls": [
            "tools/scheduler/next_blog_job.py (BLOCKED — not called)",
            "tools/shopify_publisher/publish_blog_draft.py (BLOCKED — not called)",
            "tools/shopify_publisher/update_blog_draft.py (BLOCKED — not called)",
            "tools/scheduler/mark_job_done.py (BLOCKED — not called)",
        ],
        "safety": [
            "No mode flag defaults to dry-run",
            "An explicit --dry-run takes precedence over live-draft flags",
            "A live draft requires --live-draft, --confirm-live-draft, and gate approval",
            "Never calls old publish_blog_draft.py, update_blog_draft.py, next_blog_job.py",
            "Never sets published_at",
            "Never auto-publishes",
            "Queue commit occurs only after a verified Shopify transaction result",
            "Pipeline stops safely on any blocking decision",
            "Phase 2A review is INLINE — always reviews actual writer HTML, never a stale artefact",
            "Phase 2B duplicate check is INLINE — always checks the selected job, not a batch scope",
            "All /tmp artefacts carry pipeline_run_id — stale artefacts from previous runs are rejected",
        ],
    }

    return report


def write_report(result):
    """Write JSON report to JSON_OUTPUT_PATH."""
    report = build_report(result)

    with open(JSON_OUTPUT_PATH, "w") as f:
        json.dump(report, f, indent=2, default=str)

    print(f"\n📄 JSON preview written to: {JSON_OUTPUT_PATH}")
    return report


# ─── ENTRY POINT ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if not JSON_MODE:
        print("ORIN CRON ENTRYPOINT — Phase 3B")
        print(f"Mode: {'DRY-RUN' if DRY_RUN else 'LIVE-DRAFT REQUESTED'}")
        print(f"Job filter: {JOB_FILTER or 'all (lowest-numbered due job)'}")
        print()

    result = run_pipeline()
    report = write_report(result)

    if JSON_MODE:
        print(json.dumps(report, indent=2, default=str))
    else:
        print()
        print("=" * 60)
        print("SUMMARY")
        print("=" * 60)
        print(f"  Blocked:          {report['blocked']}")
        print(f"  Shopify touched:   {report['shopify_touched']}")
        print(f"  Queue touched:    {report['queue_touched']}")
        print(f"  Selected job:     {report['selected_job'] or 'none'}")
        print(f"  Publisher pass:    {report['publisher_passed']}")
        print(f"  Pipeline run ID:   {report['pipeline_run_id']}")
        print(f"  Block reason:     {report['block_reason'] or 'none'}")
        print(f"  Stop reason:     {report['stop_reason'] or 'none'}")
        if not report["blocked"]:
            print(f"  Next action:     {report['next_action']}")
        print("=" * 60)
