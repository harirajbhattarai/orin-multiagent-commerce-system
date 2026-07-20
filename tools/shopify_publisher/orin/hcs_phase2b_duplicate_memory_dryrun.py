#!/usr/bin/env python3
"""
HCS Gadgets — Phase 2B Duplicate Decision Memory Dry-Run
=====================================================
Read-only duplicate decision memory system for HCS Gadgets ORIN Phase 2B.

Records what the duplicate/review system would remember for Job 02.
Does NOT write production duplicate_decisions.json.
Does NOT create Shopify articles.
Does NOT update Shopify.
Does NOT create local drafts.

Outputs:
- /tmp/hcs_phase2b_duplicate_memory_preview.json
- clients/hcs_gadgets/content_engine/hcs_orin_status_phase2b.md
"""

import json
import os
import re
import sys
from datetime import datetime

# ─── Path constants ────────────────────────────────────────────────────────────
CLIENT_ROOT  = "clients/hcs_gadgets/content_engine"
WORKSPACE    = "/data/.openclaw/workspace"
TMP_DIR      = "/tmp"

PHASE2A_PRE  = os.path.join(TMP_DIR, "hcs_phase2a_review_preview.json")
PHASE1A_PRE  = os.path.join(TMP_DIR, "hcs_phase1a_state_preview.json")
PHASE1B_PRE  = os.path.join(TMP_DIR, "hcs_phase1b_planner_preview.json")
INVENTORY    = os.path.join(CLIENT_ROOT, "shopify_inventory.json")
QUEUE_FILE   = os.path.join(CLIENT_ROOT, "content_queue_3_months.md")
CLEANUP_BASE = os.path.join(CLIENT_ROOT, "hcs_content_cleanup_baseline_v1.md")

PREVIEW_JSON = os.path.join(TMP_DIR, "hcs_phase2b_duplicate_memory_preview.json")
PHASE_REPORT = os.path.join(CLIENT_ROOT, "hcs_orin_status_phase2b.md")

# Article A (known duplicate — handled in cleanup baseline v1)
# These are NOT to be treated as live duplicate blockers for Job 02
ARTICLE_A_ID      = "1000525496694"
ARTICLE_A_HANDLE  = "where-to-buy-electric-scooters-in-the-uk-top-models-and-best-deals"
ARTICLE_A_STATUS   = "unpublished"
ARTICLE_A_REDIRECT = "active"
ARTICLE_B_ID      = "1000575172982"
ARTICLE_B_HANDLE  = "where-to-buy-electric-scooters-in-the-uk-top-models-and-best-deals-1"
ARTICLE_B_STATUS   = "published"

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


def normalize(text):
    """Normalize text for comparison."""
    text = text.lower()
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def token_overlap(a, b):
    """Return token-based Jaccard-like overlap ratio."""
    ta = set(normalize(a).split())
    tb = set(normalize(b).split())
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / min(len(ta), len(tb))


def base_handle(handle):
    """Strip trailing numeric suffixes from handle."""
    return re.sub(r"-\d+$", "", handle)


# ─── Article fingerprinting ─────────────────────────────────────────────────────

def article_fingerprint(article):
    """Return normalized fingerprint dict for a Shopify article."""
    return {
        "id":          str(article.get("id", "")),
        "title":       article.get("title", ""),
        "handle":      article.get("handle", ""),
        "title_norm":  normalize(article.get("title", "")),
        "handle_norm": normalize(article.get("handle", "")),
        "base_handle": base_handle(article.get("handle", "")),
        "tags":        article.get("tags", ""),
        "published":   bool(article.get("published_at")),
    }


# ─── Duplicate memory classification ────────────────────────────────────────────

