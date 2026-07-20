# ORIN Phase F.1 — Post-Write Review Canonical HTML Contract Alignment

**Phase:** F.1 — Post-Write Review Canonical HTML Contract Alignment
**Date:** 2026-07-07
**Run date for testing:** 2026-07-04
**Mode:** Read-only review + contract alignment
**Status:** ✅ PHASE F.1 COMPLETE

---

## Background

Phase F discovered that the Post-Write Review Agent (Phase E) introduced a stale non-canonical `hs-byline` HTML element requirement. The canonical Hoverboard Store HTML contract (`html_blocks.md`) and canonical validator (`html_quality_check.py`) both confirm: the only byline requirement is visible text "By Hoverboard Store" — not a `hs-byline` HTML element.

This caused the Job 21 Review decision to be `POST_WRITE_REVIEW_NEEDS_HUMAN_REVIEW` with a false-positive warning.

---

## Phase A — Stale Byline Rule Root Cause

### Evidence from Canonical Contract Sources

**`clients/hoverboard_store/content_engine/html_blocks.md`** (canonical HTML contract):
- Lists `hs-authority` as an approved class (line 33) — not `hs-byline`
- No mention of `hs-byline` anywhere in the contract
- Authority block (`hs-authority`) is the defined author content block

**`tools/shopify_publisher/html_quality_check.py`** (canonical HTML validator):
- Line 76–77: Checks for visible text `"By Hoverboard Store"` in article body
- No check for `hs-byline` HTML element

### Phase E Introduction

The stale `hs-byline` requirement was introduced during Phase E when `review_agent.py` was extended with structural checks. The reviewer added a check for `<p class="hs-byline">` without verifying it against the actual canonical contract (`html_blocks.md`) or the canonical validator (`html_quality_check.py`).

This is a **CANONICAL_CONTRACT_MISMATCH** — the Phase E review invented a CSS-class requirement that does not exist in the canonical HTML contract.

### Root Cause Summary

| Item | Detail |
|------|--------|
| **File** | `tools/shopify_publisher/orin/review_agent.py` |
| **Lines** | 779–780 (byline_match check), 885–886 (warning) |
| **Stale rule** | Check for `<p class="hs-byline">` HTML element |
| **Classification** | STALE_REVIEW_RULE / CANONICAL_CONTRACT_MISMATCH |
| **Introduced** | Phase E (not from Job 20 or any canonical source) |
| **Canonical contract** | Requires visible text "By Hoverboard Store" only |

---

## Phase B — Review Agent Alignment

### Changes Made

**File:** `tools/shopify_publisher/orin/review_agent.py`

**Removed:**
```python
byline_match = re.search(r'class="[^"]*hs-byline[^"]*"', content, re.IGNORECASE)
structure["byline_present"] = bool(byline_match)
```

```python
if not byline_match:
    post_write_warnings.append("structure: byline element (<p class=\"hs-byline\">) not found...")
```

**Replaced with:**
```python
# Canonical Hoverboard Store byline requirement (from html_quality_check.py):
# Visible article text must contain "By Hoverboard Store".
# This is the ONLY canonical byline requirement.
# hs-byline is NOT in the canonical HTML contract (html_blocks.md).
# HTML class/markup byline checks belong to the Canonical HTML Validator, not Review.
visible_for_byline = re.sub(r"<[^>]+>", " ", content)
visible_for_byline = re.sub(r"\s+", " ", visible_for_byline).strip()
structure["canonical_byline_text_present"] = "By Hoverboard Store" in visible_for_byline
```

```python
if not structure["canonical_byline_text_present"]:
    post_write_warnings.append(
        "byline: canonical Hoverboard Store visible text 'By Hoverboard Store' not found in article"
    )
```

**Wrapper update:** `orin_phase2a_post_write_review_dryrun.py` — updated print to use new key name.

### Review/Validator Ownership Boundary — Documented

| Responsibility | Owner |
|---------------|--------|
| Article identity (H1, title, handle) | Post-Write Review |
| Content quality (word count, no placeholders) | Post-Write Review |
| Compliance (claims_to_avoid, dangerous phrases) | Post-Write Review |
| Source grounding (verified/unverified claims) | Post-Write Review |
| Article angle consistency | Post-Write Review |
| Structural completeness (H2s, FAQ, CTA) | Post-Write Review |
| Exact HTML class/markup requirements | Canonical HTML Validator (`html_quality_check.py`) |
| Approved CSS class enforcement | Canonical HTML Validator |
| Canonical HTML structure | Canonical HTML Validator |
| Byline text requirement | Canonical HTML Validator (visible text check) |

Post-Write Review must NOT invent CSS-class requirements that do not exist in the canonical HTML contract.

---

## Phase C — Job 21 Review Rerun

### Results

| Check | Before (Phase E) | After (Phase F.1) |
|-------|-----------------|-------------------|
| **Decision** | `POST_WRITE_REVIEW_NEEDS_HUMAN_REVIEW` | **`POST_WRITE_REVIEW_PASSED`** ✅ |
| **Blockers** | 0 | 0 ✅ |
| **Warnings** | 1 (hs-byline false positive) | **0** ✅ |
| **Byline check** | hs-byline HTML element | Canonical visible text ✅ |
| **Draft SHA256 before** | `048234d6...` | `048234d6...` ✅ |
| **Draft SHA256 after** | `048234d6...` | `048234d6...` ✅ |
| **Draft mutated** | No | No ✅ |

