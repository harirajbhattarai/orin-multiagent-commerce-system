# ORIN Phase F — Selected-Job HTML Validation and Contract Audit

**Phase:** F — HTML Validation and Contract Audit
**Date:** 2026-07-07
**Run date for testing:** 2026-07-04
**Mode:** Read-only HTML validation
**Status:** ✅ PHASE F COMPLETE

---

## Phase F1 — HTML Contract Discovery

### Canonical HTML Contract

**File:** `clients/hoverboard_store/content_engine/html_blocks.md`
**Classification:** EXISTING_CANONICAL_HTML_CONTRACT_FOUND ✅

This file explicitly documents the Hoverboard Store HTML/CSS Blog Design System. It defines:
- Approved parent wrapper: `<div class="hs-article"><div class="hs-container">`
- All approved CSS classes
- Required article structure (SEO comment → hs-article → hs-container → H1 → meta → quick answer → intro → highlights → H2/H3 sections → notes → tables → pros/cons → product blocks → FAQ → related → CTA → authority)
- FAQ format: `div.hs-faq-q` + `div.hs-faq-a` (NOT h3/p)
- Authority block: `hs-authority`
- **hs-byline is NOT listed as an approved class**

### Canonical HTML Validator

**File:** `tools/shopify_publisher/html_quality_check.py`
**Classification:** EXISTING_CANONICAL_HOVERBOARD_STORE_VALIDATOR ✅

The `html_quality_check.py` is the canonical Hoverboard Store HTML validator. It checks:
- `hs-article` wrapper present
- `hs-container` wrapper present
- H1 present
- `hs-quick-answer` present
- No invalid `<di>` tags
- No empty `<p></p>` paragraphs
- No visible SEO metadata in article body
- No blocked author terms (TOXIC, AISEO, ChatGPT, OpenAI, ORIN Test)
- "By Hoverboard Store" in visible text (byline TEXT, not `hs-byline` element)
- Correct FAQ format: `div.hs-faq-q` + `div.hs-faq-a` (not h3/p)
- No manual FAQPage JSON-LD inside article

**Does NOT check for `hs-byline` — that element is not in the canonical contract.**

### hs-byline Investigation

| Question | Answer |
|----------|--------|
| Is `hs-byline` in `html_blocks.md` approved classes? | **No** ✅ |
| Is `hs-byline` in `html_quality_check.py` checks? | **No** ✅ |
| Is `hs-byline` in the canonical Job 20 draft? | **No** ✅ |
| Does `hs-authority` block exist in Job 20? | **Yes** ✅ (for author content) |
| Does Job 21 draft have "By Hoverboard Store" text? | **Yes** ✅ (in hs-meta section) |
| Does `html_quality_check.py` require hs-byline element? | **No** ✅ |
| Is Phase E's hs-byline check in the canonical contract? | **No** — false positive |

**Conclusion:** `hs-byline` is NOT a canonical Hoverboard Store HTML contract requirement. The Phase E review warning was a **false positive** — the review_agent.py added an `hs-byline` check without verifying it against the actual canonical contract (`html_blocks.md`). The canonical byline representation is "By Hoverboard Store" in visible text, which Job 21 has.

---

## Phase F2 — Validator Path Decision

**Decision:** Use existing canonical Hoverboard Store HTML validator (`html_quality_check.py`) ✅

Do NOT use `hcs_html_contract_validator.py` (HCS Gadgets-specific) ✅

---

## Phase F3 — Selected-Job HTML Validation

### Validation Results

**Draft:** `/tmp/orin_job21_writer_test/job_21_draft.html`
**Job:** 21 — Hoverkart Compatibility Checklist Before You Buy
**SHA256:** `048234d6bde164c6d70986d994690537ca5d4423c4ed3014d2fe7a5889ad8049`

| Check | Result |
|-------|--------|
| Canonical HTML validator | `html_quality_check.py` ✅ |
| Validator exit code | 0 ✅ |
| Validator issues | 0 ✅ |
| Validation status | **PASS** ✅ |
| Draft mutated | No ✅ |

### Canonical Contract Structure Checks

| Check | Result |
|-------|--------|
| `hs-article` wrapper | PASS ✅ |
| `hs-container` wrapper | PASS ✅ |
| H1 present | PASS ✅ |
| H1 text | Hoverkart Compatibility Checklist Before You Buy ✅ |
| `hs-meta` section | PASS ✅ |
| `hs-quick-answer` block | PASS ✅ |
| `hs-highlights` block | PASS ✅ |
| `hs-cta` block | PASS ✅ |
| Byline text "By Hoverboard Store" | PASS ✅ |
| FAQ count | 4 ✅ |
| FAQ correct format (div.hs-faq-q/div.hs-faq-a) | PASS ✅ |
| No old FAQ format (h3/p) | PASS ✅ |
| No manual FAQPage JSON-LD | PASS ✅ |
| No invalid `<di>` tags | PASS ✅ |
| No empty `<p></p>` | PASS ✅ |
| No visible SEO metadata in body | PASS ✅ |
| No blocked author terms | PASS ✅ |
| External hrefs | 3 (legitimate) |
| Broken/placeholder hrefs | 0 ✅ |

---

## Phase F4 — Byline Warning Decision

**Classification:** PHASE_E_FALSE_POSITIVE

The Phase E post-write review added a `hs-byline` structural check to `review_agent.py`. However:

1. `hs-byline` is **NOT** in the canonical Hoverboard Store HTML contract (`html_blocks.md`)
2. `html_quality_check.py` (the canonical validator) checks for byline **TEXT** ("By Hoverboard Store"), not an `hs-byline` element
3. The canonical validated Job 20 article does **NOT** use `hs-byline` — it uses `hs-authority` for author content
4. Job 21 draft has "By Hoverboard Store" in its meta section — satisfying the canonical byline text requirement
5. `html_quality_check.py` passes Job 21 with 0 issues

