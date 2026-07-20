# ORIN Timing Fix Regression Check Report

**Inspection date:** 2026-07-06
**Strict rules:** No Shopify edits, no queue edits, no live cron runs

---

## Purpose

Confirm that after the business date fix and delivery cleanup:
1. No hardcoded production date (`date(2026, 6, 28)`) remains in any ORIN production file
2. No production cron command contains `--as-of-date`
3. The canonical business date source is correctly configured
4. Shopify and queue remain untouched

---

## Regression Check A: Hardcoded Production Date Search

### Command

```bash
grep -rn "date(2026, 6, 28)" tools/shopify_publisher/orin/ --include="*.py"
```

### Result

**No matches in any ORIN production pipeline file.**

### Stray matches (not in ORIN pipeline)

| File | Match | Action |
|---|---|---|
| `hcs_phase1a_state_dryrun.py` | `TODAY = date(2026, 7, 1)` | Not in ORIN pipeline — not modified |
| `hcs_phase1b_planner_dryrun.py` | `TODAY = date(2026, 7, 1)` | Not in ORIN pipeline — not modified |

These HCS files are separate from the ORIN `cron_entrypoint.py` pipeline and are not referenced by the production cron.

---

## Regression Check B: Production Cron Contains No `--as-of-date`

### Command payload (cron ID: c5c7e16b-5ee1-4855-ae7a-97fd25bfd67d)

```
cd /data/.openclaw/workspace && python3 tools/shopify_publisher/orin/cron_entrypoint.py --live-draft --confirm-live-draft
```

**Result:** ✅ No `--as-of-date` present. Production cron uses production default (current Europe/London date).

---

## Regression Check C: Hardcoded Date Strings in Source Files

### Command

```bash
grep -rn "2026-06-28" tools/shopify_publisher/orin/ --include="*.py"
```

### Result

**No matches** in any ORIN production pipeline file.

Note: `orin_phase2a_review_dryrun.py` had `print("Run date: 2026-06-28")` — **FIXED** (now uses `biz_today`).

---

## Regression Check D: Shopify and Queue Safety Confirmation

### Shopify touched across all test runs

| Test | Shopify touched |
|---|---|
| `--as-of-date 2026-06-28` dry-run | ❌ No |
| `--as-of-date 2026-07-04` dry-run | ❌ No |
| Current-date dry-run (2026-07-06) | ❌ No |

### Queue touched across all test runs

| Test | Queue touched |
|---|---|
| `--as-of-date 2026-06-28` dry-run | ❌ No |
| `--as-of-date 2026-07-04` dry-run | ❌ No |
| Current-date dry-run (2026-07-06) | ❌ No |

---

## Regression Check E: Canonical Business Date Source

| Property | Expected | Actual |
|---|---|---|
| Utility file | `business_time.py` exists | ✅ |
| Canonical timezone | `Europe/London` | ✅ `ZoneInfo("Europe/London")` |
| Production default | `datetime.now(ZoneInfo("Europe/London")).date()` | ✅ |
| as-of-date override | Supported | ✅ |
| State Agent uses `get_business_today()` | Yes | ✅ |
| Cron entrypoint uses `get_business_today(AS_OF_DATE)` | Yes | ✅ |
| All phase wrappers support `--as-of-date` | Yes | ✅ Phase 1A, 1B, 1C, 2A, 2B, 2D |
| Environment var propagation | `ORIN_BUSINESS_DATE` env var | ✅ |

---

## Regression Check F: Cron Delivery Configuration

| Property | Expected | Actual |
|---|---|---|
| `delivery.mode` | `none` | ✅ |
| `delivery.channel` | Not required (mode = none) | ✅ |
| Schedule | `0 9 * * *` | ✅ |
| Timezone | `Europe/London` | ✅ |
| Command | Unchanged | ✅ |
| Cron enabled | `true` | ✅ |
| Legacy cron 1 | `enabled: false` | ✅ |
| Legacy cron 2 | `enabled: false` | ✅ |

---

## Summary

| Regression Check | Result |
|---|---|
| No `date(2026, 6, 28)` in ORIN production files | ✅ PASS |
| No `2026-06-28` string literals in ORIN production files | ✅ PASS |
| Production cron has no `--as-of-date` | ✅ PASS |
| Business time utility has correct timezone | ✅ PASS |
| `get_business_today()` used as canonical source | ✅ PASS |
| All date-sensitive stages receive consistent date | ✅ PASS |
| Shopify untouched across all runs | ✅ PASS |
| Queue untouched across all runs | ✅ PASS |
| Cron delivery.mode = none | ✅ PASS |
| Legacy crons remain disabled | ✅ PASS |

**Overall regression check: PASS**
