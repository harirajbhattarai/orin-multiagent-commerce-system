# ORIN Phase H — Live-Draft Safety Gate v2

**Report Date:** 2026-07-08
**Phase:** H — Production Live-Draft Safety Gate v2
**Selected Job:** Job 21 — Hoverkart Compatibility Checklist Before You Buy

---

## 1. Production Cron Enabled

**No.** Production cron `c5c7e16b-5ee1-4855-ae7a-97fd25bfd67d` remains disabled throughout Phase H.

---

## 2. Old Live-Draft Block Source File

`tools/shopify_publisher/orin/cron_entrypoint.py`

---

## 3. Old Live-Draft Block Exact Condition

```python
# ── LIVE DRAFT (BLOCKED) ─────────────────────────────────────────────
return pipeline_blocked(
    "--live-draft is BLOCKED. Do not use until explicitly enabled."
)
```

Unconditionally returned regardless of pipeline state, job context, or any safety check. Blanket permanent block at the end of the live-draft path.

---

## 4. Old Block Classified Temporary

**No.** This is a **permanent blanket block** — not a Phase 3C temporary safety block. It was in the codebase before Phase H.

---

## 5. Shopify Draft Creation Function/Module

**Module:** `tools/shopify_publisher/publish_blog_draft.py`
**Function:** `main()` — accepts one argument: an HTML file path

| Field | How Provided | Controllable |
|---|---|---|
| HTML file path | CLI argument | Yes |
| Title | Extracted from HTML `<meta name="title">` | Yes (via HTML) |
| Handle/slug | Extracted from `<meta name="url_slug">` | Yes (via HTML) |
| Body HTML | Full HTML from file | Yes |
| Author | Hardcoded "Hoverboard Store" | No |
| `published` | Hardcoded `False` (draft mode only) | No — always draft |
| Tags | Hardcoded | No |
| `published_at` | **Not sent** | N/A — always draft |

---

## 6. Shopify Write Path Draft-Only Capable

**Yes.** `publish_blog_draft.py` hardcodes `published: False`. It only creates drafts. It never publishes.

---

## 7. `published_at` Null Controllable

**Yes.** `published_at` is not sent in the payload. Articles are created as hidden drafts with no `published_at` timestamp.

---

## 8. `body_html` Sent

**Yes.** The full HTML file content is read and sent as the article body.

---

## 9. Post-Fetch Body Hash Verification Capability Exists

**No.** `publish_blog_draft.py` does not fetch the created article after creation. It only logs success. Body hash verification is not implemented.

**Required sequence for implementation:**
1. Create Shopify draft
2. Fetch created article via Shopify API
3. Extract `body_html`
4. Compute SHA256
5. Compare with local Writer HTML SHA256

**Gate enforces:** `BLOCK_POST_FETCH_BODY_VERIFICATION_UNAVAILABLE` until this capability exists.

---

## 10. Live-Draft Gate Module Path

`tools/shopify_publisher/orin/live_draft_gate.py`

---

## 11. Gate Structured Decision Field

**Yes.** Gate returns structured JSON with `decision`, `approved`, `blockers[]`, `message`, and all required context fields.

---

## 12. Only `LIVE_DRAFT_WRITE_APPROVED` Authorises Write

**Yes.** Only one decision value (`LIVE_DRAFT_WRITE_APPROVED`) sets `approved: true`. All other decisions set `approved: false`.

---

## 13. CLI Live-Draft Intent Required

**Yes.** `--live-draft` flag must be present in argv.

---

## 14. CLI Confirmation Required

**Yes.** `--confirm-live-draft` flag must also be present. Both flags together trigger the gate. Absence of `--confirm-live-draft` returns `BLOCK_LIVE_DRAFT_CONFIRMATION_REQUIRED`.

---

## 15. Job-Context Invariants Implemented

**Yes.** Gate checks all five job number invariants:
- `writer_plan.job_number` == `selected_job_context.job_number`
- `writer_execution.job_number` == `selected_job_context.job_number`
- `post_write_review.job_number` == `selected_job_context.job_number`
- `html_validation.job_number` == `selected_job_context.job_number`
- `publisher_preflight.job_number` == `selected_job_context.job_number`

Failure: `BLOCK_JOB_CONTEXT_MISMATCH`

**Note:** For `no_writer_action` plans (where writer_plan has no top-level `job_number`), the gate also accepts `writer_plan.next_writing_candidate.job_number`.

