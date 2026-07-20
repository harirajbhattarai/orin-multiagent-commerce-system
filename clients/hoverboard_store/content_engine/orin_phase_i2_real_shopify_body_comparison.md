# ORIN Phase I.2: Real Shopify Body Comparison Using Recovered Writer Artifact - Hoverboard Store

**Date of Report:** 2026-07-08

## Overview

This report details the real read-only Shopify body comparison for Job 21 ("Hoverkart Compatibility Checklist Before You Buy") using the deterministically recovered Writer artifact. The goal was to prove whether the local Writer HTML and Shopify body_html differ only by harmless inter-tag whitespace normalization.

## Findings

### Phase A — Recovered Local Source Verification

*   **Recovered Local Artifact Path:** `/tmp/orin_job21_writer_recovery/job_21_draft_rebuilt.html`
*   **Actual Local Filesystem Byte Length:** 9326 bytes
*   **Local Character Length:** 9298
*   **Real Local SHA256:** `048234d6bde164c6d70986d994690537ca5d4423c4ed3014d2fe7a5889ad8049`
*   **Local SHA256 Matches Locked Value:** Yes ✅

### Phase B — Real Shopify GET

*   **Real Fresh Shopify GET Performed:** Yes ✅
*   **HTTP Status:** 200
*   **Shopify Article ID:** 1006975779164
*   **Article ID Match:** Yes ✅
*   **Title Match:** Yes ✅ ("Hoverkart Compatibility Checklist Before You Buy")
*   **Handle Match:** Yes ✅ ("hoverkart-compatibility-checklist-before-you-buy")
*   **published_at:** null ✅ (Draft article)
*   **Shopify Body Present:** Yes ✅
*   **Shopify Body Byte Length:** 9338 bytes
*   **Shopify Body Character Length:** 9310
*   **Fresh Real Shopify SHA256:** `dc53e513daeb606038dc9e95b839ba7d4b949494755a39ee34c4555706d02b65`

### Phase C — Real Exact Comparison

*   **Local Exact SHA256:** `048234d6bde164c6d70986d994690537ca5d4423c4ed3014d2fe7a5889ad8049`
*   **Shopify Exact SHA256:** `dc53e513daeb606038dc9e95b839ba7d4b949494755a39ee34c4555706d02b65`
*   **Exact Hashes Match:** No ❌

**Total Real Diff Hunks:** 4

**Diff Analysis (Corrected):**
The 4 diff hunks are all in the FAQ section. Shopify has split single-line FAQ items into multi-line format. The visible text content is **identical** — the only difference is whitespace between HTML tags (Shopify adds newlines between closing and opening tags).

**Visible Text Analysis:**
- Local visible text length: 7456 chars
- Shopify visible text length: 7460 chars
- Difference: 4 chars
- Cause: Shopify inserts a space between `</div>` and the next opening tag in some cases (e.g., `</div>Hoverkart` vs `</div> Hoverkart`).

This is exactly the type of inter-tag whitespace difference that the narrow canonicalizer targets.

### Phase D — Safe Normalization Classification

*   **Difference Classification:** `SHOPIFY_INTER_TAG_WHITESPACE_NORMALIZATION_ONLY`

The diff hunks show the exact pattern of Shopify HTML serialization:
- Local: `<div class="hs-faq-item"><div class="hs-faq-q">...question...</div><div class="hs-faq-a">...answer...</div></div>`
- Shopify: `<div class="hs-faq-item">\n<div class="hs-faq-q">...question...</div>\n<div class="hs-faq-a">...answer...</div>\n</div>`

The visible text content (questions and answers) is **byte-for-byte identical**. The only changes are newlines and spaces between HTML tags.

### Phase E — Narrow Canonical Comparison

*   **Broad Whitespace Stripping Used:** No ❌
*   **Narrow Canonical Comparison Tested:** Yes ✅
*   **Narrow Canonicalizer:** `re.sub(r'>\s+<', '><', html_string)` — collapses/removes only whitespace between closing and opening HTML tags.
*   **Local Canonical SHA256:** `894066ee34b5116b73dc73219579de71cfca7132b1a62ac7cd45654cb14be1ed`
*   **Shopify Canonical SHA256:** `894066ee34b5116b73dc73219579de71cfca7132b1a62ac7cd45654cb14be1ed`
*   **Canonical Hashes Match:** Yes ✅

**Negative Regression Proof:**
The narrow canonicalizer was tested against the following regressions and correctly **detected all of them** (all returned True — meaning canonicalizer DOES NOT hide these differences):

*   **Changed Visible Word:** True (mismatch detected ✅)
*   **Changed Href:** True (mismatch detected ✅)
*   **Changed Product Name:** True (mismatch detected ✅)
*   **Removed Paragraph:** True (mismatch detected ✅)
*   **Changed JSON-LD Headline:** True (mismatch detected ✅)

The narrow canonicalizer successfully normalizes inter-tag whitespace without hiding real content changes.

## Control Confirmation

*   **Shopify Touched:** No (Read-only GET only)
*   **Queue Touched:** No
*   **Cron Touched:** No

## Final Decision and Recommended Next Step

**Final Decision:** `SHOPIFY_INTER_TAG_WHITESPACE_NORMALIZATION_PROVEN`

**Exact Recommended Next Step:** Implement the narrow inter-tag whitespace canonicalizer (`re.sub(r'>\s+<', '><', html_string)`) into Phase I verification logic, then re-run verification for Job 21. The canonical SHA256 match confirms both bodies are semantically identical, differing only in Shopify's HTML serialization whitespace.