# ORIN Phase 3A — Cron / Auto-Draft Mode Audit Report

## Audit Scope
Read-only audit. No Shopify writes, no queue edits, no script changes.

---

## Critical Finding: Two Duplicate Old Cron Jobs Are Active

Two OpenClaw cron jobs — both named **"Hoverboard Store — Every-3-Day Blog Draft Creator"** — are running the old automation system (not ORIN). Both are enabled.

| Field | Cron Job 1 | Cron Job 2 |
|---|---|---|
| **Job ID** | `a337eeaf-23f6-422a-bb37-17f102a0a119` | `571fcccf-927f-4347-ba68-67988d13edb3` |
| **Enabled** | ✅ YES | ✅ YES |
| **Schedule** | Every 3 days (anchor: 1779017209374 ms) | Every 3 days (anchor: 1782033573054 ms) |
| **Last run status** | error (16 consecutive) | error (6 consecutive) |
| **Last error** | Edit to `cron_runs.md` failed | Channel delivery failed |
| **Created** | May 2026 | June 2026 |

### Why Two Jobs Exist
The second cron job (June creation date) appears to have been set up as a duplicate or fallback, but it has a different anchor date, making the two jobs fire at different times. This doubles the risk of duplicate Shopify pushes.

---

## Old Automation System — What It Actually Does

The cron jobs run this sequence (via OpenClaw agentTurn):

```
STEP 1  tools/scheduler/next_blog_job.py       → selects next planned job
STEP 2  Generate prompt → next_openclaw_prompt.md
STEP 3  Write local HTML draft
STEP 4  tools/shopify_publisher/publish_blog_draft.py   → push to Shopify immediately
STEP 5  Append to cron_runs.md
```

### What the Old System Checks
| Check | Done by old system |
|---|---|
| Live Shopify inventory | ❌ NO |
| Exact handle match | ❌ NO |
| Exact title match | ❌ NO |
| Near-handle variant | ❌ NO |
| Queue article ID anchor | ❌ NO |
| Phase 2A review | ❌ NO |
| Phase 2B duplicate memory | ❌ NO |
| Phase 2C writer planning | ❌ NO |
| Phase 2D writer local draft | ❌ NO |
| Phase 2E publisher dry-run | ❌ NO |
| Phase 2G preflight | ❌ NO |

### What Happens If File Exists Locally
The old cron logs say "stopped: file already exists" — but it checks **local file only**, not Shopify. If the local draft exists but the Shopify article was created (or created under a different slug), the cron would stop on local file but the Shopify push was already done in a previous run.

---

## How the Duplicate Job 20 Shopify Draft Was Created

The duplicate Article ID **1006842446172** was created by the old cron on **2026-06-30T10:19** via `publish_blog_draft.py`. The ORIN Phase 2F push (Article ID 1006845985116) happened the same day at 16:20.

Timeline:
- 10:19 — Old cron ran Job 20 → called `publish_blog_draft.py` → created Article ID 1006842446172 (wrong slug, old content)
- 16:20 — ORIN Phase 2F manual push → created Article ID 1006845985116 (correct slug, improved content)
- 20:12 — Duplicate deleted

Root cause: Old cron bypassed all ORIN gates and pushed to Shopify without Phase 2G preflight.

---

## Old Automation Scripts

| Script | Role | Phase 2G Status |
|---|---|---|
| `tools/scheduler/next_blog_job.py` | Queue reader + job selector | Legacy — not ORIN |
| `tools/shopify_publisher/publish_blog_draft.py` | Shopify draft push | 🔴 No Phase 2G hardening |
| `tools/scheduler/mark_job_done.py` | Queue status updater | ⚠️ Partially OK — status list includes `published_live` |
| `tools/shopify_publisher/update_blog_draft.py` | Shopify draft update | 🔴 No Phase 2G hardening |
| `tools/shopify_publisher/hcs_publish_blog_draft.py` | HCS Shopify push | 🔴 No Phase 2G hardening |

---

## ORIN Scripts Available

| Script | Role |
|---|---|
| `tools/shopify_publisher/orin/publisher_agent.py` | Phase 2G-hardened publisher preflight |
| `tools/shopify_publisher/orin/orin_phase2e_publisher_dryrun.py` | Phase 2E dry-run wrapper |
| `tools/shopify_publisher/orin/orin_phase2f_publisher_dryrun.py` | Phase 2F dry-run wrapper |
| `tools/shopify_publisher/orin/state_agent.py` | Phase 1A |
| `tools/shopify_publisher/orin/planner_agent.py` | Phase 1B |
| `tools/shopify_publisher/orin/recovery_agent.py` | Phase 1C |
| `tools/shopify_publisher/orin/reporter_agent.py` | Phase 1D |
| `tools/shopify_publisher/orin/review_agent.py` | Phase 2A |
| `tools/shopify_publisher/orin/duplicate_decision_agent.py` | Phase 2B |
| `tools/shopify_publisher/orin/writer_agent.py` | Phase 2D |

