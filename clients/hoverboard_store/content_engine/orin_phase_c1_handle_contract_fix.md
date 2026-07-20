# ORIN Phase C.1 — Planned Handle Contract Fix and Writer Plan Identity Hardening

**Phase:** C.1 — Handle Contract Fix
**Date:** 2026-07-07
**Run date for testing:** 2026-07-04
**Mode:** Dry-run / isolated test
**Status:** ✅ PHASE C.1 COMPLETE

---

## Goal

Fix the approved handle so every downstream ORIN phase uses exactly one canonical normalised handle, and harden the writer plan identity invariant.

---

## PHASE A — HANDLE SOURCE AUDIT

### Root Cause Found

| Field | Value |
|-------|-------|
| **Root cause** | `writer_agent._generate_slug()` used `r"\\s+"` (escaped backslash) instead of `r"\s+"`. In a raw string, `\\s` is the literal two characters `\` and `s`. The regex looked for literal `\s+` (backslash-s-plus) in the topic string, which never matched any whitespace. Spaces were never replaced with hyphens. |
| **Affected file** | `tools/shopify_publisher/orin/writer_agent.py` |
| **Affected line** | 49 |
| **Old code** | `slug = re.sub(r"\\s+", "-", slug).strip("-")` |
| **Correct code** | `re.sub(r"\s+", "-", slug)` (no extra backslash) |
| **Effect** | `approved_handle` output had spaces: `"hoverkart compatibility checklist before you buy"` instead of `"hoverkart-compatibility-checklist-before-you-buy"` |

### Competing Handle Generation Algorithms (Before Fix)

| Location | Function | Status |
|----------|----------|--------|
| `writer_agent.py` `_generate_slug()` | Lines 48-50 | **BROKEN** — `\\s+` bug |
| `job_context.py` `resolve_planned_handle()` | Lines 155-165 | Correct but separate algorithm |

`job_context.py`'s `resolve_planned_handle()` actually used `\s+` (correct), but it lived in a separate module. There were two independent implementations creating a risk of divergence.

### Search Results — All Handle Transformation Points

```
writer_agent.py:48        _generate_slug()          BROKEN (\\s+)
writer_agent.py:376       shopify_handle check      uses job_ctx value
writer_agent.py:398-400  approved_handle logic     calls _generate_slug
writer_agent.py:504       proposed_slug             derived from approved_handle
writer_agent.py:514       approved_handle in plan   output field
job_context.py:155        resolve_planned_handle()  correct but separate
job_context.py:164        slug generation           correct (\\s was NOT present)
state_agent.py:75,97,101  Shopify handle reads      from Shopify inventory
state_agent.py:155-166    read_approved_handles()   canonical approved handle store
```

### Spaces in Current Writer Plan (Before Fix)

The writer plan at `/tmp/orin_selected_job_writer_plan.json` showed:
- `approved_handle: "hoverkart compatibility checklist before you buy"` — **spaces present, not canonical**

---

## PHASE B — CANONICAL HANDLE UTILITY

### File Created

**`tools/shopify_publisher/orin/handle_utils.py`** — Single source of truth for handle operations.

### Functions Implemented

#### `normalise_shopify_handle(value: str) -> str`

Converts any input string to a canonical Shopify handle.

| Step | Operation |
|------|-----------|
| 1 | Lowercase |
| 2 | Strip leading/trailing whitespace |
| 3 | Keep only `a-z`, `0-9`, spaces, hyphens |
| 4 | Convert whitespace sequences to single hyphens |
| 5 | Collapse repeated hyphens |
| 6 | Strip leading/trailing hyphens |

#### `is_canonical_shopify_handle(value: str) -> bool`

Returns `True` if the handle is canonical:
- No spaces
- All lowercase (a-z only)
- No repeated hyphens (`--`)
- No leading hyphen
- No trailing hyphen
- Only `a-z0-9-`

#### `validate_or_raise_canonical_handle(handle: str, job_label: str) -> None`

Validates a handle is canonical. Raises `ValueError` with `BLOCK_INVALID_PLANNED_HANDLE` if not.

### Test Results

| Input | Output | Canonical |
|-------|--------|-----------|
| `"Hoverkart Compatibility Checklist Before You Buy"` | `"hoverkart-compatibility-checklist-before-you-buy"` | ✅ |
| `"Best Hoverboard Accessories: UK 2026"` | `"best-hoverboard-accessories-uk-2026"` | ✅ |
| `" Portable BBQ -- Guide "` | `"portable-bbq-guide"` | ✅ |
| `"hoverkart compatibility checklist"` (spaces) | — | ❌ fires `BLOCK_INVALID_PLANNED_HANDLE` |
| `"Hoverkart-Compatibility"` (uppercase) | — | ❌ fires `BLOCK_INVALID_PLANNED_HANDLE` |
| `"hoverkart--compatibility"` (double hyphen) | — | ❌ fires `BLOCK_INVALID_PLANNED_HANDLE` |
| `"-hoverkart"` (leading hyphen) | — | ❌ fires `BLOCK_INVALID_PLANNED_HANDLE` |

---

## PHASE C — HANDLE SOURCE OF TRUTH + INVARIANTS

### Fix 1: `writer_agent.py` — Replace `_generate_slug`

**Before (broken):**
```python
def _generate_slug(self, topic):
    slug = re.sub(r"[^a-z0-9\s-]", "", topic.lower())
    slug = re.sub(r"\\s+", "-", slug).strip("-")  # BUG: \\s+ matches literal
    return slug
