# ORIN Phase I.2S.2A — Credential Boundary Final Correction

**Date:** 2026-07-09
**Scope:** Hoverboard Store only
**Strict scope:** No HCS Gadgets, no other clients, no Shopify calls, no credential rotation

---

## Phase A — Function-Level Credential Access Audit

### hoverboard_shopify_config.py
**Classification: CANONICAL_CONFIG_LOADER**

| Function | Reads env var directly | Calls canonical loader | Receives token value | Constructs auth header |
|---|---|---|---|---|
| `load_hoverboard_shopify_config()` | YES — HOVERBOARD_STORE_SHOPIFY_ACCESS_TOKEN | No (origin) | YES (returns it in dict) | No |
| `get_shopify_request_headers()` | No | No | YES (parameter) | YES — X-Shopify-Access-Token |

Canonical: YES. Single source. No HTTP.

---

### shopify_draft_transaction.py
**Classification: AUTHENTICATED_TRANSACTION_LAYER**

| Function | Reads env var directly | Calls canonical loader | Receives token value | Constructs auth header |
|---|---|---|---|---|
| `_get_shopify_config()` | No | YES — calls load_hoverboard_shopify_config() | YES (from loader dict) | No |
| `shopify_request()` | No | No | YES (from _get_shopify_config) | YES — via get_shopify_request_headers |
| `_shopify_get_raw()` | No | No | YES (from _get_shopify_config) | YES — via get_shopify_request_headers |
| `fetch_blog_articles_paginated()` | No | No | YES (from _get_shopify_config) | YES — via _shopify_get_raw |
| `create_shopify_draft()` | No | No | YES (via _get_shopify_config → shopify_request) | YES (via shopify_request) |
| `fetch_shopify_article()` | No | No | YES (via _get_shopify_config → shopify_request) | YES (via shopify_request) |

Authenticated: YES. All HTTP flows through canonical `shopify_request` or `_shopify_get_raw`.

---

### publisher_agent.py (AFTER CORRECTION)
**Classification: TRANSACTION_LAYER_CALLER**

| Function | Reads env var directly | Calls canonical loader | Receives token value | Constructs auth header |
|---|---|---|---|---|
| `run_dryrun()` | No | No | No | No |
| `analyse_shopify_conflicts()` | No | No | No | No |
| `compliance_check()` | No | No | No | No |
| `html_quality_check()` | No | No | No | No |

Publisher BEFORE correction: **PUBLISHER_CREDENTIAL_BOUNDARY_VIOLATION**
- Directly called `load_hoverboard_shopify_config()`
- Directly called `get_shopify_request_headers(cfg["access_token"])`
- Directly constructed `urllib.request.Request` with auth headers
- Directly made authenticated HTTP calls via `urllib.request.urlopen()`

Publisher AFTER correction: **TRANSACTION_LAYER_CALLER**
- Imports only `fetch_blog_articles_paginated` from `shopify_draft_transaction`
- Calls `fetch_blog_articles_paginated()` for live inventory
- No token access, no header construction, no urllib outside transaction layer

---

## Phase B — Corrections Applied

### Correction 1: shopify_draft_transaction.py
- Added `raw: bool = False` parameter to `shopify_request()` for GET/inventory requests
- Added `_shopify_get_raw(endpoint)` — internal helper exposing response headers for pagination
- Added `fetch_blog_articles_paginated(limit, max_pages)` — canonical paginated inventory fetch

### Correction 2: publisher_agent.py
- Removed `urllib.request`, `urllib.error`, `os` imports
- Removed `from hoverboard_shopify_config import load_hoverboard_shopify_config, get_shopify_request_headers`
- Removed `_publisher_cached_config` variable
- Removed `_get_publisher_shopify_config()` function
- Removed `fetch_live_shopify_inventory()` function
- Replaced with: `from shopify_draft_transaction import fetch_blog_articles_paginated`
- Replaced call: `fetch_live_shopify_inventory()` → `fetch_blog_articles_paginated(limit=250, max_pages=20)`
- Removed `blog_id` from payload preview (Publisher no longer loads config)

---

## Phase C — Single-Boundary Proof

### HOVERBOARD_STORE_SHOPIFY_ACCESS_TOKEN — production code references

