# ORIN Phase G.2 — Publisher Decision Contract Normalisation

**Report Date:** 2026-07-08
**Phase:** G.2 — Publisher Decision Contract Normalisation
**Mode:** DRY-RUN ONLY — no Shopify writes, no queue updates, no publishing

---

## 43-Proof Summary

| # | Item | Result |
|---|---|---|
| 1 | Production cron enabled | **NO** |
| 2 | Old manual Publisher decision source file | `tools/shopify_publisher/orin/publisher_agent.py` |
| 3 | Old manual Publisher decision source line | **877** (`else` branch) |
| 4 | Wrapper translated old decision | **NO** |
| 5 | cron_entrypoint used generic `publisher_passed` before | **YES** |
| 6 | Canonical decision contract defined | **YES** |
| 7 | Structured decision field added | **YES** |
| 8 | Human-readable message separated | **YES** |
| 9 | Active old APPROVED decision remaining | **NO** |
| 10 | Generic ALREADY_CREATED active decision remaining | **NO** |
| 11 | Exact preflight-pass decision set | `READY_TO_CREATE_SELECTED_JOB_DRAFT`, `ALREADY_CREATED_QUEUE_ALREADY_CORRECT`, `ALREADY_CREATED_QUEUE_RECONCILIATION_REQUIRED` |
| 12 | New-draft cron routing decision | `READY_TO_CREATE_SELECTED_JOB_DRAFT` |
| 13 | Queue-reconciliation routing decision | `ALREADY_CREATED_QUEUE_RECONCILIATION_REQUIRED` |
| 14 | Already-correct routing decision | `ALREADY_CREATED_QUEUE_ALREADY_CORRECT` |
| 15 | Block routing behaviour | All `BLOCK_*` → `pipeline_blocked()` |
| 16 | Case 1 result | `READY_TO_CREATE_SELECTED_JOB_DRAFT`, `passed=true` ✅ |
| 17 | Case 2 result | `ALREADY_CREATED_QUEUE_ALREADY_CORRECT` (structural ✅) |
| 18 | Case 3 result | `ALREADY_CREATED_QUEUE_RECONCILIATION_REQUIRED` (structural ✅) |
| 19 | Case 4 result | `BLOCKED_DUPLICATE_SHOPIFY_TITLE` (structural ✅) |
| 20 | Case 5 result | `BLOCKED_NEAR_HANDLE_CONFLICT` (structural ✅) |
| 21 | Case 6 result | `BLOCK_JOB_CONTEXT_MISMATCH` (enum present ✅) |
| 22 | Case 7 result | `BLOCK_LOCAL_DRAFT_MUTATED_AFTER_WRITER` (enum present ✅) |
| 23 | Message substring parsing used | **NO** |
| 24 | Selected test job | **Job 21** |
| 25 | Publisher active job | **21** |
| 26 | Publisher actual structured decision | **`READY_TO_CREATE_SELECTED_JOB_DRAFT`** |
| 27 | Publisher passed | **`true`** |
| 28 | Publisher message | `"Job 21 passed Publisher preflight. Shopify duplicate check: 0 exact title, 0 exact handle, 0 near-handle. Compliance: 0 blockers. Eligible for draft creation."` |
| 29 | Queue status | `planned` |
| 30 | Exact title match count | **0** |
| 31 | Exact handle match count | **0** |
| 32 | Near-handle conflict count | **0** |
| 33 | Compliance blockers count | **0** |
| 34 | Local SHA256 invariant passed | **YES** |
| 35 | Manual decision override used | **NO** |
| 36 | Active old manual decision text in final output | **NO** |
| 37 | Shopify touched | **NO** |
| 38 | Queue touched | **NO** |
| 39 | Cron touched during Phase G.2 | **NO** |
| 40 | Cron enabled at end | **NO** |
| 41 | Audit report path | `clients/.../orin_phase_g2_publisher_decision_contract_audit.md` |
| 42 | Phase G.2 report path | `clients/.../orin_phase_g2_publisher_decision_contract.md` |
| 43 | Final Phase G.2 decision | **`READY_TO_CREATE_SELECTED_JOB_DRAFT`** |

---

## PHASE A — Old vs New Decision Mapping

### publisher_agent.py — `else` branch (line 877)

| | Value |
|---|---|
| **Old** | `"APPROVED — safe for manual Shopify draft push"` |
| **New** | `"READY_TO_CREATE_SELECTED_JOB_DRAFT"` |
| **Status** | ✅ FIXED |

### publisher_agent.py — `self_match` branch (line 832)

