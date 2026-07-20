# HCS Gadgets — Five-Gate Claim Test

**Version:** 1.0
**Date:** 2026-07-04
**Phase:** Product Intelligence Phase 0 — PHASE G
**Status:** APPROVED — Every article claim must pass this test before entering the Article Claim Allowlist

---

## Purpose

The Five-Gate Claim Test is the final filter before any claim enters the Article Claim Allowlist. It applies to every factual claim a writer intends to include in an HCS Gadgets article.

A claim must pass **all applicable gates** before it is approved.

---

## The Five Gates

---

### Gate 1 — Truth Gate

**Question:** Is the claim supported by evidence?

A claim passes the Truth Gate if:
- It is traceable to a named source (Shopify product description, verified specification, structured field)
- It is confirmed by at least one source (never from inference or assumption)
- The source does not contradict itself

**Evidence requirements by claim type:**

| Claim Type | Minimum Evidence |
|-----------|-----------------|
| Dimension, weight, capacity | Must be explicitly stated in source |
| Material composition | Must be explicitly stated |
| Included items | Must be explicitly stated in description or listing |
| Battery capacity | Must be stated in mAh or Wh |
| Speed/range | Must be stated numerically |
| Certifications | Must include named standard (e.g., `BS EN 14682`) |
| Marketing superlatives | Not sufficient evidence for factual claims |

**FAIL indicators:**
- The claim is based on an inference or assumption
- The claim cannot be traced to any source
- The source is a marketing phrase without supporting data
- The writer is filling a gap with "likely" or "probably"

**Result:** `PASS_TTruth` or `FAIL` → claim excluded from allowlist

---

### Gate 2 — Exposure Gate

**Question:** Is the claim appropriate for customer-facing content?

A claim passes the Exposure Gate if:
- It is appropriate for public/customer-facing content
- It does not expose internal operational data
- It does not expose Shopify IDs, SKUs, or stock data
- It does not expose commercial pricing (unless explicitly approved for price-led content)

**FAIL indicators:**
- The claim uses an internal-only field (SKU, inventory count, product ID)
- The claim exposes real-time stock or commercial pricing in non-price-led content
- The claim reveals internal workflow or operational information
- The claim could mislead customers about HCS operations

**Result:** `PASS_Exposure` or `FAIL` → claim excluded from allowlist

---

### Gate 3 — Stability Gate

**Question:** Is the claim sufficiently stable for the article type?

Match the claim's stability to the article's permanence:

| Article Type | Permitted Stability |
|-------------|-------------------|
| Evergreen buying guide | `stable` only |
| Product comparison | `stable` only |
| How-to / usage guide | `stable` and `medium` |
| News / announcement | Any including volatile |
| Sale / offer content | Any including volatile |

**Stability classifications:**
- `stable` — will not change without product redesign (dimensions, material, capacity)
- `volatile` — may change without notice (price, stock, offers, included accessories)

**FAIL indicators:**
- Using a volatile claim (price, stock) in an evergreen article
- Using a `medium` confidence claim in an evergreen buying guide without flagging it
- Claim is a current offer that will expire

**Result:** `PASS_Stability` or `FAIL` → claim excluded from allowlist for this article type

---

### Gate 4 — Relevance Gate

**Question:** Does this fact directly help the reader for this article topic?

A claim passes the Relevance Gate if:
- It is directly related to the article's stated topic
- It helps a reader make an informed decision or understand a product
- It is not tangential or redundant padding

**FAIL indicators:**
- The claim is technically true but irrelevant to the article topic
- The claim is included to fill word count rather than serve the reader
- The claim does not answer any question the article raises
- The claim duplicates another already in the allowlist

**Result:** `PASS_Relevance` or `FAIL` → claim excluded from allowlist

---

### Gate 5 — Compliance Gate

**Question:** Does the claim require stronger evidence or human review?

A claim passes the Compliance Gate if it does not carry regulatory or liability risk, OR if it has received human review approval.

**Claims requiring human review before Gate 5 approval:**
- Safety certifications: `UK certified`, `BS EN`, `road legal`, `fireproof`, `waterproof`
- Compliance claims: `CE marked`, `child-safe`, `non-toxic`, `flame-retardant`
- Performance claims without numeric backing: `safe for all ages`, `suitable for beginners to experts`
- Medical/wellness claims: any claim about health benefits, injury prevention, therapeutic effect

**FAIL indicators:**
- Claim is a safety or compliance assertion without a named standard
- Claim could expose HCS to liability if incorrect
- Claim has not received human sign-off

**Result:** `PASS_Compliance` or `FAIL_REVIEW_REQUIRED` → claim flagged for human review

---

## Five-Gate Decision Matrix

| Truth | Exposure | Stability | Relevance | Compliance | Final Decision |
|-------|----------|-----------|-----------|------------|----------------|
| PASS | PASS | PASS | PASS | PASS | **APPROVED** → Add to Article Claim Allowlist |
| PASS | PASS | PASS | PASS | FAIL_REVIEW | **CONDITIONAL** → Add to allowlist with compliance note |
| Any FAIL | — | — | — | — | **REJECTED** → Do not add to allowlist |

---

## Applying the Five Gates — Worked Example

**Claim:** "The H1 BBQ reaches cooking temperature in 20–30 minutes"

**Gate 1 — Truth:**
- Source: Product description says "depending on charcoal amount and conditions, the coals are typically ready in 20 to 30 minutes"
- Assessment: Explicitly stated in product description
- Result: **PASS_TTruth**

**Gate 2 — Exposure:**
- Customer-facing fact about cooking performance
- No internal IDs, stock data, or pricing exposed
- Result: **PASS_Exposure**

**Gate 3 — Stability:**
- This is an article about the H1 BBQ — an evergreen buying guide
- The claim is about a product characteristic (lighting time) which is stable
- Result: **PASS_Stability**

**Gate 4 — Relevance:**
- Article topic is "portable BBQ guide"
- Claim directly answers "how long to light" — a key reader question
- Result: **PASS_Relevance**

**Gate 5 — Compliance:**
- No safety, certification, or compliance claim involved
- Result: **PASS_Compliance**

**Final: APPROVED** → Enter Article Claim Allowlist

---

**Counter-example:** "200 units in stock at HCS Gadgets"

**Gate 1 — Truth:** PASS — confirmed by inventory data
**Gate 2 — Exposure:** FAIL — stock count is internal operational data
**Final: REJECTED** → Never add to allowlist

---

## Using This Document

The Five-Gate Claim Test must be applied:
1. By ORIN when building Article-Specific Product Briefs
2. By the writer before adding any claim to an article
3. By ORIN Guard when reviewing article outputs

Reference: `product_claim_extraction_rules.md` for claim classification guidance.