---

## 16. Handle Invariant Implemented

**Yes.** Gate checks that `writer_plan.approved_handle`, `publisher_preflight.payload_preview.handle`, and `selected_job_context.shopify_handle` all agree.

Failure: `BLOCK_HANDLE_CONTEXT_MISMATCH`

---

## 17. Draft Path Invariant Implemented

**Yes.** Gate checks that the current local file path matches `writer_execution.output_path`.

Failure: `BLOCK_LOCAL_DRAFT_PATH_MISMATCH`

---

## 18. SHA256 Invariant Implemented

**Yes.** Gate computes current file SHA256 and compares with `writer_execution.sha256`.

Failure: `BLOCK_LOCAL_DRAFT_MUTATED_AFTER_WRITER`

---

## 19. Review Exact-Decision Gate Implemented

**Yes.** Review decision must equal exactly `POST_WRITE_REVIEW_PASSED`.

Failure: `BLOCK_REVIEW_GATE`

---

## 20. HTML Exact-Result Gate Implemented

**Yes.** HTML validation must return `validation_passed: true` AND `safe_for_publisher_preflight: true`.

Failure: `BLOCK_HTML_VALIDATION_GATE`

---

## 21. Publisher Exact-Decision Gate Implemented

**Yes.** Publisher decision must equal exactly `READY_TO_CREATE_SELECTED_JOB_DRAFT`.

Failure: `BLOCK_PUBLISHER_GATE`

---

## 22. Publisher Route Gate Implemented

**Yes.** For `READY_TO_CREATE_SELECTED_JOB_DRAFT`, publisher_route must equal `NEW_DRAFT_CREATION_ROUTE`. Any other route blocks.

Failure: `BLOCK_PUBLISHER_GATE`

---

## 23. Queue Planned-State Gate Implemented

**Yes.** Queue status must be `planned` for new draft creation.

Failure: `BLOCK_INVALID_QUEUE_STATE_FOR_DRAFT_CREATION`

---

## 24. Canonical Business Date Used

**Yes.** Gate uses `business_date` parameter (from `business_time.py`) not `date.today()` or hardcoded UTC date.

---

## 25. Due/Overdue Gate Implemented

**Yes.** Uses `business_time.py` `is_due()` with business date. Job must be due or overdue.

Failure: `BLOCK_JOB_NOT_DUE`

---

## 26. Draft-Only/`published_at`-Null Gate Implemented

**Yes.** Gate sets `published_at_required: null` and records the configuration. The H13 check is defined.

Failure: `BLOCK_PUBLISH_CONFIGURATION_UNSAFE`

---

## 27. Body Hash Verification Capability Gate Implemented

**Yes.** Gate returns `body_hash_verification_available: false` and blocks with `BLOCK_POST_FETCH_BODY_VERIFICATION_UNAVAILABLE` until verification is implemented.

---

## 28. Job 21 Gate Decision

`BLOCK_POST_FETCH_BODY_VERIFICATION_UNAVAILABLE`

---

## 29. Job 21 Gate Approved

`false`

---

## 30. Job 21 Gate Job Number

`21`

---

## 31. Job 21 Gate Title

`Hoverkart Compatibility Checklist Before You Buy`

---

## 32. Job 21 Gate Handle

`hoverkart-compatibility-checklist-before-you-buy`

---

## 33. Job 21 Local SHA256

`048234d6bde164c6d70986d994690537ca5d4423c4ed3014d2fe7a5889ad8049`

---

## 34–47. Regression Results

See: `orin_phase_h_live_draft_gate_regressions.md`

**Summary:** 12 applicable cases — all ✅ PASS. 0 failures. 0 false approvals.

