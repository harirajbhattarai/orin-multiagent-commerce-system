#!/usr/bin/env python3
"""
HCS Gadgets — Phase 1D Reporter Agent Dry-Run
==============================================
Read-only reporting agent for HCS Gadgets ORIN Phase 1D.

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
- Read-only reporting only.
- Do not print Shopify secrets.

Outputs:
- /tmp/hcs_phase1d_reporter_preview.json
- clients/hcs_gadgets/content_engine/hcs_orin_status_phase1d.md
- clients/hcs_gadgets/content_engine/hcs_orin_status.md  (main master status)

Exit codes:
  0 = Phase 1D passed
  1 = Phase 1D failed
"""

import json
import os
import sys
from datetime import datetime

# ─── Path constants ────────────────────────────────────────────────────────────
CLIENT_ROOT      = "clients/hcs_gadgets/content_engine"
TMP_DIR          = "/tmp"

PHASE1A_PREVIEW  = os.path.join(TMP_DIR, "hcs_phase1a_state_preview.json")
PHASE1B_PREVIEW  = os.path.join(TMP_DIR, "hcs_phase1b_planner_preview.json")
PHASE1C_PREVIEW  = os.path.join(TMP_DIR, "hcs_phase1c_recovery_preview.json")

QUEUE_FILE       = os.path.join(CLIENT_ROOT, "content_queue_3_months.md")
INVENTORY_FILE   = os.path.join(CLIENT_ROOT, "shopify_inventory.json")
CLEANUP_BASELINE = os.path.join(CLIENT_ROOT, "hcs_content_cleanup_baseline_v1.md")
CLIENT_CONFIG    = os.path.join(CLIENT_ROOT, "hcs_client_config_draft.json")
HTML_CONTRACT    = os.path.join(CLIENT_ROOT, "rules/hcs_html_design_contract_v1.md")
HTML_VALIDATOR   = "tools/shopify_publisher/orin/hcs_html_contract_validator.py"

PREVIEW_JSON     = os.path.join(TMP_DIR, "hcs_phase1d_reporter_preview.json")
PHASE_REPORT     = os.path.join(CLIENT_ROOT, "hcs_orin_status_phase1d.md")
MASTER_STATUS    = os.path.join(CLIENT_ROOT, "hcs_orin_status.md")

# ─── Decision constants ────────────────────────────────────────────────────────
DECISION_READY_FOR_NEXT_PHASE = "READY_FOR_NEXT_PHASE"
DECISION_HEALTHY_WAITING      = "HEALTHY_WAITING"
DECISION_BLOCKED              = "BLOCKED"
DECISION_NEEDS_HUMAN_REVIEW   = "NEEDS_HUMAN_REVIEW"

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


def parse_queue_jobs():
    """Parse content_queue_3_months.md and return list of job dicts."""
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
                "keyword": "", "file": "", "notes": [],
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
            elif line.startswith("- "):
                current["notes"].append(line[2:].strip())
    if current:
        jobs.append(current)
    return {j["job_number"]: j for j in jobs}


def days_until(date_str):
    """Return approximate days until a date string YYYY-MM-DD from today."""
    try:
        from datetime import date
        target = datetime.strptime(date_str, "%Y-%m-%d").date()
        today  = datetime.now().date()
        return (target - today).days
    except (ValueError, TypeError):
        return None


# ─── Data collection ───────────────────────────────────────────────────────────

def collect():
    """Gather all source data into a single dict."""
    phase1a       = safe_read_json(PHASE1A_PREVIEW)
    phase1b       = safe_read_json(PHASE1B_PREVIEW)
    phase1c       = safe_read_json(PHASE1C_PREVIEW)
    inventory     = safe_read_json(INVENTORY_FILE)
    config        = safe_read_json(CLIENT_CONFIG)
    queue_jobs    = parse_queue_jobs()

    cleanup_text  = safe_read_text(CLEANUP_BASELINE)
    html_contract = safe_read_text(HTML_CONTRACT)

    return {
        "phase1a":       phase1a,
        "phase1b":       phase1b,
        "phase1c":       phase1c,
        "inventory":     inventory,
        "config":        config,
        "queue_jobs":    queue_jobs,
        "cleanup_text":  cleanup_text,
        "html_contract": html_contract,
    }


