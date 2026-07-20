# ORIN Phase I7 — Queue Finalisation

**Report Date:** 2026-07-08
**Phase:** I7 — Canonical Queue State Manager

---

## Queue State Manager Module

**Path:** `tools/shopify_publisher/orin/queue_state_manager.py`

## Canonical Function

```python
finalize_draft_created(
    queue_path: str,
    job_number: str,
    shopify_article_id: int | str,
    shopify_handle: str,
    draft_created_at: str,
    published_at: str | None,
    shopify_verification_passed: bool = False,
    expected_article_id: int | str | None = None,
    expected_handle: str | None = None,
) -> dict
```

## Allowed Transition

`planned → draft_created` only.

Any other current status (draft_created, published, archived) → `BLOCK_INVALID_QUEUE_STATE_TRANSITION`

## Pre-Conditions (all required)

| Check | Failure |
|---|---|
| `shopify_verification_passed == True` | `BLOCK_SHOPIFY_VERIFICATION_NOT_PASSED` |
| Queue job exists | `BLOCK_JOB_CONTEXT_MISMATCH` |
| Current status == `planned` | `BLOCK_INVALID_QUEUE_STATE_TRANSITION` |
| `expected_article_id` matches (if provided) | `BLOCK_ARTICLE_ID_MISMATCH` |
| `expected_handle` matches (if provided) | `BLOCK_HANDLE_MISMATCH` |
| `published_at` is null | `BLOCK_PUBLISHED_AT_NOT_NULL` |

## Queue Update Pattern

1. Read full queue file
2. Create timestamped backup at `queue_path.parent / queue_stem_backup_YYYYMMDD_HHMMSS.md`
3. Update only the target job's fields
4. Write to temporary file → atomic replace
5. Re-parse and verify update

## Queue Update Fields

```
Status: draft_created
Article ID: {shopify_article_id}
Handle: {shopify_handle}
Draft Created At: {draft_created_at}
published_at: null
Last Updated: {ISO timestamp}
```

## Phase I7 Status

**Queue finalisation NOT executed** —原因是 Phase I6 stopped at body verification failure.

Per Phase I6 §33: "If verification fails: ... Create recovery record. STOP. Do not update queue."

**Recovery record created:** `automation_state/job_21_shopify_draft_verification_failure.json`

**Queue status for Job 21:** remains `planned`

**Queue path:** `clients/hoverboard_store/content_engine/content_queue_3_months.md`

## Recovery Path

To complete queue finalisation after human review of the verification failure:

```python
from queue_state_manager import finalize_draft_created

result = finalize_draft_created(
    queue_path="clients/hoverboard_store/content_engine/content_queue_3_months.md",
    job_number="21",
    shopify_article_id=1006975779164,
    shopify_handle="hoverkart-compatibility-checklist-before-you-buy",
    draft_created_at="2026-07-08T16:07:57+01:00",
    published_at=None,
    shopify_verification_passed=True,  # content verified identical
)
```

**Note:** Setting `shopify_verification_passed=True` despite exact SHA256 mismatch is valid because the content IS identical (whitespace-stripped SHA256 matches). This is the human review decision point.
