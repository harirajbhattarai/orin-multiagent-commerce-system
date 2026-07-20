# HCS Product Intelligence — Phase 0 Architecture Report

**Date:** 2026-07-04
**Phase:** Product Intelligence Phase 0 — PHASE I
**Status:** COMPLETE

---

## Executive Summary

HCS Product Intelligence Phase 0 establishes the data architecture separating raw Shopify product data from the writer-safe Public Content View. The system prevents the writer from accessing volatile commercial fields, internal operational data, and unverified supplier claims directly.

The root cause of the Job 02 BBQ incident was the writer reading `product_catalog.json` as if it were a direct writing source — treating SKU, stock count, compare-at price, and supplier marketing copy as confirmed article facts.

Phase 0 eliminates this risk by creating a structured pipeline with multiple validation gates.

---

## New HCS Writer Data Pipeline

### Full Pipeline (17 steps)

```
Step 1:  SHOPIFY RAW PRODUCT DATA
         → product_catalog_raw.json
         Source: Shopify Admin API
         Contains: ALL fields including admin IDs, body_html, images, variants

Step 2:  PRODUCT KNOWLEDGE PROFILE BUILDER
         → hcs_product_knowledge_builder.py
         Process: Extract claims, classify by category, detect conflicts
         Input: product_catalog_raw.json + product_catalog.json

Step 3:  CLAIM EXTRACTION AND SOURCE PROVENANCE
         → product_claim_extraction_rules.md
         Process: Classify claims as A (stable), B (marketing), C (safety/compliance),
                  D (volatile), E (internal)
         Output: Each claim tagged with source field and confidence

Step 4:  CONFLICT AND MISSING DATA CHECK
         → hcs_product_knowledge_builder.py (detect_conflicts)
         Process: Cross-reference title, description, and structured fields
         Detects: capacity mismatch, dimension mismatch, price conflicts
         Action: Conflicted facts recorded — not added to verified claims

Step 5:  PRODUCT KNOWLEDGE PROFILES
         → product_knowledge_profiles.json + .md
         Content: Structured profiles for all 93 active products
         Every fact has: claim, source, confidence, stability, exposure, compliance risk

Step 6:  WRITER-SAFE PUBLIC CONTENT VIEW
         → product_content_view.json + .md
         Content: Only safe, stable, public facts
         Excludes: price, stock, SKU, IDs, inventory_quantity, compare_at_price
         This is the ONLY file the writer may use for general article writing

Step 7:  PRODUCT RELEVANCE GATE
         → article_product_brief_rules.md (ORIN responsibility)
         Process: ORIN matches article topic to relevant products
         Scope: Never all 93 products — only topic-relevant products

Step 8:  ARTICLE-SPECIFIC PRODUCT BRIEF
         → ORIN-generated per job
         Content: Only approved claims for the specific article topic
         Each claim: Five-Gate test result recorded

Step 9:  FIVE-GATE CLAIM TEST
         → five_gate_claim_test.md
         Gates: Truth → Exposure → Stability → Relevance → Compliance
         Output: APPROVED / CONDITIONAL / REJECTED per claim

Step 10: ARTICLE CLAIM ALLOWLIST
         → Built into Article Product Brief
         Content: Only claims that passed all applicable gates
         Use: Writer may only use claims from this allowlist

Step 11: WRITER
         Receives: Article Product Brief + Writing Rules + HCS Design System v2
         Must NOT: Read product_catalog.json directly

Step 12: CONTENT EXPOSURE VALIDATOR
         → hcs_html_contract_validator.py (product truth mode)
         Checks: No SKU, stock, price, or internal IDs in draft HTML

Step 13: CLAIM EVIDENCE VALIDATOR
         → ORIN Guard responsibility
         Checks: Every claim in draft is backed by an allowlist entry

Step 14: PRODUCT TRUTH VALIDATOR
         → hcs_html_contract_validator.py (--link-map mode)
         Checks: All internal URLs are verified in hcs_verified_link_map.json
         Checks: CTA URL is from verified link map only

Step 15: HTML DESIGN SYSTEM v2 VALIDATOR
         → hcs_html_contract_validator.py (structural mode)
         Checks: hcs-article wrapper, hero, top-grid, hcs-content,
                 hcs-table-scroll, hcs-split, hcs-faq, hcs-cta, JSON-LD

Step 16: SAFE SHOPIFY DRAFT UPDATE
         → hcs_shopify_draft_update_safety_rules.md
         Pre-condition: All validators must pass
         Action: Update Shopify draft body_html

Step 17: POST-FETCH SHA256 VERIFICATION
         → ORIN responsibility
         Action: After Shopify update, verify the fetched draft matches submitted HTML
         Purpose: Detect any server-side sanitisation or modification

---

## Key Architectural Rules

### Rule 1: No Direct Catalog Access
The writer must NEVER read `product_catalog.json` directly for article content.

**Reason:** It contains `compare_at_price`, `inventory_quantity`, `sku`, and `images_count` — fields that have no place in customer-facing evergreen content.

### Rule 2: Price = Separate Process
Price may only appear in explicitly price-led content and only after a current verified price lookup at time of writing.

### Rule 3: MISSING DATA != PERMISSION TO INFER
If a fact is not in the Product Knowledge Profile, it is not available to the writer. The writer records `unknown` rather than guessing.

### Rule 4: Conflicted Facts Are Excluded
Facts with conflicting sources (e.g., description says X kg, variant says Y kg) are recorded in `data_conflicts` and excluded from the writer-safe view. Writers must not choose the more impressive number.

### Rule 5: Safety/Compliance Claims Require Human Review
Any claim in the `claims_needing_review` category cannot enter the allowlist without explicit human approval.

---

## Files Created in Phase 0

| File | Purpose |
|------|---------|
| `hcs_product_source_field_audit.md` | Full audit of all Shopify fields, classified by exposure risk |
| `rules/product_knowledge_profile_schema.md` | Canonical schema for Product Knowledge Profiles |
| `rules/product_claim_extraction_rules.md` | Claim classification rules (A–E categories) |
| `tools/.../hcs_product_knowledge_builder.py` | Automated profile generation tool |
| `product_knowledge_profiles.json` | All 93 product profiles (structured JSON) |
| `product_knowledge_profiles.md` | All 93 product profiles (readable) |
| `product_content_view.json` | Writer-safe public content view (JSON) |
| `product_content_view.md` | Writer-safe public content view (readable) |
| `rules/five_gate_claim_test.md` | Five-gate claim approval framework |
| `rules/article_product_brief_rules.md` | Article Product Brief generation rules |
| `hcs_product_intelligence_phase0_architecture.md` | This document |
| `hcs_product_knowledge_quality_report.md` | Quality assessment of all 93 profiles |

---

## Phase 0 Restrictions Enforced

| Restriction | Status |
|-------------|--------|
| No Shopify articles created | ✓ |
| No Shopify articles updated | ✓ |
| No publishing | ✓ |
| No content queue changes | ✓ |
| No cron enabled | ✓ |
| No article generation | ✓ |
| Shopify product fetch = read-only | ✓ |
| Local files only | ✓ |
| No Shopify secrets printed | ✓ |

---

## Phase 1 Scope (Not Done in Phase 0)

- [ ] Update ORIN writer workflow to generate Article Product Briefs
- [ ] Build Article Claim Allowlist into ORIN's brief generation process
- [ ] Integrate Five-Gate Claim Test into ORIN Guard review
- [ ] Update `hcs_verified_link_map.json` to include all 93 product URLs
- [ ] Add product brief generation to the queue job card template
- [ ] Create a `product_truth_draft_validator.py` for pre-submission checks