```

**After (fixed):**
```python
def _generate_slug(self, topic):
    # Use canonical handle utility — single source of truth
    from handle_utils import normalise_shopify_handle
    return normalise_shopify_handle(topic)
```

### Fix 2: `writer_agent.py` — Canonical Handle Invariant

Added after `approved_handle` is set:

```python
from handle_utils import (
    is_canonical_shopify_handle,
    validate_or_raise_canonical_handle,
    BLOCK_INVALID_PLANNED_HANDLE,
)
validate_or_raise_canonical_handle(approved_handle, job_label=f"Job {job_number}")
```

If any `approved_handle` is not canonical, `BLOCK_INVALID_PLANNED_HANDLE` is raised before the plan is returned. No downstream phase can ever receive a non-canonical handle.

### Fix 3: `job_context.py` — Use Shared Utility

Updated `resolve_planned_handle()` to import from `handle_utils` instead of duplicating the regex logic.

### Handle Source Precedence (Defined)

| Priority | Source | When used |
|----------|--------|-----------|
| A | `job_ctx["shopify_handle"]` | If present and non-empty |
| B | `normalise_shopify_handle(topic)` | For new planned jobs with no Shopify handle |

### Identity Invariant Retained

```python
# In plan_writing() — pre-build check
expected_job_number = str(job_ctx.get("job_number", ""))
writer_plan = self._build_dynamic_writer_plan(job_ctx)
plan_job_number = str(writer_plan.get("job_number", ""))
if plan_job_number != expected_job_number:
    raise ValueError(f"{BLOCK_JOB_CONTEXT_MISMATCH}: ...")

# In _build_dynamic_writer_plan() — empty check
if not expected_job_number:
    raise ValueError(f"{BLOCK_JOB_CONTEXT_MISMATCH}: selected_job_context.job_number is empty ...")
