# ORIN Pre-Live Job 21 Regression Report

**Date:** 2026-07-06
**Mode:** Dry-run only — no Shopify writes, no queue edits, no live cron
**Purpose:** Confirm the full ORIN pipeline is ready for the production cron to take over

---

## Pipeline Run: Full Dry-Run with Current Europe/London Date

### Command

```
python3 tools/shopify_publisher/orin/cron_entrypoint.py --dry-run --json
```

### Resolved Business Date

**2026-07-06 (Europe/London)** — correctly using current date via `datetime.now(ZoneInfo("Europe/London")).date()`

---

## Phase Results

| Phase | Job | Result |
|---|---|---|
| Phase 1A — State Agent | Jobs 15–20 | ✅ 6 jobs analysed |
| Phase 1B — Planner Agent | Job 21 | ✅ `job_selected` — Hoverkart Compatibility Checklist Before You Buy |
| Phase 1C — Recovery Agent | Job 21 | ✅ 1 active recovery item (Job 20 — `local_file_exists_shopify_missing`); no TypeError |
| Phase 2A — Review Agent | Job 21 | ✅ PASS — ready for duplicate decision |
| Phase 2B — Duplicate Memory | Job 21 | ✅ PASS |
| Phase 2D — Writer Planning | Job 21 | ✅ `no_writer_action` |
| Phase 2E — Publisher Preflight | Job 21 | ✅ `ALREADY_CREATED` — canonical article in Shopify |

---

## Job 21 Status

| Field | Value |
|---|---|
| Job number | 21 |
| Topic | Hoverkart Compatibility Checklist Before You Buy |
| Target keyword | hoverkart compatibility checklist |
| Queue status | planned |
| Date target | 2026-07-18 |
| Expected draft date | 2026-07-04 |
| Days overdue (as of 2026-07-06) | 2 days |
| Shopify article | Already created (Article ID in queue notes) |
| Publisher decision | `ALREADY_CREATED` |
| Shopify touched by dry-run | ❌ No |
| Queue touched by dry-run | ❌ No |

---

## What the Production Cron Will Do

At 09:00 BST, the production cron fires:
```
python3 tools/shopify_publisher/orin/cron_entrypoint.py --live-draft --confirm-live-draft
```

**Confirmed pipeline behaviour for Job 21:**
1. Phase 1A: Audit state → Job 21 planned, overdue
2. Phase 1B: Select Job 21 (overdue, no blocking issues)
3. Phase 1C: Recovery audit → Job 20 flagged (not Job 21); non-blocking
4. Phase 2A: Review Job 21 → `ALREADY_CREATED` → PASS
5. Phase 2B: Duplicate check → PASS
6. Phase 2D: Writer planning → no new write needed
7. Phase 2E: Publisher preflight → `ALREADY_CREATED` → PASS
8. Pipeline stops safely — no live draft created (already exists)

---

## Safety Confirmation

| Check | Result |
|---|---|
| Shopify article created during dry-run | ❌ No |
| Shopify article updated during dry-run | ❌ No |
| Queue edited during dry-run | ❌ No |
| Live draft created during dry-run | ❌ No |
| Phase 1C TypeError | ❌ Resolved |
| Pipeline blocked unexpectedly | ❌ No — clean completion |
| Cron delivery mode | `none` — no spurious errors |

---

## Active Recovery Item

Job 20 (`Best Hoverboard Accessories for Safer Riding`) is flagged by Phase 1C with `local_file_exists_shopify_missing`. This means the local draft file exists but no Shopify article ID is associated with it. This is a **recovery item for Job 20**, not Job 21, and does not block the pipeline.

**Action for operator:** Investigate Job 20's local draft and Shopify inventory. The draft may need to be pushed to Shopify, or the Shopify article ID needs to be recorded in the queue.

---

## Next Scheduled Run

**2026-07-07 09:00 BST** — via production cron (`c5c7e16b-5ee1-4855-ae7a-97fd25bfd67d`)

The cron is configured with `delivery.mode: "none"` so no delivery errors will occur.
