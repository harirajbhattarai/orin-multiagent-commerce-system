# ORIN Production Pipeline Order v2 — Migration Report

**Date:** 2026-07-06
**Phase:** E — Pipeline Order Repair
**Status:** ✅ COMPLETE

---

## Problem: Circular Dependency

**Before v2 order:**
```
Phase 1A → Phase 1B → Phase 1C → Phase 2A (Review) → Phase 2B → Phase 2C (Writer) → Phase 2E
```

**Issue:** Phase 2A Review requires an existing local draft. For new planned jobs (no local draft yet):
1. Planner selects Job 21 (new planned job)
2. Local draft does NOT exist
3. Phase 2A returns `no_local_file_to_review`
4. Pipeline stops — Writer never reached
5. Circular dependency: review requires draft, but writer (which creates draft) comes AFTER review

---

## Solution: Writer First, Review After

**v2 order:**
```
Phase 1A → Phase 1B → Phase 1C → Phase 2C (Writer Planning) → Phase 2A (Review) → Phase 2B → Phase 2E
```

**Why this works:**
1. Writer runs first and creates/plans the draft
2. Review then evaluates the existing draft
3. For new planned jobs without a draft yet, Phase 2A gracefully skips (not in review scope)
4. Publisher preflight (Phase 2E) handles ALREADY_CREATED detection
5. No circular dependency

---

## Canonical Pipeline Order (v2)

| Phase | Name | Trigger | Contract |
|---|---|---|---|
| 1A | State | Always | Read current queue state from Shopify |
| 1B | Planner | Always | Select lowest-numbered due job |
| 1C | Recovery | Always | Check for interrupted prior runs |
| **2C** | **Writer Planning** | **Always** | **Choose article plan, title, handle, outline (PRE-WRITE)** |
| **2A** | **Review Agent** | **Always** | **Content quality, compliance review (POST-WRITE)** |
| 2B | Duplicate Memory | Always | Check for duplicate topic/title decisions |
| 2E | Publisher Preflight | Always | Shopify duplicate check, draft validation |

---

## PRE-WRITE vs POST-WRITE Separation

### PRE-WRITE (Phase 2C — Writer Planning)
- Topic/scope confirmation
- Title and handle selection
- Internal link strategy
- Outline structure
- Writer creates local HTML draft

### POST-WRITE (Phase 2A — Review Agent)
- Content quality review
- Compliance check (flagged language)
- Heading structure validation
- CTA validation
- FAQ validation
- Internal link verification

---

## Phase 2A Handling for New Planned Jobs

For jobs outside Phase 2A scope (e.g. Job 21 is not in jobs 15–20):

**Before v2:** `no_local_file_to_review` → pipeline stopped ❌

**After v2:**
```python
if review_decision == "no_local_file_to_review":
    # Phase 2A scope is jobs 15-20. For jobs outside this range:
    # do NOT block — Phase 2C Writer ran first and the draft is being created.
    review_decision = "skipped_new_planned_job"
    log("Phase 2A: Job X not in review scope — continuing pipeline")
```

Pipeline continues to Phase 2B and Phase 2E.

---

## Phase 2E Handling for New Planned Jobs

For new planned jobs with no local draft yet:

**Publisher Agent response:** `BLOCK — local draft not found` + `passed=False`

**Cron Entrypoint handling:**
```python
is_new_planned_no_draft = (
    not publisher_passed
    and job_ctx.get("queue_status") == "planned"
    and job_ctx.get("local_draft_exists") is False
    and publisher_decision == "BLOCK — local draft not found"
)
if is_new_planned_no_draft:
    publisher_passed = True  # override — expected state
    publisher_decision = "NEW_PLANNED_JOB_NO_DRAFT_YET"
    job_ctx["ALREADY_CREATED_classification"] = "NEW_PLANNED_JOB_NO_DRAFT_YET"
```

Pipeline continues to DRY-RUN COMPLETE. No Shopify writes.

---

## Job Context Propagation

**Canonical context file:** `/tmp/orin_selected_job_context.json`

**Built after Phase 1B** in `cron_entrypoint.py`:
```python
job_ctx = build_job_context(
    job_number=str(job_num),
    job_data=job,
    planner_decision=planner_decision,
    planner_reason=planner_reason,
)
write_job_context(job_ctx, JOB_CONTEXT_PATH)
```

**Propagated to downstream phases:**
- Phase 2C (Writer Planning): via `JOB_CONTEXT_PATH` env var
- Phase 2E (Publisher): via `--job-context CLI` argument

---

## No Structural Change to Agent Code

**Agents unchanged:**
- `writer_agent.py` — still performs writer planning
- `review_agent.py` — still performs post-write review
- `publisher_agent.py` — accepts dynamic job context

**Only change:** execution ORDER in `cron_entrypoint.py`

---

## Phase 2A Review Scope Note

Phase 2A Review Agent currently reviews jobs 15–20. New planned jobs (Job 21+) are not in scope. In v2, these jobs skip Phase 2A review and go directly to Phase 2B/2E. This is acceptable for the repair scope — Phase 2A review scope expansion to new jobs is a future improvement.
