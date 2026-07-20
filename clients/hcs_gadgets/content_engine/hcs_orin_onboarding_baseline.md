# HCS Gadgets ORIN Onboarding Baseline — Phase 0.1

## Discovery — Existing Setup

### HCS Folders Found
```
clients/hcs_gadgets/                        # Root client folder
  content_engine/
    drafts/                                  # 1 live draft + 3 backups
    logs/                                    # Empty
    automation_state/                         # Empty
    shopify_config/.env                      # Live credentials
  shopify_config/                            # Duplicated config path
  brand_rules.md                             # At client root
  design_rules.md                            # At client root
  obsidian_vault/                            # Empty
  search_console/                            # Empty
```

### HCS Scripts Found
| Script | Purpose | Risk |
|---|---|---|
| `tools/shopify_publisher/hcs_fetch_blogs.py` | Lists Shopify blogs | Low — read-only |
| `tools/shopify_publisher/hcs_publish_blog_draft.py` | Creates new Shopify draft | 🔴 High — no Phase 2G hardening |
| `tools/shopify_publisher/hcs_update_blog_draft.py` | Updates existing Shopify draft | 🔴 High — no Phase 2G hardening |

### HCS Rules Files Found
| File | Location | Status |
|---|---|---|
| compliance_rules.md | content_engine/ | ✅ Reusable |
| writing_rules.md | content_engine/ | ✅ Reusable |
| product_scope_rules.md | content_engine/ | ✅ Reusable |
| cluster_map.md | content_engine/ | ✅ Reusable |
| html_article_template.md | content_engine/ | ✅ Reusable |
| next_openclaw_prompt.md | content_engine/ | ⚠️ Legacy — to be archived |
| brand_rules.md | clients/hcs_gadgets/ (root) | ✅ Move to content_engine/rules/ |
| design_rules.md | clients/hcs_gadgets/ (root) | ✅ Move to content_engine/rules/ |

### HCS Queue Status
| | |
|---|---|
| Queue file | `clients/hcs_gadgets/content_engine/content_queue_3_months.md` |
| Jobs queued | 6 (Jobs 01–06) |
| Job 01 status | planned (queue) — but Shopify shows PUBLISHED |
| Jobs 02–06 | all planned / TBD |

---

## Job 01 — Live Verification

> ⚠️ **Important discrepancy found.**

| Field | Queue says | Live Shopify shows |
|---|---|---|
| **Article ID** | 1001606873462 | 1001606873462 ✅ |
| **Handle** | useful-home-gadgets-that-make-daily-life-easier | useful-home-gadgets-that-make-daily-life-easier ✅ |
| **Status** | draft | **PUBLISHED** ❌ |
| **published_at** | null | **2026-06-12T15:03:16+01:00** ❌ |
| **created_at** | — | 2026-06-02T00:27:33+01:00 |
| **Local draft** | exists | ✅ confirmed |

**Queue is out of date for Job 01.** The article was published on 2026-06-12 but the queue still says "planned" and the local status file says `published: null`. Queue needs updating after this phase.

### Job 01 Duplicate Checks (live inventory)
| Check | Result |
|---|---|
| Duplicate handle exists | NO — 1 (self only) |
| Duplicate title exists | NO — 1 (self only) |
| Shopify inventory count | 36 articles total |

---

## Live Shopify Inventory

| Field | Value |
|---|---|
| **Store** | hcsgadgets-com.myshopify.com |
| **Blog** | Gadget Blog |
| **Blog ID** | 89150259452 |
| **Total articles** | 36 |
| **Drafts** | 0 |
| **Published** | 36 |
| **Inventory files created** | `shopify_inventory_raw.json`, `shopify_inventory.json`, `shopify_inventory.md`, `draft_inventory.md`, `published_inventory.md` |

---

## HCS Script Risk Assessment

### hcs_publish_blog_draft.py
| Check | Status |
|---|---|
| Live inventory refresh before preflight | ❌ NO |
| Exact handle duplicate check | ✅ YES |
| Exact title duplicate check | ✅ YES |
| Near-handle variant detection | ❌ NO |
| Canonical self-match detection | ❌ NO |
| Queue article ID anchor | ❌ NO |
| Phase 2G-level hardening | ❌ NO |

**Verdict:** 🔴 UNSAFE for future use. Must be replaced by ORIN Publisher Agent (Phase 2G hardened).

### hcs_update_blog_draft.py
| Check | Status |
|---|---|
| Live inventory refresh before preflight | ❌ NO |
| Exact handle duplicate check | ⚠️ PARTIAL (during update) |
| Exact title duplicate check | ❌ NO |
| Near-handle variant detection | ❌ NO |
| Canonical self-match detection | ❌ NO |
| Phase 2G-level hardening | ❌ NO |

**Verdict:** 🔴 UNSAFE for future use. Must be replaced by ORIN Publisher Agent update logic.

---

## Known Risks

| Risk | Severity | Notes |
|---|---|---|
| HCS publish scripts have no Phase 2G hardening | 🔴 High | Same vulnerability as pre-Phase 2G Hoverboard Store ORIN |
| No local Shopify inventory for HCS | 🔴 High | Inventory files created in this phase — first time |
| Job 01 queue status is wrong | 🟡 Medium | Queue says "planned/draft" but article is published |
| No GSC or search console data | 🟡 Medium | obsidian_vault and search_console are empty |
| Obsidian vault not connected | 🟡 Medium | No SEO performance data |
| brand_rules.md and design_rules.md in wrong location | 🟡 Low | Should be in content_engine/rules/ |
| HCS scripts not archived yet | 🟡 Low | Archive pending next phase |

---

## Migration Recommendations

| Item | Action |
|---|---|
| `hcs_publish_blog_draft.py` | Archive later — replace with ORIN Publisher Agent (Phase 2G) |
| `hcs_update_blog_draft.py` | Archive later — replace with ORIN Publisher Agent update logic |
| `hcs_fetch_blogs.py` | Keep as-is — useful utility |
| `shopify_inventory_raw.json` | Keep — live raw data snapshot |
| `shopify_inventory.json` | Keep — structured inventory |
| `shopify_inventory.md` | Keep — human-readable inventory |
| `draft_inventory.md` | Keep — draft tracker (currently 0 drafts) |
| `published_inventory.md` | Keep — published tracker (36 articles) |
| `compliance_rules.md` | Keep as-is |
| `writing_rules.md` | Keep as-is |
| `product_scope_rules.md` | Keep as-is |
| `cluster_map.md` | Keep as-is |
| `html_article_template.md` | Keep as-is |
| `brand_rules.md` (root) | Move later to content_engine/rules/ |
| `design_rules.md` (root) | Move later to content_engine/rules/ |
| `next_openclaw_prompt.md` | Archive later |
| `latest_shopify_draft_status.json` | Update to reflect Job 01 is published |
| `content_queue_3_months.md` | Update Job 01 status to reflect published state |

---

## Next Recommended Phase

**Phase 0.2 — Queue Correction and Rule File Organisation**

1. Update `latest_shopify_draft_status.json` to reflect Job 01 is published
2. Note Job 01 published_at in queue (without changing queue status — do not retroactively change queue)
3. Create `content_engine/rules/` folder
4. Move brand_rules.md and design_rules.md to rules/
5. Do NOT archive HCS scripts yet — await Phase 1 decision

---

_Locked: 2026-07-01 00:43 GMT+1_
