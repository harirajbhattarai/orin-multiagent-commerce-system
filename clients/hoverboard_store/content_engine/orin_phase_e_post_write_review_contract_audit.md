# ORIN Phase E1 — Post-Write Review Contract Audit

**Phase:** E1 — Post-Write Review Contract Audit
**Date:** 2026-07-07
**Status:** ✅ COMPLETE

---

## Scope

Audit the existing Review Agent and its wrappers to identify:
- Current Review input/output contracts
- Where the Jobs 15–20 scope is defined
- Whether Review independently finds a draft or accepts an explicit path
- Whether Review accepts selected job context
- Whether Review uses queue scope vs selected-job scope
- Whether Review contains Job 20-specific assumptions

---

## Files Audited

| File | Role | Lines |
|------|------|-------|
| `tools/shopify_publisher/orin/review_agent.py` | Core Review Agent | 500+ |
| `tools/shopify_publisher/orin/orin_phase2a_review_dryrun.py` | Phase 2A batch-review dry-run wrapper | 170 |

---

## `review_agent.py` — Interface Audit

### `review_job()` — Single-job review

```python
def review_job(
    job_num: str,
    job_topic: str,
    local_file_path: Optional[str],
    shopify_handle: Optional[str],
    shopify_article_id: Optional[str],
    is_due: bool,
    queue_status: str,
) -> dict
```

**Input contract:**
- `job_num` — job identifier (string)
- `job_topic` — topic string
- `local_file_path` — resolved by caller via `local_file_for_job()` (queue lookup)
- `shopify_handle`, `shopify_article_id` — resolved by caller
- `is_due` — caller determines due status
- `queue_status` — from queue

**No hardcoded scope.** Accepts ANY job number.

**How it finds the draft:**
- `local_file_for_job(job)` — looks up `KNOWN_DRAFT_FILES` dict, then checks `DRAFTS_DIR`
- `KNOWN_DRAFT_FILES = {15: ..., 16: ..., 17: ..., 18: ..., 19: ...}` — Jobs 15–19 only (no Job 20, no Job 21)
- For unknown jobs: `local_file_for_job()` returns `(False, None)` → review returns `no_local_file_to_review`

### `review_jobs()` — Multi-job batch review

```python
def review_jobs(job_numbers: list) -> list
```

**Input contract:**
- `job_numbers: list` — caller provides the list
- **No internal scope restriction** — accepts any list of job numbers

**How it resolves each job:**
- Reads queue via `read_queue()`
- Calls `local_file_for_job()` for each job
- Has NO internal Jobs 15–20 range

**Conclusion:** The scope restriction was entirely in the WRAPPER, not in the Review Agent itself.

---

## `orin_phase2a_review_dryrun.py` — Wrapper Audit

### Jobs 15–20 Scope

**Line 43:**
```python
results = review_jobs([str(i) for i in range(15, 21)])
```

**Impact:** Only Jobs 15, 16, 17, 18, 19, 20 are reviewed. Jobs 21+ are never reviewed by this wrapper.

**This is the root cause of the previous "skipped because Job 21 is not in review scope" report.**

### How it finds drafts

Uses `local_file_for_job()` from `state_agent.py`:
- Checks `KNOWN_DRAFT_FILES` in `review_agent.py`
- Falls back to scanning `DRAFTS_DIR`
- Does NOT accept an explicit draft path

### No selected-job context acceptance

The wrapper:
- Does NOT read `/tmp/orin_selected_job_context.json`
- Does NOT read `/tmp/orin_selected_job_writer_plan.json`
- Does NOT accept a writer execution output path
- Uses queue lookup to find drafts (not the Writer execution output)

### Job 20-specific assumptions

- Line 55: `job_label = sys.argv[1] if len(sys.argv) > 1 else "Job 20"` — default argument, not active logic
- Lines 150–153: Status table shows "Job 20" as a specific row — cosmetic, not functional

---

## Contract Gap Analysis

| Requirement | Review Agent | Phase 2A Wrapper |
|-------------|-------------|-------------------|
| Accept selected job context | No | No |
| Accept writer plan | No | No |
| Accept explicit draft path | No | No |
| No queue-based job selection | N/A | Yes — always selects from queue |
| No fixed Jobs 15–20 scope | Yes | **No — hardcoded** |
| Accept any job number | Yes | No — scope restricted |
| New planned article support | Limited | No — requires existing draft in DRAFTS_DIR |

---

## Post-Write Review Required Contract

For the selected-job post-write Review stage, the following contract is required:

**Input:**
- `job_ctx` — canonical selected-job context (from Phase 1B)
- `writer_plan` — writer plan (from Phase 2C)
- `draft_path` — explicit path to Writer execution output (from Phase 2D)

**Forbidden:**
- Queue-based job selection
- Fixed range (Jobs 15–20)
- Independent draft discovery via DRAFTS_DIR scan

**Identity invariants:**
- `review_job_number == job_ctx.job_number`
- `review_job_number == writer_plan.job_number`

---

## Production Reference Classification

| File | Reference | Classification | Notes |
|------|-----------|----------------|-------|
| `review_agent.py` | `KNOWN_DRAFT_FILES` dict has Jobs 15–19 only | TEST_ONLY | Used by `local_file_for_job()` fallback; Jobs 20+ use DRAFTS_DIR scan |
| `orin_phase2a_review_dryrun.py` | `range(15, 21)` on line 43 | ACTIVE_PRODUCTION_DEPENDENCY | The blocker — fixed in Phase E |
| `orin_phase2a_review_dryrun.py` | `"Job 20"` default arg | TEST_ONLY | Default argument, not active logic |
| `review_agent.py` | No `simulated_job_20_plan` references | CLEAN | — |

---

*Report generated by ORIN Phase E1 — Post-Write Review Contract Audit.*
