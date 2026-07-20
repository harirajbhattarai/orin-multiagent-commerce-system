# ORIN Phase G.2B — Remove Legacy Publisher Decision Alias from Production Routing

**Report Date:** 2026-07-08
**Phase:** G.2B — Remove Legacy Publisher Decision Alias from Production Routing
**Mode:** DRY-RUN ONLY — no Shopify writes, no queue updates, no publishing

---

## 25-Proof Summary

| # | Item | Result |
|---|---|---|
| 1 | Production cron enabled | **NO** |
| 2 | Legacy decision active references before | `cron_entrypoint.py` lines 507, 514, 529, 532, 534 |
| 3 | Publisher can emit legacy decision before | **NO** |
| 4 | Publisher can emit legacy decision after | **NO** |
| 5 | Legacy cron route existed before | **YES** |
| 6 | Legacy cron route exists after | **NO** |
| 7 | Canonical passing decision count | **3** |
| 8 | `READY_TO_CREATE` route | `NEW_DRAFT_CREATION_ROUTE` |
| 9 | `ALREADY_CREATED_QUEUE_ALREADY_CORRECT` route | `SAFE_STOP_ALREADY_CORRECT` |
| 10 | `ALREADY_CREATED_QUEUE_RECONCILIATION_REQUIRED` route | `QUEUE_RECONCILIATION_ROUTE` |
| 11 | `BLOCK_*` route | `BLOCK_AND_STOP` |
| 12 | Legacy decision regression decision | `NEW_PLANNED_JOB_NO_DRAFT_YET` |
| 13 | Legacy decision regression route | `BLOCK_UNKNOWN_PUBLISHER_DECISION` |
| 14 | Unknown decision regression route | `BLOCK_UNKNOWN_PUBLISHER_DECISION` |
| 15 | Message substring routing used | **NO** |
| 16 | Generic `passed` routing used | **NO** |
| 17 | Job 21 actual Publisher decision | `READY_TO_CREATE_SELECTED_JOB_DRAFT` |
| 18 | Job 21 actual Publisher route | `NEW_DRAFT_CREATION_ROUTE` |
| 19 | Local SHA256 unchanged | **YES** |
| 20 | Shopify touched | **NO** |
| 21 | Queue touched | **NO** |
| 22 | Cron touched | **NO** |
| 23 | Cron enabled at end | **NO** |
| 24 | Report path | `clients/.../orin_phase_g2b_legacy_publisher_decision_removal.md` |
| 25 | Final Phase G.2B decision | **`READY_TO_CREATE_SELECTED_JOB_DRAFT`** |

---

## PHASE A — Legacy Decision Audit

### Where `NEW_PLANNED_JOB_NO_DRAFT_YET` existed before

| File | Line | Type | Classification |
|---|---|---|---|
| `cron_entrypoint.py` | 507 | `elif publisher_decision == "NEW_PLANNED_JOB_NO_DRAFT_YET":` route branch | **ACTIVE_PRODUCTION_ROUTING** |
| `cron_entrypoint.py` | 514 | `# ── NEW_PLANNED_JOB_NO_DRAFT_YET ─` comment | HISTORICAL_COMMENT |
| `cron_entrypoint.py` | 529 | `publisher_decision = "NEW_PLANNED_JOB_NO_DRAFT_YET"` override assignment | **ACTIVE_PRODUCTION_DECISION** |
| `cron_entrypoint.py` | 532 | `job_ctx["ALREADY_CREATED_classification"] = "NEW_PLANNED_JOB_NO_DRAFT_YET"` | **ACTIVE_PRODUCTION_DECISION** |
| `cron_entrypoint.py` | 534 | `print(f"Classification: NEW_PLANNED_JOB_NO_DRAFT_YET")` | ACTIVE_PRODUCTION_REPORT_TEXT |

### Publisher can emit `NEW_PLANNED_JOB_NO_DRAFT_YET`?

**NO.** `publisher_agent.py` does not emit this decision. `orin_phase2e_publisher_dryrun.py` does not emit this decision. It was entirely a `cron_entrypoint.py`-internal alias.

---

## PHASE B — Strict Canonical Routing

### Before
```
READY_TO_CREATE_SELECTED_JOB_DRAFT     → NEW_DRAFT_CREATION_ROUTE  ✅
ALREADY_CREATED_QUEUE_ALREADY_CORRECT  → SAFE_STOP_ALREADY_CORRECT ✅
ALREADY_CREATED_QUEUE_RECONCILIATION_… → QUEUE_RECONCILIATION_ROUTE ✅
BLOCK_*                                 → BLOCK_AND_STOP           ✅
NEW_PLANNED_JOB_NO_DRAFT_YET           → NEW_DRAFT_CREATION_ROUTE  ❌ LEGACY
(unknown)                               → BLOCK_UNKNOWN            ✅
```

