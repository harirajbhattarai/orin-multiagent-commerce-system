# ORIN Phase I.2S.2B — Single Authenticated HTTP Path Lock

**Date:** 2026-07-09
**Scope:** Hoverboard Store only
**Strict scope:** No HCS Gadgets, no other clients, no Shopify calls, no credential rotation

---

## Phase A — HTTP Executor Audit

### Initial authenticated HTTP executor count: 2

| # | Function | File | HTTP Constructor | urlopen Caller |
|---|---|---|---|---|
| 1 | `shopify_request()` | shopify_draft_transaction.py | YES | YES |
| 2 | `_shopify_get_raw()` | shopify_draft_transaction.py | YES | YES |

**Classification: MULTIPLE_AUTHENTICATED_HTTP_EXECUTORS**

Additional issue: `get_shopify_request_headers()` was in `hoverboard_shopify_config.py` — auth header construction outside the transaction layer.

---

## Phase B — Config Loader Audit

### hoverboard_shopify_config.py — BEFORE

| Responsibility | Status |
|---|---|
| Reads HOVERBOARD_STORE_SHOPIFY_STORE_DOMAIN | ✓ |
| Reads HOVERBOARD_STORE_SHOPIFY_ACCESS_TOKEN | ✓ |
| Reads HOVERBOARD_STORE_SHOPIFY_API_VERSION | ✓ |
| Validates required variable presence | ✓ |
| Returns validated config dict | ✓ |
| Raises HOVERBOARD_SHOPIFY_CONFIG_MISSING | ✓ |
| Constructs X-Shopify-Access-Token | ✗ REMOVED |
| Imports urllib | ✗ NOT PRESENT |
| Performs HTTP | ✗ NOT PRESENT |

`get_shopify_request_headers()` — REMOVED from config loader. Moved to transaction layer.

### hoverboard_shopify_config.py — AFTER

Config loader is configuration-only. Zero HTTP responsibility.

---

## Phase C — Single Canonical HTTP Executor

### Changes Applied

**hoverboard_shopify_config.py:**
- Removed `get_shopify_request_headers()` — auth header construction no longer in config loader

**shopify_draft_transaction.py:**
- Added `get_shopify_request_headers()` — canonical auth header builder, now in transaction layer only
- Extended `shopify_request()` with `return_headers: bool = False` parameter
  - When `return_headers=True`: returns `(data, headers_dict, error)`
  - When `return_headers=False` (default): returns `(data, error)` — existing behaviour preserved
- Removed `_shopify_get_raw()` — duplicate HTTP executor eliminated
- Updated `fetch_blog_articles_paginated()`: `shopify_request("GET", endpoint, return_headers=True)` — single executor path

### Final authenticated HTTP executor count: 1

| Function | File | Status |
|---|---|---|
| `shopify_request()` | shopify_draft_transaction.py | SOLE HTTP EXECUTOR ✓ |

---

## Phase D — Static Proof

### urllib.request.Request locations — ORIN production modules

| Module | Function | Status |
|---|---|---|
| shopify_draft_transaction.py | `shopify_request()` | SOLE ✓ |
| All other ORIN modules | — | NOT PRESENT ✓ |

### urllib.request.urlopen locations — ORIN production modules

| Module | Function | Status |
|---|---|---|
| shopify_draft_transaction.py | `shopify_request()` | SOLE ✓ |
| All other ORIN modules | — | NOT PRESENT ✓ |

### X-Shopify-Access-Token construction — ORIN production modules

| Module | Function | Status |
|---|---|---|
| shopify_draft_transaction.py | `get_shopify_request_headers()` (via `shopify_request`) | SOLE ✓ |
| hoverboard_shopify_config.py | — | NOT PRESENT ✓ |

### HOVERBOARD_STORE_SHOPIFY_ACCESS_TOKEN — ORIN production modules

| Module | Type | Status |
|---|---|---|
| hoverboard_shopify_config.py | `os.environ.get()` — canonical config loader | SOLE ✓ |
| shopify_draft_transaction.py | Docstring references only | NOT ACTUAL CODE ✓ |

---

## Publisher-to-HTTP Function Chain (Final)

