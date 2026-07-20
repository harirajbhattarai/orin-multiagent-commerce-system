# ORIN Phase G.2 — Publisher Decision Contract Audit

**Report Date:** 2026-07-08
**Phase:** G.2 — Publisher Decision Contract Normalisation

---

## PHASE A — Decision Source Audit

### Publisher Agent Decisions

**File:** `tools/shopify_publisher/orin/publisher_agent.py`

All decision assignments in `run_dryrun()` Step 11 (lines 828–880):

| Line | Decision (Old) | `passed` | Canonical Replacement |
|---|---|---|---|
| 832 | `"ALREADY_CREATED — canonical article already in Shopify, matches queue article ID"` | `True` | `ALREADY_CREATED_QUEUE_ALREADY_CORRECT` |
| 838 | `"BLOCKED — exact same title exists in Shopify under different handle — reconcile before creating"` | `False` | `BLOCKED_DUPLICATE_SHOPIFY_TITLE` |
| 843 | `"BLOCKED — near-handle variant exists in Shopify — reconcile before creating"` | `False` | `BLOCKED_NEAR_HANDLE_CONFLICT` |
| 848 | `"BLOCKED — exact handle already exists in Shopify"` | `False` | `BLOCKED_DUPLICATE_SHOPIFY_HANDLE` |
| 853 | `"BLOCKED — queue_status={queue_status}"` | `False` | `BLOCKED_QUEUE_STATUS_MISMATCH` |
| 858 | `"BLOCKED — local draft not found"` | `False` | `BLOCKED_DRAFT_NOT_FOUND` |
| 863 | `"BLOCKED — slug mismatch"` | `False` | `BLOCKED_SLUG_MISMATCH` |
| 868 | `"BLOCKED — affirmative compliance claims found"` | `False` | `BLOCKED_COMPLIANCE` |
| 873 | `"BLOCKED — HTML quality issues"` | `False` | `BLOCKED_HTML_QUALITY` |
| 877 | `"APPROVED — safe for manual Shopify draft push"` | `True` | `READY_TO_CREATE_SELECTED_JOB_DRAFT` |

### Publisher Agent — Human-Readable Message Field

**Not yet implemented.** The Publisher does not emit a separate `message` field.
Human-readable context is embedded in the `decision` string.

**Fix:** Add `results["message"]` field with human-readable text.
Keep `results["decision"]` as canonical enum only.

### Wrapper — Decision Translation

**File:** `tools/shopify_publisher/orin/orin_phase2e_publisher_dryrun.py`

Line 212: `decision = agent_results.get("decision", "")`

The wrapper extracts `decision` from Publisher output and uses it only for exit-code logic (line 219: `return agent_passed or is_soft_block`). It does **not** translate or modify the decision string.

**Wrapper decision translation:** NO

### cron_entrypoint — Decision Consumption

**File:** `tools/shopify_publisher/orin/cron_entrypoint.py`

Lines 457–508 — how Publisher result is consumed:

```
publisher_passed = phase2e.get("passed", False)       # line 457
publisher_decision = phase2e.get("decision", "")       # line 458
publisher_job = phase2e.get("publisher_job_number")    # line 459
```

Decision routing logic:
1. **ALREADY_CREATED job mismatch check** (lines 465–472): Compares `publisher_job` vs `job_num`. Blocks if mismatch.
2. **NEW_PLANNED_JOB_NO_DRAFT_YET** (lines 490–504): Detects `"BLOCK — local draft not found"` or `"BLOCKED — local draft not found"` for planned jobs with no local draft. Overrides `publisher_passed = True`.
3. **Block on `not publisher_passed`** (line 507): `return pipeline_blocked(...)`.
4. **next_action text** (line 533): `"APPROVED for manual push..."` — uses old human-readable text.

**cron_entrypoint uses generic `publisher_passed` for pass routing:** YES
**cron_entrypoint uses exact decision enum for routing:** NO (only for string-matching `no_draft_decisions`)
**cron_entrypoint uses old APPROVED text:** YES — line 533 `next_action` field

---

## PHASE B — Canonical Decision Enum (Defined)

```
READY_TO_CREATE_SELECTED_JOB_DRAFT
ALREADY_CREATED_QUEUE_ALREADY_CORRECT
ALREADY_CREATED_QUEUE_RECONCILIATION_REQUIRED
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

**Passing decisions:** `READY_TO_CREATE_SELECTED_JOB_DRAFT`, `ALREADY_CREATED_QUEUE_ALREADY_CORRECT`, `ALREADY_CREATED_QUEUE_RECONCILIATION_REQUIRED`
**Blocking decisions:** All `BLOCK_*` prefixed decisions

---

## PHASE C — Selected-Job Decision Mapping Issues

**Issue 1 — `self_match` uses old decision text:**
Line 832: `"ALREADY_CREATED — canonical article already in Shopify, matches queue article ID"` → should be `ALREADY_CREATED_QUEUE_ALREADY_CORRECT`

**Issue 2 — `else` branch uses old APPROVED text:**
Line 877: `"APPROVED — safe for manual Shopify draft push"` → should be `READY_TO_CREATE_SELECTED_JOB_DRAFT`

**Issue 3 — Missing `message` field:**
Publisher emits only `decision` field. No separate human-readable `message`.

---

## Blocking Issues Confirmed

1. Publisher emits old `APPROVED — safe for manual Shopify draft push` → blocks canonical decision contract
2. Publisher emits old `ALREADY_CREATED — canonical article...` → blocks canonical ALREADY_CREATED classification
3. cron_entrypoint `next_action` uses old `APPROVED for manual push` text
4. No `message` field separating human-readable from machine decision
