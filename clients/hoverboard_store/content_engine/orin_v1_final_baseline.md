# ORIN v1 Final Baseline — Hoverboard Store

## ORIN Status

**ORIN v1 — draft-automation foundation COMPLETE**

Hoverboard Store ORIN has completed a full end-to-end pipeline run and is now locked as the clean base template before any new client onboarding begins.

---

## Phase Completion Registry

| Phase | Module | Status | Notes |
|---|---|---|---|
| Phase 1A | State Agent | LOCKED | Baseline locked |
| Phase 1B | Planner Agent | LOCKED | Baseline locked |
| Phase 1C | Recovery Agent | LOCKED | Baseline locked |
| Phase 1D | Reporter Agent | LOCKED | Baseline locked |
| Phase 1E | Orchestrator Wrapper | LOCKED | Baseline locked |
| Phase 2A | Review Agent | LOCKED | Review Agent passed |
| Phase 2B | Duplicate Decision Memory | LOCKED | Duplicate Decision Memory passed |
| Phase 2C | Writer Planning | LOCKED | Date bug fixed |
| Phase 2D | Writer Local Draft | LOCKED | 4 targeted edits applied |
| Phase 2E | Publisher Dry-Run | LOCKED | --json mode fixed |
| Phase 2F | Manual Shopify Draft Push | LOCKED | Manual early approval — draft only |
| Phase 2G | Publisher Preflight Hardening | LOCKED | Live inventory + exact title + near-handle blocking |

---

## Job 20 — Canonical Article Record

| Field | Value |
|---|---|
| **Article ID** | 1006845985116 |
| **Handle** | best-hoverboard-accessories-safer-riding-uk-2026 |
| **Title** | Best Hoverboard Accessories for Safer Riding UK 2026 |
| **Status** | draft |
| **published_at** | null |
| **Tags** | accessories, hoverboard, safety, uk |
| **Queue status** | draft_created |
| **Content** | Improved — compliant, Phase 2D edits applied |
| **Local draft** | clients/hoverboard_store/content_engine/drafts/best-hoverboard-accessories-safer-riding.html |

---

## Duplicate Cleanup Record

**Incident date:** 2026-06-30

| | |
|---|---|
| **Deleted duplicate Article ID** | 1006842446172 |
| **Deleted duplicate handle** | best-hoverboard-accessories-for-safer-riding-uk-2026 |
| **Reason for deletion** | Wrong slug (inserted "for"), old content with non-compliant wording, non-canonical, not recorded in queue |
| **Canonical article kept** | 1006845985116 |
| **Root cause** | Stale local inventory + exact-handle-only preflight |
| **Fix applied** | Phase 2G Publisher Preflight Hardening |

---

## Publisher Agent — Phase 2G Hardening Record

The Publisher Agent (`tools/shopify_publisher/orin/publisher_agent.py`) now includes the following safety layers:

### Live Inventory Refresh
- **Always** fetches live Shopify inventory via API before running any preflight checks
- No longer relies on stale local snapshot
- Falls back to local inventory only if live API call fails

### Blocking Rules (Priority Order)

| Priority | Condition | Decision |
|---|---|---|
| 1 | Self-match: exact handle matches queue article ID | `ALREADY_CREATED` — not a failure |
| 2 | Same title, different handle | `BLOCKED — exact title conflict` |
| 3 | Near-handle variant exists | `BLOCKED — near-handle conflict` |
| 4 | Exact handle already exists | `BLOCKED — handle exists` |
| 5 | Queue status mismatch | `BLOCKED — queue_status=X` |
| 6 | Local draft missing | `BLOCKED — no draft` |
| 7 | Slug mismatch | `BLOCKED — slug mismatch` |
| 8 | Compliance issues | `BLOCKED — compliance fail` |
| 9 | HTML quality issues | `BLOCKED — quality fail` |
| 10 | All checks pass | `APPROVED — safe for manual Shopify draft push` |

### Blocking Rule Definitions

- **exact title conflict:** Article exists in Shopify with **identical title** but a **different handle** → BLOCK
- **near-handle conflict:** Article exists in Shopify with a handle that differs only by a small token (e.g. "for" inserted or removed) → BLOCK
- **canonical self-match:** Exact handle exists AND matches the Shopify article ID recorded in the queue → `ALREADY_CREATED`, not blocked

---

## Wording Clarification — Future Reports

> ⚠️ Future Phase reports must use these exact terms:

| Old ambiguous wording | New precise wording |
|---|---|
| "exact title match" | `exact title conflict: yes` (same title, different handle → block) |
| "exact title match" | `canonical self-match: yes` (same title AND same handle AND queue article ID match → already created) |

This distinction is critical — the two cases have opposite outcomes.

---

## Safe Operating Model

### What ORIN May Do
- Create local HTML drafts in `content_engine/drafts/`
- Run dry-runs and preflight checks
- Prepare Shopify payloads and preview them
- Push Shopify drafts only after **explicit manual user approval**
- Run Phase 2G preflight checks before every live Shopify write

### What ORIN Must Never Do
- **Auto-publish** — ORIN never publishes; user reviews and publishes manually from Shopify
- **Create Shopify draft without explicit user approval**
- **Edit or delete existing published Shopify articles**
- **Push a draft when an exact title conflict or near-handle conflict exists**
- **Use stale local inventory** for duplicate checks

### Review Gate
All Phase 2A–2G outputs require human review before Shopify draft push. ORIN prepares and checks. Human approves and publishes.

---

## Next Recommended Step

**HCS Gadgets Onboarding — Phase 0: Read-Only Discovery**

Before any content work begins:
1. Read-only discovery of HCS Gadgets Shopify store
2. Map existing content inventory
3. Establish HCS Gadgets content baseline
4. No drafts, no pushes, no publishing

---

## Files Created by ORIN v1

| File | Phase |
|---|---|
| agents/orin_core/* | Phase 1A |
| agents/orin_seo/* | Phase 1A |
| agents/orin_guard/* | Phase 1A |
| agents/orin_content/* | Phase 1A |
| tools/shopify_publisher/orin/planner_agent.py | Phase 1B |
| tools/shopify_publisher/orin/recovery_agent.py | Phase 1C |
| tools/shopify_publisher/orin/reporter_agent.py | Phase 1D |
| tools/shopify_publisher/orin/orchestrator.py | Phase 1E |
| tools/shopify_publisher/orin/review_agent.py | Phase 2A |
| tools/shopify_publisher/orin/duplicate_decision_agent.py | Phase 2B |
| clients/hoverboard_store/content_engine/orin_phase2c_baseline.md | Phase 2C |
| clients/hoverboard_store/content_engine/orin_phase2d_baseline.md | Phase 2D |
| clients/hoverboard_store/content_engine/orin_status_phase2d.md | Phase 2D |
| clients/hoverboard_store/content_engine/orin_phase2e_baseline.md | Phase 2E |
| clients/hoverboard_store/content_engine/orin_phase2f_baseline.md | Phase 2F |
| clients/hoverboard_store/content_engine/orin_duplicate_incident_job20.md | Phase 2G |
| clients/hoverboard_store/content_engine/orin_status_phase2g.md | Phase 2G |
| clients/hoverboard_store/content_engine/orin_v1_final_baseline.md | Final |

---

_Locked: 2026-07-01 00:04 GMT+1_
_ORIN v1 — Hoverboard Store — ready for HCS Gadgets Onboarding_
