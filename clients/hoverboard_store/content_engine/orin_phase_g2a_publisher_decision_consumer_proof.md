# ORIN Phase G.2A — Publisher Decision Consumer and Regression Proof

**Report Date:** 2026-07-08
**Phase:** G.2A — Publisher Decision Consumer and Regression Proof
**Mode:** DRY-RUN ONLY — no Shopify writes, no queue updates, no publishing

---

## 36-Proof Summary

| # | Item | Result |
|---|---|---|
| 1 | Production cron enabled | **NO** |
| 2 | Decision consumer classification before | MIXED — `publisher_passed` boolean + old string matching |
| 3 | Generic `publisher_passed` routing existed before | **YES** |
| 4 | Exact decision routing implemented | **YES** |
| 5 | `publisher_route` field exists | **YES** |
| 6 | New draft route decision | `READY_TO_CREATE_SELECTED_JOB_DRAFT` |
| 7 | Queue reconciliation route decision | `ALREADY_CREATED_QUEUE_RECONCILIATION_REQUIRED` |
| 8 | Already correct route decision | `ALREADY_CREATED_QUEUE_ALREADY_CORRECT` |
| 9 | Block route behaviour | All `BLOCK_*` → `BLOCK_AND_STOP` → `pipeline_blocked()` |
| 10 | Unknown decision behaviour | `BLOCK_UNKNOWN_PUBLISHER_DECISION` → `pipeline_blocked()` |
| 11 | Case 1 decision | `READY_TO_CREATE_SELECTED_JOB_DRAFT` |
| 12 | Case 1 route | `NEW_DRAFT_CREATION_ROUTE` ✅ |
| 13 | Case 2 decision | `ALREADY_CREATED_QUEUE_ALREADY_CORRECT` |
| 14 | Case 2 route | `SAFE_STOP_ALREADY_CORRECT` ✅ |
| 15 | Case 3 decision | `ALREADY_CREATED_QUEUE_RECONCILIATION_REQUIRED` |
| 16 | Case 3 route | `QUEUE_RECONCILIATION_ROUTE` ✅ |
| 17 | Case 4 decision | `BLOCKED_DUPLICATE_SHOPIFY_TITLE` |
| 18 | Case 4 route | `BLOCK_AND_STOP` ✅ |
| 19 | Case 5 decision | `BLOCKED_NEAR_HANDLE_CONFLICT` |
| 20 | Case 5 route | `BLOCK_AND_STOP` ✅ |
| 21 | Case 6 decision | `BLOCK_JOB_CONTEXT_MISMATCH` |
| 22 | Case 6 route | `BLOCK_AND_STOP` ✅ |
| 23 | Case 7 decision | `BLOCK_LOCAL_DRAFT_MUTATED_AFTER_WRITER` |
| 24 | Case 7 route | `BLOCK_AND_STOP` ✅ |
| 25 | Unknown-decision regression result | `BLOCK_UNKNOWN_PUBLISHER_DECISION` ✅ |
| 26 | Message substring routing used | **NO** |
| 27 | Generic `publisher_passed`-only routing used after | **NO** |
| 28 | Job 21 actual Publisher decision | `READY_TO_CREATE_SELECTED_JOB_DRAFT` |
| 29 | Job 21 Publisher passed | `true` |
| 30 | Job 21 publisher route | `NEW_DRAFT_CREATION_ROUTE` |
| 31 | Shopify touched | **NO** |
| 32 | Queue touched | **NO** |
| 33 | Cron touched | **NO** |
| 34 | Cron enabled at end | **NO** |
| 35 | Report path | `clients/.../orin_phase_g2a_publisher_decision_consumer_proof.md` |
| 36 | Final Phase G.2A decision | **`READY_TO_CREATE_SELECTED_JOB_DRAFT`** |

---

## PHASE A — Cron Decision Consumer Audit

### Before: MIXED Routing

**File:** `tools/shopify_publisher/orin/cron_entrypoint.py`

| What | Before | After |
|---|---|---|
| Pass routing | `if publisher_passed:` | `publisher_route` enum |
| Block routing | `if not publisher_passed:` | `BLOCK_AND_STOP` |
| NEW_PLANNED override | Matches old text `"BLOCK — local draft not found"`, `"BLOCKED — local draft not found"` | Matches new enum `BLOCK_DRAFT_NOT_FOUND` |
| `publisher_route` field | **Missing** | **Added** |
| `next_action` | Old `"APPROVED for manual push..."` text | `"Publisher route: {publisher_route}..."` |

### After: Exact Decision Routing

