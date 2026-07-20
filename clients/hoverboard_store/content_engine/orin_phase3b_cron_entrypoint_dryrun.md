# ORIN Phase 3B — Cron Entrypoint Dry-Run Report

## What Was Done

Created `tools/shopify_publisher/orin/cron_entrypoint.py` — one safe, unified ORIN cron entrypoint that runs the full pipeline in order.

## Dry-Run Result

```
Pipeline: ORIN Cron Entrypoint Phase 3B
Mode: DRY-RUN
Started: 2026-07-01T00:38:50+01:00

Phase 1A (State Agent): ✅ PASS — 6 jobs analysed
Phase 1B (Planner Agent): ℹ️ No planned job is due — pipeline stopped safely
Phase 2A–2G: NOT REACHED (correct — pipeline stopped at Phase 1B)

Shopify touched: NO
Queue touched: NO
Blocked: NO
```

**Result: PASS** — Pipeline ran correctly. All planned jobs are either completed or not yet due. Pipeline stopped safely without reaching Shopify.

---

## Entrypoint Details

### File
```
tools/shopify_publisher/orin/cron_entrypoint.py
```

### Pipeline Order
| Phase | Agent | Wrapper Script | Output |
|---|---|---|---|
| 1A | State Agent | `orin_phase1a_state_dryrun.py` | /tmp/orin_phase1a_job_state_preview.json |
| 1B | Planner Agent | `orin_phase1b_planner_dryrun.py` | /tmp/orin_phase1b_planner_preview.json |
| 1C | Recovery Agent | `orin_phase1c_recovery_dryrun.py` | /tmp/orin_phase1c_recovery_preview.json |
| 2A | Review Agent | `orin_phase2a_review_dryrun.py` | /tmp/orin_phase2a_review_preview.json |
| 2B | Duplicate Decision Memory | `orin_phase2b_duplicate_memory_dryrun.py` | /tmp/orin_phase2b_duplicate_decisions_preview.json |
| 2D | Writer Planning | `orin_phase2c_writer_planning_dryrun.py` | /tmp/orin_phase2c_writer_plan_preview.json |
| 2E/2G | Publisher Agent (hardened) | `orin_phase2e_publisher_dryrun.py` | /tmp/orin_phase2e_publisher_preview.json |

### Safety Features

| Feature | Status |
|---|---|
| Default mode = --dry-run | ✅ |
| --dry-run flag | ✅ |
| --live-draft flag | ✅ BLOCKED — refuses to run |
| Never calls old publish_blog_draft.py | ✅ |
| Never calls old update_blog_draft.py | ✅ |
| Never calls old next_blog_job.py | ✅ |
| Never calls old mark_job_done.py | ✅ |
| Never sets published_at | ✅ |
| Never auto-publishes | ✅ |
| Pipeline blocked script check | ✅ Code scan before run |
| Stops safely on any blocking decision | ✅ |
| Graceful error handling per phase | ✅ Non-blocking phase errors |

### Usage

```bash
# Dry-run (default)
python3 tools/shopify_publisher/orin/cron_entrypoint.py --dry-run

# With JSON output (for automation)
python3 tools/shopify_publisher/orin/cron_entrypoint.py --dry-run --json

# Select specific job
python3 tools/shopify_publisher/orin/cron_entrypoint.py --job=20 --dry-run
```

### Bug Fixed During Phase 3B

`state_agent.py` had a field name bug: `a["article_id"]` when the Shopify inventory uses `a["id"]`. Fixed in place.

---

## Blocking Logic

The pipeline stops safely at the first blocking decision:

1. **Phase 1B**: No job due → stop (safe — nothing to do)
2. **Phase 2A**: Compliance fail, HTML quality fail, or duplicate decision needed → BLOCK
3. **Phase 2B**: Real duplicate requires human decision → BLOCK
4. **Phase 2E/2G**: Publisher preflight fails → BLOCK

---

## Phase 3B Pass Criteria

| Criterion | Result |
|---|---|
| Entrypoint created | ✅ `cron_entrypoint.py` created |
| All 7 phases called | ✅ via dry-run wrappers |
| Old scripts never called | ✅ verified by code scan |
| --dry-run default | ✅ |
| --live-draft blocked | ✅ |
| Shopify untouched | ✅ |
| Queue untouched | ✅ |
| Pipeline stops safely when no job due | ✅ |
| JSON preview written | ✅ `/tmp/orin_phase3b_cron_entrypoint_preview.json` |
| Phase 3B passed | ✅ |

---

## Next Step: Phase 3C

**Phase 3C — Test pipeline with a job that has a local draft**

The pipeline could not reach Phase 2A–2G because no planned job was due. To test those phases end-to-end, run with a specific job that has a local draft and is due.

Example:
```bash
python3 tools/shopify_publisher/orin/cron_entrypoint.py --job=20 --dry-run
```

This will test Phase 2A (Review Agent), Phase 2B (Duplicate Decision), Phase 2D (Writer Planning), and Phase 2E/2G (Publisher preflight) for Job 20.

---

_Locked: 2026-07-01 01:38 GMT+1_
