# ORIN Business Date Source Fix Report

**Inspection date:** 2026-07-06
**Phase:** Emergency Timing Fix — Phase A + Phase B
**Strict rules:** No Shopify edits, no queue edits, no live cron runs

---

## Background

Both `state_agent.py` and `cron_entrypoint.py` contained a hardcoded date:

```python
today = date(2026, 6, 28)  # fixed for dry-run
```

This froze ORIN's planning date at 2026-06-28. As of 2026-07-06, the planner evaluated all job timing against a date 8 days in the past, causing Job 21 (expected_draft_date: 2026-07-04, overdue by 2 days) to potentially be missed.

---

## Phase A — Date Source Audit

### Files containing hardcoded production dates

| File | Hardcoded Date | Used for | In ORIN pipeline |
|---|---|---|---|
| `state_agent.py` | `date(2026, 6, 28)` | State Agent `today()` | ✅ Yes — FIXED |
| `cron_entrypoint.py` | `date(2026, 6, 28)` | Pipeline `today()` | ✅ Yes — FIXED |
| `planner_agent.py` | `date(2026, 6, 28)` as `TODAY` | Planner date math | ✅ Yes — FIXED |
| `recovery_agent.py` | `date(2026, 6, 28)` as `TODAY` | Recovery date math | ✅ Yes — FIXED |
| `review_agent.py` | `date(2026, 6, 28)` as `today` | Review date math | ✅ Yes — FIXED |
| `duplicate_decision_agent.py` | `date.today()` | Phase 2B metadata | ✅ Yes — FIXED |
| `orin_phase1a_state_dryrun.py` | None | — | ✅ Updated — `--as-of-date` supported |
| `orin_phase1b_planner_dryrun.py` | None | — | ✅ Updated — `--as-of-date` supported |
| `orin_phase1c_recovery_dryrun.py` | None | — | ✅ Updated — `--as-of-date` supported |
| `orin_phase2a_review_dryrun.py` | `print("Run date: 2026-06-28")` | Print only | ✅ Fixed |
| `orin_phase2b_duplicate_memory_dryrun.py` | `print("Run date: 2026-06-29")` | Print only | ✅ Fixed |
| `orin_phase2c_writer_planning_dryrun.py` | `CURRENT_DATE_STR = "2026-06-29"` | Writer date | ✅ Fixed |
| `hcs_phase1a_state_dryrun.py` | `date(2026, 7, 1)` | HCS (separate pipeline) | ⚠️ Not in ORIN pipeline |
| `hcs_phase1b_planner_dryrun.py` | `date(2026, 7, 1)` | HCS (separate pipeline) | ⚠️ Not in ORIN pipeline |

### Date source findings

- `date.today()` found in `duplicate_decision_agent.py` — used for metadata only — FIXED
- `datetime.now()` — not found in any ORIN production agent
- `utcnow()` — not found in any ORIN production agent
- No timezone assumptions beyond ZoneInfo Europe/London
- Different agents were NOT disagreeing on date — all shared the same `date(2026, 6, 28)` hardcode

---

## Phase B — Canonical Business Date Source Created

### File created

**Path:** `tools/shopify_publisher/orin/business_time.py`

### Design

```python
BUSINESS_TZ = ZoneInfo("Europe/London")  # Handles GMT/BST automatically

def get_business_today(as_of_date: str | None = None) -> date:
    # Priority: explicit arg > ORIN_BUSINESS_DATE env var > sys.argv --as-of-date > current Europe/London date
```

### Canonical timezone

**Europe/London** via `zoneinfo.ZoneInfo("Europe/London")` — correctly handles GMT/BST daylight-saving transitions.

### Production default

```python
datetime.now(ZoneInfo("Europe/London")).date()
```

### Deterministic override

```python
get_business_today(as_of_date="2026-07-04")
# or via CLI:
python3 ... --as-of-date 2026-07-04
```

### Validation

- Invalid format (`04-07-2026`) → raises `ValueError: Invalid as_of_date format: '04-07-2026'. Expected YYYY-MM-DD`
- Impossible date (`2026-02-30`) → raises `ValueError: Impossible date '2026-02-30'`
- No silent fall-back to another date

### Subprocess propagation

`ORIN_BUSINESS_DATE` environment variable carries the resolved date into subprocesses (phase wrappers). Each wrapper also accepts `--as-of-date` for direct CLI use.

---

## Phase B — Integration

### Updated files