```

---

## PHASE D — JOB 21 REGRESSION

### Test Command

```bash
cd /data/.openclaw/workspace
python3 tools/shopify_publisher/orin/orin_phase2c_writer_planning_dryrun.py --as-of-date 2026-07-04
```

### Results

| Check | Expected | Actual | Status |
|-------|----------|--------|--------|
| Selected job | 21 | 21 | ✅ |
| Writer plan title | Hoverkart Compatibility Checklist Before You Buy | Hoverkart Compatibility Checklist Before You Buy | ✅ |
| Old approved handle | spaces (broken) | `hoverkart compatibility checklist before you buy` | ❌ (before fix) |
| New approved handle | canonical hyphens | `hoverkart-compatibility-checklist-before-you-buy` | ✅ |
| Canonical validation | PASS | PASS | ✅ |
| Spaces in handle | No | No | ✅ |
| Uppercase in handle | No | No | ✅ |
| Repeated hyphens | No | No | ✅ |
| Job 20 leakage | No | No | ✅ |
| BLOCK_INVALID_PLANNED_HANDLE fires (spaces) | Yes | Yes | ✅ |
| BLOCK_INVALID_PLANNED_HANDLE fires (uppercase) | Yes | Yes | ✅ |
| BLOCK_INVALID_PLANNED_HANDLE fires (double hyphen) | Yes | Yes | ✅ |
| BLOCK_JOB_CONTEXT_MISMATCH fires (empty job) | Yes | Yes | ✅ |
| BLOCK_JOB_CONTEXT_MISMATCH invariant | retained | retained | ✅ |

---

## Proof — 23 Items

| # | Item | Result |
|---|------|--------|
| 1 | Handle root cause | `_generate_slug` used `r"\\s+"` — literal `\s+` never matched spaces. Fixed: replaced with `normalise_shopify_handle` from `handle_utils` |
| 2 | Existing competing handle generators count | **2** — `writer_agent._generate_slug` (broken) + `job_context.resolve_planned_handle` (correct but separate). Now **1** via `handle_utils` |
| 3 | Canonical handle utility path | `tools/shopify_publisher/orin/handle_utils.py` |
| 4 | Handle normalisation function | `normalise_shopify_handle(value)` |
| 5 | Handle validation function | `is_canonical_shopify_handle(value)` + `validate_or_raise_canonical_handle()` |
| 6 | Handle source precedence defined | **YES** — A. `shopify_handle` if present, B. `normalise_shopify_handle(topic)` |
| 7 | Writer plan canonical handle invariant added | **YES** — `validate_or_raise_canonical_handle(approved_handle)` fires before plan is returned |
| 8 | Writer plan job context invariant retained | **YES** — `BLOCK_JOB_CONTEXT_MISMATCH` in both `plan_writing` (pre-build) and `_build_dynamic_writer_plan` |
| 9 | Selected test job | **21** |
| 10 | Writer plan title | **Hoverkart Compatibility Checklist Before You Buy** |
| 11 | Old approved handle | `hoverkart compatibility checklist before you buy` (spaces — BROKEN) |
| 12 | New approved handle | `hoverkart-compatibility-checklist-before-you-buy` (canonical) ✅ |
| 13 | Canonical handle validation result | **PASS** ✅ |
| 14 | Spaces in new handle | **NO** ✅ |
| 15 | Uppercase in new handle | **NO** ✅ |
| 16 | Repeated hyphens | **NO** ✅ |
| 17 | Job 20 leakage | **NO** ✅ |
| 18 | HTML draft created | **NO** ✅ |
| 19 | Shopify touched | **NO** ✅ |
| 20 | Queue touched | **NO** ✅ |
| 21 | Cron enabled | **NO** (`enabled=false`) ✅ |
| 22 | Report path | `clients/hoverboard_store/content_engine/orin_phase_c1_handle_contract_fix.md` |
| 23 | Final decision | **PHASE C.1 COMPLETE — canonical handle contract established** |

---

## Files Modified

| File | Change |
|------|--------|
| `tools/shopify_publisher/orin/handle_utils.py` | **Created** — canonical handle utility with `normalise_shopify_handle`, `is_canonical_shopify_handle`, `validate_or_raise_canonical_handle`, `BLOCK_INVALID_PLANNED_HANDLE` |
| `tools/shopify_publisher/orin/writer_agent.py` | Fixed `_generate_slug` to use `normalise_shopify_handle`; added canonical handle invariant; added `BLOCK_INVALID_PLANNED_HANDLE` sentinel |
| `tools/shopify_publisher/orin/job_context.py` | Updated `resolve_planned_handle()` to use `normalise_shopify_handle` from `handle_utils` |

---

## Production Pipeline Safety

| Check | Result |
|-------|--------|
| Shopify articles touched | No ✅ |
| Queue file edited | No ✅ |
| Live cron re-enabled | No ✅ |
| HTML draft created | No ✅ |
| Cron enabled | No ✅ (`enabled=false`) |
| Non-canonical handle can exit Writer Planning | No ✅ (invariant blocks it) |
| Job 20 handle leaked | No ✅ |
| `simulated_job_20_plan` refs | 0 ✅ |

---

*Report generated by ORIN Phase C.1 — Planned Handle Contract Fix — no production files were modified except `writer_agent.py`, `job_context.py`, and new `handle_utils.py`.*
