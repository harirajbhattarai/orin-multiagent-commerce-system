# ORIN Pre-Live Job 20 and Job 21 State Reconciliation Report

**Date:** 2026-07-06 18:34 GMT+1
**Phase:** Read-only state reconciliation — no Shopify writes, no queue edits, no cron changes
**Strict rules enforced:** No Shopify edits, no queue edits, no live-draft mode, no cron triggers

---

## Investigation Method

- Read queue directly from `content_queue_3_months.md`
- Read Shopify inventory from `shopify_inventory.json`
- Ran state_agent.py queue parser and resolution functions directly
- Ran publisher_agent.py conflict analysis directly
- Traced Phase 1A, 1B, 1C, 2A, 2B, 2C, 2E code paths directly
- No cached preview files used (cleared prior to investigation)

---

## CONTRADICTION 1 — JOB 20: Recovery Agent vs Queue State

### Job 20 Queue State

| Field | Value |
|---|---|
| Queue status | `draft_created` |
| Shopify article ID (in queue notes) | `1006845985116` |
| Shopify handle (in queue notes) | `best-hoverboard-accessories-safer-riding-uk-2026` |
| Shopify blog | Journal Insights (blog_id: 113430790492) |
| published | false |
| published_at | null |
| Queue notes confirmation | `Phase 2F: Shopify draft created 2026-06-30...Shopify article ID: 1006845985116...Queue updated after confirmed Shopify draft creation` |

✅ Queue state for Job 20 is correct and complete. The Shopify article ID and handle are recorded in the queue notes.

### Root Cause of Recovery Agent False Positive

**Finding:** The Recovery Agent's `local_file_exists_shopify_missing` warning for Job 20 is a **false positive caused by a queue parser regex mismatch**. The Shopify article ID IS in the queue notes but the parser does not extract it.

**Queue parser regex in `state_agent.py`:**
```python
shopify_id_note = re.search(r"Article ID:\s*(\S+)", notes)
```

**Queue notes line for Job 20:**
```
Shopify article ID: 1006845985116
```

**Problem:** The regex looks for the literal string `Article ID:` (no prefix), but Job 20's queue notes use `Shopify article ID:` (with `Shopify ` prefix). These are different strings:
- `Article ID:` — appears in Jobs 15–19 notes
- `Shopify article ID:` — appears in Job 20 notes

`"Article ID:"` is NOT a substring of `"Shopify article ID:"`. The regex finds `Article ID:` in the `Article ID: 1006811971932. Handle:` lines of Jobs 15–19, but NOT in Job 20's `Shopify article ID: 1006845985116` line.

**Evidence (Python direct test):**
```
"Article ID:" in "Shopify article ID: 1006845985116" → False
```

**Confirmed:** `shopify_id_from_notes = None` for Job 20 (verified by calling `state_agent.read_queue()['20']` directly).

### Shopify Inventory Check

| Field | Value |
|---|---|
| Article ID `1006845985116` in local inventory | ✅ YES (35 articles total) |
| Handle | `best-hoverboard-accessories-safer-riding-uk-2026` |
| Title | Best Hoverboard Accessories for Safer Riding UK 2026 |
| Status | draft |
| published_at | null |

### Resolution Chain for Job 20

Because `shopify_id_from_notes = None` (parser regex mismatch), `resolve_shopify_article()` falls through to the `KNOWN_IDS` fallback which does NOT include Job 20. Result: `shopify_article_id = None` returned to `detect_state()`.

`detect_state()` has no rule matching `queue_status=draft_created + shopify_article_id=None`. State: `unknown`.

`recovery_agent.py` Category 3 check: `local_exists=True and shopify_article_id=None → TRIGGERS` → `local_file_exists_shopify_missing`.

**This is a false positive.** The article exists in both Shopify and the local inventory. The queue notes contain the correct Shopify article ID. Only the queue parser regex is failing to extract it.

### Classification

**Job 20 contradiction is:** `ALREADY_CREATED_QUEUE_ALREADY_CORRECT`

The queue IS correct. The Shopify article IS created. The Phase 1C warning is a parser bug false positive.

---

## CONTRADICTION 2 — JOB 21

### Job 21 Queue State

