# HCS Gadgets Rules Manifest

**Client:** HCS Gadgets  
**Generated:** 2026-07-01  
**Purpose:** Centralised index of all rule files for HCS Gadgets content engine

---

## Rules Index

| # | Rule File | Source Path | New Canonical Path | Copied | Duplicate Exists | Content Match | Notes |
|---|-----------|------------|-------------------|--------|-----------------|--------------|-------|
| 1 | `compliance_rules.md` | `content_engine/compliance_rules.md` | `rules/compliance_rules.md` | ✅ YES | ❌ NO | N/A | Already in content_engine — copied to rules/ |
| 2 | `writing_rules.md` | `content_engine/writing_rules.md` | `rules/writing_rules.md` | ✅ YES | ❌ NO | N/A | Already in content_engine — copied to rules/ |
| 3 | `product_scope_rules.md` | `content_engine/product_scope_rules.md` | `rules/product_scope_rules.md` | ✅ YES | ❌ NO | N/A | Already in content_engine — copied to rules/ |
| 4 | `cluster_map.md` | `content_engine/cluster_map.md` | `rules/cluster_map.md` | ✅ YES | ❌ NO | N/A | Already in content_engine — copied to rules/ |
| 5 | `html_article_template.md` | `content_engine/html_article_template.md` | `rules/html_article_template.md` | ✅ YES | ❌ NO | N/A | Already in content_engine — copied to rules/ |
| 6 | `brand_rules.md` | `hcs_gadgets/brand_rules.md` | `rules/brand_rules.md` | ✅ YES | ❌ NO | N/A | Copied from parent directory |
| 7 | `design_rules.md` | `hcs_gadgets/design_rules.md` | `rules/design_rules.md` | ✅ YES | ❌ NO | N/A | Copied from parent directory |

---

## Files Not Found (Not Yet Created)

| Rule File | Status |
|-----------|--------|
| `old_scripts_manifest.md` | ❌ Not present — to be created in future phase |
| `campaign_rules.md` | ❌ Not present — to be created if campaigns are added |
| `ad_rules.md` | ❌ Not present — to be created if ads are added |

---

## Original Files

**All original files were kept in their original locations.** No files were deleted or moved.

| Original Location | Files |
|-------------------|-------|
| `clients/hcs_gadgets/` | `brand_rules.md`, `design_rules.md` |
| `clients/hcs_gadgets/content_engine/` | `compliance_rules.md`, `writing_rules.md`, `product_scope_rules.md`, `cluster_map.md`, `html_article_template.md` |

---

## Recommended Future Actions

| Priority | Action | Rationale |
|----------|--------|-----------|
| High | Consolidate all rules into `rules/` folder | Single source of truth for ORIN content engine |
| Medium | Deprecate `hcs_gadgets/` root level rule files | Keep originals until rules/ is confirmed canonical |
| Low | Create `old_scripts_manifest.md` | Document blocked legacy scripts |
| Low | Create `campaign_rules.md` | For future ad/campaign work |
| Low | Create `ad_rules.md` | For future ads work |

---

## Folder Structure After Phase 0.2B

```
clients/hcs_gadgets/content_engine/
├── rules/                          ← NEW canonical rules folder
│   ├── compliance_rules.md
│   ├── writing_rules.md
│   ├── product_scope_rules.md
│   ├── cluster_map.md
│   ├── html_article_template.md
│   ├── brand_rules.md
│   └── design_rules.md
├── content_queue_3_months.md
├── draft_inventory.md
├── published_inventory.md
├── shopify_inventory.md
├── hcs_orin_onboarding_baseline.md
├── hcs_phase0_2a_state_reconciliation.md
└── [other operational files]
```