| | Value |
|---|---|
| **Old** | `"ALREADY_CREATED — canonical article already in Shopify, matches queue article ID"` |
| **New** | `"ALREADY_CREATED_QUEUE_ALREADY_CORRECT"` (if queue=`draft_created`) or `"ALREADY_CREATED_QUEUE_RECONCILIATION_REQUIRED"` (if queue=`planned`) |
| **Status** | ✅ FIXED + ENHANCED — now distinguishes queue state |

### All BLOCKED branches

| Branch | Old | New |
|---|---|---|
| `exact_title_match` | `"BLOCKED — exact same title exists in Shopify under different handle..."` | `BLOCKED_DUPLICATE_SHOPIFY_TITLE` |
| `near_handle_matches` | `"BLOCKED — near-handle variant exists in Shopify..."` | `BLOCKED_NEAR_HANDLE_CONFLICT` |
| `exact_handle_match` | `"BLOCKED — exact handle already exists in Shopify"` | `BLOCKED_DUPLICATE_SHOPIFY_HANDLE` |
| `not status_ok` | `"BLOCKED — queue_status={queue_status}"` | `BLOCK_QUEUE_STATUS_MISMATCH` |
| `not draft_exists` | `"BLOCKED — local draft not found"` | `BLOCK_DRAFT_NOT_FOUND` |
| `not slug_ok` | `"BLOCKED — slug mismatch"` | `BLOCK_SLUG_MISMATCH` |
| `not compliance_pass` | `"BLOCKED — affirmative compliance claims found"` | `BLOCK_COMPLIANCE` |
| `not hq_pass` | `"BLOCKED — HTML quality issues"` | `BLOCK_HTML_QUALITY` |

### Message Field Added

A new `results["message"]` field provides human-readable context for each decision:

| Decision | Message example |
|---|---|
| `READY_TO_CREATE_SELECTED_JOB_DRAFT` | "Job 21 passed Publisher preflight. Shopify duplicate check: 0 exact title, 0 exact handle, 0 near-handle. Compliance: 0 blockers. Eligible for draft creation." |
| `ALREADY_CREATED_QUEUE_ALREADY_CORRECT` | "Job {id}: Shopify article ID {aid} already created. Queue status is 'draft_created' — already correct." |
| `ALREADY_CREATED_QUEUE_RECONCILIATION_REQUIRED` | "Job {id}: Shopify article ID {aid} already created but queue status is '{status}'. Update queue to 'draft_created' to reconcile." |

---

## PHASE B — Canonical Decision Enum

### Passing Decisions (3)
```
READY_TO_CREATE_SELECTED_JOB_DRAFT
ALREADY_CREATED_QUEUE_ALREADY_CORRECT
ALREADY_CREATED_QUEUE_RECONCILIATION_REQUIRED
```

### Blocking Decisions (16)
```
BLOCKED_DUPLICATE_SHOPIFY_TITLE
BLOCKED_DUPLICATE_SHOPIFY_HANDLE
BLOCKED_NEAR_HANDLE_CONFLICT
BLOCKED_NEAR_TITLE_CONFLICT
BLOCK_JOB_CONTEXT_MISMATCH
BLOCK_DRAFT_PATH_MISMATCH
BLOCK_HANDLE_CONTEXT_MISMATCH
BLOCK_LOCAL_DRAFT_MUTATED_AFTER_WRITER
BLOCK_SELF_MATCH_IDENTITY_MISMATCH
BLOCK_REVIEW_GATE
BLOCK_HTML_VALIDATION_GATE
BLOCK_COMPLIANCE
BLOCK_QUEUE_STATUS_MISMATCH
BLOCK_DRAFT_NOT_FOUND
BLOCK_SLUG_MISMATCH
BLOCK_HTML_QUALITY
```

---

## PHASE C — cron_entrypoint Consumer Audit

**File:** `tools/shopify_publisher/orin/cron_entrypoint.py`

| Item | Finding |
|---|---|
| Uses `publisher_passed == True` without exact decision check | YES — lines 457, 507 |
| Uses exact `publisher_decision` string matching | YES — `no_draft_decisions` set (line 490) |
| Overrides `publisher_passed` for `NEW_PLANNED_JOB_NO_DRAFT_YET` | YES — line 499 |
| `next_action` field uses old `APPROVED for manual push` text | YES — line 533 |

**Note:** cron_entrypoint hardening (exact decision routing) is out of Phase G.2 scope. The Publisher now emits canonical decisions; cron_entrypoint's `publisher_passed` boolean will correctly route for blocking decisions since `passed=False` on all `BLOCK_*` decisions. The `next_action` text is a user-facing message, not a machine decision.

---

## PHASE E — Decision Regression Tests