**There is currently no single ORIN command that runs the full Phase 1–2E pipeline as a cron entrypoint.** Phase 3B would need to build this.

---

## Old Cron Risks

| Risk | Severity | Detail |
|---|---|---|
| Two duplicate cron jobs running | 🔴 Critical | Both enabled — doubles risk of duplicate pushes |
| Old cron calls publish without Phase 2E/2G preflight | 🔴 Critical | Same failure mode as Job 20 duplicate |
| Old cron uses local file check only, not Shopify | 🔴 Critical | Will not detect duplicate Shopify article if local file was deleted |
| No live inventory refresh in old automation | 🔴 Critical | Same root cause as Job 20 incident |
| Old cron bypasses ORIN review/duplicate/content pipeline | 🔴 Critical | No Phase 2A, 2B, 2C, 2D gates |
| Cron Job 1 has 16 consecutive errors | 🟡 Medium | Failing to write cron_runs.md — not stopping dangerous Shopify pushes |
| Cron Job 2 has 6 consecutive errors | 🟡 Medium | Channel delivery failing — not stopping dangerous Shopify pushes |
| Old cron still calls publish_blog_draft.py | 🔴 High | Will push without Phase 2G duplicate checks |

---

## Recommendations

### Must Disable Before Auto-Draft Mode

| Action | Priority |
|---|---|
| **Disable Cron Job 1** (a337eeaf...) | 🔴 Critical |
| **Disable Cron Job 2** (571fcccf...) | 🔴 Critical |
| Both cron jobs must be disabled before any auto-draft mode is re-enabled | — |

### Old Scripts to Archive

| Script | Action |
|---|---|
| `tools/shopify_publisher/publish_blog_draft.py` | Archive — replace with ORIN Publisher Agent |
| `tools/shopify_publisher/update_blog_draft.py` | Archive — replace with ORIN Publisher Agent |
| `tools/shopify_publisher/orin/hcs_publish_blog_draft.py` | Archive (HCS version same risk) |
| `tools/scheduler/next_blog_job.py` | Archive — replace with ORIN queue selector |
| `tools/scheduler/mark_job_done.py` | Keep — status list needs adding `blocked` and `failed` |

### ORIN Command to Build for Future Cron

There is no clean single ORIN command for cron yet. The ideal cron entrypoint would:
1. Run Phase 1A state check
2. Run Phase 1B planner
3. Run Phase 2A review on selected job
4. Run Phase 2B duplicate check
5. Run Phase 2D writer (or confirm local draft exists)
6. Run Phase 2E publisher dry-run
7. **Only if all gates pass** → push via Phase 2G-hardened Publisher Agent
8. Update queue status: planned → draft_created
9. Log to ORIN status files

---

## Phase 3B Recommended Plan

**Step 1 — Disable old cron jobs**
- Disable both "Hoverboard Store — Every-3-Day Blog Draft Creator" cron jobs
- Verify no further Shopify pushes via old automation

**Step 2 — Archive old scripts**
- Archive `publish_blog_draft.py`, `update_blog_draft.py`, `next_blog_job.py`

**Step 3 — Build ORIN cron entrypoint**
- Create `tools/shopify_publisher/orin/cron_entrypoint.py`
- Combines Phase 1A → 1B → 2A → 2B → 2D → 2E dry-run → Phase 2G Publisher Agent
- Only pushes if ALL gates pass
- Falls back to "stopped" with reason if any gate fails
- Writes ORIN-native log files

**Step 4 — Test ORIN cron entrypoint**
- Dry-run only before enabling
- Verify it correctly stops on duplicate, wrong slug, compliance fail

**Step 5 — Enable ORIN cron**
- Schedule ORIN cron entrypoint every 3 days
- Use live inventory refresh on every run
- User receives notification only if Shopify push succeeded
- User manually reviews and publishes inside Shopify

---

## Audit Conclusion

**Auto-draft mode cannot be safely enabled with the current setup.**

The old cron jobs are actively dangerous — they bypass all ORIN gates and push directly to Shopify without Phase 2G duplicate checks. The Job 20 duplicate is direct evidence of this failure mode.

**Immediate action required: disable both old cron jobs before any auto-draft mode.**

---

_Locked: 2026-07-01 01:02 GMT+1_