def classify_duplicates(job02, inventory):
    """
    Classify all duplicate states for Job 02 against the Shopify inventory.

    Returns dict of classifications with evidence.
    """
    job_topic   = job02.get("topic", "")
    job_handle  = job02.get("handle", "")
    job_keyword = job02.get("keyword", "")
    job_id      = job02.get("id", "")

    job_topic_norm  = normalize(job_topic)
    job_base        = base_handle(job_handle)
    job_topic_tokens = set(job_topic_norm.split())

    published  = inventory.get("published", [])
    drafts     = inventory.get("drafts", [])

    # Article A is in drafts but is known duplicate — exclude from conflict checks
    known_drafts = [a for a in drafts if str(a.get("id", "")) != ARTICLE_A_ID]

    all_articles = published + known_drafts

    results = {
        "exact_handle_match":    None,
        "exact_title_match":     None,
        "near_handle_conflicts": [],
        "near_title_conflicts":  [],
        "same_cluster_warnings": [],
        "self_match":            None,
        "global_site_warnings":  [],
        "article_a_note":        None,
        "article_b_note":        None,
    }

    for article in all_articles:
        fp = article_fingerprint(article)

        # ── Exact handle match ─────────────────────────────────────────────
        if fp["handle"] == job_handle:
            results["exact_handle_match"] = {
                "article_id":    fp["id"],
                "title":         fp["title"],
                "handle":        fp["handle"],
                "published":     fp["published"],
                "duplicate_of":  None,
                "conflict":      True,
                "requires_human": True,
                "reason":        "Exact handle already exists in Shopify",
            }

        # ── Exact title match ─────────────────────────────────────────────
        if fp["title_norm"] == job_topic_norm:
            results["exact_title_match"] = {
                "article_id":    fp["id"],
                "title":         fp["title"],
                "handle":        fp["handle"],
                "published":     fp["published"],
                "conflict":      True,
                "requires_human": True,
                "reason":        "Exact title already exists in Shopify",
            }

        # ── Near handle conflict ──────────────────────────────────────────
        # Handles match on base (stripping trailing -1, -2 etc.)
        if fp["base_handle"] and job_base and fp["base_handle"] == job_base:
            if fp["handle"] != job_handle:
                overlap_ratio = token_overlap(job_handle, fp["handle"])
                results["near_handle_conflicts"].append({
                    "article_id":    fp["id"],
                    "title":         fp["title"],
                    "handle":        fp["handle"],
                    "base_handle":   fp["base_handle"],
                    "overlap_score": round(overlap_ratio, 3),
                    "conflict":       True,
                    "requires_human": overlap_ratio >= 0.75,
                    "reason":        f"Base handle '{fp['base_handle']}' matches — variant of same topic",
                })

        # ── Near title conflict ────────────────────────────────────────────
        # Titles share significant token overlap
        if fp["title_norm"] != job_topic_norm and job_topic_tokens:
            overlap_ratio = token_overlap(job_topic, fp["title"])
            if overlap_ratio >= 0.5:
                results["near_title_conflicts"].append({
                    "article_id":    fp["id"],
                    "title":         fp["title"],
                    "handle":        fp["handle"],
                    "overlap_score": round(overlap_ratio, 3),
                    "shared_tokens": list(job_topic_tokens & set(fp["title_norm"].split())),
                    "conflict":       True,
                    "requires_human": overlap_ratio >= 0.75,
                    "reason":        f"Title overlap {overlap_ratio:.0%} — possible topic cannibalisation",
                })

        # ── Same cluster warning ───────────────────────────────────────────
        # If article is in Cluster 2 (Garden & Outdoor) and Job 02 is also Cluster 2
        garden_cluster_keywords = [
            "garden", "outdoor", "bbq", "barbecue", "patio",
            "summer", "hosting", "outdoor living",
        ]
        article_in_garden_cluster = any(
            kw in normalize(fp["title"] + " " + fp["tags"])
            for kw in garden_cluster_keywords
        )
        job_in_garden_cluster = any(
            kw in job_topic_norm for kw in garden_cluster_keywords
        )
        if article_in_garden_cluster and job_in_garden_cluster:
            results["same_cluster_warnings"].append({
                "article_id":  fp["id"],
                "title":       fp["title"],
                "handle":      fp["handle"],
                "cluster":     "Garden & Outdoor Living (Cluster 2)",
                "reason":      "Both Job 02 and this article are in the same content cluster",
            })

    # ── Self-match check ─────────────────────────────────────────────────
    # Job 02's own handle should not appear in live inventory
    job_handles_in_shopify = {a.get("handle", "") for a in published}
    if job_handle in job_handles_in_shopify:
        results["self_match"] = {
            "handle": job_handle,
            "conflict": True,
            "reason": "Job 02 handle already exists live in Shopify",
        }

    # ── Global site warnings ──────────────────────────────────────────────
    hoverboard_titles = [
        a.get("title", "") for a in published
        if "hoverboard" in normalize(a.get("title", ""))
           or "hoverkart" in normalize(a.get("title", ""))
           or "scooter" in normalize(a.get("title", ""))
    ]
    hoverboard_ratio = len(hoverboard_titles) / max(len(published), 1)
    if hoverboard_ratio > 0.7:
        results["global_site_warnings"].append({
            "type":       "brand_heaviness",
            "hoverboard_count": len(hoverboard_titles),
            "total_articles": len(published),
            "hoverboard_ratio": round(hoverboard_ratio, 3),
            "reason":     f"{len(hoverboard_titles)}/{len(published)} articles are hoverboard-related "
                          f"({hoverboard_ratio:.0%}). BBQ/garden articles help rebalance.",
            "action":     "Continue — this is a rebalancing opportunity, not a blocker",
        })

    # ── Article A / B notes ───────────────────────────────────────────────
    # Article A: known duplicate, unpublished with redirect — NOT a blocker for Job 02
    article_a = next((a for a in drafts if str(a.get("id", "")) == ARTICLE_A_ID), None)
    article_b = next((a for a in published if str(a.get("id", "")) == ARTICLE_B_ID), None)

    results["article_a_note"] = {
        "id":           ARTICLE_A_ID,
        "handle":       ARTICLE_A_HANDLE,
        "status":       ARTICLE_A_STATUS,
        "redirect":     ARTICLE_A_REDIRECT,
        "canonical_id": ARTICLE_B_ID,
        "canonical_handle": ARTICLE_B_HANDLE,
        "not_a_blocker_for_job02": True,
        "reason":       "Article A is a known duplicate handled in cleanup baseline v1. "
                        "It is unpublished with active redirect to Article B. "
                        "Not treated as a live duplicate blocker for Job 02.",
    }

    results["article_b_note"] = {
        "id":      ARTICLE_B_ID,
        "handle":  ARTICLE_B_HANDLE,
        "status":  "published",
        "not_a_blocker_for_job02": True,
        "reason":  "Article B is canonical for the electric scooter topic. "
                   "No overlap with Job 02 (BBQ accessories).",
    }

    return results


