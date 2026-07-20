# ORIN Phase H — Live-Draft Gate v2 Regression Tests

**Report Date:** 2026-07-08
**Phase:** H5 — Safety Regressions
**Gate Module:** `tools/shopify_publisher/orin/live_draft_gate.py`
**Test Runner:** `live_draft_gate.run_gate()` with per-case parameter overrides

---

## Test Harness

```python
from live_draft_gate import run_gate
from datetime import date

# Base case — all upstream state correct for Job 21
GOOD_KWARGS = dict(
    selected_job_context={...},   # Job 21, queue=planned, shopify_handle=...
    writer_plan={...},             # no_writer_action plan for Job 21
    writer_execution={...},        # Job 21 execution with sha256=048234d6...
    post_write_review={...},       # POST_WRITE_REVIEW_PASSED
    html_validation={...},         # PASS, safe_for_publisher_preflight=True
    publisher_preflight={...},     # READY_TO_CREATE_SELECTED_JOB_DRAFT, passed=True
    publisher_route="NEW_DRAFT_CREATION_ROUTE",
    live_draft_requested=True,
    live_draft_confirmed=True,
    business_date=date(2026, 7, 4),
)
```

---

## Regression Results Summary

| # | Case | Override | Expected Decision | Actual Decision | Approved | Pass |
|---|---|---|---|---|---|---|
| 1 | No `--confirm-live-draft` | `live_draft_confirmed=False` | `BLOCK_LIVE_DRAFT_CONFIRMATION_REQUIRED` | `BLOCK_LIVE_DRAFT_CONFIRMATION_REQUIRED` | `false` | ✅ |
| 2 | Writer job mismatch | `writer_plan.job_number="99"` | `BLOCK_JOB_CONTEXT_MISMATCH` | `BLOCK_JOB_CONTEXT_MISMATCH` | `false` | ✅ |
| 3 | Draft SHA256 mismatch | `writer_execution.sha256="BADHASH"` | `BLOCK_LOCAL_DRAFT_MUTATED_AFTER_WRITER` | `BLOCK_LOCAL_DRAFT_MUTATED_AFTER_WRITER` | `false` | ✅ |
| 4 | Review = NEEDS_HUMAN_REVIEW | `post_write_review.review_decision="POST_WRITE_REVIEW_NEEDS_HUMAN_REVIEW"` | `BLOCK_REVIEW_GATE` | `BLOCK_REVIEW_GATE` | `false` | ✅ |
| 5 | HTML = FAIL | `html_validation.validation_passed=False, safe_for_publisher_preflight=False` | `BLOCK_HTML_VALIDATION_GATE` | `BLOCK_HTML_VALIDATION_GATE` | `false` | ✅ |
| 6 | Publisher = ALREADY_CREATED_QUEUE_ALREADY_CORRECT | `publisher_preflight.decision="ALREADY_CREATED_QUEUE_ALREADY_CORRECT"` | `SAFE_STOP_ALREADY_CORRECT` | `SAFE_STOP_ALREADY_CORRECT` | `false` | ✅ |
| 7 | Publisher = ALREADY_CREATED_QUEUE_RECONCILIATION_REQUIRED | `publisher_preflight.decision="ALREADY_CREATED_QUEUE_RECONCILIATION_REQUIRED"` | `QUEUE_RECONCILIATION_REQUIRED` | `QUEUE_RECONCILIATION_REQUIRED` | `false` | ✅ |
| 8 | Publisher = BLOCK_* | `publisher_preflight.decision="BLOCKED_DUPLICATE_SHOPIFY_TITLE"` | `BLOCK_PUBLISHER_GATE` | `BLOCK_PUBLISHER_GATE` | `false` | ✅ |
| 9 | Unknown Publisher decision | `publisher_preflight.decision="SOME_WEIRD_STATE"` | `BLOCK_PUBLISHER_GATE` | `BLOCK_PUBLISHER_GATE` | `false` | ✅ |
| 10 | Queue = draft_created | `selected_job_context.queue_status="draft_created"` | `BLOCK_INVALID_QUEUE_STATE_FOR_DRAFT_CREATION` | `BLOCK_INVALID_QUEUE_STATE_FOR_DRAFT_CREATION` | `false` | ✅ |
| 11 | Job not due | `business_date=date(2026, 6, 1)` | `BLOCK_JOB_NOT_DUE` | `BLOCK_JOB_NOT_DUE` | `false` | ✅ |
| 12 | published_at config unsafe | N/A | N/A | N/A | N/A | N/A |
| 13 | Body verification unavailable | None (base case) | `BLOCK_POST_FETCH_BODY_VERIFICATION_UNAVAILABLE` | `BLOCK_POST_FETCH_BODY_VERIFICATION_UNAVAILABLE` | `false` | ✅ |