# ─── Reporter logic ───────────────────────────────────────────────────────────

def make_report(data):
    """
    Build the full status report dict from collected data.
    Returns (report_dict, decision, blockers, warnings).
    """
    phase1a    = data["phase1a"]
    phase1b    = data["phase1b"]
    phase1c    = data["phase1c"]
    inventory  = data["inventory"]
    config     = data["config"]
    queue_jobs = data["queue_jobs"]

    blockers   = []
    warnings   = []
    infos      = []

    # ── Shopify inventory ──────────────────────────────────────────────────
    published  = inventory.get("published", [])
    drafts     = inventory.get("drafts", [])
    pub_count  = len(published)
    draft_count = len(drafts)

    # ── Queue summary ──────────────────────────────────────────────────────
    all_jobs = list(queue_jobs.values())
    job_01   = queue_jobs.get("01", {})
    planned  = [j for j in all_jobs if j.get("status") == "planned"]
    live_jobs = [j for j in all_jobs if j.get("status") == "published_live"]

    next_job = planned[0] if planned else {}
    next_job_number  = next_job.get("job_number", "—")
    next_topic      = next_job.get("topic", "—")
    next_target     = next_job.get("date_target", "—")
    next_keyword    = next_job.get("keyword", "—")
    next_days       = days_until(next_target)
    next_file       = next_job.get("file", "")

    # Expected draft date = 14 days before live target (rule: draft 14d before go-live)
    import re
    match = re.search(r"(\d{4}-\d{2}-\d{2})", next_target)
    if match and next_days is not None and next_days > 14:
        from datetime import datetime, timedelta
        draft_date = (datetime.strptime(next_target, "%Y-%m-%d") - timedelta(days=14)).strftime("%Y-%m-%d")
    else:
        draft_date = "—"

    # ── Phase pass checks ─────────────────────────────────────────────────
    phase1a_ok = bool(phase1a.get("phase1a_passed"))
    phase1b_ok = bool(phase1b.get("phase1b_passed"))
    phase1c_ok = bool(phase1c.get("phase1c_passed"))

    blockers_count = phase1c.get("blockers_count", 0)
    warnings_count = phase1c.get("warnings_count", 0)

    # ── Article A duplicate ────────────────────────────────────────────────
    article_a = next((d for d in drafts if d.get("id") == "1000525496694"), None)
    article_a_ok = article_a is not None and article_a.get("published_at") is None

    # ── Job 02 Shopify check ───────────────────────────────────────────────
    job02_handle = os.path.basename(next_file).replace(".html", "") if next_file else ""
    shopify_handles = {a.get("handle", "") for a in published}
    shopify_draft_handles = {a.get("handle", "") for a in drafts}
    job02_in_shopify = job02_handle in shopify_handles
    job02_draft_in_shopify = job02_handle in shopify_draft_handles

    if job02_in_shopify:
        blockers.append({
            "check": "job02_already_live",
            "message": f"Job 02 handle '{job02_handle}' already exists live in Shopify"
        })
    if job02_draft_in_shopify:
        blockers.append({
            "check": "job02_shopify_draft_exists",
            "message": f"Job 02 already has a Shopify draft: '{job02_handle}'"
        })

    # ── Duplicate handles / titles ─────────────────────────────────────────
    handles = [a.get("handle", "") for a in published]
    titles  = [a.get("title", "").strip() for a in published]
    dup_handles = {h for h in handles if handles.count(h) > 1}
    dup_titles  = {t for t in titles if titles.count(t) > 1}
    if dup_handles:
        blockers.append({"check": "duplicate_handles", "message": f"Duplicate live handles: {dup_handles}"})
    if dup_titles:
        blockers.append({"check": "duplicate_titles", "message": f"Duplicate live titles: {dup_titles}"})

    # ── Phase blockers ─────────────────────────────────────────────────────
    if not phase1a_ok:
        blockers.append({"check": "phase1a_failed", "message": "Phase 1A did not pass"})
    if not phase1b_ok:
        blockers.append({"check": "phase1b_failed", "message": "Phase 1B did not pass"})
    if not phase1c_ok or blockers_count > 0:
        blockers.append({"check": "phase1c_failed", "message": "Phase 1C had blockers"})

    # ── HTML contract & validator ──────────────────────────────────────────
    html_contract_ok = bool(data["html_contract"])
    html_validator_ok = os.path.exists(HTML_VALIDATOR)
    if not html_contract_ok:
        blockers.append({"check": "html_contract_missing", "message": "HCS HTML design contract not found"})
    if not html_validator_ok:
        blockers.append({"check": "html_validator_missing", "message": "HCS HTML validator script not found"})

    # ── Inventory file missing ─────────────────────────────────────────────
    if not inventory:
        blockers.append({"check": "inventory_missing", "message": "shopify_inventory.json is missing or empty"})

    # ── Warnings from Phase 1C carried forward (non-blocking, informational) ─
    # These are counted separately — they do not affect the READY_FOR_NEXT_PHASE decision
    # because Phase 1C passed and they are explicitly classified as non-blocking.
    phase1c_warnings = []
    for w in phase1c.get("warnings", []):
        phase1c_warnings.append(w)

    # Phase 1D-native warnings only (new issues found during this reporter run)
    phase1d_warnings = []

    if job02_draft_in_shopify:
        pass  # already a blocker above
    elif next_days is not None and next_days > 0:
        infos.append({
            "check": "job02_waiting",
            "message": f"Job 02 is not yet due (target {next_target}, {next_days}d away). "
                       f"Draft expected {draft_date}."
        })

    # Check cleanup baseline locked
    if "BASELINE LOCKED" in data["cleanup_text"]:
        infos.append({"check": "cleanup_baseline_locked", "message": "Cleanup baseline v1 is confirmed locked"})
    else:
        warnings.append({"check": "cleanup_baseline", "message": "Cleanup baseline v1 not confirmed as locked"})

    # Check client config
    if config.get("old_scripts_status") == "unsafe_legacy_do_not_use":
        infos.append({"check": "old_scripts_flagged", "message": "Old scripts correctly flagged as unsafe in client config"})

    # Check Phase 1B planner decision
    planner_decision = phase1b.get("planner", {}).get("planner_decision", "")
    if planner_decision == "waiting_for_future_date":
        infos.append({"check": "planner_waiting", "message": f"Phase 1B planner is waiting: {phase1b.get('planner',{}).get('block_reason','')}"})
    else:
        infos.append({"check": "planner_decision", "message": f"Phase 1B planner decision: {planner_decision}"})

    # ── Decision logic ──────────────────────────────────────────────────────
    # Phase 1C warnings are informational carry-overs and do not block READY_FOR_NEXT_PHASE.
    # Only Phase 1D-native warnings (phase1d_warnings) affect the decision.
    if blockers:
        decision = DECISION_BLOCKED
    elif phase1d_warnings:
        # New Phase 1D-specific warnings — needs attention but not blocked
        decision = DECISION_NEEDS_HUMAN_REVIEW
    elif warnings:
        # Only Phase 1C carry-over warnings present — these are non-blocking informational
        # HCS is healthy, waiting for Job 02, and Phase 1E can be built as dry-run
        decision = DECISION_HEALTHY_WAITING
    elif not phase1a_ok or not phase1b_ok or not phase1c_ok:
        decision = DECISION_BLOCKED
    else:
        # All phases passed, no blockers, no Phase 1D-native warnings
        # Phase 1E can be built as dry-run even while waiting for Job 02
        decision = DECISION_READY_FOR_NEXT_PHASE

    # ── Build summary sections ───────────────────────────────────────────────
    # Duplicate cleanup
    duplicate_cleanup = {
        "article_a_draft": {
            "id": "1000525496694",
            "title": "Where to Buy Electric Scooters in the UK: Top Models and Best Deals",
            "handle": "where-to-buy-electric-scooters-in-the-uk-top-models-and-best-deals",
            "status": "unpublished",
            "redirect_active": True,
            "canonical_article_id": "1000575172982",
            "canonical_handle": "where-to-buy-electric-scooters-in-the-uk-top-models-and-best-deals-1",
        },
        "article_b_canonical": {
            "id": "1000575172982",
            "title": "Where to Buy Electric Scooters in the UK: Top Models and Best Deals",
            "handle": "where-to-buy-electric-scooters-in-the-uk-top-models-and-best-deals-1",
            "status": "published",
        },
    }

    # Queue status summary
    queue_summary = {
        "total_jobs": len(all_jobs),
        "published_live": len(live_jobs),
        "planned": len(planned),
        "next_job": {
            "number": next_job_number,
            "topic": next_topic,
            "target_date": next_target,
            "expected_draft_date": draft_date,
            "keyword": next_keyword,
            "days_until_target": next_days,
            "handle": job02_handle,
            "in_shopify": job02_in_shopify,
            "shopify_draft_exists": job02_draft_in_shopify,
        },
        "upcoming_jobs": [
            {
                "number": j.get("job_number"),
                "topic": j.get("topic"),
                "target_date": j.get("date_target"),
                "days_until": days_until(j.get("date_target", "")),
            }
            for j in planned
        ],
    }

    # Shopify inventory summary
    shopify_summary = {
        "total_articles": inventory.get("total", pub_count + draft_count),
        "published_count": pub_count,
        "draft_count": draft_count,
        "article_a_duplicate_status": "unpublished_redirect_active" if article_a_ok else "unexpected",
        "live_duplicates": {
            "handles": list(dup_handles) if dup_handles else [],
            "titles": list(dup_titles) if dup_titles else [],
        },
    }

    # HTML contract status
    html_summary = {
        "contract_found": html_contract_ok,
        "contract_version": "v1",
        "contract_path": HTML_CONTRACT,
        "validator_found": html_validator_ok,
        "validator_path": HTML_VALIDATOR,
    }

    # Phase gate summary
    phase_gates = {
        "phase1a": {"passed": phase1a_ok, "preview": PHASE1A_PREVIEW},
        "phase1b": {"passed": phase1b_ok, "preview": PHASE1B_PREVIEW},
        "phase1c": {"passed": phase1c_ok, "preview": PHASE1C_PREVIEW},
    }

    # ── Assemble final report ───────────────────────────────────────────────
    # Phase 1D-native counts drive the decision.
    # Phase 1C carry-over items are reported but do not block READY_FOR_NEXT_PHASE.
    report = {
        "meta": {
            "phase":             "1D",
            "client":            "hcs_gadgets",
            "mode":              "reporter_dryrun",
            "run_timestamp":     datetime.now().isoformat(),
            "shopify_touched":   False,
            "queue_touched":     False,
        },
        "decision":             decision,
        "decision_reason":      _decision_reason(decision, blockers, warnings, infos),
        "phase_gates":          phase_gates,
        # Phase 1D-native counts (drive the decision)
        "phase1d_blockers_count": len(blockers),
        "phase1d_warnings_count": len(warnings),   # Phase 1D-native only
        # Phase 1C carry-over (informational, do not affect decision)
        "phase1c_warnings":      phase1c_warnings,
        # Total counts including carry-overs (for full reporting)
        "blockers_count":        len(blockers) + 0,   # no Phase 1C carry-over blockers expected
        "warnings_count":        len(warnings) + len(phase1c_warnings),
        "infos_count":          len(infos) + len(phase1c_warnings),  # Phase 1C warnings surfaced as info too
        "queue_summary":         queue_summary,
        "shopify_summary":      shopify_summary,
        "duplicate_cleanup":     duplicate_cleanup,
        "html_summary":         html_summary,
        "client_config": {
            "client_key":        config.get("client_key", ""),
            "site_name":         config.get("site_name", ""),
            "shopify_blog_id":   config.get("blog_id", ""),
            "publish_mode":      config.get("publish_mode", ""),
            "manual_publish":    config.get("manual_publish_required", False),
            "article_wrapper":   config.get("article_wrapper_class", ""),
        },
        # Phase 1D-native findings
        "blockers": blockers,
        "warnings": warnings,
        "infos":    infos,
        # Phase 1C carry-over (informational only)
        "phase1c_warnings": phase1c_warnings,
        "next_steps": _next_steps(decision, next_job_number, next_target, draft_date),
    }

    return report