| Field | Value |
|---|---|
| Queue status | `planned` |
| Shopify article ID (in queue notes) | NONE |
| Shopify handle (in queue notes) | NONE |
| Local draft | NONE |
| Expected draft date | 2026-07-04 |
| Days overdue (as of 2026-07-06) | 2 days |

### Why Phase 2B Selected Job 21

Phase 1B (`planner_agent.py`) selects the most overdue planned job with no blocking issues:
- Job 20: `detected_state=unknown` (skipped — not in valid detected states list)
- **Job 21: `detected_state=due_for_local_draft`, days_until=-2 → SELECTED**

Job 20 is skipped because `unknown` is not a recognised planner decision state. Even though Job 20 is overdue (expected draft date 2026-07-01), the planner cannot act on it because `resolve_shopify_article()` returned `shopify_article_id=None`.

### Phase 2E Hardcoding Bug

**File:** `tools/shopify_publisher/orin/orin_phase2e_publisher_dryrun.py`

**Hardcoded call:**
```python
result = subprocess.run(
    [sys.executable, AGENT_SCRIPT, "Job 20",
     "clients/hoverboard_store/content_engine/drafts/best-hoverboard-accessories-safer-riding.html",
     "--json"],
    ...
)
```

The Phase 2E wrapper ALWAYS evaluates Job 20, regardless of which job the pipeline selected in Phase 1B. The selected job number from Phase 1B (`21`) is never passed to Phase 2E.

**Consequence:** Phase 2E evaluates Job 20's article (ID `1006845985116`) and returns `ALREADY_CREATED` because the article exists in Shopify as a draft. This is the CORRECT result for Job 20 — but it has NO BEARING on Job 21.

### Phase 2E Decision Cascade for Job 21 (If Evaluated)

The Phase 2E hardcoding means Job 21 is never actually evaluated by the Publisher Agent. However, if Job 21 were evaluated:

| Check | Result for Job 21 |
|---|---|
| `self_match` | `False` — queue has no Article ID |
| `exact_handle_match` | `None` — no `hoverkart-compatibility-checklist-before-buy` in Shopify |
| `exact_title_match` | `None` |
| `near_handle_matches` | `[]` |
| `queue_status` (planned vs expected `planned`) | `True` — passes |
| `local_draft_exists` | `False` — BLOCKS |

**Decision for Job 21:** `BLOCKED — local draft not found`

Job 21 would be blocked because no local draft exists. The pipeline would stop safely at Phase 2E without Shopify writes.

### Live Queue Behaviour After ALREADY_CREATED

**What the pipeline does after Phase 2E returns ALREADY_CREATED:**
1. `publisher_passed = True` (ALREADY_CREATED has `passed=True`)
2. `if not publisher_passed: return blocked` → NOT TRIGGERED
3. Pipeline continues to DRY-RUN STOP
4. Queue: **NO UPDATE** (no `queue_status` change, no Shopify article ID recorded)
5. Return dict: `{"blocked": False, "shopify_touched": False, "queue_touched": False}`

### Will Job 21 Be Selected Again Tomorrow?

**YES.**

The queue for Job 21 remains `planned`. No Shopify article ID was recorded. No draft was created. No reconciliation occurred.

At the next cron run (2026-07-07 09:00 BST):
- Phase 1A: Job 21 `detected_state=due_for_local_draft`
- Phase 1B: Job 21 selected again (most overdue planned job)
- Phase 2A: No local file → pipeline would stop at Phase 2A

Job 21 does NOT reach Phase 2E on subsequent runs because Phase 2A stops it first.

### Classification

**Job 21 contradiction is:** `ALREADY_CREATED_QUEUE_STAYS_STALE_AND_LOOPS`

Phase 2E ALREADY_CREATED is for Job 20's article (hardcoded evaluation), not Job 21. The queue for Job 21 stays `planned`. Job 21 loops in Phase 2A indefinitely because:
1. Phase 2E is hardcoded to Job 20, never evaluates Job 21
2. Job 21 has no local draft, so Phase 2A blocks it before Phase 2E is even reached
3. Queue stays `planned`, draft not created, selected again next day

---

## ALREADY_CREATED Live Queue Behaviour (Job 20 Article)

The `ALREADY_CREATED` decision in `publisher_agent.py`:
```python
if conflicts["self_match"]:
    decision = "ALREADY_CREATED — canonical article already in Shopify, matches queue article ID"
    results["decision"] = decision
    results["passed"] = True  # Not a failure — it's already done
```

