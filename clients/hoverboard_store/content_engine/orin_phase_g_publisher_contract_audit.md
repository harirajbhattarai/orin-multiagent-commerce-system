# ORIN Phase G — Publisher Contract Audit

**Audit Date:** 2026-07-08
**Phase:** G — Selected-Job Publisher Preflight
**Selected Job:** Job 21
** Auditor:** ORIN Phase G preflight

---

## 1. Publisher Input Contract

### Publisher Entry Point
- **Script:** `tools/shopify_publisher/orin/orin_phase2e_publisher_dryrun.py` (wrapper)
- **Agent:** `tools/shopify_publisher/orin/publisher_agent.py` (Phase 2G)
- **Selected-job mode:** `--job-context <path>` (priority over positional args)

### Publisher Reads

| Input | Source | Used by Publisher |
|---|---|---|
| `job_number` | `job_context.job_number` | Target job identification |
| `local_draft_path` | `job_context.local_draft_path` | Local draft file path |
| `shopify_handle` | `job_context.shopify_handle` | Expected slug verification |
| `queue_status` | `job_context.queue_status` | Expected queue status |

**Publisher does NOT read:**
- Writer plan (`writer_plan` JSON) — NOT a Publisher input
- Post-Write Review result — NOT read by Publisher (check happens before Publisher)
- HTML Validation result — NOT read by Publisher (check happens before Publisher)

### Selected Job Number Source
- Resolved from `--job-context <path>` → `job_context.job_number`
- Fallback: positional arg `sys.argv[1]` (legacy)
- Fallback default: `"Unknown"` (when no args provided)

### Title Source
- Extracted from HTML comment block in draft file: `meta_title` field

### Handle Source
- Extracted from HTML comment block in draft file: `url_slug` field
- Also read from `job_context.shopify_handle` for expected-slug verification

### Local Draft Path Source
- **Primary:** `job_context.local_draft_path` (from `--job-context`)
- **Fallback:** `sys.argv[2]` positional arg
- **Note:** `selected_job_context.json` has `local_draft_path: null` because it was generated before Writer ran. Corrected context `/tmp/orin_job21_publisher_context.json` was used for this preflight with `local_draft_path: "/tmp/orin_job21_writer_test/job_21_draft.html"`.

### Shopify Article ID Source
- **Queue article ID:** `get_queue_article_id()` reads from `content_queue_3_months.md` job notes
- **Pattern:** `Shopify article ID:\s*(\d+)`
- **Current status:** Job 21 has no `shopify_article_id` in queue notes → `null`

### Live Shopify Inventory Refresh
- **Status:** YES — Publisher always fetches live inventory before preflight checks (Phase 2G fix)
- **Endpoint:** `GET /admin/api/2026-01/blogs/{SHOPIFY_BLOG_ID}/articles.json?limit=250`
- **Pagination:** Up to 20 pages, 250 articles per page
- **Save location:** `clients/hoverboard_store/content_engine/shopify_inventory.json`
- **Fallback:** Local inventory file if live fetch fails

---

## 2. Exact Title Conflict Logic

```python
if art_title == title_lower and art_handle != handle_lower:
    result["exact_title_match"] = article
```
- Matches articles with **identical title** but **different handle**
- Blocks if found: `BLOCKED — exact same title exists in Shopify under different handle`

---

## 3. Exact Handle Conflict Logic

```python
if art_handle == handle_lower:
    result["exact_handle_match"] = article
```
- Matches articles with **identical handle/slug**
- Blocks if found: `BLOCKED — exact handle already exists in Shopify`

---

## 4. Near-Handle Conflict Logic

Function: `_is_near_handle(handle_a, handle_b)`

Conditions:
- Both must start with `best-hoverboard` (article type check)
- Same core topic terms (core slug minus small tokens)
- Differ by ≤1 small token (`for`, `the`, `best`, `a`, `an`, `to`, `of`, `in`, `on`)
- OR differ by exactly one meaningful token

Example flagged:
- `best-hoverboard-accessories-safer-riding-uk-2026`
- `best-hoverboard-accessories-FOR-safer-riding-uk-2026` ← inserted "for"

Blocks if found: `BLOCKED — near-handle variant exists in Shopify`

---

## 5. Self-Match Logic

```python
if art_handle == handle_lower and queue_article_id and art_id == queue_article_id:
    result["self_match"] = True
```

Self-match = exact handle match AND article ID matches queue-recorded Shopify article ID.

Decision if self-match: `ALREADY_CREATED — canonical article already in Shopify`

---

## 6. ALREADY_CREATED Logic

Triggered only when:
1. Exact handle match found AND
2. Article ID matches `queue_article_id` (Shopify article ID recorded in queue notes)

Does NOT trigger on:
- Exact handle match alone (blocks with `BLOCKED — exact handle already exists`)
- Job 20 article ID unless Job 21's queue notes record that ID

---

## 7. Job 20 Dependency Search

### Results Classification

