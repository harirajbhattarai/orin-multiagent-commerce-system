# ORIN Phase I2 — Canonical Safe Draft Transaction

**Report Date:** 2026-07-08
**Phase:** I2 — Safe Shopify Draft Transaction Module

---

## Transaction Module

**Path:** `tools/shopify_publisher/orin/shopify_draft_transaction.py`

## Pre-Write Invariant Checks

| Check | Trigger | Decision if fails |
|---|---|---|
| Gate approval | `live_draft_gate_result.decision != LIVE_DRAFT_WRITE_APPROVED` | `BLOCK_LIVE_DRAFT_NOT_APPROVED` |
| Gate approved | `live_draft_gate_result.approved != True` | `BLOCK_LIVE_DRAFT_NOT_APPROVED` |
| Job context identity | Any `job_number` mismatch across 6 sources | `BLOCK_JOB_CONTEXT_MISMATCH` |
| Handle validity | `approved_handle` fails canonical format check | `BLOCK_INVALID_HANDLE` |
| Local SHA256 invariance | `compute_sha256(file) != writer_execution.sha256` | `BLOCK_LOCAL_DRAFT_MUTATED_AFTER_WRITER` |
| published_at safety | `_unsafe_publish_config=True` (regression) | `BLOCK_PUBLISH_CONFIGURATION_UNSAFE` |

## Payload Configuration

```python
{
    "title": expected_title,       # from selected_job_context.topic
    "body_html": file_content,     # exact local file
    "handle": expected_handle,     # from writer_plan.approved_handle
    "published": False,            # always draft
    # published_at: NOT sent (null)
}
```

## Shopify API Endpoint

```
POST https://5a1679-88.myshopify.com/admin/api/2026-01/blogs/113430790492/articles.json
```

## Post-Create Verification Sequence

1. **Create draft** — POST to Shopify
2. **Immediately fetch** — GET exact article by returned ID (not from POST response)
3. **Verify** — ID, title, handle, published_at null, draft status, body SHA256

## Regression: Unsafe publish_at Config (Phase I2 §14)

```python
result = run_safe_draft_transaction(
    ..., _unsafe_publish_config=True  # regression override
)
```

**Expected:** `BLOCK_PUBLISH_CONFIGURATION_UNSAFE`, `approved=false`

**Result:** ✅ `BLOCK_PUBLISH_CONFIGURATION_UNSAFE`, `approved=false`

## Regression: Gate Not Approved Block

```python
fake_gate = {
    "decision": "BLOCK_POST_FETCH_BODY_VERIFICATION_UNAVAILABLE",
    "approved": False,
    "job_number": "21",
}
```

**Expected:** `BLOCK_LIVE_DRAFT_NOT_APPROVED`

**Result:** ✅ `BLOCK_LIVE_DRAFT_NOT_APPROVED`, `approved=false`

## Shopify API Path Fix

**Bug found during Phase I6:** `shopify_draft_transaction.py` was using endpoint `/blogs/{blog_id}/articles.json` without the `/admin/api/{version}` prefix, causing 404 errors.

**Fixed to:** `/admin/api/2026-01/blogs/{blog_id}/articles.json`

## Live Test Result (Phase I6)

**Article ID:** 1006975779164
**Title:** Hoverkart Compatibility Checklist Before You Buy ✅
**Handle:** hoverkart-compatibility-checklist-before-you-buy ✅
**published_at:** null ✅
**Draft/hidden:** true ✅
**Body content:** Verified identical (whitespace-stripped SHA256 match) ✅
**Exact byte SHA256:** Mismatch — Shopify adds `\n` between HTML tags ✅

**Transaction decision:** `SHOPIFY_DRAFT_VERIFICATION_FAILED`
**Reason:** Exact byte SHA256 mismatch due to Shopify HTML formatting normalization
**Recovery record:** `clients/hoverboard_store/content_engine/automation_state/job_21_shopify_draft_verification_failure.json`
