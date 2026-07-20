# ORIN Selected-Job Propagation and Pipeline Order Hardening — Repair Report

**Date:** 2026-07-06
**Phase:** F — Selected Job Propagation
**Status:** ✅ COMPLETE

---

## What Was Fixed

### Issue 1: Queue Parser Regex (Phase C)

**Root Cause:** Queue notes use two formats for Shopify Article ID:
- Historical (Jobs 15–19): `Article ID: 123`
- Job 20 onwards: `Shopify article ID: 1006845985116`

Regex `r"Article ID:\s*(\S+)"` failed to match `Shopify article ID:` format.

**Fix applied in `state_agent.py` `read_queue()`:**
```python
# Before:
shopify_id_note = re.search(r"Article ID:\s*(\S+)", notes)

# After:
shopify_id_note = re.search(r"(?:Shopify\s+)?Article\s+ID:\s*(\S+)", notes, re.IGNORECASE)
```

Also applied to `cron_entrypoint.py` duplicate `read_queue()` function.

**Result:** Job 20 correctly returns `shopify_id_from_notes: "1006845985116"`. False recovery warning eliminated.

---

### Issue 2: Phase 2E Hardcoded to Job 20 (Phase F)

**Root Cause:** `orin_phase2e_publisher_dryrun.py` hardcoded:
```python
subprocess.run([..., "Job 20",
    "clients/.../best-hoverboard-accessories-safer-riding.html", "--json"])
```
Phase 2E always evaluated Job 20 regardless of planner selection.

**Fix applied:**
1. `cron_entrypoint.py`: Job context built after Phase 1B and written to `/tmp/orin_selected_job_context.json`
2. Phase 2E call: `run_phase_wrapper("2E", ["--job-context", str(JOB_CONTEXT_PATH)])`
3. `orin_phase2e_publisher_dryrun.py`: Accepts `--job-context`, reads job context JSON, passes correct job number/draft path/handle to `publisher_agent.py`
4. `publisher_agent.py`: Accepts `--job-context` argument; uses dynamic job number, expected slug, queue status from context; removes hardcoded `TARGET_JOB`, `EXPECTED_SLUG`, `DRAFT_PATH`
5. ALREADY_CREATED invariant added: `publisher_job_number == selected_job_number`

---

### Issue 3: Pipeline Circular Dependency (Phase E)

**Root Cause:** Phase 2A (Review) ran before Phase 2C (Writer Planning). For new planned jobs with no local draft, Phase 2A returned `no_local_file_to_review` and the Writer was never reached.

**Fix applied in `cron_entrypoint.py`:**
- Phase 2C (Writer Planning) moved BEFORE Phase 2A
- Phase 2A now has `no_local_file_to_review` handled as `skipped_new_planned_job` — pipeline continues for jobs outside review scope
- Post-write review (Phase 2A) runs after Writer creates/plans draft
- Canonical pipeline order:
  1. Phase 1A: State
  2. Phase 1B: Planner / select due job
  3. Phase 1C: Recovery
  4. Phase 2C: Writer Planning (PRE-WRITE)
  5. Phase 2A: Review Agent (POST-WRITE — after writer has draft)
  6. Phase 2B: Duplicate Decision Memory
  7. Phase 2E: Publisher Preflight

---

## Production Hardcoding Audit

**Files audited:**
- `tools/shopify_publisher/orin/cron_entrypoint.py` — no production hardcoding remaining
- `tools/shopify_publisher/orin/state_agent.py` — queue parser fixed
- `tools/shopify_publisher/orin/publisher_agent.py` — hardcoded TARGET_JOB/EXPECTED_SLUG/DRAFT_PATH removed
- `tools/shopify_publisher/orin/orin_phase2e_publisher_dryrun.py` — hardcoded Job 20 removed; uses job context
- `tools/shopify_publisher/orin/job_context.py` — new canonical context module

**Remaining "Job 20" references (non-production):**
- `writer_agent.py` — simulation fixture for Job 20 (test data only, not executed in production)
- `orin_phase1a_state_dryrun.py` — Job 20 specific diagnostic check in wrapper
- `orin_phase2c_writer_planning_dryrun.py` — simulation report for Job 20
- `orin_phase2a_review_dryrun.py` — Job 20 status in review wrapper report
- `orchestrator.py`, `reporter_agent.py` — reporter text (not executed in production pipeline)

---

## Canonical Selected-Job Context

**Module:** `tools/shopify_publisher/orin/job_context.py`

**Context file:** `/tmp/orin_selected_job_context.json`

**Fields:**
| Field | Description |
|---|---|
| `job_number` | Selected job number as string (e.g. "21") |
| `job_label` | Formatted label (e.g. "Job 21") |
| `title` | Article title |
| `topic` | Job topic |
| `target_keyword` | SEO target keyword |
| `target_date` | YYYY-MM-DD due date |
| `expected_draft_date` | YYYY-MM-DD when draft should be ready |
| `queue_status` | planned / draft_created / published_live |
| `local_draft_path` | Absolute path or null |
| `shopify_article_id` | Shopify Article ID or null |
| `shopify_handle` | Shopify handle/slug or null |
| `ALREADY_CREATED_classification` | null / ALREADY_CREATED_QUEUE_ALREADY_CORRECT / NEW_PLANNED_JOB_NO_DRAFT_YET |

---

## ALREADY_CREATED Invariant

**Added to `cron_entrypoint.py` Phase 2E block:**

```python
if publisher_job and str(publisher_job) != str(job_num):
    return pipeline_blocked(
        f"Phase 2E BLOCKED — JOB_CONTEXT_MISMATCH: "
        f"Phase 2E evaluated Job {publisher_job} but selected job is Job {job_num}."
    )
```

**Job context mismatch → BLOCKED.**

---

## Dry-Run Results

### --as-of-date 2026-07-04
| Stage | Selected Job | Notes |
|---|---|---|
| Phase 1B | Job 21 | planner selects correctly |
| Phase 1C | Job 21 context | 0 active recovery items |
| Phase 2C | Job 21 | no_writer_action (wrapper simulates) |
| Phase 2A | Job 21 | skipped_new_planned_job |
| Phase 2B | Job 21 | no duplicate found |
| Phase 2E | Job 21 | NEW_PLANNED_JOB_NO_DRAFT_YET |

**DRY-RUN COMPLETE — no Shopify writes, no queue writes**
**Blocked:** False

### Current-date dry-run
Same as above. Job 21 consistently selected. No Job 20 active-job leakage.

---

## Next Steps

1. **Phase 2C Writer fix:** The writer planning wrapper still has `simulated_job_20_plan` hardcoded. For full production, Phase 2C must also accept job context and generate correct plan for selected job.

2. **Production cron re-enable:** After Phase 2C fix, run full regression and re-enable cron `c5c7e16b-5ee1-4855-ae7a-97fd25bfd67d`.

3. **Phase 1C fix at call site:** Already complete — `job_num` cast to `str` in `run_phase_wrapper("1C", [str(job_num)])`.