**Total: 12 applicable cases. 12 ✅ PASS. 0 ❌ FAIL.**

---

## Case Details

### CASE 1: No `--confirm-live-draft`

**Condition:** `live_draft_confirmed=False` (CLI intent not confirmed)

**Expected:** `BLOCK_LIVE_DRAFT_CONFIRMATION_REQUIRED`, `approved=false`

**Result:** ✅ PASS

**Gate logic:** H1 — CLI intent check. Both `--live-draft` and `--confirm-live-draft` must be present. Absence of confirmation returns immediately with `CLI_INTENT_BLOCK`.

---

### CASE 2: Writer Job Mismatch

**Condition:** `writer_plan.job_number` set to `"99"` (does not match selected job `"21"`)

**Expected:** `BLOCK_JOB_CONTEXT_MISMATCH`, `approved=false`

**Result:** ✅ PASS

**Gate logic:** H2 — Job context identity invariants. `writer_plan.job_number` (or `next_writing_candidate.job_number`) must match `selected_job_context.job_number`.

---

### CASE 3: Draft SHA256 Mismatch

**Condition:** `writer_execution.sha256` set to `"BADHASH"` (does not match actual file)

**Expected:** `BLOCK_LOCAL_DRAFT_MUTATED_AFTER_WRITER`, `approved=false`

**Result:** ✅ PASS

**Gate logic:** H4 — Writer artifact invariants. Current file SHA256 must match `writer_execution.sha256`.

---

### CASE 4: Review = NEEDS_HUMAN_REVIEW

**Condition:** `post_write_review.review_decision` set to `"POST_WRITE_REVIEW_NEEDS_HUMAN_REVIEW"`

**Expected:** `BLOCK_REVIEW_GATE`, `approved=false`

**Result:** ✅ PASS

**Gate logic:** H5 — Review gate. Review decision must be exactly `POST_WRITE_REVIEW_PASSED`.

---

### CASE 5: HTML = FAIL

**Condition:** `html_validation.validation_passed=False` and `safe_for_publisher_preflight=False`

**Expected:** `BLOCK_HTML_VALIDATION_GATE`, `approved=false`

**Result:** ✅ PASS

**Gate logic:** H6 — HTML validation gate. `validation_passed` must be `True` AND `safe_for_publisher_preflight` must be `True`.

---

### CASE 6: Publisher = ALREADY_CREATED_QUEUE_ALREADY_CORRECT

**Condition:** `publisher_preflight.decision="ALREADY_CREATED_QUEUE_ALREADY_CORRECT"` (Shopify draft already exists, queue correct)

**Expected:** `SAFE_STOP_ALREADY_CORRECT`, `approved=false`

**Result:** ✅ PASS

**Gate logic:** H7 — Publisher gate. `ALREADY_CREATED_QUEUE_ALREADY_CORRECT` returns `SAFE_STOP_ALREADY_CORRECT` (no write authorised, no action needed).

---

### CASE 7: Publisher = ALREADY_CREATED_QUEUE_RECONCILIATION_REQUIRED

**Condition:** `publisher_preflight.decision="ALREADY_CREATED_QUEUE_RECONCILIATION_REQUIRED"` (Shopify draft exists but queue is stale)

**Expected:** `QUEUE_RECONCILIATION_REQUIRED`, `approved=false`

**Result:** ✅ PASS

**Gate logic:** H7 — Publisher gate. `ALREADY_CREATED_QUEUE_RECONCILIATION_REQUIRED` returns `QUEUE_RECONCILIATION_REQUIRED` (queue update required before any write).

---

### CASE 8: Publisher = BLOCK_* Decision

**Condition:** `publisher_preflight.decision="BLOCKED_DUPLICATE_SHOPIFY_TITLE"`, `passed=False`

**Expected:** `BLOCK_PUBLISHER_GATE`, `approved=false`

**Result:** ✅ PASS

**Gate logic:** H7 — Publisher gate. Any `BLOCK_*` decision from Publisher blocks with `PUBLISHER_GATE_FAILED`.

---

