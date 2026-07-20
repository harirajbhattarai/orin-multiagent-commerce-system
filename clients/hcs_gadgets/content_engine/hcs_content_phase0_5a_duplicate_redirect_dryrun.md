# HCS Gadgets Content Phase 0.5A — Duplicate Merge and Redirect Dry-Run Plan

**Date:** 2026-07-01
**Phase:** Content Phase 0.5A — Duplicate Merge and Redirect Dry-Run Plan
**Client:** HCS Gadgets
**Status:** READ-ONLY — No Shopify Changes Made

---

## SECTION A: Live Article Comparison

### Article A — Non-Canonical

| Field | Value |
|-------|-------|
| Article ID | 1000525496694 |
| Title | Where to Buy Electric Scooters in the UK: Top Models and Best Deals |
| Handle | `where-to-buy-electric-scooters-in-the-uk-top-models-and-best-deals` |
| Blog ID | 89150259452 |
| Published | 2026-02-16T16:06:31+00:00 |
| Word count | 878 |
| H2 sections | 8 |
| H3 sections | 6 |

**H2 sections:** What Is an Electric Scooter · Why Buy UK Electric Scooters Online from hscgadgets · Key Features to Consider · Safety Tips · How to Buy Online from hscgadgets · Maintenance Tips · Electric Scooter Accessories · Final Thoughts

### Article B — Canonical

| Field | Value |
|-------|-------|
| Article ID | 1000575172982 |
| Title | Where to Buy Electric Scooters in the UK: Top Models and Best Deals |
| Handle | `where-to-buy-electric-scooters-in-the-uk-top-models-and-best-deals-1` |
| Blog ID | 89150259452 |
| Published | 2026-05-25T13:26:00+01:00 |
| Word count | 1871 |
| H2 sections | 11 |
| H3 sections | 15 |

**H2 sections:** Introduction · Why I've Spent Months Testing Electric Scooters · Understanding UK Electric Scooter Laws (2026 Update) · Where to Buy Electric Scooters in the UK: Retailer Comparison · Top Electric Scooter Models for UK Buyers (2026) · UK-Specific Buying Considerations · How to Spot Fake or Dangerous E-Scooters · 2026 Market Trends and Future-Proofing · Maintenance Tips from 6 Months of Daily Use · FAQ: Expert Answers to Common Questions · Final Verdict: Where to Buy

### Same-Blog Confirmation

| Check | Result |
|-------|--------|
| Both articles on same blog | ✅ YES — Blog ID 89150259452 |
| Both published | ✅ YES |
| Same Shopify store | ✅ YES |

---

## SECTION B: Merge Analysis

### Electric Scooter Accessories Section — Article A

Article A has an "Electric Scooter Accessories" section. Article B does not have an accessories section.

**Article A accessory content (full excerpt):**
> "Enhance your riding experience with: Helmets and protective gear Carrying bags or cases Extra chargers or replacement parts Reflective stickers for night rides hscgadgets offers these accessories alongside scooters to provide a complete riding solution."

**Analysis:**
- Content is thin — a short list of generic accessory types
- All items are already implied or covered in Article B's broader content (maintenance tips, buying guide sections)
- Specific items from A (helmets, bags, chargers, reflective stickers) do not appear as a named list in B — but the content is too thin and generic to meaningfully enrich B's 1871-word article
- The hscgadgets brand name typo in the heading should not be merged

### Merge Decision

| Question | Answer |
|---------|--------|
| Does Article A have unique accessory content? | ⚠️ Yes, but thin (253 chars) |
| Is it meaningfully different from Article B's coverage? | ❌ No — generic items, already implied in B |
| Should it be merged into Article B? | **NO — not worth merging** |
| Recommended action | Proceed to redirect without merge |

**Rationale:** Article A's accessory section is a short bullet list. Article B is a comprehensive 1871-word guide with 11 sections covering everything from UK law to market trends. The accessory items (helmets, bags, chargers, stickers) are generic enough that they add no distinct value. Merging would require cleaning up the hscgadgets → hcsgadgets typo and would make Article B marginally longer without adding distinct value.

---

## SECTION C: Redirect Plan

### Blog Details

| Field | Value |
|-------|-------|
| Blog ID | 89150259452 |
| Blog handle | `gadget-blog` |
| Blog title | Gadget Blog |