| File | Change |
|---|---|
| `state_agent.py` | `today()` now calls `get_business_today()` — hardcoded date removed |
| `cron_entrypoint.py` | `BUSINESS_TODAY = get_business_today(AS_OF_DATE)` — parsed from `--as-of-date` CLI arg; propagated to subprocesses via `ORIN_BUSINESS_DATE` env var |
| `planner_agent.py` | `TODAY = date(2026, 6, 28)` removed — uses `today()` from `state_agent` |
| `recovery_agent.py` | `TODAY = date(2026, 6, 28)` removed — uses `today()` from `state_agent` |
| `review_agent.py` | `today = date(2026, 6, 28)` removed — uses `today()` from `state_agent` |
| `duplicate_decision_agent.py` | `date.today()` replaced with `get_business_today()` |
| `orin_phase1a_state_dryrun.py` | Added `get_business_today_from_args`; `--as-of-date` supported |
| `orin_phase1b_planner_dryrun.py` | Added `get_business_today_from_args`; `--as-of-date` supported |
| `orin_phase1c_recovery_dryrun.py` | Added `get_business_today_from_args`; `--as-of-date` supported |
| `orin_phase2a_review_dryrun.py` | Added `get_business_today_from_args`; hardcoded `2026-06-28` removed |
| `orin_phase2b_duplicate_memory_dryrun.py` | Added `get_business_today_from_args`; hardcoded `2026-06-29` removed |
| `orin_phase2c_writer_planning_dryrun.py` | `CURRENT_DATE_STR` resolved from `get_business_today_from_args`; hardcoded `2026-06-29` removed |

### Consistent date across all stages

`cron_entrypoint.py` resolves `BUSINESS_TODAY` once at startup and propagates it via:
1. Environment variable `ORIN_BUSINESS_DATE` to all subprocess phase wrappers
2. Direct `--as-of-date` CLI argument to phase wrappers

All date-sensitive stages receive the same business date. No stage can disagree.

---

## Phase C — Test Results

### Test A: `--as-of-date 2026-06-28`

```
Business date: 2026-06-28 (Europe/London)
Decision: no_job_due
Selected job: none
Reason: No planned job is due.
Shopify touched: No
Queue touched: No
```
**Result:** ✅ Reproduces historic no-job-due state correctly

### Test B: `--as-of-date 2026-07-04`

```
Business date: 2026-07-04 (Europe/London)
Decision: job_selected
Selected job: 21
Topic: Hoverkart Compatibility Checklist Before You Buy
Reason: Job 21 is planned, due (expected_draft_date=2026-07-04), and has no blocking issues.
Publisher decision: ALREADY_CREATED
Shopify touched: No
Queue touched: No
Blocked: No
```
**Result:** ✅ Job 21 correctly selected as due/overdue

### Test C: No override (production default — current date 2026-07-06)

```
Business date: 2026-07-06 (Europe/London)
Decision: job_selected
Selected job: 21
Reason: Job 21 is planned, due (expected_draft_date=2026-07-04), and has no blocking issues.
Shopify touched: No
Queue touched: No
Publisher passed: True
Blocked: No
```
**Result:** ✅ Production default correctly resolves to 2026-07-06 and selects Job 21

### Test D: Invalid date — `2026-02-30`

```
ValueError: Impossible date '2026-02-30' (Input to date.fromisoformat is out of range)
```
**Result:** ✅ Clearly fails with descriptive error

### Test E: Invalid format — `04-07-2026`

```
ValueError: Invalid as_of_date format: '04-07-2026'. Expected YYYY-MM-DD (e.g. 2026-07-04).
```
**Result:** ✅ Clearly fails with descriptive error

---

## HCS Files Note

`hcs_phase1a_state_dryrun.py` and `hcs_phase1b_planner_dryrun.py` contain `date(2026, 7, 1)` hardcoded. These are **separate from the ORIN pipeline** and are not referenced in `cron_entrypoint.py`. Not modified as they are outside the ORIN production scope.

---

## Production Cron Command

The production cron command is:

```
cd /data/.openclaw/workspace && python3 tools/shopify_publisher/orin/cron_entrypoint.py --live-draft --confirm-live-draft
```

**No `--as-of-date` is present.** Production default resolves to the current Europe/London date at each run.

---

## Final Status

| Check | Status |
|---|---|
| Hardcoded `date(2026, 6, 28)` removed from all ORIN production files | ✅ |
| Canonical business date = Europe/London via ZoneInfo | ✅ |
| Production default = `datetime.now(ZoneInfo("Europe/London")).date()` | ✅ |
| `--as-of-date YYYY-MM-DD` override supported | ✅ |
| Invalid date clearly rejected | ✅ |
| Consistent date across all date-sensitive stages | ✅ |
| Shopify untouched across all test runs | ✅ |
| Queue untouched across all test runs | ✅ |
| Production cron command unchanged | ✅ |
| Production cron contains no `--as-of-date` | ✅ |