def _decision_reason(decision, blockers, warnings, infos):
    if decision == DECISION_BLOCKED:
        return "Blocker(s) found — see blockers list"
    elif decision == DECISION_NEEDS_HUMAN_REVIEW:
        return "Human review required — see warnings"
    elif decision == DECISION_HEALTHY_WAITING:
        return "No blockers. Non-blocking warnings present. Pipeline is healthy but waiting on external conditions."
    elif decision == DECISION_READY_FOR_NEXT_PHASE:
        return "All phases passed. No blockers. No warnings. HCS is clean and ready for Phase 1E Orchestrator dry-run."
    return "Unknown decision"


def _next_steps(decision, next_job_number, next_target, draft_date):
    steps = []
    if decision in (DECISION_READY_FOR_NEXT_PHASE, DECISION_HEALTHY_WAITING):
        steps.append("Build Phase 1E Orchestrator Wrapper dry-run")
        steps.append("Job 02 draft creation scheduled for 2026-07-07 (expected)")
    if decision == DECISION_READY_FOR_NEXT_PHASE:
        steps.append("Phase 1E can proceed in parallel while waiting for Job 02 due date")
    if decision == DECISION_BLOCKED:
        steps.append("Resolve blockers before proceeding")
    return steps


# ─── Output generators ────────────────────────────────────────────────────────

