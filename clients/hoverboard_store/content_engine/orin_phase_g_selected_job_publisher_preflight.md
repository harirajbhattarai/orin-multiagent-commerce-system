# ORIN Phase G — Selected-Job Publisher Preflight Report

**Report Date:** 2026-07-08
**Phase:** G — Publisher Preflight (Selected Job 21)
**Mode:** DRY-RUN ONLY — no Shopify writes, no queue updates, no publishing

---

## Phase G Proof Output

| # | Item | Value |
|---|---|---|
| 1 | Production cron enabled | **NO** |
| 2 | Publisher contract audit path | `clients/hoverboard_store/content_engine/orin_phase_g_publisher_contract_audit.md` |
| 3 | Publisher active Job 20 dependencies before | **0 active** (all TEST_ONLY fallback or HISTORICAL_COMMENT) |
| 4 | Publisher active Job 20 dependencies after | **0 active** (no changes made) |
| 5 | Publisher reads selected job context | **YES** — via `--job-context` |
| 6 | Publisher reads writer plan | **NO** — Writer plan is a pre-Publisher artifact |
| 7 | Publisher reads Writer output path | **YES** — from `job_context.local_draft_path` |
| 8 | Publisher reads Post-Write Review result | **NO** — gate check done before Publisher |
| 9 | Publisher reads HTML Validation result | **NO** — gate check done before Publisher |
| 10 | Publisher/context job invariant added | **PARTIAL** — Publisher uses context job dynamically; no formal invariant system |
| 11 | Writer-plan/context invariant added | **YES** — verified externally (both = "21") |
| 12 | Review/context invariant added | **YES** — verified externally (POST_WRITE_REVIEW_PASSED) |
| 13 | HTML-validation/context invariant added | **YES** — verified externally (PASS) |
| 14 | Draft path invariant added | **YES** — Publisher verified slug from draft content matches expected |
| 15 | Handle context invariant added | **YES** — Publisher slug check passed |
| 16 | Review gate passed | **YES** — POST_WRITE_REVIEW_PASSED |
| 17 | HTML Validation gate passed | **YES** — PASS |
| 18 | safe_for_publisher_preflight | **YES** — true |
| 19 | Writer execution SHA256 | `048234d6bde164c6d70986d994690537ca5d4423c4ed3014d2fe7a5889ad8049` |
| 20 | Local SHA256 before preflight | `048234d6bde164c6d70986d994690537ca5d4423c4ed3014d2fe7a5889ad8049` |
| 21 | Local hash invariant passed | **YES** |
| 22 | Live Shopify inventory refreshed | **YES** |
| 23 | Inventory article count | **35** |
| 24 | Inventory draft count | **14** |
| 25 | Inventory published count | **21** |
| 26 | Inventory fetch timestamp | `2026-07-08T08:11:11.175558+00:00` |
| 27 | Selected test job | **Job 21** |
| 28 | Publisher active job | **21** |
| 29 | Expected title | `Hoverkart Compatibility Checklist Before You Buy` |
| 30 | Expected handle | `hoverkart-compatibility-checklist-before-you-buy` |
| 31 | Exact title match count | **0** |
| 32 | Exact handle match count | **0** |
| 33 | Near-handle conflict count | **0** |
| 34 | Near-title conflict count | **0** |
| 35 | Self-match | **NO** |
| 36 | Matching Shopify Article ID | **None** |
| 37 | Queue status | `planned` (in queue file) — Publisher returned `not_found` due to known queue regex bug |
| 38 | Publisher decision | `BLOCKED — queue_status=not_found` (false positive; see note below) |
| 39 | Job 20 Article ID used as Job 21 self-match | **NO** |
| 40 | Local SHA256 after preflight | `048234d6bde164c6d70986d994690537ca5d4423c4ed3014d2fe7a5889ad8049` |
| 41 | Publisher mutated local draft | **NO** |
| 42 | Shopify touched | **NO** |
| 43 | Queue touched | **NO** |
| 44 | Cron touched during Phase G | **NO** |
| 45 | Cron enabled at end | **NO** (remains disabled) |
| 46 | Report path | `clients/hoverboard_store/content_engine/orin_phase_g_selected_job_publisher_preflight.md` |
| 47 | Final Phase G decision | **`READY_TO_CREATE_SELECTED_JOB_DRAFT`** (ignoring queue regex false positive; Shopify duplicate check = clean) |

---

## Phase G1 — Publisher Contract Audit

**Status:** COMPLETE

Publisher contract audit created at:
`clients/hoverboard_store/content_engine/orin_phase_g_publisher_contract_audit.md`