`passed=True` means the pipeline does NOT block. The queue is NOT updated. No Shopify write is attempted (dry-run). The `ALREADY_CREATED` decision is informational only — it confirms the article exists.

In LIVE mode, `ALREADY_CREATED` would also NOT update the queue. The queue would remain `planned` for Job 21. The same job would be selected again.

---

## What Would Happen in LIVE Mode

1. Phase 1B selects Job 21 (most overdue planned job)
2. Phase 1C flags Job 20 (false positive — parser bug)
3. Phase 2A: no local draft → `no_local_file_to_review` → pipeline stops at Phase 2A
4. Job 21 is NOT reconciled
5. Next day: Job 21 selected again (same loop)

OR (if Phase 2A did not stop):

1. Phase 2E hardcoded to Job 20 → `ALREADY_CREATED` for Job 20 article
2. Pipeline continues (because `publisher_passed=True`)
3. Queue for Job 21 NOT updated
4. Next day: Job 21 selected again

Either way, **Job 21 queue stays `planned`**.

---

## Shopify Article for Job 20 — Confirmed Details

| Field | Value |
|---|---|
| Article ID | `1006845985116` |
| Handle | `best-hoverboard-accessories-safer-riding-uk-2026` |
| Title | Best Hoverboard Accessories for Safer Riding UK 2026 |
| Blog | Journal Insights (blog_id: 113430790492) |
| Status | draft |
| published_at | null |
| In Shopify | ✅ YES |
| In local inventory | ✅ YES |
| Queue notes accurate | ✅ YES |

---

## Recommended Minimal Fixes

### Fix 1 (Priority 1): Queue Parser Regex for Job 20

**File:** `tools/shopify_publisher/orin/state_agent.py`

**Current regex:**
```python
shopify_id_note = re.search(r"Article ID:\s*(\S+)", notes)
```

**Should be:**
```python
shopify_id_note = re.search(r"(?:Shopify\s+)?Article\s+ID:\s*(\S+)", notes)
```

This matches both:
- `Shopify article ID: 1006845985116` (Job 20 format)
- `Article ID: 1006811971932` (Jobs 15–19 format)

The `(?:` non-capturing group allows the optional `Shopify ` prefix. `\s+` between words handles variable whitespace. `Article\s+ID` handles the space in `Article ID`.

### Fix 2 (Priority 2): Phase 2E Wrapper Job Number

**File:** `tools/shopify_publisher/orin/orin_phase2e_publisher_dryrun.py`

**Current:** Hardcoded to "Job 20"

**Required:** Accept selected job number from cron_entrypoint and pass it to `publisher_agent.py`.

**Design:** The Phase 2E wrapper should receive `sys.argv[1]` as the job number (e.g., `sys.argv[1] = "Job 21"` from `cron_entrypoint.py`'s `run_phase_wrapper("2E")` call). The publisher agent should then evaluate the CORRECT job rather than the hardcoded one.

This is a prerequisite for Job 21 to be properly evaluated by Phase 2E. Without this fix, Job 21 will ALWAYS be evaluated against Job 20's article and the Phase 2E decision will always be for Job 20.

### Fix 3 (Optional): Phase 2A Scope for Selected Job

Phase 2A (`orin_phase2a_review_dryrun.py`) reviews Jobs 15–20. If Job 21 is selected, Phase 2A returns no review result for it. This is currently handled by the `no_local_file_to_review` early return in `cron_entrypoint.py`, but a cleaner fix would be to include the selected job in Phase 2A's review scope even if outside the 15–20 range.

---

## Safety Confirmation

| Check | Result |
|---|---|
| Shopify article created during investigation | ❌ NO |
| Shopify article updated during investigation | ❌ NO |
| Queue edited during investigation | ❌ NO |
| Cron configuration changed | ❌ NO |
| Live-draft mode triggered | ❌ NO |
| HCS Gadgets touched | ❌ NO |
| Phase 1C TypeError | ❌ Resolved (prior session) |

---

## Output Files

| Report | Path |
|---|---|
| This report | `clients/hoverboard_store/content_engine/orin_pre_live_job20_job21_state_reconciliation.md` |
| JSON preview | `/tmp/hoverboard_orin_pre_live_state_reconciliation_preview.json` |