```
READY_TO_CREATE_SELECTED_JOB_DRAFT     → NEW_DRAFT_CREATION_ROUTE
ALREADY_CREATED_QUEUE_ALREADY_CORRECT  → SAFE_STOP_ALREADY_CORRECT
ALREADY_CREATED_QUEUE_RECONCILIATION_… → QUEUE_RECONCILIATION_ROUTE
BLOCK_*                                 → BLOCK_AND_STOP
NEW_PLANNED_JOB_NO_DRAFT_YET            → NEW_DRAFT_CREATION_ROUTE
(unknown)                               → BLOCK_UNKNOWN_PUBLISHER_DECISION
```

### Invariant Added

A passing Publisher decision maps to exactly one allowed route. No two passing decisions collapse to the same route unless their required action is genuinely identical.

- `SAFE_STOP_ALREADY_CORRECT` ≠ `NEW_DRAFT_CREATION_ROUTE` (different actions)
- `QUEUE_RECONCILIATION_ROUTE` ≠ `SAFE_STOP_ALREADY_CORRECT` (different actions)
- All three passing routes are distinct.

---

## PHASE B — Regression Proof

### CASE 1 — New clean planned job
**Input:** `READY_TO_CREATE_SELECTED_JOB_DRAFT`, `passed=true`
**Expected route:** `NEW_DRAFT_CREATION_ROUTE`
**Actual route:** `NEW_DRAFT_CREATION_ROUTE` ✅

### CASE 2 — Existing verified draft, queue correct
**Input:** `ALREADY_CREATED_QUEUE_ALREADY_CORRECT`, `passed=true`
**Expected route:** `SAFE_STOP_ALREADY_CORRECT`
**Actual route:** `SAFE_STOP_ALREADY_CORRECT` ✅

### CASE 3 — Existing draft, queue stale
**Input:** `ALREADY_CREATED_QUEUE_RECONCILIATION_REQUIRED`, `passed=true`
**Expected route:** `QUEUE_RECONCILIATION_ROUTE`
**Actual route:** `QUEUE_RECONCILIATION_ROUTE` ✅

### CASE 4 — Exact title conflict
**Input:** `BLOCKED_DUPLICATE_SHOPIFY_TITLE`, `passed=false`
**Expected route:** `BLOCK_AND_STOP`
**Actual route:** `BLOCK_AND_STOP` ✅

### CASE 5 — Near-handle conflict
**Input:** `BLOCKED_NEAR_HANDLE_CONFLICT`, `passed=false`
**Expected route:** `BLOCK_AND_STOP`
**Actual route:** `BLOCK_AND_STOP` ✅

### CASE 6 — Job-context mismatch
**Input:** `BLOCK_JOB_CONTEXT_MISMATCH`, `passed=false`
**Expected route:** `BLOCK_AND_STOP`
**Actual route:** `BLOCK_AND_STOP` ✅

### CASE 7 — Draft SHA256 mismatch
**Input:** `BLOCK_LOCAL_DRAFT_MUTATED_AFTER_WRITER`, `passed=false`
**Expected route:** `BLOCK_AND_STOP`
**Actual route:** `BLOCK_AND_STOP` ✅

### CASE 8 — Unknown decision
**Input:** `SOME_UNKNOWN_DECISION_STATE`
**Expected route:** `BLOCK_UNKNOWN_PUBLISHER_DECISION`
**Actual route:** `BLOCK_UNKNOWN_PUBLISHER_DECISION` ✅

**All 8 cases: ✅ PASS**

---

## PHASE C — Job 21 Routing Proof

**Command:** `python3 tools/shopify_publisher/orin/cron_entrypoint.py --dry-run --job 21`

**Cron entrypoint output:**
```
Publisher decision: READY_TO_CREATE_SELECTED_JOB_DRAFT
Publisher passed: True
Publisher evaluated: Job 21
Publisher route: NEW_DRAFT_CREATION_ROUTE
✅ Phase 2E/2G PASS — preflight all checks passed
Next action: Publisher route: NEW_DRAFT_CREATION_ROUTE. Queue status: planned.
```

| Field | Value |
|---|---|
| Publisher decision | `READY_TO_CREATE_SELECTED_JOB_DRAFT` |
| Publisher passed | `true` |
| Publisher route | `NEW_DRAFT_CREATION_ROUTE` |
| Queue status | `planned` |

---

## PHASE D — Safety Proof

| Check | Result |
|---|---|
| Local SHA256 unchanged | `048234d6...` ✅ |
| Shopify touched | **NO** ✅ |
| Queue touched | **NO** ✅ |
| Cron touched | **NO** ✅ |
| Cron enabled at end | **NO** ✅ |

---

## Changes Made

### Modified Files

| File | Change |
|---|---|
| `tools/shopify_publisher/orin/cron_entrypoint.py` | Canonical routing sets added; `publisher_route` field added; `no_draft_decisions` updated to new enum; `next_action` updated; `pipeline_blocked` calls updated |

---

## ORIN Guard Check

- **Unsupported claims:** None
- **Verification needed:** None
- **Approval needed:** None

---

*Phase G.2A complete. Production cron remains disabled. No Shopify writes performed.*