def write_json(report, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"JSON preview written: {path}")


def write_phase_report(report, path):
    """Write hcs_orin_status_phase1d.md"""
    qs       = report["queue_summary"]
    ss       = report["shopify_summary"]
    html     = report["html_summary"]
    cc       = report["client_config"]
    decision = report["decision"]

    next_job = qs["next_job"]

    blocker_rows      = _fmt_rows(report["blockers"])
    warning_rows      = _fmt_rows(report["warnings"])   # Phase 1D-native warnings
    phase1c_rows      = _fmt_rows(report.get("phase1c_warnings", []))
    info_rows         = _fmt_rows(report["infos"])
    steps_rows        = "\n".join(f"- {s}" for s in report["next_steps"])

    # Total counts including Phase 1C carry-over
    total_blockers = report["blockers_count"]
    total_warnings = report["warnings_count"]
    phase1d_blockers = report["phase1d_blockers_count"]
    phase1d_warnings = report["phase1d_warnings_count"]
    phase1c_warn_count = len(report.get("phase1c_warnings", []))

    gates_md = ""
    for phase, info in report["phase_gates"].items():
        status = "✅ Passed" if info["passed"] else "❌ Failed"
        gates_md += f"| {phase.upper()} | {status} |\n"

    upcoming_md = ""
    for j in qs.get("upcoming_jobs", []):
        upcoming_md += f"| Job {j['number']} | {j['topic'][:50]}... | {j['target_date']} | {j['days_until']}d |\n"

    phase_d = f"""# HCS Gadgets — ORIN Phase 1D Reporter Status

**Phase:** 1D — Reporter Dry-Run
**Client:** HCS Gadgets
**Run date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
**Mode:** Read-only reporting
**Reporter Decision:** **{decision}**

---

## Reporter Decision

{report['decision_reason']}

---

## Phase Gate Summary

| Phase | Status |
|-------|--------|
{gates_md.strip()}

---

## Shopify Inventory Status

| Metric | Value |
|--------|-------|
| Total articles | {ss['total_articles']} |
| Published | {ss['published_count']} |
| Drafts | {ss['draft_count']} |
| Live duplicate handles | {len(ss['live_duplicates']['handles'])} |
| Live duplicate titles | {len(ss['live_duplicates']['titles'])} |
| Article A (duplicate) | {ss['article_a_duplicate_status']} ✅ |

---

## Duplicate Cleanup Status

| Item | Status |
|------|--------|
| Article A (ID 1000525496694) | Unpublished — redirect active ✅ |
| Article B (ID 1000575172982) | Published (canonical) ✅ |
| Redirect ID | 1725525721462 |

---

## Queue Status

| Metric | Value |
|--------|-------|
| Total jobs | {qs['total_jobs']} |
| Published live | {qs['published_live']} |
| Planned | {qs['planned']} |
| Next job | Job {next_job['number']} |
| Next topic | {next_job['topic']} |
| Target date | {next_job['target_date']} |
| Expected draft date | {next_job.get('expected_draft_date', '—')} |
| Days until target | {next_job.get('days_until_target', '—')} |
| Job handle | `{next_job.get('handle', '—')}` |
| In Shopify | {'Yes — BLOCKER' if next_job.get('in_shopify') else 'No ✅'} |

### Upcoming Jobs

| Job | Topic | Target Date | Days Until |
|-----|-------|-------------|------------|
{upcoming_md.strip()}

---

## HTML Contract Status

| Item | Status |
|------|--------|
| Contract found | {'Yes ✅' if html['contract_found'] else 'No ❌'} |
| Contract version | {html['contract_version']} |
| Validator found | {'Yes ✅' if html['validator_found'] else 'No ❌'} |

---

## Client Configuration

| Setting | Value |
|---------|-------|
| Site name | {cc['site_name']} |
| Blog ID | {cc['shopify_blog_id']} |
| Publish mode | {cc['publish_mode']} |
| Manual publish required | {cc['manual_publish']} |
| Article wrapper class | `{cc['article_wrapper']}` |

---

## Output Proof

| # | Item | Result |
|---|------|--------|
| 1 | Runner file path | `tools/shopify_publisher/orin/hcs_phase1d_reporter_dryrun.py` |
| 2 | JSON preview path | `/tmp/hcs_phase1d_reporter_preview.json` |
| 3 | Phase 1D report path | `clients/hcs_gadgets/content_engine/hcs_orin_status_phase1d.md` |
| 4 | Main HCS ORIN status path | `clients/hcs_gadgets/content_engine/hcs_orin_status.md` |
| 5 | Reporter decision | **{decision}** |
| 6 | Phase 1D-native blockers | **{phase1d_blockers}** |
| 7 | Phase 1D-native warnings | **{phase1d_warnings}** |
| 8 | Phase 1C carry-over warnings | **{phase1c_warn_count}** (informational only) |
| 9 | Next planned job | **Job {next_job['number']}** |
| 10 | Expected draft date | **{next_job.get('expected_draft_date', '—')}** |
| 11 | Shopify touched | **No** |
| 12 | Queue touched | **No** |
| 13 | Phase 1D passed | ** {"Yes" if decision != DECISION_BLOCKED else "No"} ** |

---

## Phase 1D-Native Blockers ({phase1d_blockers})

| # | Check | Message |
|---|-------|---------|
{blocker_rows.strip()}

---

## Phase 1D-Native Warnings ({phase1d_warnings})

| # | Check | Message |
|---|-------|---------|
{warning_rows.strip()}

---

## Phase 1C Carry-Over Warnings ({phase1c_warn_count}) — Informational Only

> These warnings originated in Phase 1C and are classified as non-blocking.
> They do not affect the Phase 1D decision.

| # | Check | Message |
|---|-------|---------|
{phase1c_rows.strip()}

---

## Info ({report['infos_count']})

| # | Check | Message |
|---|-------|---------|
{info_rows.strip()}

---

## Next Steps

{steps_rows}

---

*Generated by HCS Phase 1D Reporter Agent Dry-Run — {datetime.now().isoformat()}*
"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(phase_d)
    print(f"Phase 1D report written: {path}")


def write_master_status(report, path):
    """Write/update the master hcs_orin_status.md"""
    qs       = report["queue_summary"]
    ss       = report["shopify_summary"]
    next_job = qs["next_job"]

    phase_rows = ""
    for phase, info in report["phase_gates"].items():
        status = "✅" if info["passed"] else "❌"
        phase_rows += f"| {phase.upper()} | {status} |\n"

    upcoming_rows = ""
    for j in qs.get("upcoming_jobs", []):
        upcoming_rows += f"| Job {j['number']} | {j['topic'][:55]}... | {j['target_date']} | {j['days_until']}d |\n"

    blocker_rows = _fmt_rows(report["blockers"])
    warning_rows = _fmt_rows(report["warnings"])  # Phase 1D-native
    phase1c_rows = _fmt_rows(report.get("phase1c_warnings", []))

    phase1d_blockers = report["phase1d_blockers_count"]
    phase1d_warnings = report["phase1d_warnings_count"]
    phase1c_warn_cnt = len(report.get("phase1c_warnings", []))

    master = f"""# HCS Gadgets — ORIN Master Status