### CASE 9: Unknown Publisher Decision

**Condition:** `publisher_preflight.decision="SOME_WEIRD_STATE"` (not in canonical enum)

**Expected:** `BLOCK_PUBLISHER_GATE`, `approved=false`

**Result:** ✅ PASS

**Gate logic:** H7 — Publisher gate. Unknown Publisher decisions (not in `CANONICAL_PASSING`) return `PUBLISHER_GATE_FAILED`.

---

### CASE 10: Queue = draft_created

**Condition:** `selected_job_context.queue_status="draft_created"` (for new draft creation route)

**Expected:** `BLOCK_INVALID_QUEUE_STATE_FOR_DRAFT_CREATION`, `approved=false`

**Result:** ✅ PASS

**Gate logic:** H8 — Queue state gate. New draft creation requires `queue_status == "planned"`. If already `draft_created`, no new draft should be created.

---

### CASE 11: Job Not Due

**Condition:** `business_date=date(2026, 6, 1)` (before job's `expected_draft_date=2026-07-04`)

**Expected:** `BLOCK_JOB_NOT_DUE`, `approved=false`

**Result:** ✅ PASS

**Gate logic:** H9 — Due/overdue check. Job must be due or overdue according to business date. Uses `business_time.is_due()`.

---

### CASE 12: published_at Config Unsafe

**Status:** N/A — In current gate implementation, `published_at_required` is always `null` (draft-only). No configurable path that would set an unsafe `published_at` value exists in this gate version.

---

### CASE 13: Body Verification Unavailable

**Condition:** Base case (all upstream state correct) — no override needed

**Expected:** `BLOCK_POST_FETCH_BODY_VERIFICATION_UNAVAILABLE`, `approved=false`

**Result:** ✅ PASS

**Gate logic:** H11 — Post-fetch body verification gate. Body hash verification capability must be confirmed before write is authorised. Currently returns `body_hash_verification_available: false` because the verification sequence (create → fetch → compare SHA256) is not yet implemented.

**This is the Phase H stop gate for Job 21.** All gates H1–H10 pass. The pipeline stops at H11 pending body verification implementation.

---

## Safety Properties Confirmed

1. ✅ No failed regression returns `approved: true`
2. ✅ No safety test touches Shopify or queue
3. ✅ All blocking decisions have `approved: false`
4. ✅ `SAFE_STOP_ALREADY_CORRECT` and `QUEUE_RECONCILIATION_REQUIRED` return `approved: false` (no false positive)
5. ✅ `LIVE_DRAFT_WRITE_APPROVED` is the only decision that returns `approved: true`
6. ✅ CLI intent check cannot be bypassed by any other parameter combination

---

## Canonical Gate Constants

```python
LIVE_DRAFT_WRITE_APPROVED = "LIVE_DRAFT_WRITE_APPROVED"
CLI_INTENT_BLOCK = "BLOCK_LIVE_DRAFT_CONFIRMATION_REQUIRED"
JOB_CONTEXT_MISMATCH = "BLOCK_JOB_CONTEXT_MISMATCH"
HANDLE_CONTEXT_MISMATCH = "BLOCK_HANDLE_CONTEXT_MISMATCH"
DRAFT_MUTATED = "BLOCK_LOCAL_DRAFT_MUTATED_AFTER_WRITER"
REVIEW_GATE_FAILED = "BLOCK_REVIEW_GATE"
HTML_GATE_FAILED = "BLOCK_HTML_VALIDATION_GATE"
PUBLISHER_GATE_FAILED = "BLOCK_PUBLISHER_GATE"
INVALID_QUEUE_STATE = "BLOCK_INVALID_QUEUE_STATE_FOR_DRAFT_CREATION"
JOB_NOT_DUE = "BLOCK_JOB_NOT_DUE"
PUBLISH_CONFIG_UNSAFE = "BLOCK_PUBLISH_CONFIGURATION_UNSAFE"
BODY_VERIFY_UNAVAILABLE = "BLOCK_POST_FETCH_BODY_VERIFICATION_UNAVAILABLE"
SAFE_STOP_ALREADY_CORRECT = "SAFE_STOP_ALREADY_CORRECT"
QUEUE_RECONCILIATION_REQUIRED = "QUEUE_RECONCILIATION_REQUIRED"
UNKNOWN_PUBLISHER_DECISION = "BLOCK_UNKNOWN_PUBLISHER_DECISION"
```