| Module | Line | Type |
|---|---|---|
| hoverboard_shopify_config.py | 78 | `os.environ.get("HOVERBOARD_STORE_SHOPIFY_ACCESS_TOKEN", "")` — ACTUAL CODE READ |
| hoverboard_shopify_config.py | 80 | `missing.append(...)` — error classification |
| hoverboard_shopify_config.py | 58 | Docstring reference |
| shopify_draft_transaction.py | 10, 16 | Docstring reference |
| publisher_agent.py | — | NOT PRESENT (removed) |

**Conclusion:** `hoverboard_shopify_config.py` ONLY — canonical loader. ✓

---

### X-Shopify-Access-Token — production code references

| Module | Type |
|---|---|
| hoverboard_shopify_config.py:106 | `get_shopify_request_headers()` — canonical header construction |
| shopify_draft_transaction.py:101 (via get_shopify_request_headers) | `shopify_request` and `_shopify_get_raw` — transaction layer only |
| publisher_agent.py | NOT PRESENT (removed) |

**Conclusion:** `hoverboard_shopify_config.py` AND `shopify_draft_transaction.py` — transaction layer only. ✓

---

### Exact Publisher-to-HTTP Function Chain (AFTER CORRECTION)

```
publisher_agent.run_dryrun()
  └─ calls: fetch_blog_articles_paginated(limit=250, max_pages=20)
        └─ calls: _shopify_get_raw(endpoint)
              └─ calls: _get_shopify_config()
              └─ calls: get_shopify_request_headers(cfg["access_token"])
              └─ constructs: urllib.request.Request(url, headers=headers, method="GET")
              └─ sends: urllib.request.urlopen(req, timeout=30)
```

Non-secret transaction results returned to Publisher:
- `article` dict (list of article dicts from inventory)
- `error_or_none` string

The Publisher does NOT receive the access-token string.

---

### Import Tests (No Credentials Required)

| Module | Import without credentials |
|---|---|
| publisher_agent.py | ✓ PASS |
| shopify_draft_transaction.py | ✓ PASS |
| Writer dry-run | ✓ PASS |

---

### Missing Credential Fail-Before-HTTP Test

```
shopify_draft_transaction.fetch_blog_articles_paginated()
  → HoverboardShopifyConfigError: HOVERBOARD_SHOPIFY_CONFIG_MISSING
  → NO HTTP request attempted
```

✓ Confirmed.

---

## Phase D — Zero-Literal Secret Checks

| Category | Count |
|---|---|
| Executable-code literal secret count | 0 |
| Docstring literal secret count | 0 |
| Comment literal secret count | 0 |
| Markdown literal secret count | 0 |
| JSON literal secret count | 0 |
| /tmp script literal secret count | 0 |

---

## Final Classifications

| Item | Before | After |
|---|---|---|
| hoverboard_shopify_config.py | CANONICAL_CONFIG_LOADER | CANONICAL_CONFIG_LOADER ✓ |
| shopify_draft_transaction.py | AUTHENTICATED_TRANSACTION_LAYER | AUTHENTICATED_TRANSACTION_LAYER ✓ |
| publisher_agent.py | PUBLISHER_CREDENTIAL_BOUNDARY_VIOLATION | TRANSACTION_LAYER_CALLER ✓ |
| Single credential-loading boundary | Partial | PROVEN ✓ |
| Single authenticated transaction boundary | Partial | PROVEN ✓ |
| Publisher directly loads token | YES (violation) | NO ✓ |
| Publisher directly receives token value | YES (violation) | NO ✓ |
| Publisher constructs auth header | YES (violation) | NO ✓ |
| Publisher calls transaction layer for all Shopify ops | NO (was bypass) | YES ✓ |
| Shopify touched | No | No ✓ |
| Queue touched | No | No ✓ |
| Cron touched | No | No ✓ |

**Final classification: CREDENTIAL_BOUNDARY_PROVEN**

**Exact next step:** Proceed to Phase I.2S.2B or next accepted work package.

---

## SHA256 Verification

Post-correction SHA256 values for modified files (for future reference):

- `hoverboard_shopify_config.py` — unchanged from Phase I.2S.2
- `shopify_draft_transaction.py` — MODIFIED (raw parameter + _shopify_get_raw + fetch_blog_articles_paginated)
- `publisher_agent.py` — MODIFIED (credential boundary corrected)

Run: `sha256sum tools/shopify_publisher/orin/{hoverboard_shopify_config,shopify_draft_transaction,publisher_agent}.py`