| Case | Description | Result |
|---|---|---|
| 1 | No `--confirm-live-draft` | ✅ BLOCK_LIVE_DRAFT_CONFIRMATION_REQUIRED |
| 2 | Writer job mismatch | ✅ BLOCK_JOB_CONTEXT_MISMATCH |
| 3 | Draft SHA256 mismatch | ✅ BLOCK_LOCAL_DRAFT_MUTATED_AFTER_WRITER |
| 4 | Review = NEEDS_HUMAN_REVIEW | ✅ BLOCK_REVIEW_GATE |
| 5 | HTML = FAIL | ✅ BLOCK_HTML_VALIDATION_GATE |
| 6 | Publisher = ALREADY_CREATED_QUEUE_ALREADY_CORRECT | ✅ SAFE_STOP_ALREADY_CORRECT |
| 7 | Publisher = ALREADY_CREATED_QUEUE_RECONCILIATION_REQUIRED | ✅ QUEUE_RECONCILIATION_REQUIRED |
| 8 | Publisher = BLOCK_* | ✅ BLOCK_PUBLISHER_GATE |
| 9 | Unknown Publisher decision | ✅ BLOCK_PUBLISHER_GATE |
| 10 | Queue = draft_created | ✅ BLOCK_INVALID_QUEUE_STATE_FOR_DRAFT_CREATION |
| 11 | Job not due | ✅ BLOCK_JOB_NOT_DUE |
| 12 | published_at config unsafe | N/A (always null in current gate) |
| 13 | Body verification unavailable | ✅ BLOCK_POST_FETCH_BODY_VERIFICATION_UNAVAILABLE |

---

## 48. cron_entrypoint Gate v2 Integrated

**Yes.** Gate is called in `cron_entrypoint.py` after Publisher preflight (Phase 2E/2G) and before any Shopify write path. It is positioned after `publisher_passed` check and before the live-draft write branch.

---

## 49. Old Blanket Live-Draft Block Removed

**Yes.** The permanent blanket block at lines 548–552 has been replaced with the Gate v2 integration code.

---

## 50. Phase H Stop-Before-Write Gate Active

**Yes.** When Gate returns `LIVE_DRAFT_WRITE_APPROVED`, the integration code records the approval and stops before calling `publish_blog_draft.py`. The Phase H stop is explicitly coded.

---

## 51. Production Cron Contains `--live-draft`

**No.** Production cron does not contain `--live-draft`. Both `--live-draft` and `--confirm-live-draft` are absent from the production cron command.

---

## 52. Production Cron Contains `--confirm-live-draft`

**No.** See above.

---

## 53. Production Cron Contains `--as-of-date`

**No.** Production cron does not contain `--as-of-date`.

---

## 54. Legacy Cron 1 Disabled

**Yes.** Cron `c5c7e16b-5ee1-4855-ae7a-97fd25bfd67d` is disabled.

---

## 55. Legacy Cron 2 Disabled

N/A — only one production cron is in use.

---

## 56. Shopify Touched

**No.** Zero Shopify writes during Phase H.

---

## 57. Queue Touched

**No.** Queue file was not modified.

---

## 58. Cron Touched During Phase H

**No.** No cron modifications were made.

---

## 59. Cron Enabled at End

**No.** Production cron remains disabled.

---

## 60. Gate Report Path

`clients/hoverboard_store/content_engine/orin_phase_h_live_draft_gate_v2.md`

---

## 61. Regression Report Path

`clients/hoverboard_store/content_engine/orin_phase_h_live_draft_gate_regressions.md`

---

## 62. Final Phase H Decision

**BLOCK_POST_FETCH_BODY_VERIFICATION_UNAVAILABLE** — Phase H gate correctly stops the pipeline at H11 because post-fetch body hash verification is not yet implemented. All other gates H1–H10 pass.

**Phase H stop gate is active.** Shopify write will not execute. Body verification implementation is required before `LIVE_DRAFT_WRITE_APPROVED` can be returned.

---

## Integration Evidence

**Gate position in `cron_entrypoint.py`:** After Phase 2E/2G Publisher preflight + `publisher_passed` check, before live-draft write path.

**Gate called with canonical inputs:**
- `selected_job_context` from pipeline job object
- `writer_plan` from `/tmp/orin_phase2c_writer_plan_preview.json`
- `writer_execution` from `/tmp/orin_job21_writer_execution_preview.json`
- `post_write_review` from `/tmp/orin_selected_job_post_write_review.json`
- `html_validation` from `/tmp/orin_selected_job_html_validation.json`
- `publisher_preflight` from Phase 2E result + `/tmp/orin_phase2e_publisher_preview.json`
- `publisher_route` from canonical `publisher_route` variable
- `business_date` from `BUSINESS_TODAY` (Europe/London, `--as-of-date` aware)

**Phase H stop recorded:**
```python
print("  🛑 PHASE H STOP — LIVE_DRAFT_WRITE_APPROVED recorded.")
print("  🛑 Phase H dry-run: Shopify write NOT executed.")
```