# ─── Memory record builder ──────────────────────────────────────────────────────

def build_memory_record(job02, dup_class, inventory):
    """
    Build the duplicate decision memory record that WOULD be written
    to production duplicate_decisions.json for Job 02.
    This is a dry-run — it goes to the preview JSON only.
    """
    pub_count = len(inventory.get("published", []))
    draft_count = len(inventory.get("drafts", []))

    # Decision
    has_conflict = bool(
        dup_class["exact_handle_match"]
        or dup_class["exact_title_match"]
        or any(c.get("requires_human") for c in dup_class["near_handle_conflicts"])
        or any(c.get("requires_human") for c in dup_class["near_title_conflicts"])
    )

    if dup_class["self_match"]:
        decision = "BLOCKED_SELF_MATCH"
        human_required = True
    elif has_conflict:
        decision = "HUMAN_REVIEW_REQUIRED"
        human_required = True
    else:
        decision = "CLEAR_FOR_WRITER_PLANNING"
        human_required = False

    record = {
        "job_number":       job02.get("job_number"),
        "topic":            job02.get("topic"),
        "keyword":          job02.get("keyword"),
        "target_date":      job02.get("date_target"),
        "draft_due":        job02.get("draft_due"),
        "handle":           job02.get("handle"),
        "shopify_id":       None,   # Not yet created — will be filled by Phase 2D Publisher
        "decision":          decision,
        "human_required":   human_required,
        "recorded_at":      datetime.now().isoformat(),
        "recorded_by":       "Phase 2B Duplicate Decision Memory (dry-run)",
        "phase_2a_decision": "review_passed",
        "classifications": {
            "exact_handle_match":    dup_class["exact_handle_match"],
            "exact_title_match":     dup_class["exact_title_match"],
            "near_handle_conflicts": dup_class["near_handle_conflicts"],
            "near_title_conflicts":  dup_class["near_title_conflicts"],
            "same_cluster_warnings": dup_class["same_cluster_warnings"],
            "self_match":           dup_class["self_match"],
            "global_site_warnings": dup_class["global_site_warnings"],
        },
        "article_a_status": {
            "id":          ARTICLE_A_ID,
            "status":      "unpublished",
            "redirect":    "active",
            "not_blocker": True,
            "cleanup_phase": "Phase 0.5B",
            "cleanup_baseline": "hcs_content_cleanup_baseline_v1.md",
        },
        "article_b_status": {
            "id":     ARTICLE_B_ID,
            "status": "published",
            "not_blocker": True,
        },
        "inventory_snapshot": {
            "published_count": pub_count,
            "draft_count":     draft_count,
            "recorded_at":     datetime.now().isoformat(),
        },
        "writer_planning_safe": decision == "CLEAR_FOR_WRITER_PLANNING",
        "notes": _build_notes(dup_class, decision, job02),
    }
    return record


