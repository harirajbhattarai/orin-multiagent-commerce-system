# ORIN Phase I1 — Shopify Write Path Audit

**Report Date:** 2026-07-08
**Phase:** I1 — Shopify Write Path Audit

---

## 1. Shopify Credentials (from publisher_agent.py)

| Field | Value |
|---|---|
| Domain | `5a1679-88.myshopify.com` |
| Access Token | `[REDACTED_SECRET]` |
| API Version | `2026-01` |
| Blog ID | `113430790492` |
| Blog Title | Journal Insights |

---

## 2. Shopify REST API Pattern

All Shopify article operations use `urllib.request` with header:
```
X-Shopify-Access-Token: <token>
```

**GET articles (inventory fetch):**
```
GET /blogs/{blog_id}/articles.json?limit=250
```

**POST article (create draft):**
```
POST /blogs/{blog_id}/articles.json
Payload: {"article": {"title": ..., "body_html": ..., "handle": ..., "published": false}}
```

---

## 3. publish_blog_draft.py — LEGACY_BLOCKED

| Attribute | Value |
|---|---|
| Path | `tools/shopify_publisher/publish_blog_draft.py` |
| Classification | **LEGACY_BLOCKED** |
| In BLOCKED_SCRIPT_PATTERNS | Yes |
| Called by cron_entrypoint | No |
| Can be called by Phase I | No |

**Article creation code:**
```python
blog_id, blog_title, blog_handle = get_blog_id()  # Journal Insights
payload = {
    "title": title,
    "body_html": html,
    "handle": handle,
    "published": False,   # hardcoded draft
    # NO published_at sent
}
result = shopify_request("POST", f"/blogs/{blog_id}/articles.json", payload)
```

**Payload config:**
- `published`: `False` (hardcoded) — always creates draft
- `published_at`: **not sent** — articles are hidden drafts
- `body_html`: full HTML from file — sent as-is
- `handle`: extracted from HTML meta or derived from title

---

## 4. hcs_publish_blog_draft.py — HCS_ONLY

| Attribute | Value |
|---|---|
| Path | `tools/shopify_publisher/hcs_publish_blog_draft.py` |
| Classification | **HCS_ONLY** |
| Shopify store | Separate HCS store (different from ORIN) |
| Used by Phase I | No — different store |

---

## 5. publisher_agent.py — ACTIVE_ORIN_PRODUCTION_PATH (read-only preflight)

| Attribute | Value |
|---|---|
| Path | `tools/shopify_publisher/orin/publisher_agent.py` |
| Classification | **ACTIVE_ORIN_PRODUCTION_PATH** |
| Mode | Read-only preflight — does NOT create articles |
| Shopify write | None — uses GET only |

Functions:
- `fetch_live_shopify_inventory()` — GET all articles (read)
- `analyse_shopify_conflicts()` — analyse inventory (read)
- `run_dryrun()` — preflight decision (read-only)

---

## 6. cron_entrypoint.py — ACTIVE_ORIN_PRODUCTION_PATH (orchestration)

| Attribute | Value |
|---|---|
| Path | `tools/shopify_publisher/orin/cron_entrypoint.py` |
| Classification | **ACTIVE_ORIN_PRODUCTION_PATH** |
| Shopify write | None — calls phase wrappers only |

Phase wrappers (read-only previews):
- `Phase 1A` → `orin_phase1a_state_dryrun.py`
- `Phase 1B` → `orin_phase1b_planner_dryrun.py`
- `Phase 1C` → `orin_phase1c_recovery_dryrun.py`
- `Phase 2A` → `orin_phase2a_review_dryrun.py`
- `Phase 2B` → `orin_phase2b_duplicate_memory_dryrun.py`
- `Phase 2C/2D` → `orin_phase2c_writer_planning_dryrun.py`
- `Phase 2E/2G` → `orin_phase2e_publisher_dryrun.py`
- `Phase H` → `live_draft_gate.py`

No Shopify write wrapper exists in the current phase chain.

---

## 7. BLOCKED_SCRIPT_PATTERNS in cron_entrypoint.py

```python
BLOCKED_SCRIPT_PATTERNS = [
    "tools/shopify_publisher/hcs_publish_blog_draft.py",
    "tools/shopify_publisher/publish_blog_draft.py",
    "tools/shopify_publisher/hcs_update_blog_draft.py",
    "tools/shopify_publisher/update_blog_draft.py",
    "tools/shopify_publisher/update_blog_article_preserve_status.py",
]
```

`publish_blog_draft.py` is on the blocked list. It cannot be invoked by the pipeline.

---

## 8. Shopify Article Creation Function — Needed

**Finding:** No canonical ORIN-selected-job Shopify writer module exists.

| Requirement | Status |
|---|---|
| Create Shopify article draft | Not implemented in ORIN modules |
| Fetch exact article by ID | Not implemented in ORIN modules |
| POST body verification | Not implemented |
| Selected-job queue finaliser | Not implemented |

**Required to build:**
1. `tools/shopify_publisher/orin/shopify_draft_transaction.py` — canonical safe draft transaction
2. `tools/shopify_publisher/orin/queue_state_manager.py` — canonical queue finaliser

---

## 9. CANONICAL_SELECTED_JOB_WRITER_EXISTS

**No.** A canonical selected-job Shopify draft writer does not exist in the ORIN module path.

---

## 10. Article Creation API Contract (for new writer)

Based on `publish_blog_draft.py` and `publisher_agent.py`:

**Endpoint:**
```
POST https://5a1679-88.myshopify.com/admin/api/2026-01/blogs/113430790492/articles.json
```

**Headers:**
```
X-Shopify-Access-Token: [REDACTED_SECRET]
Content-Type: application/json
```

**Minimal payload for draft creation:**
```json
{
  "article": {
    "title": "<title>",
    "body_html": "<html>",
    "handle": "<slug>",
    "published": false
  }
}
```

**Response contains:**
```json
{
  "article": {
    "id": <int>,
    "title": "...",
    "handle": "...",
    "published": false,
    "published_at": null,
    "body_html": "..."
  }
}
```

---

## 11. fetch_live_shopify_inventory() — Existing Reader

Used by `publisher_agent.py` for preflight. Returns all articles from Journal Insights blog. Uses pagination. Returns `List[dict]`, each with `id`, `title`, `handle`, `body_html`, `published`, `published_at`.

---

## 12. No-Canonical-Writer Conclusion

The Phase I safe draft transaction module must:
1. Use the same Shopify credentials as `publisher_agent.py`
2. Use the same blog ID (`113430790492`, Journal Insights)
3. Use `urllib.request` pattern (same as publisher_agent)
4. Create draft only (published=false, no published_at)
5. Immediately GET the created article by ID for verification
6. Compute SHA256 of fetched body_html
7. Compare with local Writer HTML SHA256