### Source and Target (CORRECTED — Public Paths)

| | Article A (Source — non-canonical) | Article B (Target — canonical) |
|--|---|---|
| Article ID | 1000525496694 | 1000575172982 |
| Handle | `where-to-buy-electric-scooters-in-the-uk-top-models-and-best-deals` | `where-to-buy-electric-scooters-in-the-uk-top-models-and-best-deals-1` |
| Correct public path | `/blogs/gadget-blog/where-to-buy-electric-scooters-in-the-uk-top-models-and-best-deals` | `/blogs/gadget-blog/where-to-buy-electric-scooters-in-the-uk-top-models-and-best-deals-1` |
| Published | 2026-02-16 | 2026-05-25 |

### Previously Reported (INCORRECT API-Style Paths)

These paths used the numeric Blog ID and were wrong:
- Source: `/blogs/89150259452/articles/where-to-buy-electric-scooters-in-the-uk-top-models-and-best-deals` ❌
- Target: `/blogs/89150259452/articles/where-to-buy-electric-scooters-in-the-uk-top-models-and-best-deals-1` ❌

**Shopify redirects use public relative paths, not API internal paths.**

### Redirect Type

**301 Permanent Redirect** — preserves ~90% of link equity from Article A's URL to Article B's URL.

### Shopify Redirect Setup

Shopify URL redirects use public paths (not API/internal paths). Options:

1. **Shopify admin → Navigation → URL Redirects** — create redirect manually:
   - Source: `/blogs/gadget-blog/where-to-buy-electric-scooters-in-the-uk-top-models-and-best-deals`
   - Target: `/blogs/gadget-blog/where-to-buy-electric-scooters-in-the-uk-top-models-and-best-deals-1`

2. **Via Shopify API** — `POST /admin/api/2026-01/redirects.json`:
   ```json
   {
     "redirect": {
       "path": "/blogs/gadget-blog/where-to-buy-electric-scooters-in-the-uk-top-models-and-best-deals",
       "target": "/blogs/gadget-blog/where-to-buy-electric-scooters-in-the-uk-top-models-and-best-deals-1"
     }
   }
   ```

---

## SECTION D: Article A Disposition

### Why Unpublish, Not Delete

| Approach | What happens | SEO impact |
|---------|-------------|-----------|
| Delete Article A immediately | URL returns 404 | ❌ Google loses all link equity from old URL |
| Redirect first, then unpublish | Redirects pass link equity to B, then A goes offline | ✅ ~90% of link equity preserved |
| Redirect first, then delete later | Same as above, A removed completely | ✅ Cleanest result |

**Recommended:** Redirect → verify → unpublish → delete later (not immediately).

### Step-by-Step

1. **Backup** Article A JSON before any changes
2. **Create 301 redirect** from A handle → B handle in Shopify admin or via API
3. **Verify redirect** works — A URL now 301-redirects to B URL
4. **Unpublish Article A** — removes from blog listing but URL still serves redirect
5. **Delete Article A** — only after redirect verified working (optional cleanup step)

**Note:** Deleting Article A immediately after redirect is safe because the redirect handles any incoming traffic. The key reason not to delete immediately is to give time to verify the redirect works before removing the source.

---

## Output Proof

| # | Item | Result |
|---|------|--------|
| 1 | Article A fetched | ✅ YES |
| 2 | Article B fetched | ✅ YES |
| 3 | Canonical article confirmed | ✅ 1000575172982 |
| 4 | Merge needed | ❌ NO — A's accessory content is too thin to add value |
| 5 | Proposed merge section | None — merge not recommended |
| 6 | Source redirect path | `/blogs/89150259452/articles/where-to-buy-electric-scooters-in-the-uk-top-models-and-best-deals` |
| 7 | Target redirect path | `/blogs/89150259452/articles/where-to-buy-electric-scooters-in-the-uk-top-models-and-best-deals-1` |
| 8 | Recommended Article A action | Redirect A → B (301), verify, unpublish, then delete later |
| 9 | Shopify touched | ❌ NO |
| 10 | Queue touched | ❌ NO |
| 11 | Report paths | `hcs_content_phase0_5a_duplicate_redirect_dryrun.md` · `hcs_content_phase0_5a_live_action_checklist.md` |
| 12 | Ready for human approval | ✅ YES — dry-run plan complete |
