# ORIN Phase I.2S.2C — Auth Header Ownership Final Lock

**Date:** 2026-07-09
**Scope:** Hoverboard Store only
**Strict scope:** No HCS Gadgets, no other clients, no Shopify calls, no credential rotation

---

## Phase A — Header Ownership Verification

### Before correction

| Function | File | Constructs X-Shopify-Access-Token |
|---|---|---|
| `get_shopify_request_headers()` | shopify_draft_transaction.py | YES |
| `shopify_request()` | shopify_draft_transaction.py | NO (called the helper) |

**Issue:** Auth header construction was owned by a helper function, not `shopify_request()` itself.

---

## Phase B — Inline Auth Header Ownership

### Change applied

**shopify_draft_transaction.py:**
- Removed `get_shopify_request_headers()` helper
- Inlined header dict directly into `shopify_request()`:

```python
# Before:
headers = get_shopify_request_headers(cfg["access_token"])

# After:
headers = {
    "X-Shopify-Access-Token": cfg["access_token"],
    "Content-Type": "application/json",
    "Accept": "application/json",
}
```

`shopify_request()` is now the sole owner of:
1. Authenticated header construction
2. HTTP Request construction
3. HTTP execution (urlopen)

---

## Phase C — Static Ownership Proof

### X-Shopify-Access-Token — ORIN production modules

| Module | Function | Status |
|---|---|---|
| shopify_draft_transaction.py | `shopify_request()` | **SOLE OWNER** ✓ |

### urllib.request.Request — ORIN production modules

| Module | Function | Status |
|---|---|---|
| shopify_draft_transaction.py | `shopify_request()` | **SOLE OWNER** ✓ |

### urllib.request.urlopen — ORIN production modules

| Module | Function | Status |
|---|---|---|
| shopify_draft_transaction.py | `shopify_request()` | **SOLE OWNER** ✓ |

### HOVERBOARD_STORE_SHOPIFY_ACCESS_TOKEN — ORIN production modules

| Module | Type | Status |
|---|---|---|
| hoverboard_shopify_config.py | `os.environ.get()` — canonical config loader | **SOLE** ✓ |
| shopify_draft_transaction.py | Docstring references only | NOT ACTUAL CODE ✓ |

`get_shopify_request_headers()`: **NOT FOUND in ORIN scope** ✓

---

## Publisher-to-Network Chain (Complete, Final)

```
publisher_agent.run_dryrun()
  └─ fetch_blog_articles_paginated(limit=250, max_pages=20)
        └─ shopify_request("GET", endpoint, return_headers=True)
              ├─ _get_shopify_config()
              │     └─ load_hoverboard_shopify_config()
              │           └─ reads: HOVERBOARD_STORE_SHOPIFY_STORE_DOMAIN
              │           └─ reads: HOVERBOARD_STORE_SHOPIFY_ACCESS_TOKEN
              │           └─ reads: HOVERBOARD_STORE_SHOPIFY_API_VERSION
              ├─ builds headers dict (inline):
              │     { "X-Shopify-Access-Token": cfg["access_token"],
              │       "Content-Type": "application/json",
              │       "Accept": "application/json" }
              ├─ urllib.request.Request(url, headers=headers, method="GET")
              └─ urllib.request.urlopen(req, timeout=30)
                    └─ response body parsed and returned
```

---

## Phase D — Regression Tests

| Test | Description | Result |
|---|---|---|
| A | Missing credentials → HOVERBOARD_SHOPIFY_CONFIG_MISSING; urlopen count=0 | **PASS** |
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

## Phase E — Zero-Literal Secret Checks

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
| Auth header helper function | `get_shopify_request_headers()` | **REMOVED** ✓ |
| `get_shopify_request_headers` in ORIN scope | YES | **NO** ✓ |
| X-Shopify-Access-Token owner | `get_shopify_request_headers()` + `shopify_request()` | **`shopify_request()` only** ✓ |
| urllib Request constructor owner | `shopify_request()` | **`shopify_request()` only** ✓ |
| urlopen executor owner | `shopify_request()` | **`shopify_request()` only** ✓ |
| Authenticated HTTP executor count | 1 | **1** ✓ |
| Shopify touched | No | No ✓ |
| Queue touched | No | No ✓ |
| Cron touched | No | No ✓ |

**Final classification: AUTH_HEADER_AND_HTTP_OWNERSHIP_LOCKED**

**Exact next step:** Await next approved work package.

---

## Architecture (Final — All Three Phases)

```
hoverboard_shopify_config.py     CANONICAL_CONFIG_LOADER
  └─ load_hoverboard_shopify_config()
       → reads HOVERBOARD_STORE_SHOPIFY_{STORE_DOMAIN,ACCESS_TOKEN,API_VERSION}
       → raises HOVERBOARD_SHOPIFY_CONFIG_MISSING if absent
       → returns {store_domain, access_token, api_version, blog_id}

shopify_draft_transaction.py     AUTHENTICATED_TRANSACTION_LAYER — SOLE HTTP BOUNDARY
  └─ shopify_request(method, endpoint, payload, raw, return_headers)
       → SOLE AUTHENTICATED HEADER CONSTRUCTOR (X-Shopify-Access-Token inlined)
       → SOLE HTTP REQUEST CONSTRUCTOR (urllib.request.Request)
       → SOLE HTTP EXECUTOR (urllib.request.urlopen)
       → returns (data, error) or (data, headers, error)
  └─ fetch_blog_articles_paginated()    ← calls shopify_request(return_headers=True)
  └─ create_shopify_draft()              ← calls shopify_request("POST", ...)
  └─ fetch_shopify_article()             ← calls shopify_request("GET", ...)

publisher_agent.py               TRANSACTION_LAYER_CALLER
  └─ calls fetch_blog_articles_paginated() only
  └─ ZERO token access, ZERO header construction, ZERO urllib
```