```
publisher_agent.run_dryrun()
  └─ fetch_blog_articles_paginated(limit=250, max_pages=20)
        └─ shopify_request("GET", endpoint, return_headers=True)
              ├─ _get_shopify_config()
              │     └─ load_hoverboard_shopify_config()
              │           └─ reads: HOVERBOARD_STORE_SHOPIFY_STORE_DOMAIN
              │           └─ reads: HOVERBOARD_STORE_SHOPIFY_ACCESS_TOKEN
              │           └─ reads: HOVERBOARD_STORE_SHOPIFY_API_VERSION
              ├─ get_shopify_request_headers(cfg["access_token"])
              │     └─ constructs: X-Shopify-Access-Token
              ├─ urllib.request.Request(url, headers=headers, method="GET")
              └─ urllib.request.urlopen(req, timeout=30)
```

Non-secret results returned to Publisher:
- `list of article dicts` (inventory)
- `str | None` (error_or_none)

Publisher does NOT receive the access-token string.

---

## Phase E — Mocked Transaction Regressions

| Test | Description | Result |
|---|---|---|
| A | Missing credentials → HOVERBOARD_SHOPIFY_CONFIG_MISSING, urlopen count=0 | **PASS** |
| B | Normal article JSON response → correct parsing | **PASS** |
| C | Raw collection response → articles list returned | **PASS** |
| D | Link pagination header → response headers available | **PASS** |
| E | Two-page pagination → 3 articles, 2 urlopen calls | **PASS** |
| F | HTTP 429 error → structured error returned | **PASS** |

### Import tests (no credentials present)

| Module | Import without credentials |
|---|---|
| hoverboard_shopify_config.py | **PASS** |
| shopify_draft_transaction.py | **PASS** |
| publisher_agent.py | **PASS** |

---

## Phase D — Zero-Literal Secret Checks

| Category | Count |
|---|---|
| Executable-code literal secret count | 0 ✓ |
| Docstring literal secret count | 0 ✓ |
| Comment literal secret count | 0 ✓ |
| Markdown literal secret count | 0 ✓ |
| JSON literal secret count | 0 ✓ |
| /tmp script literal secret count | 0 ✓ |

---

## Final Classifications

| Item | Before | After |
|---|---|---|
| Config loader HTTP responsibility | YES (had get_shopify_request_headers) | NO ✓ |
| Auth header in config loader | YES | NO ✓ |
| HTTP executor count | 2 | **1** ✓ |
| HTTP executor function | `shopify_request`, `_shopify_get_raw` | `shopify_request` only ✓ |
| `_shopify_get_raw` removed | NO (was added Phase I.2S.2A) | YES ✓ |
| `fetch_blog_articles_paginated` calls `shopify_request` | NO (was `_shopify_get_raw`) | YES ✓ |
| Publisher → transaction layer → config loader → HTTP | PARTIAL | COMPLETE ✓ |
| Shopify touched | No | No ✓ |
| Queue touched | No | No ✓ |
| Cron touched | No | No ✓ |

**Final classification: SINGLE_AUTHENTICATED_HTTP_PATH_PROVEN**

**Exact next step:** Await next approved work package.

---

## Architecture Summary (Final State)

```
hoverboard_shopify_config.py
  → load_hoverboard_shopify_config()
       → reads HOVERBOARD_STORE_SHOPIFY_* env vars
       → raises HOVERBOARD_SHOPIFY_CONFIG_MISSING if absent
       → returns {store_domain, access_token, api_version, blog_id}

shopify_draft_transaction.py
  → get_shopify_request_headers(access_token)
       → returns {X-Shopify-Access-Token, Content-Type, Accept}
  → shopify_request(method, endpoint, payload, raw, return_headers)
       → SOLE AUTHENTICATED HTTP EXECUTOR
       → calls _get_shopify_config() → load_hoverboard_shopify_config()
       → calls get_shopify_request_headers(cfg["access_token"])
       → constructs urllib.request.Request
       → calls urllib.request.urlopen
       → returns (data, error) or (data, headers, error)
  → fetch_blog_articles_paginated(limit, max_pages)
       → calls shopify_request(return_headers=True)
  → create_shopify_draft(title, body_html, handle)
       → calls shopify_request("POST", ...)
  → fetch_shopify_article(article_id)
       → calls shopify_request("GET", ...)

publisher_agent.py
  → calls fetch_blog_articles_paginated() from shopify_draft_transaction
  → NO token access
  → NO header construction
  → NO urllib import
```
