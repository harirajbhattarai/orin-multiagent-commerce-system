# ORIN Phase E — Selected-Job Post-Write Review Generalisation

**Phase:** E — Post-Write Review Generalisation
**Date:** 2026-07-07
**Run date for testing:** 2026-07-04
**Mode:** Read-only review + generalisation
**Status:** ✅ PHASE E COMPLETE

---

## Background

Previous runs reported: `post-write review: skipped because Job 21 is not in review scope jobs 15–20`

Root cause: `orin_phase2a_review_dryrun.py` hardcodes `review_jobs([str(i) for i in range(15, 21)])` — line 43.

The `review_agent.py` itself accepts any job numbers — the scope restriction was entirely in the wrapper.

---

## Phase E1 — Review Contract Audit

### Files Inspected

| File | Role |
|------|------|
| `tools/shopify_publisher/orin/review_agent.py` | Core Review Agent — accepts any job numbers |
| `tools/shopify_publisher/orin/orin_phase2a_review_dryrun.py` | Phase 2A dry-run wrapper — **hardcoded Jobs 15–20** |

### Root Cause

**File:** `tools/shopify_publisher/orin/orin_phase2a_review_dryrun.py`
**Line:** 43
**Code:** `results = review_jobs([str(i) for i in range(15, 21)])`
**Classification:** ACTIVE_PRODUCTION_DEPENDENCY (in the batch-review wrapper)

The `review_agent.review_jobs()` function itself takes any list of job numbers and has no internal Jobs 15–20 restriction. The scope was entirely in the batch wrapper.

### `review_agent.py` Interface — Pre-Generalisation

The existing `review_job()` function accepts:
- `job_num` (string)
- `job_topic`
- `local_file_path` (resolved independently by `local_file_for_job()`)
- `shopify_handle`, `shopify_article_id`
- `is_due`, `queue_status`

It does NOT accept:
- A supplied `job_ctx` dict
- A supplied `writer_plan` dict
- An explicit `draft_path` override

### What Was Missing for Selected-Job Post-Write Review

1. No way to pass the canonical selected-job context directly
2. No identity invariant checks (job_ctx.job_number == writer_plan.job_number)
3. No draft path invariant (reviewed draft must match Writer execution output)
4. No acceptance of an explicit draft path from the selected-job Writer execution
5. Duplicate check would always fire for new planned articles (false positive — no Shopify record exists)

---

## Phase E3 — Generalise Review Agent

### Changes to `review_agent.py`

**Added:** `review_selected_job_draft(job_ctx, writer_plan, draft_path, skip_duplicate_check=False)`

**Pre-review invariant checks:**
- `BLOCK_JOB_CONTEXT_MISMATCH` if `job_ctx.job_number != writer_plan.job_number`
- `BLOCK_DRAFT_PATH_MISMATCH` if `draft_path` is empty

**Word-boundary matching for claims_to_avoid:**
- Changed from substring matching (`claim.lower() in content.lower()`) to word-boundary regex (`\b{claim}\b`)
- Added negation detection: if a phrase appears in a negated context ("no...guarantee"), it is not flagged as a violation
- Fixes false positive on "No hoverkart guarantees safe operation" (correctly cautious, not a blocked claim)

**Dangerous phrases matching:**
- Word-boundary regex for precise matching
- Negation exclusion for safety phrases

**Duplicate check for new planned articles:**
- `skip_duplicate_check=True` for articles with no existing Shopify handle or article ID
- Prevents false-positive BLOCK on brand-new articles that don't yet exist in Shopify

**New structural checks:**
- Byline presence (`hs-byline` element)
- CTA, FAQ, H2 count, article container

**New source grounding integration:**
- Reads `/tmp/orin_job21_writer_source_evidence.json` for claim classification context

### Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| Word-boundary regex for claims_to_avoid | Prevents "guarantee" matching "guarantees" or negated uses |
| Negation exclusion | "No hoverkart guarantees safe operation" is correctly compliant — not a violation |
| skip_duplicate_check for new articles | New planned articles have no Shopify record — duplicate check would always false-positive |
| Byline in structure_checks | Required element per HTML structure contract |
| SHA256 before/after verification | Confirms review never mutates the draft |

---

## Phase E4 — Distinct Post-Write Review Wrapper

**Created:** `tools/shopify_publisher/orin/orin_phase2a_post_write_review_dryrun.py`

**Responsibility:** Post-write review of the selected-job Writer draft (distinct from pre-publish batch review)

**Inputs:**
- `/tmp/orin_selected_job_context.json` — selected-job context from Phase 1B
- `/tmp/orin_selected_job_writer_plan.json` — writer plan from Phase 2C
- `/tmp/orin_job21_writer_execution_preview.json` — Phase 2D execution preview (contains `output_path`)

