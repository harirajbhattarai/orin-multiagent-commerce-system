# ORIN Phase 1 — Baseline

**Status:** Phase 1 COMPLETE — baseline locked
**Locked:** 2026-06-28 23:37 BST
**Client:** hoverboard_store

---

## Phase 1 Completion

Phase 1 is a read-only audit and orchestration system. It reads queue, Shopify inventory, and filesystem state to produce decisions. It makes no changes to Shopify, queue files, or article drafts.

**Completed:** 2026-06-28

---

## Components Completed

| Phase | Component | File | Status |
|-------|-----------|------|--------|
| 1A | State Agent | `tools/shopify_publisher/orin/state_agent.py` | PASS |
| 1B | Planner Agent | `tools/shopify_publisher/orin/planner_agent.py` | PASS |
| 1C | Recovery Agent | `tools/shopify_publisher/orin/recovery_agent.py` | PASS |
| 1D | Reporter Agent | `tools/shopify_publisher/orin/reporter_agent.py` | PASS |
| 1E | Orchestrator Wrapper | `tools/shopify_publisher/orin/orchestrator.py` | PASS |

---

## System Health

| Field | Value |
|-------|-------|
| **Health status** | `HEALTHY_WAITING` |
| **Planner decision** | `no_job_due` |
| **Blocking issues** | `0` |
| **Active recovery items** | `0` |
| **Historical resolved** | `0` |
| **No action needed** | `6` |

---

## Jobs 15–19 Status

| Job | Queue | State | Shopify ID | Shopify Handle | Draft Due | Blocking |
|-----|-------|-------|-----------|---------------|-----------|----------|
| Job 15 | `draft_created` | `clean_draft_created` | `1006811971932` | `how-to-store-a-hoverboard-battery-safely-hoverboard-store` | 2026-06-16 | none |
| Job 16 | `draft_created` | `clean_draft_created` | `1006814593372` | `6-5-vs-8-5-inch-hoverboards-for-kids-simple-buying-guide-hoverboard-store` | 2026-06-19 | none |
| Job 17 | `draft_created` | `clean_draft_created` | `1006818689372` | `hoverboard-won-t-turn-on-safe-checks-before-you-replace-it` | 2026-06-22 | none |
| Job 18 | `draft_created` | `clean_draft_created` | `1006819246428` | `hoverboard-weight-limit-guide-for-parents` | 2026-06-25 | none |
| Job 19 | `draft_created` | `clean_draft_created` | `1006822064476` | `christmas-hoverboard-gift-guide-for-kids-uk` | 2026-06-28 | none |

---

## Approved Shopify Handles

All handles locked in `clients/hoverboard_store/content_engine/orin_preflight_rules.md`.

| Job | Article ID | Approved Handle |
|-----|-----------|----------------|
| Job 15 | `1006811971932` | `how-to-store-a-hoverboard-battery-safely-hoverboard-store` |
| Job 16 | `1006814593372` | `6-5-vs-8-5-inch-hoverboards-for-kids-simple-buying-guide-hoverboard-store` |
| Job 17 | `1006818689372` | `hoverboard-won-t-turn-on-safe-checks-before-you-replace-it` |
| Job 18 | `1006819246428` | `hoverboard-weight-limit-guide-for-parents` |
| Job 19 | `1006822064476` | `christmas-hoverboard-gift-guide-for-kids-uk` |

---

## Next Due Job

| Field | Value |
|-------|-------|
| Next due job | **Job 20** |
| Topic | Best Hoverboard Accessories for Safer Riding |
| Target date | 2026-07-15 |
| **Expected draft date** | **2026-07-01** |
| Days until draft | 3 |
| Ready to start | No — wait |

---

## Phase 1 Dry-Run Commands

```bash
# Phase 1A — State Agent
cd /data/.openclaw/workspace && python3 tools/shopify_publisher/orin/orin_phase1a_state_dryrun.py

# Phase 1B — Planner Agent
cd /data/.openclaw/workspace && python3 tools/shopify_publisher/orin/orin_phase1b_planner_dryrun.py

# Phase 1C — Recovery Agent
cd /data/.openclaw/workspace && python3 tools/shopify_publisher/orin/orin_phase1c_recovery_dryrun.py

# Phase 1D — Reporter Agent
cd /data/.openclaw/workspace && python3 tools/shopify_publisher/orin/orin_phase1d_reporter_dryrun.py

# Phase 1E — Orchestrator (runs all agents in sequence)
cd /data/.openclaw/workspace && python3 tools/shopify_publisher/orin/orin_phase1e_orchestrator_dryrun.py
```

---

## Phase 1 Files

All files under `tools/shopify_publisher/orin/`:

```
tools/shopify_publisher/orin/
├── state_agent.py                               # Phase 1A — State detection module
├── planner_agent.py                             # Phase 1B — Job selection logic
├── recovery_agent.py                            # Phase 1C — Stuck-state detection
├── reporter_agent.py                           # Phase 1D — Consolidated reporting
├── orchestrator.py                             # Phase 1E — Agent orchestration wrapper
├── orin_phase1a_state_dryrun.py               # Phase 1A runner
├── orin_phase1b_planner_dryrun.py             # Phase 1B runner
├── orin_phase1c_recovery_dryrun.py            # Phase 1C runner
├── orin_phase1d_reporter_dryrun.py             # Phase 1D runner
└── orin_phase1e_orchestrator_dryrun.py         # Phase 1E runner
```

Supporting files:

```
clients/hoverboard_store/content_engine/orin_preflight_rules.md     # Handle preservation rules
clients/hoverboard_store/content_engine/orin_status.md              # Live ORIN status
clients/hoverboard_store/content_engine/orin_status_phase1a.md      # Phase 1A report
clients/hoverboard_store/content_engine/orin_status_phase1b.md      # Phase 1B report
clients/hoverboard_store/content_engine/orin_status_phase1c.md      # Phase 1C report
clients/hoverboard_store/content_engine/orin_status_phase1d.md      # Phase 1D report
clients/hoverboard_store/content_engine/orin_status_phase1e.md      # Phase 1E report
clients/hoverboard_store/content_engine/orin_phase1_baseline.md     # THIS FILE
```

---

## Phase 2 Scope (Next Phase)

Phase 2 adds live-mode agents that can make changes. All Phase 2 agents operate within Phase 1's state machine and handle preservation rules.

| Phase | Agent | Purpose |
|-------|-------|---------|
| 2A | Writer Agent | Creates local HTML drafts from topic + keyword |
| 2B | Review Agent | Runs compliance, HTML quality, duplicate checks |
| 2C | Publisher Agent | Pushes drafts to Shopify; preserves handles |
| 2D | Cron Integration | Replaces legacy cron with ORIN-controlled scheduling |

Phase 2 does NOT change the Phase 1 dry-run commands above. Dry-run mode remains active until explicitly switched to live mode.

---

*ORIN Phase 1 baseline locked. Do not modify Phase 1 files without creating a new baseline.*