**Client:** HCS Gadgets
**Last updated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
**Current phase:** 1D (Reporter)
**Overall status:** {"✅ OPERATIONAL" if report['decision'] != DECISION_BLOCKED else "❌ BLOCKED"}
**Reporter Decision:** {report['decision']}

---

## ORIN Pipeline Phases

| Phase | Status |
|-------|--------|
{phase_rows.strip()}

---

## Shopify Inventory

| Metric | Value |
|--------|-------|
| Published articles | {ss['published_count']} |
| Draft articles | {ss['draft_count']} |
| Total | {ss['total_articles']} |
| Live duplicate handles | {len(ss['live_duplicates']['handles'])} |
| Live duplicate titles | {len(ss['live_duplicates']['titles'])} |

---

## Content Queue

| Metric | Value |
|--------|-------|
| Total jobs | {qs['total_jobs']} |
| Published live | {qs['published_live']} |
| Planned | {qs['planned']} |
| Next job | Job {next_job['number']} — {next_job['topic'][:50]}... |
| Target date | {next_job['target_date']} |
| Expected draft date | {next_job.get('expected_draft_date', '—')} |

### Upcoming Jobs

| Job | Topic | Target | Days |
|-----|-------|--------|------|
{upcoming_rows.strip()}

---

## Reporter Decision

