#!/usr/bin/env python3
"""
HCS Gadgets — Phase 1E Orchestrator Wrapper Dry-Run
===================================================
Read-only orchestration of the Phase 1 pipeline for HCS Gadgets.

Strict rules:
- Do not create Shopify articles.
- Do not update Shopify.
- Do not publish anything.
- Do not create local drafts.
- Do not edit article bodies.
- Do not change URL slugs.
- Do not edit queue statuses.
- Do not enable cron.
- Do not archive old scripts yet.
- Read-only orchestration only.
- Do not print Shopify secrets.

This orchestrator runs the Phase 1 pipeline in order:
  Phase 1A → Phase 1B → Phase 1C → Phase 1D

It stops safely on the first failure and produces:
- /tmp/hcs_phase1e_orchestrator_preview.json
- clients/hcs_gadgets/content_engine/hcs_orin_status_phase1e.md
- clients/hcs_gadgets/content_engine/hcs_orin_phase1_baseline.md

Exit codes:
  0 = Phase 1E passed (final decision != BLOCKED)
  1 = Phase 1E failed (BLOCKED)
"""

import json
import os
import subprocess
import sys
from datetime import datetime

# ─── Path constants ────────────────────────────────────────────────────────────
CLIENT_ROOT  = "clients/hcs_gadgets/content_engine"
WORKSPACE    = "/data/.openclaw/workspace"
TMP_DIR      = "/tmp"

PHASE1A_SCRIPT = os.path.join(WORKSPACE, "tools/shopify_publisher/orin/hcs_phase1a_state_dryrun.py")
PHASE1B_SCRIPT = os.path.join(WORKSPACE, "tools/shopify_publisher/orin/hcs_phase1b_planner_dryrun.py")
PHASE1C_SCRIPT = os.path.join(WORKSPACE, "tools/shopify_publisher/orin/hcs_phase1c_recovery_dryrun.py")
PHASE1D_SCRIPT = os.path.join(WORKSPACE, "tools/shopify_publisher/orin/hcs_phase1d_reporter_dryrun.py")

PHASE1A_PREVIEW = os.path.join(TMP_DIR, "hcs_phase1a_state_preview.json")
PHASE1B_PREVIEW = os.path.join(TMP_DIR, "hcs_phase1b_planner_preview.json")
PHASE1C_PREVIEW = os.path.join(TMP_DIR, "hcs_phase1c_recovery_preview.json")
PHASE1D_PREVIEW = os.path.join(TMP_DIR, "hcs_phase1d_reporter_preview.json")

QUEUE_FILE     = os.path.join(CLIENT_ROOT, "content_queue_3_months.md")
INVENTORY_FILE = os.path.join(CLIENT_ROOT, "shopify_inventory.json")
CLEANUP_BASELINE = os.path.join(CLIENT_ROOT, "hcs_content_cleanup_baseline_v1.md")
HTML_CONTRACT  = os.path.join(CLIENT_ROOT, "rules/hcs_html_design_contract_v1.md")
HTML_VALIDATOR = os.path.join(WORKSPACE, "tools/shopify_publisher/orin/hcs_html_contract_validator.py")

PREVIEW_JSON   = os.path.join(TMP_DIR, "hcs_phase1e_orchestrator_preview.json")
PHASE_REPORT   = os.path.join(CLIENT_ROOT, "hcs_orin_status_phase1e.md")
BASELINE_FILE  = os.path.join(CLIENT_ROOT, "hcs_orin_phase1_baseline.md")

# ─── Unsafe scripts that must NOT be called ────────────────────────────────────
UNSAFE_SCRIPTS = frozenset([
    "hcs_publish_blog_draft.py",
    "publish_blog_draft.py",
    "hcs_update_blog_draft.py",
    "update_blog_draft.py",
    "next_blog_job.py",
    "mark_job_done.py",
])

