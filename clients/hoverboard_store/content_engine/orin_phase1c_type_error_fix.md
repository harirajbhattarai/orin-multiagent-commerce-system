# ORIN Phase 1C Type Error Root Cause and Fix Report

**Inspection date:** 2026-07-06
**Phase:** Phase 1C Type Error Fix — Root Cause Analysis + Minimal Fix
**Strict rules:** No Shopify edits, no queue edits, no live cron runs

---

## Phase A — Error Reproduction

### Command

```
python3 tools/shopify_publisher/orin/cron_entrypoint.py --dry-run --as-of-date 2026-07-04
```

### Confirmed output

```
[16:27:50] Running Phase 1C (orin_phase1c_recovery_dryrun.py)...
[16:27:50]   ⚠️  Phase 1C error (non-blocking): Phase 1C: expected str, bytes or os.PathLike object, not int
[16:27:50]   Phase 1C complete — 0 active recovery items
```

### Confirmed: TypeError reproduced ✅

---

## Phase A — Root Cause Analysis

### Method

Added debug tracing to `cron_entrypoint.py`'s `run_phase_wrapper` function to capture the exact subprocess call arguments.

### Key debug output

```
DEBUG ARGS[1C]: ['/usr/bin/python3', '/data/.../orin_phase1c_recovery_dryrun.py', 21]
```

### Root cause value: `21` (integer)

### Root cause Python type: `int`

### Root cause explanation

In `cron_entrypoint.py`, Phase 1B returns `planner.get("selected_job_number")`, which returns an **integer** (`21`), not a string (`"21"`).

When Phase 1C is called:

```python
job_num = selected_job  # integer: 21
...
phase1c, err1c = run_phase_wrapper("1C", [job_num])
#                              ↑ integer 21 passed as subprocess arg
```

Python's `subprocess.run()` requires all elements in the `args` list to be strings, bytes, or `os.PathLike` objects. An integer is not valid. This causes:

```
TypeError: expected str, bytes or os.PathLike object, not int
```

The error occurred **inside `subprocess.run()` itself**, in `subprocess.py`'s `Popen.__init__` → `_execute_child`, before the subprocess even started.

### Why Phase 1C appeared to work when run directly

When Phase 1C was tested directly with:
```
python3 .../orin_phase1c_recovery_dryrun.py --as-of-date 2026-07-04
```
The Phase 1C wrapper **ignores positional arguments** (`sys.argv[1:]` is not used for job selection — it always audits Jobs 15–20). The error only manifested when `cron_entrypoint.py` passed `21` as a subprocess argument.

### Exact file

`tools/shopify_publisher/orin/cron_entrypoint.py`

### Exact line

Line 347 (before fix):
```python
phase1c, err1c = run_phase_wrapper("1C", [job_num])
#                                                ↑ integer 21
```

---

## Phase B — Minimal Fix

### Fix applied

```python
# Before:
phase1c, err1c = run_phase_wrapper("1C", [job_num])

# After:
phase1c, err1c = run_phase_wrapper("1C", [str(job_num)])
```

### Design decisions

1. **Convert at the call site** — `str(job_num)` at the `run_phase_wrapper` call. This is the smallest possible change.

2. **Do NOT change `selected_job_number`** — The planner returns an integer for `selected_job_number`. This is consistent with `planner_agent.py` which uses integer job numbers internally. Changing it would require changes across multiple call sites.

3. **Only affects subprocess args** — The `str()` conversion is applied only when building the subprocess argument list. All other uses of `job_num` (comparisons, queue lookups) already use `str(j["job_number"]) == str(job_num)` or equivalent guards.

4. **No broad exception suppression** — No try/except was added. The fix removes the cause of the TypeError entirely.

5. **No changes to `recovery_agent.py`, `state_agent.py`, or any agent logic** — The issue was purely in how `cron_entrypoint.py` passed arguments to its subprocesses.

### Files changed

| File | Change |
|---|---|
| `tools/shopify_publisher/orin/cron_entrypoint.py` | `[job_num]` → `[str(job_num)]` on Phase 1C subprocess call |

### Regression check added

The debug output in `run_phase_wrapper` (removed after fix) confirmed all phase args are properly typed strings after the fix. A type-checking assertion could be added:

```python
# Optional future guard in run_phase_wrapper:
for arg in extra_args or []:
    if not isinstance(arg, (str, bytes)):
        raise TypeError(f"subprocess arg must be str/bytes, got {type(arg).__name__}: {arg!r}")
```

This is optional — the fix ensures `str(job_num)` is always passed.

---

## Phase C — Phase 1C Regression

### Test A: Current date (2026-07-06) — Phase 1C dry-run

```
Run date: 2026-07-06
Jobs audited: 6
Active recovery: 1
Phase 1D Readiness: [FAIL] — 1 active recovery item (Job 20)
TypeError: NONE
```

✅ No TypeError. Phase 1C completes cleanly.

### Test B: `--as-of-date 2026-07-04` — Phase 1C dry-run

```
Run date: 2026-07-04
Jobs audited: 6
Active recovery: 1
Phase 1D Readiness: [FAIL] — 1 active recovery item (Job 20)
TypeError: NONE
```

✅ No TypeError. Phase 1C completes cleanly.

---

## Phase D — Full Pipeline Pre-Live Dry-Run (Current Date)

### Command

```
python3 tools/shopify_publisher/orin/cron_entrypoint.py --dry-run --json
```

### Results

| Phase | Result |
|---|---|
| Business date | 2026-07-06 (Europe/London) |
| Phase 1A | ✅ 6 jobs analysed |
| Phase 1B | ✅ `job_selected`, Job 21 selected |
| Phase 1C | ✅ `1 active recovery item` — **NO TypeError** |
| Phase 2A | ✅ PASS |
| Phase 2B | ✅ PASS |
| Phase 2D | ✅ PASS |
| Phase 2E | ✅ PASS — `ALREADY_CREATED` |
| Final | DRY-RUN COMPLETE |
| Shopify touched | ❌ No |
| Queue touched | ❌ No |

---

## Phase E — Summary

| Check | Status |
|---|---|
| TypeError reproduced | ✅ Yes |
| Exact file | `cron_entrypoint.py` |
| Exact line | Line 347 |
| Root cause value | `21` (integer `job_num`) |
| Root cause type | `int` |
| Root cause explanation | `subprocess.run()` requires str/bytes/PathLike args; integer 21 is invalid |
| Files changed | 1 (`cron_entrypoint.py`) |
| Broad exception suppression added | ❌ No |
| Phase 1C current-date result | ✅ Clean — 1 active recovery item |
| Phase 1C TypeError after fix | ❌ No TypeError |
| Full pipeline clean | ✅ Yes |
| Shopify untouched | ✅ Yes |
| Queue untouched | ✅ Yes |