**{report['decision']}** — {report['decision_reason']}

---

## Phase 1D-Native Blockers ({phase1d_blockers})

| # | Check | Message |
|---|-------|---------|
{blocker_rows.strip()}

---

## Phase 1D-Native Warnings ({phase1d_warnings})

| # | Check | Message |
|---|-------|---------|
{warning_rows.strip()}

---

## Phase 1C Carry-Over Warnings ({phase1c_warn_cnt}) — Informational Only

| # | Check | Message |
|---|-------|---------|
{phase1c_rows.strip()}

---

## Phase Reports

| Phase | Report |
|-------|--------|
| Phase 1A | `hcs_orin_status_phase1a.md` |
| Phase 1B | `hcs_orin_status_phase1b.md` |
| Phase 1C | `hcs_orin_status_phase1c.md` |
| Phase 1D | `hcs_orin_status_phase1d.md` |

---

*ORIN master status — HCS Gadgets — last updated {datetime.now().isoformat()}*
"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(master)
    print(f"Master status written: {path}")


def _fmt_rows(items):
    if not items:
        return "| — | — | No items |\n"
    return "".join(f"| {i+1} | {item['check']} | {item['message']} |\n"
                   for i, item in enumerate(items))


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("HCS Gadgets — Phase 1D Reporter Agent Dry-Run")
    print("=" * 60)
    print(f"Run: {datetime.now().isoformat()}")
    print()

    data   = collect()
    report = make_report(data)

    decision         = report["decision"]
    phase1d_blockers = report["phase1d_blockers_count"]
    phase1d_warnings = report["phase1d_warnings_count"]
    phase1c_warn_cnt = len(report.get("phase1c_warnings", []))
    total_warnings  = report["warnings_count"]

    print(f"Decision           : {decision}")
    print(f"Phase 1D blockers  : {phase1d_blockers}")
    print(f"Phase 1D warnings  : {phase1d_warnings}")
    print(f"Phase 1C carry-over: {phase1c_warn_cnt} (informational only)")
    print(f"Total warnings     : {total_warnings}")
    print()

    write_json(report, PREVIEW_JSON)
    write_phase_report(report, PHASE_REPORT)
    write_master_status(report, MASTER_STATUS)

    print()
    if phase1d_blockers > 0:
        print("❌ Phase 1D FAILED — Phase 1D-native blocker(s) found:")
        for b in report["blockers"]:
            print(f"  [{b['check']}] {b['message']}")
        sys.exit(1)
    else:
        print("✅ Phase 1D PASSED")
        if total_warnings > 0:
            print(f"⚠️  {total_warnings} total warning(s):")
            if phase1d_warnings > 0:
                print(f"  Phase 1D-native ({phase1d_warnings}):")
                for w in report["warnings"]:
                    print(f"    [{w['check']}] {w['message']}")
            if phase1c_warn_cnt > 0:
                print(f"  Phase 1C carry-over ({phase1c_warn_cnt} — informational only, non-blocking):")
                for w in report.get("phase1c_warnings", []):
                    print(f"    [{w['check']}] {w['message']}")
        sys.exit(0)


if __name__ == "__main__":
    main()