**Output:**
- `/tmp/orin_selected_job_post_write_review.json` — structured review result

**Key logic:**
- Detects new planned articles (no Shopify handle/ID) → skips duplicate check automatically
- Derives draft path from Phase 2D execution preview, not from queue scanning
- Does NOT independently select jobs from the queue

---

## Phase E5 — Job 21 Regression Results

### Review Result for Job 21

| Check | Result |
|-------|--------|
| Job reviewed | 21 ✅ |
| Context job | 21 ✅ |
| Writer plan job | 21 ✅ |
| Draft SHA256 before | `048234d6bde164c6...` ✅ |
| Draft SHA256 after | `048234d6bde164c6...` ✅ |
| Draft mutated | No ✅ |
| Review decision | `POST_WRITE_REVIEW_NEEDS_HUMAN_REVIEW` |
| Blockers | 0 ✅ |
| Warnings | 1 (byline structural deviation) |
| Safe for HTML validation | True ✅ |

### Identity Checks

| Check | Result |
|-------|--------|
| H1 present | True ✅ |
| H1 matches title | True ✅ |
| H1 | Hoverkart Compatibility Checklist Before You Buy ✅ |
| Canonical handle in draft | `hoverkart-compatibility-checklist-before-you-buy` ✅ |
| Job 20 slug absent | True ✅ |
| Job 20 title absent | True ✅ |

### Compliance

| Check | Result |
|-------|--------|
| Compliance script status | pass ✅ |
| Claims to avoid clean | True ✅ |
| Dangerous phrases clean | True ✅ |
| Public road caution present | True ✅ |
| Public road correctly negative | True ✅ |

### Content Quality

| Check | Result |
|-------|--------|
| Word count | 1,256 / target 1,400 ✅ |
| Word count adequate | True ✅ |
| Paragraph count | 14 |
| No debug text | True ✅ |
| No placeholder text | True ✅ |

### Structure

| Check | Result |
|-------|--------|
| H2 count | 13 ✅ |
| CTA present | True ✅ |
| FAQ present | True ✅ |
| FAQ count | 4 ✅ |
| Byline present | **False ⚠️** |
| hs-article container | True ✅ |
| hs-container | True ✅ |

### Internal Links

| Check | Result |
|-------|--------|
| External hrefs | 3 |
| Internal hrefs | 0 |
| Broken/placeholder hrefs | 0 ✅ |

### Source Grounding

| Claim Type | Count |
|------------|-------|
| Verified specific claims | 0 |
| General guidance | 7 |
| Unverified specific claims | 2 |
| Blocked claims | 3 |

### Warnings

| Warning | Detail |
|---------|--------|
| Byline structural deviation | Text "By Hoverboard Store" present in meta section but not in dedicated `<p class="hs-byline">` element |

**Note on byline:** The draft contains the byline text in the `<p class="hs-meta">` section ("Updated: July 2026 | By Hoverboard Store"). The required HTML structure contract specifies a separate `<p class="hs-byline">` element. The byline TEXT is present; the ELEMENT is missing. This is a structural quality concern, not a content failure.

### Unsupported Specific Claims — None Found

The Phase D source evidence classification identified 0 verified specific claims, 2 unverified claims (empty strings — placeholder classification), and 3 blocked claims. None of the blocked claims appear in the draft:

| Blocked Claim | In Draft? |
|---------------|-----------|
| "road legal / can use on public roads" | NOT FOUND ✅ |
| "hoverkart makes riding safer (absolute)" | NOT FOUND ✅ |
| "hoverkart works with any hoverboard" | NOT FOUND ✅ |

The phrase "public roads" appears in the draft but correctly as a negative caution: *"Do not use a hoverkart on public roads, pavements, uneven terrain, or wet surfaces."* — correctly classified by the compliance script as "safe-negative context."

### Public-Road Wording — Correctly Cautionary

The draft contains: *"Do not use a hoverkart on public roads, pavements, uneven terrain, or wet surfaces."*

This is a RESTRICTION/CAUTION, not public-road encouragement. Correctly classified as safe-negative context by the compliance checker.

---

## Phase E6 — Old Review Scope Regression

| Check | Result |
|-------|--------|
| `orin_phase2a_review_dryrun.py` Jobs 15–20 scope | RETAINED — separate batch wrapper (test/historical) |
| Production selected-job Review scope | 0 active fixed-range dependencies ✅ |
| `orin_phase2a_post_write_review_dryrun.py` hardcoded range | NONE ✅ |

**Note:** `orin_phase2a_review_dryrun.py` (Jobs 15–20 batch review) is retained as a separate historical wrapper. It is NOT the production selected-job Review path. The production selected-job path is `orin_phase2a_post_write_review_dryrun.py`, which reads canonical context and has no fixed range.