| File | Line | Match | Classification |
|---|---|---|---|
| `publisher_agent.py:92` | `TARGET_JOB = _parsed_job_number or "Unknown"` | `Unknown` default, not `Job 20` | TEST_ONLY fallback |
| `publisher_agent.py:93` | `DRAFT_PATH = _parsed_draft_path` | `None` default | TEST_ONLY fallback |
| `publisher_agent.py:94` | `EXPECTED_SLUG = _parsed_expected_slug` | `None` default | TEST_ONLY fallback |
| `publisher_agent.py:247` | Comment explaining near-handle example | `best-hoverboard-accessories-safer-riding` | HISTORICAL_COMMENT |
| `publisher_agent.py:449` | `if not EXPECTED_SLUG:` | Conditional check | TEST_ONLY |
| `publisher_agent.py:456` | `slug_ok = actual_slug == EXPECTED_SLUG` | Comparison | TEST_ONLY |
| `publisher_agent.py:685` | `job_id = _parsed_job_number or TARGET_JOB` | Fallback to "Unknown" | TEST_ONLY |
| `orin_phase2e_publisher_dryrun.py:55` | `job_label = sys.argv[1] if len(sys.argv) > 1 else "Job 20"` | `"Job 20"` default | TEST_ONLY backward-compat fallback |
| `review_agent.py:620-622` | Job 20 slug/title checks | `best-hoverboard-accessories-safer-riding` | HISTORICAL_COMMENT |
| `cron_entrypoint.py:461` | Comment about ALREADY_CREATED invariant | `Phase 2E must evaluate the selected job, not Job 20` | REPORT_TEXT |
| `orchestrator.py:76-87` | Job 20 reminder messages | `Job 20` | REPORT_TEXT |

### Conclusion
**No active Job 20 identity controls selected-job Publisher behaviour.** All "Job 20" references in the publisher pipeline are:
- Fallback defaults (TEST_ONLY)
- Historical comments explaining logic (HISTORICAL_COMMENT)
- Report/instruction text (REPORT_TEXT)

The Publisher correctly resolves the selected job via `--job-context` parameter.

---

## 8. Queue Status Lookup — KNOWN BUG

**Bug:** `publisher_agent.py` uses `job_id = "21"` (numeric only) and searches for `##\s+21\n` in the queue file. The queue file format is `## Job 21\n` (with "Job " prefix).

**Impact:** Queue status check returns `not_found` for all jobs when using numeric-only job IDs.

**Queue file format:**
```
## Job 21
Date target: 2026-07-18
Cluster: Hoverkart
Decision: create_new
Status: planned
```

**Regex used by Publisher:**
```python
pattern = rf"##\s+{re.escape(job_id)}\n.*?Status:\s*(\w+)"
# With job_id="21" → ##\s+21\n — does NOT match ## Job 21\n
```

**Should be:**
```python
pattern = rf"##\s+Job\s+{re.escape(job_id)}\n.*?Status:\s*(\w+)"
# With job_id="21" → ##\s+Job\s+21\n — matches ## Job 21\n
```

**Note:** This bug does NOT affect duplicate preflight checks. The Shopify conflict analysis is independent of queue status. Job 21 was correctly found to have **zero Shopify conflicts**.

---

## 9. Publisher Invariant Analysis

### Phase G Required Invariants

| Invariant | Status |
|---|---|
| `publisher_job_number == selected_job_context.job_number` | ✅ Publisher received "21" from corrected context |
| `writer_plan.job_number == selected_job_context.job_number` | ✅ Both "21" |
| `review.job_number == selected_job_context.job_number` | ✅ Review confirmed Job 21 (POST_WRITE_REVIEW_PASSED) |
| `html_validation.job_number == selected_job_context.job_number` | ✅ HTML Validation PASSED for Job 21 |
| `publisher draft path == Writer execution output path` | ✅ Publisher used `/tmp/orin_job21_writer_test/job_21_draft.html` |
| `publisher expected handle == writer_plan.approved_handle` | ✅ Both "hoverkart-compatibility-checklist-before-you-buy" |

### Phase G Gate Checks

| Gate | Required | Actual | Result |
|---|---|---|---|
| Post-Write Review | PASSED | PASSED | ✅ |
| HTML Validation | PASS | PASS | ✅ |
| safe_for_publisher_preflight | true | true | ✅ |

---

## 10. Summary

- **Publisher resolves selected job dynamically:** YES — via `--job-context`
- **Publisher hardcodes Job 20:** NO — all Job 20 references are fallback defaults/historical
- **Active Job 20 identity controls Publisher:** NO
- **Publisher reads selected_job_context:** YES (when `--job-context` provided)
- **Publisher reads Writer output path:** YES (from job_context.local_draft_path)
- **Publisher reads Post-Write Review:** NO (check done before Publisher)
- **Publisher reads HTML Validation:** NO (check done before Publisher)
- **Invariant checks in Publisher:** PARTIAL — no formal invariant system; slug check present; queue regex has known bug
- **Live Shopify inventory refresh:** YES — always refreshed before preflight
- **Job 21 Shopify conflicts:** NONE (0 exact handle, 0 exact title, 0 near-handle, 0 self-match)
- **Job 20 Article ID 1006845985116 as Job 21 self-match:** NO