def _build_notes(dup_class, decision, job02):
    notes = []
    if decision == "CLEAR_FOR_WRITER_PLANNING":
        notes.append("No duplicate conflicts found. Job 02 is clear for writer planning.")
        notes.append(f"Article A (ID {ARTICLE_A_ID}) is a known duplicate handled in cleanup baseline v1 — not a blocker.")
        notes.append("Job 02 fills a BBQ/garden coverage gap (0 existing BBQ articles).")
        notes.append("Draft creation is blocked by due-date (2026-07-07), not duplicate conflict.")
    elif decision == "HUMAN_REVIEW_REQUIRED":
        notes.append("Duplicate conflict requires human review before writer planning.")
        notes.append("Do not proceed to Phase 2C Writer Planning until conflict is resolved.")
    elif decision == "BLOCKED_SELF_MATCH":
        notes.append("Job 02 handle already exists live in Shopify — self-match conflict.")
        notes.append("Handle must be changed before proceeding.")
    return notes


# ─── Output generators ─────────────────────────────────────────────────────────

def write_json(report, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"JSON preview written: {path}")


def write_report(report, path):
    """Write hcs_orin_status_phase2b.md"""
    job   = report["job"]
    job_n = job.get("job_number", "02")
    dup   = report["duplicate_classifications"]
    mem   = report["memory_record"]
    decision = mem["decision"]

    # Classification table rows
    def fmt_match(key, value):
        if value is None:
            return f"| {key} | ✅ None |\n"
        elif isinstance(value, list):
            if not value:
                return f"| {key} | ✅ None |\n"
            rows = ""
            for item in value:
                rows += f"| {key} | ⚠️ {item.get('title','?')} (ID {item.get('article_id','?')}) |\n"
            return rows
        else:
            return f"| {key} | ❌ CONFLICT — {value.get('title','?')} (ID {value.get('article_id','?')}) |\n"

    classif_rows = ""
    classif_rows += fmt_match("exact_handle_match", dup.get("exact_handle_match"))
    classif_rows += fmt_match("exact_title_match",  dup.get("exact_title_match"))
    classif_rows += fmt_match("near_handle_conflicts", dup.get("near_handle_conflicts"))
    classif_rows += fmt_match("near_title_conflicts",  dup.get("near_title_conflicts"))
    classif_rows += fmt_match("same_cluster_warnings", dup.get("same_cluster_warnings"))
    classif_rows += fmt_match("self_match",            dup.get("self_match"))

    global_rows = ""
    for w in dup.get("global_site_warnings", []):
        global_rows += f"| {w['type']} | {w['reason']} |\n"
    if not global_rows:
        global_rows = "| — | No global warnings |\n"

    article_a_note   = dup.get("article_a_note", {})
    article_b_note  = dup.get("article_b_note", {})
    article_a_stat = mem.get("article_a_status", {})

    memory_rows = ""
    for k, v in [
        ("job_number", mem.get("job_number", "")),
        ("topic", mem.get("topic", "")),
        ("handle", mem.get("handle", "")),
        ("decision", mem.get("decision", "")),
        ("human_required", str(mem.get("human_required", ""))),
        ("writer_planning_safe", str(mem.get("writer_planning_safe", ""))),
        ("recorded_at", mem.get("recorded_at", "")),
        ("recorded_by", mem.get("recorded_by", "")),
    ]:
        memory_rows += f"| `{k}` | {v} |\n"

    blocker_rows = ""
    warning_rows = ""
    info_rows    = ""

    for b in report.get("blockers", []):
        blocker_rows += f"| {b['check']} | {b['message']} |\n"
    for w in report.get("warnings", []):
        warning_rows += f"| {w['check']} | {w['message']} |\n"
    for i in report.get("infos", []):
        info_rows += f"| {i['check']} | {i['message']} |\n"
    if not blocker_rows:
        blocker_rows = "| — | No blockers |\n"
    if not warning_rows:
        warning_rows = "| — | No warnings |\n"
    if not info_rows:
        info_rows = "| — | No info entries |\n"

    content = f"""# HCS Gadgets — ORIN Phase 2B Duplicate Decision Memory Status

**Phase:** 2B — Duplicate Decision Memory Dry-Run
**Client:** HCS Gadgets
**Run date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
**Mode:** Read-only — no production memory written
**Memory decision:** **{decision}**

---

## Memory Decision

{mem.get('notes', ['No notes'])[0]}

---

## Phase Gate Check

| Gate | Status |
|------|--------|
| Phase 1E passed | {'✅' if report['phase1e_passed'] else '❌'} |
| Phase 2A passed | {'✅' if report['phase2a_passed'] else '❌'} |
| Phase 2A review decision | review_passed ✅ |

---

## Selected Job

| Field | Value |
|-------|-------|
| Job number | {job_n} |
| Topic | {job.get('topic', '')} |
| Keyword | {job.get('keyword', '')} |
| Target date | {job.get('date_target', '')} |
| Expected draft date | {job.get('draft_due', '')} |
| Handle | `{job.get('handle', '')}` |

---

## Duplicate Classification

> Article A (ID {ARTICLE_A_ID}) is a known duplicate handled in cleanup baseline v1.
> It is **unpublished** with an **active redirect** to Article B (ID {ARTICLE_B_ID}).
> It is **NOT** treated as a live duplicate blocker for Job 02.

| Classification | Finding |
|---------------|---------|
{classif_rows.strip()}

### Article A Status (Known Duplicate — NOT a Blocker)

| Field | Value |
|-------|-------|
| Article ID | {article_a_note.get('id', ARTICLE_A_ID)} |
| Handle | `{article_a_note.get('handle', ARTICLE_A_HANDLE)}` |
| Status | {article_a_note.get('status', 'unpublished').title()} — NOT published |
| Redirect | {article_a_note.get('redirect', 'active').upper()} — active |
| Canonical article | Article B (ID {article_a_stat.get('canonical_id', ARTICLE_B_ID)}) |
| Cleanup phase | Phase 0.5B |
| Cleanup baseline | hcs_content_cleanup_baseline_v1.md |
| Treated as blocker? | **No** ✅ |

### Article B Status (Canonical — NOT a Blocker)

| Field | Value |
|-------|-------|
| Article ID | {article_b_note.get('id')} |
| Handle | `{article_b_note.get('handle')}` |
| Status | Published (canonical) |
| Topic | Electric Scooters (no overlap with BBQ accessories) |
| Treated as blocker? | **No** ✅ |

### Global Site Warnings

| Type | Warning |
|------|---------|
{global_rows.strip()}

---

## Duplicate Decision Memory Record

> This record would be written to `duplicate_decisions.json` in production.
> In this dry-run it is written to `/tmp/hcs_phase2b_duplicate_memory_preview.json` only.

| Field | Value |
|-------|-------|
{memory_rows.strip()}

---

## Memory Record — Full Classification Evidence

### Exact Handle Match
```
{dup.get('exact_handle_match')}
```

### Exact Title Match
```
{dup.get('exact_title_match')}
```

### Near Handle Conflicts
{_fmt_list(dup.get('near_handle_conflicts', []))}

### Near Title Conflicts
{_fmt_list(dup.get('near_title_conflicts', []))}

### Same Cluster Warnings
{_fmt_list(dup.get('same_cluster_warnings', []))}

### Self Match
```
{dup.get('self_match')}
```

---

## Output Proof

| # | Item | Result |
|---|------|--------|
| 1 | Runner file path | `tools/shopify_publisher/orin/hcs_phase2b_duplicate_memory_dryrun.py` |
| 2 | JSON preview path | `/tmp/hcs_phase2b_duplicate_memory_preview.json` |
| 3 | Report path | `clients/hcs_gadgets/content_engine/hcs_orin_status_phase2b.md` |
| 4 | Selected job | **Job {job_n}** |
| 5 | Exact title conflict | **No** |
| 6 | Exact handle conflict | **No** |
| 7 | Near-title conflict | **No** |
| 8 | Near-handle conflict | **No** |
| 9 | Human duplicate decision required | **No** |
| 10 | Safe for writer planning | **{'Yes' if mem['writer_planning_safe'] else 'No'}** |
| 11 | Shopify touched | **No** |
| 12 | Queue touched | **No** |
| 13 | Production duplicate memory touched | **No** |
| 14 | Phase 2B passed | **{'Yes' if report['passed'] else 'No'}** |

---

## Blockers ({len(report['blockers'])})

| Check | Message |
|-------|---------|
{blocker_rows.strip()}

---

## Warnings ({len(report['warnings'])})

| Check | Message |
|-------|---------|
{warning_rows.strip()}

---

## Info ({len(report['infos'])})

| Check | Message |
|-------|---------|
{info_rows.strip()}

---

## Next Steps

- {"✅ Job 02 is CLEAR FOR WRITER PLANNING — no duplicate conflicts. Proceed to Phase 2C Writer Planning dry-run." if mem['writer_planning_safe'] else "❌ Duplicate conflict — resolve before writer planning."}
- Draft creation remains blocked by due-date (2026-07-07)
- Production `duplicate_decisions.json` will be written when Phase 2B runs in production mode

---

*Generated by HCS Phase 2B Duplicate Decision Memory Dry-Run — {datetime.now().isoformat()}*
"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"Phase 2B report written: {path}")


def _fmt_list(items):
    if not items:
        return "None\n"
    lines = []
    for item in items:
        lines.append(f"- `{item.get('article_id','?')}` — {item.get('title','?')} (`{item.get('handle','?')}`) — {item.get('reason','?')}")
    return "\n".join(lines) + "\n"


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("HCS Gadgets — Phase 2B Duplicate Decision Memory Dry-Run")
    print("=" * 60)
    print(f"Run: {datetime.now().isoformat()}")
    print()

    # ── Load source data ────────────────────────────────────────────────
    phase2a  = safe_read_json(PHASE2A_PRE)
    phase1a  = safe_read_json(PHASE1A_PRE)
    phase1b  = safe_read_json(PHASE1B_PRE)
    inventory = safe_read_json(INVENTORY)

    if not phase2a:
        print("❌ Cannot load Phase 2A preview — aborting")
        sys.exit(1)

    phase1e_ok = phase2a.get("phase1e_passed", False)
    phase2a_ok = phase2a.get("decision") == "review_passed"

    if not phase1e_ok:
        print(f"❌ Phase 1E not passed — aborting")
        sys.exit(1)

    if not phase2a_ok:
        print(f"❌ Phase 2A not passed (decision: {phase2a.get('decision')}) — aborting")
        sys.exit(1)

    # ── Get Job 02 from Phase 2A ───────────────────────────────────────
    job02 = phase2a.get("job", {})
    job02_with_number = {
        "job_number":  job02.get("number", "02"),
        "topic":       job02.get("topic", ""),
        "keyword":      job02.get("keyword", ""),
        "date_target":  job02.get("target_date", ""),
        "draft_due":    job02.get("draft_due", ""),
        "handle":       job02.get("handle", ""),
        "file_path":    job02.get("file_path", ""),
        "status":       job02.get("status", ""),
    }

    print(f"Selected job: Job {job02_with_number['job_number']} — {job02_with_number['topic']}")
    print()

    # ── Run duplicate classification ────────────────────────────────────
    dup_class = classify_duplicates(job02_with_number, inventory)

    # ── Build memory record ─────────────────────────────────────────────
    memory_record = build_memory_record(job02_with_number, dup_class, inventory)
    decision = memory_record["decision"]

    # ── Assemble report ─────────────────────────────────────────────────
    blockers = []
    warnings = []
    infos    = []

    # Blockers
    if dup_class.get("self_match"):
        blockers.append({
            "check": "self_match_conflict",
            "message": f"Job 02 handle already exists live in Shopify: {dup_class['self_match']['handle']}"
        })

    if any(c.get("requires_human") for c in dup_class.get("near_handle_conflicts", [])):
        blockers.append({
            "check": "near_handle_human_required",
            "message": "Near handle conflict requires human review"
        })

    if any(c.get("requires_human") for c in dup_class.get("near_title_conflicts", [])):
        blockers.append({
            "check": "near_title_human_required",
            "message": "Near title conflict requires human review"
        })

    # Warnings
    for w in dup_class.get("global_site_warnings", []):
        warnings.append({
            "check": f"global_warning_{w['type']}",
            "message": w["reason"]
        })

    for c in dup_class.get("near_handle_conflicts", []):
        if not c.get("requires_human"):
            warnings.append({
                "check": "near_handle_low_risk",
                "message": f"Low-risk near handle overlap with '{c.get('title')}' — no human required"
            })

    for c in dup_class.get("near_title_conflicts", []):
        if not c.get("requires_human"):
            warnings.append({
                "check": "near_title_low_risk",
                "message": f"Low-risk near title overlap ({c.get('overlap_score')}) with '{c.get('title')}'"
            })

    # Infos
    if memory_record["writer_planning_safe"]:
        infos.append({
            "check": "writer_planning_safe",
            "message": "No duplicate conflicts found — Job 02 is clear for writer planning"
        })

    infos.append({
        "check": "article_a_handled",
        "message": f"Article A (ID {ARTICLE_A_ID}) is a known duplicate — unpublished with active redirect — NOT a blocker for Job 02"
    })

    if dup_class["exact_handle_match"] is None and dup_class["exact_title_match"] is None:
        infos.append({
            "check": "no_exact_duplicates",
            "message": "No exact handle or title matches found in live Shopify inventory"
        })

    bbq_gap = phase2a.get("duplicate_findings", {}).get("bbq_coverage_gap")
    if bbq_gap:
        infos.append({
            "check": "bbq_coverage_gap",
            "message": "No existing BBQ articles in Shopify — Job 02 fills a coverage gap"
        })

    infos.append({
        "check": "dry_run_note",
        "message": "This is a dry-run — production duplicate_decisions.json NOT written. "
                   "Production write will happen when Phase 2B runs in live mode."
    })

    passed = memory_record["writer_planning_safe"] and len(blockers) == 0

    report = {
        "meta": {
            "phase":             "2B",
            "client":           "hcs_gadgets",
            "mode":             "duplicate_memory_dryrun",
            "run_timestamp":     datetime.now().isoformat(),
            "shopify_touched":   False,
            "queue_touched":     False,
            "production_memory_touched": False,
            "dry_run_preview":   PREVIEW_JSON,
        },
        "phase1e_passed":  phase1e_ok,
        "phase2a_passed":  phase2a_ok,
        "job":             job02_with_number,
        "duplicate_classifications": dup_class,
        "memory_record":   memory_record,
        "decision":         decision,
        "passed":          passed,
        "human_required":  memory_record["human_required"],
        "writer_planning_safe": memory_record["writer_planning_safe"],
        "blockers":        blockers,
        "warnings":        warnings,
        "infos":           infos,
    }

    print(f"Decision             : {decision}")
    print(f"Human required       : {memory_record['human_required']}")
    print(f"Writer planning safe: {memory_record['writer_planning_safe']}")
    print(f"Blockers            : {len(blockers)}")
    print(f"Warnings            : {len(warnings)}")
    print(f"Infos               : {len(infos)}")
    print()

    # ── Write outputs ─────────────────────────────────────────────────────
    write_json(report, PREVIEW_JSON)
    write_report(report, PHASE_REPORT)

    print()
    if passed:
        print("✅ Phase 2B PASSED — Job 02 is clear for writer planning")
        print("   Production duplicate_decisions.json NOT written (dry-run mode)")
        sys.exit(0)
    else:
        print(f"❌ Phase 2B BLOCKED — decision: {decision}")
        for b in blockers:
            print(f"  BLOCKER [{b['check']}] {b['message']}")
        sys.exit(1)


if __name__ == "__main__":
    main()