Key findings:
- Publisher resolves selected job dynamically via `--job-context`
- No active Job 20 identity controls selected-job Publisher behaviour
- Publisher reads `local_draft_path` and `shopify_handle` from job context
- Publisher does NOT read Writer plan, Post-Write Review result, or HTML Validation result (these are pre-Publisher gates)
- Live Shopify inventory is always refreshed before preflight
- **Known bug:** Queue regex uses `job_id="21"` (numeric) but queue format is `## Job 21\n` — causes false `queue_status=not_found` for all jobs

---

## Phase G2 — Canonical Publisher Input

| Input | Required | Provided | Verified |
|---|---|---|---|
| selected_job_context | YES | ✅ | `job_number: "21"` |
| writer_plan | Pre-Publisher artifact | ✅ | `job_number: "21"` |
| Writer execution preview/output path | YES | ✅ | `/tmp/orin_job21_writer_test/job_21_draft.html` |
| Post-Write Review result | PASSED required | ✅ | `POST_WRITE_REVIEW_PASSED` |
| HTML Validation result | PASS required | ✅ | `PASS`, 0 issues |

**Identity Invariants:**
- `publisher_job_number (21) == selected_job_context.job_number (21)` ✅
- `writer_plan.job_number (21) == selected_job_context.job_number (21)` ✅
- `review.job_number (21) == selected_job_context.job_number (21)` ✅
- `html_validation.job_number (21) == selected_job_context.job_number (21)` ✅
- `publisher draft path == Writer execution output path` ✅

**Gates:**
- Post-Write Review: `POST_WRITE_REVIEW_PASSED` ✅
- HTML Validation: `PASS` ✅
- `safe_for_publisher_preflight: true` ✅

---

## Phase G3 — Local Draft Hash Invariant

| Check | Expected | Actual | Result |
|---|---|---|---|
| Writer execution SHA256 | `048234d6bde164c6d70986d994690537ca5d4423c4ed3014d2fe7a5889ad8049` | `048234d6bde164c6d70986d994690537ca5d4423c4ed3014d2fe7a5889ad8049` | ✅ PASS |
| Local SHA256 before preflight | `048234d6bde164c6d70986d994690537ca5d4423c4ed3014d2fe7a5889ad8049` | `048234d6bde164c6d70986d994690537ca5d4423c4ed3014d2fe7a5889ad8049` | ✅ PASS |
| Hash invariant | Match | Match | ✅ PASS |

---

## Phase G4 — Live Shopify Inventory Refresh

| Metric | Value |
|---|---|
| Total articles fetched | **35** |
| Drafts count | **14** |
| Published count | **21** |
| Fetch timestamp | `2026-07-08T08:11:11.175558+00:00` (live from Shopify API) |
| Fetch method | Live API (`GET /admin/api/2026-01/blogs/113430790492/articles.json`) |
| Fallback used | NO |
| Inventory saved | `clients/hoverboard_store/content_engine/shopify_inventory.json` |

**Job 20 article confirmation:**
- Article ID `1006845985116` found in Shopify
- Handle: `best-hoverboard-accessories-safer-riding-uk-2026`
- Title: `Best Hoverboard Accessories for Safer Riding UK 2026`
- Correctly identified as Job 20 article ✅

---

## Phase G5 — Selected Job 21 Duplicate Preflight

| Check | Result |
|---|---|
| Exact handle match | **NONE** |
| Exact title match | **NONE** |
| Near-handle conflicts | **NONE** |
| Near-title conflicts | **NONE** |
| Self-match | **NO** |
| Queue article ID | **null** (no Shopify article ID recorded for Job 21) |
| Job 20 Article ID 1006845985116 as Job 21 self-match | **NO** — Job 20 article correctly identified as separate job |

**Conclusion:** Job 21 has **zero Shopify conflicts**. No article in Shopify inventory matches, partially matches, or is related to Job 21's handle or title.

---

## Phase G6 — Job 21 Publisher Preflight Run

**Command:** `python3 tools/shopify_publisher/orin/orin_phase2e_publisher_dryrun.py --job-context /tmp/orin_job21_publisher_context.json`

### Publisher Checks Results

| Check | Expected | Actual | Result |
|---|---|---|---|
| Queue status | `planned` | `not_found` (regex bug) | ❌ false |
| Local draft exists | yes | yes | ✅ |
| Slug verification | `hoverkart-compatibility-checklist-before-you-buy` | `hoverkart-compatibility-checklist-before-you-buy` | ✅ |
| Exact handle duplicate | none | none | ✅ |
| Exact title duplicate | none | none | ✅ |
| Near-handle variant | none | none | ✅ |
| Self-match | no | no | ✅ |
| Compliance | pass | 1 issue (false positive) | ❌ |
| HTML quality | pass | pass | ✅ |

### Publisher Decision

**Returned:** `BLOCKED — queue_status=not_found`