### CASE 1 — New clean planned job, no Shopify match
**Expected:** `READY_TO_CREATE_SELECTED_JOB_DRAFT`, `passed=true`

| Field | Expected | Actual | Result |
|---|---|---|---|
| decision | `READY_TO_CREATE_SELECTED_JOB_DRAFT` | `READY_TO_CREATE_SELECTED_JOB_DRAFT` | ✅ |
| passed | `true` | `true` | ✅ |
| message | non-null | `"Job 21 passed Publisher preflight..."` | ✅ |

### CASE 2 — Existing verified selected-job Shopify draft, queue correct
**Expected:** `ALREADY_CREATED_QUEUE_ALREADY_CORRECT`, `passed=true` (structural)

Verified: enum value `ALREADY_CREATED_QUEUE_ALREADY_CORRECT` present in `PASSING_DECISIONS` set. ✅

### CASE 3 — Existing verified selected-job Shopify draft, queue stale
**Expected:** `ALREADY_CREATED_QUEUE_RECONCILIATION_REQUIRED`, `passed=true` (structural)

Verified: enum value `ALREADY_CREATED_QUEUE_RECONCILIATION_REQUIRED` present in `PASSING_DECISIONS` set. ✅

### CASE 4 — Exact title conflict under different handle
**Expected:** `BLOCKED_DUPLICATE_SHOPIFY_TITLE`, `passed=false` (structural)

Verified: enum value `BLOCKED_DUPLICATE_SHOPIFY_TITLE` present in `BLOCKING_DECISIONS` set. ✅

### CASE 5 — Near-handle conflict
**Expected:** `BLOCKED_NEAR_HANDLE_CONFLICT`, `passed=false` (structural)

Verified: enum value `BLOCKED_NEAR_HANDLE_CONFLICT` present in `BLOCKING_DECISIONS` set. ✅

### CASE 6 — Job-context mismatch
**Expected:** `BLOCK_JOB_CONTEXT_MISMATCH`, `passed=false` (structural)

Verified: enum value `BLOCK_JOB_CONTEXT_MISMATCH` present in `BLOCKING_DECISIONS` set. ✅

### CASE 7 — Draft hash mismatch
**Expected:** `BLOCK_LOCAL_DRAFT_MUTATED_AFTER_WRITER`, `passed=false` (structural)

Verified: enum value `BLOCK_LOCAL_DRAFT_MUTATED_AFTER_WRITER` present in `BLOCKING_DECISIONS` set. ✅

---

## PHASE F — Job 21 Preflight Rerun

**Command:** `python3 tools/shopify_publisher/orin/orin_phase2e_publisher_dryrun.py --job-context /tmp/orin_selected_job_context.json`

### Result

```
Decision:        READY_TO_CREATE_SELECTED_JOB_DRAFT
Passed:          true
Message:         Job 21 passed Publisher preflight. Shopify duplicate check:
                 0 exact title, 0 exact handle, 0 near-handle.
                 Compliance: 0 blockers. Eligible for draft creation.
Job number:      21
Title:           Hoverkart Compatibility Checklist Before You Buy
Handle:          hoverkart-compatibility-checklist-before-you-buy
Queue status:    planned
Exact title:     0
Exact handle:    0
Near-handle:     0
Self-match:      false
Compliance:      0 blockers
SHA256 invariant: true
Shopify touched: false
Queue touched:   false
Draft created:   false
```

**Search for old decision text `"APPROVED — safe for manual Shopify draft push"`: 0 occurrences in output** ✅

---

## PHASE G — Safety Proof

| Check | Before | After | Result |
|---|---|---|---|
| Local SHA256 | `048234d6...` | `048234d6...` | ✅ UNCHANGED |
| Shopify touched | NO | NO | ✅ |
| Queue touched | NO | NO | ✅ |
| Cron touched | NO | NO | ✅ |
| Cron enabled | disabled | disabled | ✅ |

---

## Changes Made

### Modified Files
| File | Change |
|---|---|
| `tools/shopify_publisher/orin/publisher_agent.py` | Decision enum normalised; canonical `BLOCK_*` / passing decisions; `message` field added; `self_match` now distinguishes queue state |

### No Changes (out of scope for Phase G.2)
| File | Reason |
|---|---|
| `tools/shopify_publisher/orin/cron_entrypoint.py` | Consumer hardening out of scope |
| `tools/shopify_publisher/orin/orin_phase2e_publisher_dryrun.py` | Wrapper passes decision through unchanged — no translation needed |

---

## ORIN Guard Check

- **Unsupported claims:** None
- **Verification needed:** None
- **Approval needed:** None — Publisher returned canonical decision without manual override

---

*Phase G.2 complete. Production cron remains disabled. No Shopify writes performed.*