### Identity Checks — All Pass

| Check | Result |
|-------|--------|
| H1 present | True ✅ |
| H1 match | True ✅ |
| Canonical handle in draft | True ✅ |
| Job 20 slug absent | True ✅ |
| Job 20 title absent | True ✅ |

### Compliance — All Pass

| Check | Result |
|-------|--------|
| Compliance script status | pass ✅ |
| Claims to avoid clean | True ✅ |
| Dangerous phrases clean | True ✅ |
| Public road caution | True ✅ |
| Public road correctly negative | True ✅ |

---

## Phase D — HTML Validation Regression

| Check | Result |
|-------|--------|
| HTML validator | `html_quality_check.py` (canonical) ✅ |
| HCS validator used | No ✅ |
| Exit code | 0 ✅ |
| Issues | 0 ✅ |
| Validation status | PASS ✅ |
| Draft SHA256 unchanged | `048234d6...` ✅ |
| **safe_for_publisher_preflight** | **True** ✅ |

### Gate Agreement

| Gate | Result |
|------|--------|
| Post-Write Review decision | `POST_WRITE_REVIEW_PASSED` ✅ |
| HTML Validation result | PASS ✅ |
| **Gates agree** | **Yes** ✅ |

---

## Phase E — Review Rule Regression

| Check | Result |
|-------|--------|
| Active `hs-byline` requirement in Review | **0** ✅ (only documentation comment explaining why it was removed) |
| HCS class references in selected-job Review | **0** ✅ |
| Review/Validator ownership boundary | **Documented** ✅ |

---

## Proof — 39 Items

| # | Item | Result |
|---|------|--------|
| 1 | Production cron enabled | No ✅ |
| 2 | Stale byline rule root cause | Phase E introduced hs-byline check without verifying against canonical contract |
| 3 | Exact stale rule file | `tools/shopify_publisher/orin/review_agent.py` |
| 4 | Exact stale rule line/check | Lines 779–780, 885–886 — `<p class="hs-byline">` element check |
| 5 | Phase E warning classification | CANONICAL_CONTRACT_MISMATCH / STALE_REVIEW_RULE ✅ |
| 6 | Canonical HTML contract path | `clients/hoverboard_store/content_engine/html_blocks.md` |
| 7 | Canonical validator path | `tools/shopify_publisher/html_quality_check.py` |
| 8 | Canonical byline requirement | Visible article text "By Hoverboard Store" ✅ |
| 9 | hs-byline canonical requirement | **No** ✅ |
| 10 | Review Agent hs-byline requirement removed | Yes ✅ |
| 11 | Review/Validator ownership boundary documented | Yes ✅ |
| 12 | Selected test job | 21 ✅ |
| 13 | Review active job | 21 ✅ |
| 14 | Writer plan job | 21 ✅ |
| 15 | Reviewed draft path | `/tmp/orin_job21_writer_test/job_21_draft.html` ✅ |
| 16 | Draft SHA256 before Review | `048234d6bde164c6...` ✅ |
| 17 | Draft SHA256 after Review | `048234d6bde164c6...` ✅ |
| 18 | Review mutated draft | No ✅ |
| 19 | New Review decision | `POST_WRITE_REVIEW_PASSED` ✅ |
| 20 | Blocker count | 0 ✅ |
| 21 | Warning count | 0 ✅ |
| 22 | Canonical byline check passed | True ✅ |
| 23 | Unsupported specific compatibility claims count | 0 ✅ |
| 24 | Unsupported safety/compliance claims count | 0 ✅ |
| 25 | Public-road encouragement count | 0 ✅ |
| 26 | Negative road-use caution correctly classified | True ✅ |
| 27 | Job 20 active content leakage count | 0 ✅ |
| 28 | safe_for_html_validation | True ✅ |
| 29 | HTML validation rerun result | PASS ✅ |
| 30 | HTML validation issues count | 0 ✅ |
| 31 | Review and HTML gates agree | Yes ✅ |
| 32 | Active hs-byline requirement references remaining | 0 ✅ |
| 33 | Active HCS class references in selected-job Review | 0 ✅ |
| 34 | Shopify touched | No ✅ |
| 35 | Queue touched | No ✅ |
| 36 | Cron touched during Phase F.1 | No ✅ |
| 37 | Cron enabled at end | No ✅ |
| 38 | Report path | `clients/hoverboard_store/content_engine/orin_phase_f1_review_html_contract_alignment.md` |
| 39 | Final Phase F.1 decision | **PHASE_F1_COMPLETE — Review/HTML gates both agree PASS, 0 blockers, 0 warnings, canonical byline contract enforced** |

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

## Stop Gate — Phase F.1 Halt

Phase G (Publisher Preflight), Phase H (Live-Draft Gate), Phase I (Queue Finalisation), Phase J (Full Regression), Phase K (Cron Re-enable) — **NOT STARTED** ✅

---

*Report generated by ORIN Phase F.1 — Post-Write Review Canonical HTML Contract Alignment — no production files modified except review_agent.py alignment fix.*