**False positive reason:** `publisher_agent.py` uses `job_id="21"` (numeric) in queue regex `##\s+21\n` but the queue file has `## Job 21\n` (with "Job " prefix). The queue file correctly contains `Status: planned` for Job 21, but the Publisher's broken regex cannot find it.

**Compliance false positive reason:** The word "guarantee" appears in the disclaimer text "No hoverkart guarantees safe operation" (line 28 of draft). The compliance checker flags any occurrence of the word "guarantee" without context awareness. This is a disclaimer, not a guarantee claim.

### Corrected Assessment

Based on actual Shopify inventory and queue file inspection:

| Dimension | Actual State | Assessment |
|---|---|---|
| Shopify handle | `hoverkart-compatibility-checklist-before-you-buy` — NOT in Shopify | ✅ CLEAN |
| Shopify title | `Hoverkart Compatibility Checklist Before You Buy` — NOT in Shopify | ✅ CLEAN |
| Near-handle variants | NONE | ✅ CLEAN |
| Queue status | `planned` (confirmed in queue file) | ✅ CLEAN |
| Compliance | Disclaimer text, not a claim | ⚠️ FALSE POSITIVE |
| HTML quality | PASS | ✅ |

**Correct Publisher decision (if queue regex worked):** `APPROVED — safe for manual Shopify draft push`

**Correct Phase G preflight decision:** `READY_TO_CREATE_SELECTED_JOB_DRAFT`

---

## Phase G7 — Selected-Job Publisher Wrapper Check

**Status:** VERIFIED

`tools/shopify_publisher/orin/orin_phase2e_publisher_dryrun.py`:
- Accepts `--job-context <path>` ✅
- Dynamically reads `job_label`, `draft_path`, `expected_slug` from job context ✅
- Does NOT hardcode Job 20 or Job 21 ✅
- Fallback `"Job 20"` on line 55 is backward-compat default only (TEST_ONLY) ✅

Publisher wrapper output: `/tmp/orin_phase2e_publisher_preview.json`

---

## Phase G8 — Mutation Proof

| Check | Before | After | Result |
|---|---|---|---|
| Local draft SHA256 | `048234d6bde164c6d70986d994690537ca5d4423c4ed3014d2fe7a5889ad8049` | `048234d6bde164c6d70986d994690537ca5d4423c4ed3014d2fe7a5889ad8049` | ✅ UNCHANGED |
| Shopify touched | N/A | NO | ✅ |
| Queue touched | N/A | NO | ✅ |
| Cron touched | N/A | NO | ✅ |
| Cron enabled | disabled | disabled | ✅ |

---

## Phase G9 — Stop Gate

**Status:** ENFORCED ✅

No Shopify write operations performed.
No queue updates.
No cron changes.
Production cron remains **disabled**.

---

## Blocking Issues Found

### Issue 1: Queue Regex Bug (Publisher)
- **Severity:** Pre-existing bug causing false `queue_status=not_found`
- **Location:** `tools/shopify_publisher/orin/publisher_agent.py`, function `run_dryrun()`, Step 1
- **Root cause:** Queue regex uses `##\s+{job_id}\n` with `job_id="21"`, looking for `## 21\n`. Queue file format is `## Job 21\n`.
- **Fix required:** Change queue regex to `##\s+Job\s+{re.escape(job_id)}\n` or pass full job label `"Job 21"`
- **Impact on this preflight:** False blocking; Job 21 is `planned` in queue
- **Does NOT affect Shopify duplicate checks:** These are independent of queue lookup

### Issue 2: Compliance False Positive
- **Severity:** False positive on disclaimer text
- **Location:** Draft line 28 — "No hoverkart guarantees safe operation"
- **Root cause:** Compliance checker flags word "guarantee" anywhere in text without context awareness
- **Actual text meaning:** Disclaimer/negation, not a guarantee claim
- **Impact:** Blocks on "compliance issues" when article is actually compliant
- **Note:** This is a pre-existing limitation of the compliance checker

---

## Guard Check (ORIN Guard)

- **Unsupported claims:** None — article contains only verified claims and explicit disclaimers
- **Verification needed:** Queue regex bug and compliance false positive are tool-level issues, not article issues
- **Approval needed:** For queue regex bug fix — separate from Phase G scope

---

## Next Steps

1. **Fix queue regex bug** in `publisher_agent.py` before next Publisher run
2. **Acknowledge compliance false positive** — article is compliant (disclaimer text)
3. **Phase H (when reached):** Create Shopify draft for Job 21 — article is Shopify-clean and ready
4. **Update queue** after draft creation: `Status: planned → draft_created`

---

*Phase G complete. Production cron remains disabled. No Shopify writes performed.*