**Action:** No draft modification. Phase E's `hs-byline` warning is a false positive. The review agent should be updated in a future phase to remove the non-canonical `hs-byline` check — but that is outside the scope of Phase F.

---

## Phase F5 — Hash and Mutation Proof

| Check | Result |
|-------|--------|
| Draft SHA256 before validation | `048234d6bde164c6...` ✅ |
| Draft SHA256 after validation | `048234d6bde164c6...` ✅ |
| Draft mutated | **No** ✅ |
| Minimal byline fix applied | **No** ✅ |

Validation was read-only. No HTML modification occurred.

---

## Phase F6 — Production Validation Wrapper

**Created:** `tools/shopify_publisher/orin/orin_phase2f_html_validation_dryrun.py`

Features:
- Reads canonical selected-job context, writer plan, Writer execution preview
- Derives draft path from Writer execution preview (not hardcoded)
- Enforces `BLOCK_JOB_CONTEXT_MISMATCH` invariant
- Invokes `html_quality_check.py` (canonical Hoverboard Store validator)
- Runs structural inspection against canonical contract
- Writes structured validation preview to `/tmp/orin_selected_job_html_validation.json`
- Read-only — no production writes

---

## Phase F7 — Old/Job 20 Leakage Check

| Check | Result |
|-------|--------|
| Job 20 in Phase 2F validation path | 0 ✅ |
| `best-hoverboard-accessories-safer-riding` in Phase 2F | 0 ✅ |
| HCS classes in Job 21 draft | 0 ✅ |
| HCS validator used | No ✅ |

---

## Proof — 39 Items

| # | Item | Result |
|---|------|--------|
| 1 | Production cron enabled | No ✅ |
| 2 | HTML contract discovery path | `clients/hoverboard_store/content_engine/html_blocks.md` |
| 3 | HTML contract classification | EXISTING_CANONICAL_HTML_CONTRACT_FOUND ✅ |
| 4 | Canonical Hoverboard Store contract path | `clients/hoverboard_store/content_engine/html_blocks.md` |
| 5 | Canonical validator exists | Yes ✅ |
| 6 | Validator path | `tools/shopify_publisher/html_quality_check.py` |
| 7 | Validator version | Canonical Hoverboard Store HTML validator |
| 8 | Approved parent article wrapper | `<div class="hs-article"><div class="hs-container">` ✅ |
| 9 | Approved byline structure | "By Hoverboard Store" in visible text (not `hs-byline` element) ✅ |
| 10 | hs-byline mandatory | **No** ✅ (not in canonical contract) |
| 11 | Phase E byline warning classification | PHASE_E_FALSE_POSITIVE ✅ |
| 12 | Selected test job | 21 ✅ |
| 13 | Validator active job | 21 ✅ |
| 14 | Writer plan job | 21 ✅ |
| 15 | Validated draft path | `/tmp/orin_job21_writer_test/job_21_draft.html` ✅ |
| 16 | Draft SHA256 before validation | `048234d6bde164c6...` ✅ |
| 17 | Draft SHA256 after validation | `048234d6bde164c6...` ✅ |
| 18 | Validator mutated draft | No ✅ |
| 19 | Minimal byline fix applied | No ✅ (not needed) |
| 20 | Corrected SHA256 | N/A |
| 21 | Post-Write Review rerun | Not needed — Phase E decision stands |
| 22 | Validator result | PASS ✅ |
| 23 | Total validator checks | 12 (html_quality_check.py) + structural inspection |
| 24 | Passed checks | All ✅ |
| 25 | Failed checks | 0 ✅ |
| 26 | Warning count | 0 ✅ |
| 27 | Exact failures | None ✅ |
| 28 | Exact warnings | None ✅ |
| 29 | safe_for_publisher_preflight | **True** ✅ |
| 30 | Selected-job validation wrapper | `tools/shopify_publisher/orin/orin_phase2f_html_validation_dryrun.py` ✅ |
| 31 | Job 20 active validation leakage count | 0 ✅ |
| 32 | HCS class usage count | 0 ✅ |
| 33 | HCS validator used | No ✅ |
| 34 | Shopify touched | No ✅ |
| 35 | Queue touched | No ✅ |
| 36 | Cron touched during Phase F | No ✅ |
| 37 | Cron enabled at end | No ✅ |
| 38 | Report path | `clients/hoverboard_store/content_engine/orin_phase_f_selected_job_html_validation.md` |
| 39 | Final Phase F decision | **PHASE_F_COMPLETE — HTML validation passed, 0 failures, 0 warnings, safe_for_publisher_preflight=true, Phase E false-positive byline warning documented** |

---

## Files Created in Phase F

| File | Change |
|------|--------|
| `tools/shopify_publisher/orin/orin_phase2f_html_validation_dryrun.py` | Created — distinct selected-job HTML validation wrapper |

---

## Production Safety

| Check | Result |
|-------|--------|
| Shopify articles touched | No ✅ |
| Queue file edited | No ✅ |
| Live drafts folder edited | No ✅ |
| Production cron re-enabled | No ✅ |
| Draft mutated | No ✅ |

---

## Stop Gate — Phase F Halt

Phase G (Publisher Preflight), Phase H (Live-Draft Gate), Phase I (Queue Finalisation), Phase J (Full Regression), Phase K (Cron Re-enable) — **NOT STARTED** ✅

---

*Report generated by ORIN Phase F — Selected-Job HTML Validation and Contract Audit — no production files modified.*