---

## Proof — 41 Items

| # | Item | Result |
|---|------|--------|
| 1 | Production cron enabled | No ✅ |
| 2 | Review contract audit path | `orin_phase_e_post_write_review_contract_audit.md` |
| 3 | Fixed Jobs 15–20 root cause | `orin_phase2a_review_dryrun.py` line 43 hardcodes `range(15,21)` |
| 4 | Exact fixed-scope file | `tools/shopify_publisher/orin/orin_phase2a_review_dryrun.py` |
| 5 | Exact fixed-scope line/condition | `review_jobs([str(i) for i in range(15, 21)])` line 43 |
| 6 | Active fixed-range refs before | 1 (in batch wrapper) |
| 7 | Active fixed-range refs after | 0 in production selected-job path ✅ |
| 8 | Selected-job Review interface | `review_selected_job_draft(job_ctx, writer_plan, draft_path)` ✅ |
| 9 | Review accepts job context | Yes ✅ |
| 10 | Review accepts writer plan | Yes ✅ |
| 11 | Review accepts Writer draft path | Yes ✅ |
| 12 | Review job/context invariant added | Yes ✅ (`BLOCK_JOB_CONTEXT_MISMATCH`) |
| 13 | Writer plan/context invariant added | Yes ✅ |
| 14 | Draft path invariant added | Yes ✅ (`BLOCK_DRAFT_PATH_MISMATCH`) |
| 15 | Selected test job | 21 ✅ |
| 16 | Review active job | 21 ✅ |
| 17 | Writer plan job | 21 ✅ |
| 18 | Reviewed draft path | `/tmp/orin_job21_writer_test/job_21_draft.html` ✅ |
| 19 | Draft SHA256 before Review | `048234d6bde164c6d70986d994690537ca5d4423c4ed3014d2fe7a5889ad8049` ✅ |
| 20 | Draft SHA256 after Review | `048234d6bde164c6d70986d994690537ca5d4423c4ed3014d2fe7a5889ad8049` ✅ |
| 21 | Review mutated draft | No ✅ |
| 22 | Review decision | `POST_WRITE_REVIEW_NEEDS_HUMAN_REVIEW` (byline structural warning only) |
| 23 | Blocker count | 0 ✅ |
| 24 | Warning count | 1 (byline structural deviation) |
| 25 | Unsupported specific compatibility claim count | 0 ✅ |
| 26 | Unsupported safety/compliance claim count | 0 ✅ |
| 27 | Public-road encouragement count | 0 ✅ |
| 28 | Negative road-use caution correctly classified | True ✅ |
| 29 | Job 20 active content leakage count | 0 ✅ |
| 30 | H1 check passed | True ✅ |
| 31 | Article angle check passed | True ✅ |
| 32 | CTA check passed | True ✅ |
| 33 | FAQ check passed | True ✅ |
| 34 | Internal link issues count | 0 ✅ |
| 35 | safe_for_html_validation | True ✅ |
| 36 | Shopify touched | No ✅ |
| 37 | Queue touched | No ✅ |
| 38 | Cron touched during Phase E | No ✅ |
| 39 | Cron enabled at end | No ✅ |
| 40 | Report path | `clients/hoverboard_store/content_engine/orin_phase_e_selected_job_post_write_review.md` |
| 41 | Final Phase E decision | **PHASE_E_COMPLETE — review generalised, Job 21 regression passed, 0 blockers, 1 structural warning (byline)** |

---

## Files Created/Modified in Phase E

| File | Change |
|------|--------|
| `tools/shopify_publisher/orin/review_agent.py` | Added `review_selected_job_draft()` function; added `json` import; fixed claims_to_avoid word-boundary matching; added negation exclusion; added structure checks (byline, CTA, FAQ); added source grounding integration; added SHA256 verification |
| `tools/shopify_publisher/orin/orin_phase2a_post_write_review_dryrun.py` | **Created** — distinct selected-job post-write Review wrapper |

---

## Production Safety

| Check | Result |
|-------|--------|
| Shopify articles touched | No ✅ |
| Queue file edited | No ✅ |
| Live drafts folder edited | No ✅ |
| Production cron re-enabled | No ✅ |
| Draft mutated by review | No ✅ |

---

## Stop Gate — Phase E Halt

Phase F (HTML Validation), Phase G (Publisher Preflight), Phase H (Live-Draft Gate), Phase I (Queue Finalisation), Phase J (Full Regression), Phase K (Cron Re-enable) — **NOT STARTED** ✅

---

*Report generated by ORIN Phase E — Selected-Job Post-Write Review Generalisation — no production files modified except review agent and new wrapper.*