### After
```
READY_TO_CREATE_SELECTED_JOB_DRAFT     → NEW_DRAFT_CREATION_ROUTE  ✅
ALREADY_CREATED_QUEUE_ALREADY_CORRECT  → SAFE_STOP_ALREADY_CORRECT ✅
ALREADY_CREATED_QUEUE_RECONCILIATION_… → QUEUE_RECONCILIATION_ROUTE ✅
BLOCK_*                                 → BLOCK_AND_STOP           ✅
NEW_PLANNED_JOB_NO_DRAFT_YET           → BLOCK_UNKNOWN_PUBLISHER_DECISION ❌ REMOVED
(unknown)                               → BLOCK_UNKNOWN            ✅
```

### Changes Applied

1. **`elif publisher_decision == "NEW_PLANNED_JOB_NO_DRAFT_YET":` branch** — removed from routing
2. **`is_new_planned_no_draft` override block** — removed (was setting `publisher_decision = "NEW_PLANNED_JOB_NO_DRAFT_YET"`)
3. **`no_draft_decisions` variable** — removed (was only used by override block)
4. **`job_ctx["ALREADY_CREATED_classification"] = "NEW_PLANNED_JOB_NO_DRAFT_YET"`** — removed
5. **`print(f"Classification: NEW_PLANNED_JOB_NO_DRAFT_YET")`** — removed

---

## PHASE C — Regression Results

| Case | Decision | Expected Route | Actual Route | Expected Passed | Actual Passed | Result |
|---|---|---|---|---|---|---|
| Canonical — new draft | `READY_TO_CREATE_SELECTED_JOB_DRAFT` | `NEW_DRAFT_CREATION_ROUTE` | `NEW_DRAFT_CREATION_ROUTE` | `true` | `true` | ✅ |
| Canonical — already correct | `ALREADY_CREATED_QUEUE_ALREADY_CORRECT` | `SAFE_STOP_ALREADY_CORRECT` | `SAFE_STOP_ALREADY_CORRECT` | `true` | `true` | ✅ |
| Canonical — queue reconciliation | `ALREADY_CREATED_QUEUE_RECONCILIATION_REQUIRED` | `QUEUE_RECONCILIATION_ROUTE` | `QUEUE_RECONCILIATION_ROUTE` | `true` | `true` | ✅ |
| Canonical — block | `BLOCKED_DUPLICATE_SHOPIFY_TITLE` | `BLOCK_AND_STOP` | `BLOCK_AND_STOP` | `false` | `false` | ✅ |
| Canonical — block | `BLOCKED_NEAR_HANDLE_CONFLICT` | `BLOCK_AND_STOP` | `BLOCK_AND_STOP` | `false` | `false` | ✅ |
| Canonical — block | `BLOCK_JOB_CONTEXT_MISMATCH` | `BLOCK_AND_STOP` | `BLOCK_AND_STOP` | `false` | `false` | ✅ |
| Canonical — block | `BLOCK_LOCAL_DRAFT_MUTATED_AFTER_WRITER` | `BLOCK_AND_STOP` | `BLOCK_AND_STOP` | `false` | `false` | ✅ |
| **Legacy alias** | `NEW_PLANNED_JOB_NO_DRAFT_YET` | `BLOCK_UNKNOWN_PUBLISHER_DECISION` | `BLOCK_UNKNOWN_PUBLISHER_DECISION` | `false` | `false` | ✅ |
| Unknown decision | `SOME_UNKNOWN_STATE` | `BLOCK_UNKNOWN_PUBLISHER_DECISION` | `BLOCK_UNKNOWN_PUBLISHER_DECISION` | `false` | `false` | ✅ |

**All 9 cases: ✅ PASS**

---

## PHASE D — Job 21 Routing Proof

**Command:** `python3 tools/shopify_publisher/orin/cron_entrypoint.py --dry-run --job 21`

**Output:**
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
| Shopify touched | `false` |
| Queue touched | `false` |

---

## PHASE E — Safety Proof

| Check | Result |
|---|---|
| Local SHA256 | `048234d6bde164c6d70986d994690537ca5d4423c4ed3014d2fe7a5889ad8049` — **UNCHANGED** ✅ |
| Shopify touched | **NO** ✅ |
| Queue touched | **NO** ✅ |
| Cron touched | **NO** ✅ |
| Cron enabled at end | **NO** ✅ |

---

## ORIN Guard Check

- **Unsupported claims:** None
- **Verification needed:** None
- **Approval needed:** None

---

*Phase G.2B complete. Production cron remains disabled. No Shopify writes performed.*