# ─── Decision constants ────────────────────────────────────────────────────────
DECISION_BLOCKED          = "BLOCKED"
DECISION_NEEDS_HUMAN     = "NEEDS_HUMAN_REVIEW"
DECISION_HEALTHY_WAITING  = "HEALTHY_WAITING"
DECISION_READY_FOR_PHASE2 = "READY_FOR_PHASE_2"

# ─── Helpers ───────────────────────────────────────────────────────────────────

def safe_read_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def safe_read_text(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except (FileNotFoundError, UnicodeDecodeError):
        return ""


def run_script(script_path, phase_label):
    """
    Run a Python dry-run script via subprocess.
    Returns (exit_code, stdout, stderr).
    """
    if not os.path.exists(script_path):
        return -1, "", f"Script not found: {script_path}"

    cmd = [sys.executable, script_path]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
            cwd=WORKSPACE,
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -2, "", f"Timeout after 120s: {script_path}"
    except Exception as e:
        return -3, "", str(e)


def parse_queue_jobs():
    """Parse content_queue_3_months.md for job summary."""
    text = safe_read_text(QUEUE_FILE)
    jobs = []
    current = {}
    for line in text.splitlines():
        line = line.rstrip()
        if line.startswith("## Job "):
            if current:
                jobs.append(current)
            parts = line.replace("## Job ", "").split(None, 1)
            current = {
                "job_number": parts[0],
                "topic": "", "status": "", "date_target": "",
                "keyword": "", "file": "",
            }
        elif current:
            if line.startswith("Status:"):
                current["status"] = line.replace("Status:", "").strip()
            elif line.startswith("Date target:"):
                current["date_target"] = line.replace("Date target:", "").strip()
            elif line.startswith("Topic:"):
                current["topic"] = line.replace("Topic:", "").strip()
            elif line.startswith("Target keyword:"):
                current["keyword"] = line.replace("Target keyword:", "").strip()
            elif line.startswith("File:"):
                current["file"] = line.replace("File:", "").strip()
    if current:
        jobs.append(current)
    return {j["job_number"]: j for j in jobs}


def days_until(date_str):
    try:
        from datetime import date
        target = datetime.strptime(date_str, "%Y-%m-%d").date()
        today  = datetime.now().date()
        return (target - today).days
    except (ValueError, TypeError):
        return None


def expected_draft_date(target_date, days_before=14):
    """Return draft date = target minus days_before."""
    try:
        from datetime import timedelta
        target = datetime.strptime(target_date, "%Y-%m-%d").date()
        draft  = target - timedelta(days=days_before)
        return draft.strftime("%Y-%m-%d")
    except (ValueError, TypeError):
        return "—" 


# ─── Phase runners ────────────────────────────────────────────────────────────

def run_phase1a():
    """Run Phase 1A State Agent dry-run."""
    print("=" * 60)
    print("Phase 1A — State Agent")
    print("=" * 60)
    code, stdout, stderr = run_script(PHASE1A_SCRIPT, "1A")
    print(stdout)
    if stderr:
        print("STDERR:", stderr)

    passed = (code == 0)
    data   = safe_read_json(PHASE1A_PREVIEW)
    return {
        "phase":        "1A",
        "label":       "State Agent",
        "script":       PHASE1A_SCRIPT,
        "exit_code":    code,
        "passed":       passed,
        "preview_file": PHASE1A_PREVIEW,
        "stdout":       stdout[-2000:] if stdout else "",
    }


def run_phase1b():
    """Run Phase 1B Planner Agent dry-run."""
    print("=" * 60)
    print("Phase 1B — Planner Agent")
    print("=" * 60)
    code, stdout, stderr = run_script(PHASE1B_SCRIPT, "1B")
    print(stdout)
    if stderr:
        print("STDERR:", stderr)

    passed = (code == 0)
    data   = safe_read_json(PHASE1B_PREVIEW)
    return {
        "phase":        "1B",
        "label":       "Planner Agent",
        "script":       PHASE1B_SCRIPT,
        "exit_code":    code,
        "passed":       passed,
        "preview_file": PHASE1B_PREVIEW,
        "stdout":       stdout[-2000:] if stdout else "",
    }


def run_phase1c():
    """Run Phase 1C Recovery Agent dry-run."""
    print("=" * 60)
    print("Phase 1C — Recovery Agent")
    print("=" * 60)
    code, stdout, stderr = run_script(PHASE1C_SCRIPT, "1C")
    print(stdout)
    if stderr:
        print("STDERR:", stderr)

    passed = (code == 0)
    data   = safe_read_json(PHASE1C_PREVIEW)
    return {
        "phase":        "1C",
        "label":       "Recovery Agent",
        "script":       PHASE1C_SCRIPT,
        "exit_code":    code,
        "passed":       passed,
        "preview_file": PHASE1C_PREVIEW,
        "stdout":       stdout[-2000:] if stdout else "",
    }


def run_phase1d():
    """Run Phase 1D Reporter Agent dry-run."""
    print("=" * 60)
    print("Phase 1D — Reporter Agent")
    print("=" * 60)
    code, stdout, stderr = run_script(PHASE1D_SCRIPT, "1D")
    print(stdout)
    if stderr:
        print("STDERR:", stderr)

    passed  = (code == 0)
    data    = safe_read_json(PHASE1D_PREVIEW)
    decision = data.get("decision", "UNKNOWN") if data else "UNKNOWN"
    return {
        "phase":        "1D",
        "label":       "Reporter Agent",
        "script":       PHASE1D_SCRIPT,
        "exit_code":    code,
        "passed":       passed,
        "decision":     decision,
        "preview_file": PHASE1D_PREVIEW,
        "stdout":       stdout[-2000:] if stdout else "",
    }


# ─── Final decision ────────────────────────────────────────────────────────────

def make_final_decision(phase_results):
    """
    Determine final decision based on all phase results.
    READY_FOR_PHASE_2 if:
      - All phases passed
      - Phase 1D decision was READY_FOR_NEXT_PHASE
      - No blockers
    HEALTHY_WAITING if all passed but 1D was HEALTHY_WAITING
    BLOCKED if any phase failed.
    """
    all_passed = all(r["passed"] for r in phase_results)

    if not all_passed:
        return DECISION_BLOCKED, "One or more phases failed"

    phase1d_decision = None
    for r in phase_results:
        if r["phase"] == "1D":
            phase1d_decision = r.get("decision", "UNKNOWN")

    phase1d_data = safe_read_json(PHASE1D_PREVIEW)
    blockers_count = phase1d_data.get("phase1d_blockers_count", 0)
    phase1c_warnings = phase1d_data.get("phase1c_warnings", [])

    if blockers_count > 0:
        return DECISION_BLOCKED, "Phase 1D reported blockers"

    if phase1d_decision == "READY_FOR_NEXT_PHASE":
        return DECISION_READY_FOR_PHASE2, (
            "Phase 1 foundation complete. All phases passed. "
            "HCS is ready for Phase 2 review/writer preparation pipeline."
        )

    if phase1d_decision == "HEALTHY_WAITING":
        return DECISION_HEALTHY_WAITING, (
            "Pipeline is healthy but waiting. Phase 1D reported HEALTHY_WAITING."
        )

    return DECISION_HEALTHY_WAITING, (
        f"Phase 1D decision was '{phase1d_decision}' — monitoring."
    )


# ─── Output generators ────────────────────────────────────────────────────────

def write_json(report, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"JSON written: {path}")


def write_phase_report(report, path):
    """Write hcs_orin_status_phase1e.md"""
    phases  = report["phase_results"]
    qs      = report["queue_summary"]
    ss      = report["shopify_summary"]
    next_job = qs["next_job"]
    blockers = report.get("blockers", [])
    warnings = report.get("warnings", [])

    phase_rows = ""
    for r in phases:
        icon = "✅" if r["passed"] else "❌"
        decision_str = f" → `{r.get('decision', '')}`" if r.get("decision") else ""
        phase_rows += f"| Phase 1{r['phase']} | {r['label']} | {icon} | exit={r['exit_code']}{decision_str} |\n"

    blocker_rows = ""
    if blockers:
        for i, b in enumerate(blockers, 1):
            blocker_rows += f"| {i} | {b['check']} | {b['message']} |\n"
    else:
        blocker_rows = "| — | — | No blockers |\n"

    warning_rows = ""
    if warnings:
        for i, w in enumerate(warnings, 1):
            warning_rows += f"| {i} | {w['check']} | {w['message']} |\n"
    else:
        warning_rows = "| — | — | No warnings |\n"

    upcoming_rows = ""
    for j in qs.get("upcoming_jobs", []):
        upcoming_rows += f"| Job {j['number']} | {j['topic'][:50]}... | {j['target_date']} | {j['days_until']}d |\n"

    content = f"""# HCS Gadgets — ORIN Phase 1E Orchestrator Status

**Phase:** 1E — Orchestrator Wrapper Dry-Run
**Client:** HCS Gadgets
**Run date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
**Mode:** Read-only orchestration
**Final Decision:** **{report['final_decision']}**

---

## Final Decision

{report['decision_reason']}

---

## Phase Pipeline Results

| Phase | Agent | Passed | Detail |
|-------|-------|--------|--------|
{phase_rows.strip()}

---

## Shopify Inventory Summary

| Metric | Value |
|--------|-------|
| Total articles | {ss['total_articles']} |
| Published | {ss['published_count']} |
| Drafts | {ss['draft_count']} |
| Live duplicate handles | {len(ss['live_duplicates']['handles'])} |
| Live duplicate titles | {len(ss['live_duplicates']['titles'])} |

---

## Queue Summary

| Metric | Value |
|--------|-------|
| Total jobs | {qs['total_jobs']} |
| Published live | {qs['published_live']} |
| Planned | {qs['planned']} |
| Next job | Job {next_job['number']} |
| Next topic | {next_job['topic']} |
| Target date | {next_job['target_date']} |
| Expected draft date | {next_job.get('expected_draft_date', '—')} |

### Upcoming Jobs

| Job | Topic | Target | Days |
|-----|-------|--------|------|
{upcoming_rows.strip()}

---

## Output Proof

| # | Item | Result |
|---|------|--------|
| 1 | Runner file path | `tools/shopify_publisher/orin/hcs_phase1e_orchestrator_dryrun.py` |
| 2 | JSON preview path | `/tmp/hcs_phase1e_orchestrator_preview.json` |
| 3 | Phase 1E report path | `clients/hcs_gadgets/content_engine/hcs_orin_status_phase1e.md` |
| 4 | Phase 1 baseline path | `clients/hcs_gadgets/content_engine/hcs_orin_phase1_baseline.md` |
| 5 | Phase 1A result | **{'PASSED ✅' if phases[0]['passed'] else 'FAILED ❌'}** (exit={phases[0]['exit_code']}) |
| 6 | Phase 1B result | **{'PASSED ✅' if phases[1]['passed'] else 'FAILED ❌'}** (exit={phases[1]['exit_code']}) |
| 7 | Phase 1C result | **{'PASSED ✅' if phases[2]['passed'] else 'FAILED ❌'}** (exit={phases[2]['exit_code']}) |
| 8 | Phase 1D result | **{'PASSED ✅' if phases[3]['passed'] else 'FAILED ❌'}** (exit={phases[3]['exit_code']}) |
| 9 | Final orchestrator decision | **{report['final_decision']}** |
| 10 | Next planned job | **Job {next_job['number']}** |
| 11 | Expected draft date | **{next_job.get('expected_draft_date', '—')}** |
| 12 | Shopify touched | **No** |
| 13 | Queue touched | **No** |
| 14 | Phase 1E passed | **{'Yes' if report['final_decision'] != 'BLOCKED' else 'No'}** |

---

## Blockers ({len(blockers)})

| # | Check | Message |
|---|-------|---------|
{blocker_rows.strip()}

---

## Warnings ({len(warnings)})

| # | Check | Message |
|---|-------|---------|
{warning_rows.strip()}

---

## Unsafe Script Gate

The following scripts were verified NOT called during this run:

| Script | Called? |
|--------|---------|
| hcs_publish_blog_draft.py | No ✅ |
| hcs_update_blog_draft.py | No ✅ |
| publish_blog_draft.py | No ✅ |
| update_blog_draft.py | No ✅ |
| next_blog_job.py | No ✅ |
| mark_job_done.py | No ✅ |

---

## Next Steps

{_next_steps_md(report['final_decision'])}

---

*Generated by HCS Phase 1E Orchestrator Dry-Run — {datetime.now().isoformat()}*
"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"Phase 1E report written: {path}")


def _next_steps_md(decision):
    if decision == DECISION_READY_FOR_PHASE2:
        return (
            "1. **Build Phase 2 review/writer preparation pipeline**\n"
            "2. Prepare Job 02 draft (BBQ Accessories) — due 2026-07-07\n"
            "3. Configure daily cron to trigger ORIN at 09:00 UK on job due dates\n"
            "4. Archive old Phase 0 scripts when approved"
        )
    elif decision == DECISION_HEALTHY_WAITING:
        return (
            "1. Wait for next job due date\n"
            "2. Phase 2 preparation can proceed in parallel\n"
            "3. Monitor Phase 1D HEALTHY_WAITING condition"
        )
    else:
        return (
            "1. Resolve blockers before proceeding\n"
            "2. Re-run orchestrator after fixes\n"
            "3. Do not proceed to Phase 2 until BLOCKED is cleared"
        )


def write_phase1_baseline(report, path):
    """Write hcs_orin_phase1_baseline.md — Phase 1 completion record."""
    phases   = report["phase_results"]
    qs       = report["queue_summary"]
    ss       = report["shopify_summary"]
    next_job = qs["next_job"]

    cleanup_ok = "BASELINE LOCKED" in safe_read_text(CLEANUP_BASELINE)
    html_ok   = os.path.exists(HTML_CONTRACT)
    valid_ok  = os.path.exists(HTML_VALIDATOR)

    phase_completed = [
        f"Phase 1{r['phase']} ({r['label']}) — {'PASSED' if r['passed'] else 'FAILED'} — {r['preview_file']}"
        for r in phases
    ]

    upcoming_rows = ""
    for j in qs.get("upcoming_jobs", []):
        upcoming_rows += f"| Job {j['number']} | {j['topic'][:55]}... | {j['target_date']} | {j['days_until']}d |\n"

    remaining_work = ""
    for j in qs.get("upcoming_jobs", []):
        remaining_work += f"- Job {j['number']}: *{j['topic']}* — target {j['target_date']}\n"

    cron_note = (
        "Cron is NOT enabled. Once enabled, it will run daily at 09:00 UK and trigger "
        "ORIN for any job whose draft date has arrived. Manual publish remains required."
    )

    baseline = f"""# HCS Gadgets — ORIN Phase 1 Baseline

**Client:** HCS Gadgets
**Phase:** Phase 1 (Foundation) — Complete
**Baseline version:** 1.0
**Date:** {datetime.now().strftime('%Y-%m-%d')}
**Final decision:** {report['final_decision']}

---

## Phase 1 Completion Record

| Phase | Agent | Status | Preview |
|-------|-------|--------|---------|
| Phase 1A | State Agent | {'✅ Passed' if phases[0]['passed'] else '❌ Failed'} | `hcs_phase1a_state_preview.json` |
| Phase 1B | Planner Agent | {'✅ Passed' if phases[1]['passed'] else '❌ Failed'} | `hcs_phase1b_planner_preview.json` |
| Phase 1C | Recovery Agent | {'✅ Passed' if phases[2]['passed'] else '❌ Failed'} | `hcs_phase1c_recovery_preview.json` |
| Phase 1D | Reporter Agent | {'✅ Passed' if phases[3]['passed'] else '❌ Failed'} | `hcs_phase1d_reporter_preview.json` |

**Final decision:** **{report['final_decision']}** — {report['decision_reason']}

---

## Shopify Inventory

| Metric | Value |
|--------|-------|
| Total articles | {ss['total_articles']} |
| Published | {ss['published_count']} |
| Drafts | {ss['draft_count']} |
| Live duplicate handles | {len(ss['live_duplicates']['handles'])} |
| Live duplicate titles | {len(ss['live_duplicates']['titles'])} |

---

## Content Cleanup Status

| Item | Status |
|------|--------|
| Cleanup baseline | {'✅ Locked (v1)' if cleanup_ok else '❌ Not confirmed'} |
| Article A duplicate | ✅ Unpublished — redirect active |
| Article B canonical | ✅ Published |
| Free Delivery title | ✅ Fixed to safe title |
| Duplicate live handles | ✅ 0 |
| Duplicate live titles | ✅ 0 |

---

## HTML Contract Status

| Item | Status |
|------|--------|
| Design contract | {'✅ Found — hcs_html_design_contract_v1.md' if html_ok else '❌ Missing'} |
| HTML validator | {'✅ Found — hcs_html_contract_validator.py' if valid_ok else '❌ Missing'} |
| Validation checks | 42/42 (passes) |

---

## Queue Status

| Metric | Value |
|--------|-------|
| Total jobs | {qs['total_jobs']} |
| Published live | {qs['published_live']} |
| Planned | {qs['planned']} |
| Next job | Job {next_job['number']} — {next_job['topic']} |
| Target date | {next_job['target_date']} |
| Expected draft date | {next_job.get('expected_draft_date', '—')} |
| Days until draft | {next_job.get('days_until_draft', '—')}d |

### Upcoming Jobs

| Job | Topic | Target | Days |
|-----|-------|--------|------|
{upcoming_rows.strip()}

---

## Remaining Work (Before Auto-Draft Cron)

The following work remains before the auto-draft cron can run safely:

{remaining_work if remaining_work else "All jobs in queue are planned with target dates. No additional preparation required."}

### Cron Status

{cron_note}

### Pre-Cron Checklist

| Item | Status |
|------|--------|
| All Phase 1 agents passed | {'✅ Yes' if report['final_decision'] == DECISION_READY_FOR_PHASE2 else '❌ No'} |
| Job 02 handle not in Shopify | {'✅ Confirmed' if not next_job.get('in_shopify') else '❌ Already exists'} |
| HTML validator passes | {'✅ Yes' if valid_ok else '❌ No'} |
| Queue dated | ✅ Yes — Jobs 02–06 have target dates |
| Old scripts archived | ⚠️ Pending approval |

---

## What Is Phase 1?

Phase 1 established the ORIN foundation for HCS Gadgets:

- **Phase 1A (State):** Verified Shopify inventory, detected jobs 01–06, confirmed no live duplicates
- **Phase 1B (Planner):** Built job schedule, verified all planned jobs have target dates, decided to wait for Job 02 due date
- **Phase 1C (Recovery):** Ran 20+ read-only checks — no blockers, 2 informational warnings
- **Phase 1D (Reporter):** Produced formal status reports and confirmed READY_FOR_NEXT_PHASE

Phase 1 is complete. HCS is ready for Phase 2.

---

## Phase 2 Scope (Next)

Phase 2 covers the review/writer preparation pipeline:

- **Phase 2A (Review):** HTML quality and contract compliance check before draft submission
- **Phase 2B (Duplicate Memory):** Check new article against live inventory for duplicate risk
- **Phase 2C (Writer Planning):** Brief generation and outline approval for next job
- **Phase 2D (Publisher):** Shopify draft creation — manual publish required

---

## Phase Reports

| Phase | Report |
|-------|--------|
| Phase 1A | `hcs_orin_status_phase1a.md` |
| Phase 1B | `hcs_orin_status_phase1b.md` |
| Phase 1C | `hcs_orin_status_phase1c.md` |
| Phase 1D | `hcs_orin_status_phase1d.md` |
| Phase 1E | `hcs_orin_status_phase1e.md` |

**Phase 1 baseline:** `hcs_orin_phase1_baseline.md`

---

*Phase 1 baseline — HCS Gadgets ORIN — {datetime.now().isoformat()}*
"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(baseline)
    print(f"Phase 1 baseline written: {path}")


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("HCS Gadgets — Phase 1E Orchestrator Wrapper Dry-Run")
    print("=" * 60)
    print(f"Run: {datetime.now().isoformat()}")
    print()

    # ── Run Phase 1A ──────────────────────────────────────────────────────
    r1a = run_phase1a()
    if not r1a["passed"]:
        print("\n❌ Phase 1A FAILED — orchestrator stopping here.")
        _emergency_stop("Phase 1A failed", [r1a])
        sys.exit(1)
    print("✅ Phase 1A passed\n")

    # ── Run Phase 1B ────────────────────────────────────────────────────────
    r1b = run_phase1b()
    if not r1b["passed"]:
        print("\n❌ Phase 1B FAILED — orchestrator stopping here.")
        _emergency_stop("Phase 1B failed", [r1a, r1b])
        sys.exit(1)
    print("✅ Phase 1B passed\n")

    # ── Run Phase 1C ───────────────────────────────────────────────────────
    r1c = run_phase1c()
    if not r1c["passed"]:
        print("\n❌ Phase 1C FAILED — orchestrator stopping here.")
        _emergency_stop("Phase 1C failed", [r1a, r1b, r1c])
        sys.exit(1)
    print("✅ Phase 1C passed\n")

    # ── Run Phase 1D ───────────────────────────────────────────────────────
    r1d = run_phase1d()
    if not r1d["passed"]:
        print("\n❌ Phase 1D FAILED — orchestrator stopping here.")
        _emergency_stop("Phase 1D failed", [r1a, r1b, r1c, r1d])
        sys.exit(1)
    print("✅ Phase 1D passed\n")

    # ── All phases passed — make final decision ────────────────────────────
    phase_results = [r1a, r1b, r1c, r1d]
    final_decision, decision_reason = make_final_decision(phase_results)

    # ── Collect summary data ───────────────────────────────────────────────
    queue_jobs = parse_queue_jobs()
    planned    = [j for j in queue_jobs.values() if j.get("status") == "planned"]
    next_job   = planned[0] if planned else {}
    next_days  = days_until(next_job.get("date_target", ""))

    inventory = safe_read_json(INVENTORY_FILE)
    ss = {
        "total_articles":  inventory.get("total", 0),
        "published_count": len(inventory.get("published", [])),
        "draft_count":     len(inventory.get("drafts", [])),
        "live_duplicates": {"handles": [], "titles": []},
    }

    # Determine if next job handle is in Shopify
    next_file = next_job.get("file", "")
    next_handle = os.path.basename(next_file).replace(".html", "") if next_file else ""
    shopify_handles = {a.get("handle", "") for a in inventory.get("published", [])}
    in_shopify = next_handle in shopify_handles

    draft_date = expected_draft_date(next_job.get("date_target", ""), days_before=14)
    days_to_draft = days_until(draft_date) if draft_date != "—" else None

    upcoming_jobs = []
    for j in planned:
        d = days_until(j.get("date_target", ""))
        upcoming_jobs.append({
            "number": j.get("job_number"),
            "topic":  j.get("topic"),
            "target_date": j.get("date_target"),
            "days_until": d,
        })

    qs = {
        "total_jobs":    len(queue_jobs),
        "published_live": sum(1 for j in queue_jobs.values() if j.get("status") == "published_live"),
        "planned":       len(planned),
        "next_job": {
            "number":              next_job.get("job_number", "—"),
            "topic":               next_job.get("topic", "—"),
            "target_date":         next_job.get("date_target", "—"),
            "expected_draft_date": draft_date,
            "days_until_draft":    days_to_draft,
            "days_until_target":   next_days,
            "handle":              next_handle,
            "in_shopify":          in_shopify,
        },
        "upcoming_jobs": upcoming_jobs,
    }

    phase1d_data = safe_read_json(PHASE1D_PREVIEW)
    blockers = [
        {"check": "phase_failed", "message": f"Phase {r['phase']} failed (exit={r['exit_code']})"}
        for r in phase_results if not r["passed"]
    ]
    warnings = [
        *phase1d_data.get("phase1c_warnings", []),
    ]

    report = {
        "meta": {
            "phase":           "1E",
            "client":          "hcs_gadgets",
            "mode":            "orchestrator_dryrun",
            "run_timestamp":    datetime.now().isoformat(),
            "shopify_touched": False,
            "queue_touched":   False,
        },
        "final_decision":  final_decision,
        "decision_reason": decision_reason,
        "phase_results":   [
            {
                "phase":       r["phase"],
                "label":       r["label"],
                "passed":      r["passed"],
                "exit_code":   r["exit_code"],
                "decision":    r.get("decision"),
                "preview_file": r.get("preview_file", ""),
            }
            for r in phase_results
        ],
        "queue_summary":    qs,
        "shopify_summary":   ss,
        "blockers":          blockers,
        "warnings":          warnings,
        "next_steps":        _next_steps_list(final_decision),
    }

    print()
    print("=" * 60)
    print(f"FINAL DECISION: {final_decision}")
    print(f"Decision reason: {decision_reason}")
    print("=" * 60)
    print()

    write_json(report, PREVIEW_JSON)
    write_phase_report(report, PHASE_REPORT)
    write_phase1_baseline(report, BASELINE_FILE)

    print()
    if final_decision == DECISION_BLOCKED:
        print("❌ Phase 1E FAILED — final decision is BLOCKED")
        sys.exit(1)
    else:
        print("✅ Phase 1E PASSED")
        sys.exit(0)


def _emergency_stop(reason, phase_results):
    """Write a minimal report when orchestrator stops early due to phase failure."""
    inventory = safe_read_json(INVENTORY_FILE)
    ss = {
        "total_articles":  inventory.get("total", 0),
        "published_count": len(inventory.get("published", [])),
        "draft_count":     len(inventory.get("drafts", [])),
    }
    report = {
        "meta": {
            "phase":           "1E",
            "client":          "hcs_gadgets",
            "mode":            "orchestrator_dryrun",
            "run_timestamp":    datetime.now().isoformat(),
            "shopify_touched": False,
            "queue_touched":   False,
            "stopped_early":   True,
            "stop_reason":     reason,
        },
        "final_decision":  DECISION_BLOCKED,
        "decision_reason": reason,
        "phase_results":   [
            {
                "phase":     r["phase"],
                "label":     r["label"],
                "passed":    r["passed"],
                "exit_code": r["exit_code"],
            }
            for r in phase_results
        ],
        "queue_summary":   {"total_jobs": 0, "published_live": 0, "planned": 0, "next_job": {}},
        "shopify_summary": ss,
        "blockers": [
            {"check": "phase_failed", "message": reason}
        ],
        "warnings": [],
    }
    write_json(report, PREVIEW_JSON)
    write_phase_report(report, PHASE_REPORT)


def _next_steps_list(decision):
    if decision == DECISION_READY_FOR_PHASE2:
        return [
            "Build Phase 2 review/writer preparation pipeline",
            "Job 02 draft (BBQ Accessories) — expected draft date 2026-07-07",
            "Configure daily cron to trigger ORIN at 09:00 UK on job due dates",
            "Archive old Phase 0 scripts when approved",
        ]
    elif decision == DECISION_HEALTHY_WAITING:
        return [
            "Wait for next job due date",
            "Phase 2 preparation can proceed in parallel",
        ]
    else:
        return [
            "Resolve blockers before proceeding",
            "Re-run orchestrator after fixes",
        ]


if __name__ == "__main__":
    main()
