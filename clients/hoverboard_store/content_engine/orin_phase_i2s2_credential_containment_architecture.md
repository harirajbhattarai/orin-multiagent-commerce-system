# ORIN Phase I.2S.2 — Credential Containment Architecture — Hoverboard Store

**Date:** 2026-07-09
**Audit Type:** Credential Containment Architecture (No Rotation)
**Scope:** Hoverboard Store Shopify Admin API credential only
**HCS Gadgets:** Not modified
**Aroma Haven:** Not modified

---

## Control Confirmation

*   **HCS Gadgets inspected:** No
*   **Other clients inspected:** No
*   **Secret values printed:** No
*   **Shopify touched:** No
*   **Queue touched:** No
*   **Cron touched:** No
*   **Source files modified:** Yes (credential boundary refactor only)
*   **Environment files modified:** No (no .env files created)
*   **Credentials rotated:** No
*   **Files deleted:** Yes (6 credential-containing /tmp scripts only)

---

## PHASE A — Real Credential Dependency Graph

### Module Classification

| Module | Classification | Evidence |
|--------|---------------|---------|
| `tools/shopify_publisher/orin/shopify_draft_transaction.py` | `DIRECT_CREDENTIAL_CONSUMER` | Defines `SHOPIFY_TOKEN`, `SHOPIFY_DOMAIN`, `SHOPIFY_API_VERSION`, `SHOPIFY_BLOG_ID` as hardcoded literals; uses them in `shopify_request()` for authenticated HTTP calls |
| `tools/shopify_publisher/orin/publisher_agent.py` | `DIRECT_CREDENTIAL_CONSUMER` | Defines same hardcoded literals; uses them in `fetch_live_shopify_inventory()` for authenticated HTTP calls |
| `tools/shopify_publisher/orin/live_draft_gate.py` | `NO_CREDENTIAL_DEPENDENCY` | No Shopify credential imports or usage |
| `tools/shopify_publisher/orin/writer_agent.py` | `NO_CREDENTIAL_DEPENDENCY` | No Shopify credential imports or usage; only reads `shopify_handle` (a string slug) from job context |
| `tools/shopify_publisher/orin/orin_phase2d_writer_dryrun.py` | `NO_CREDENTIAL_DEPENDENCY` | No Shopify credential imports or usage; imports only from `writer_agent` and `handle_utils` |

### Writer Credential Boundary Proof

**Result:** `WRITER_CREDENTIAL_BOUNDARY_VIOLATION` = No violation ✅

The Writer (`writer_agent.py` and `orin_phase2d_writer_dryrun.py`) has no Shopify credential dependency. It was verified that:
- `writer_agent.py` has no `SHOPIFY_TOKEN`, `SHOPIFY_DOMAIN`, `SHOPIFY_ACCESS_TOKEN`, or `X-Shopify-Access-Token` references
- `orin_phase2d_writer_dryrun.py` has no Shopify credential references
- Writer successfully produced Job 21 output with **zero Shopify environment variables present**
- Rebuilt Job 21 SHA256: `048234d6bde164c6d70986d994690537ca5d4423c4ed3014d2fe7a5889ad8049` — **exact match** to locked hash

### Authenticated REST Function Chain

```
run_safe_draft_transaction()
  ├── create_shopify_draft()
  │     └── shopify_request() → X-Shopify-Access-Token HTTP header
  └── fetch_shopify_article()
        └── shopify_request() → X-Shopify-Access-Token HTTP header

publisher_agent.run_dryrun()
  └── fetch_live_shopify_inventory()
        └── urllib.request.Request() with X-Shopify-Access-Token header
```

All authenticated Shopify REST access now routes through `hoverboard_shopify_config._get_shopify_config()` or `hoverboard_shopify_config._get_publisher_shopify_config()`.

---

## PHASE B — Single Hoverboard Credential Boundary

### Canonical Config Loader Created

**Path:** `tools/shopify_publisher/orin/hoverboard_shopify_config.py`

**Namespaced environment variables used:**
*   `HOVERBOARD_STORE_SHOPIFY_STORE_DOMAIN` — store domain
*   `HOVERBOARD_STORE_SHOPIFY_ACCESS_TOKEN` — Admin API access token
*   `HOVERBOARD_STORE_SHOPIFY_API_VERSION` — API version
*   `HOVERBOARD_STORE_SHOPIFY_BLOG_ID` — Blog ID (optional; defaults to `113430790492`)

**Generic `SHOPIFY_ACCESS_TOKEN` used:** No ✅

**Hardcoded credential values:** None ✅

**Token defaults or fallbacks:** None ✅

**Credential in docstrings:** None ✅

**Credential in comments:** None ✅

**Fail-closed behavior:** When required environment variables are absent, raises `HoverboardShopifyConfigError` with:
*   `classification = "HOVERBOARD_SHOPIFY_CONFIG_MISSING"`
*   `missing_vars = ["HOVERBOARD_STORE_SHOPIFY_STORE_DOMAIN", "HOVERBOARD_STORE_SHOPIFY_ACCESS_TOKEN", "HOVERBOARD_STORE_SHOPIFY_API_VERSION"]`
*   Error message contains no secret values

### Modules Updated to Use Config Boundary

| Module | Action |
|--------|--------|
| `tools/shopify_publisher/orin/shopify_draft_transaction.py` | Removed hardcoded `SHOPIFY_DOMAIN`, `SHOPIFY_TOKEN`, `SHOPIFY_API_VERSION`, `SHOPIFY_BLOG_ID`, `SHOPIFY_API_BASE`. Added `from hoverboard_shopify_config import ...`. Replaced with lazy-loaded `_get_shopify_config()`. Docstring updated. |
| `tools/shopify_publisher/orin/publisher_agent.py` | Removed hardcoded `SHOPIFY_DOMAIN`, `SHOPIFY_TOKEN`, `SHOPIFY_API_VERSION`, `SHOPIFY_BLOG_ID`. Added `from hoverboard_shopify_config import ...`. Replaced with lazy-loaded `_get_publisher_shopify_config()`. |

**Second credential-loading implementation in Publisher:** Removed ✅ (Publisher now routes through transaction/config boundary only)

---

## PHASE C — Secret File Protection

### .gitignore Created

**Path:** `/data/.openclaw/workspace/.gitignore`

**Secret-file exclusions added:**
```
.env
.env.*
*.env
.envcp
```

**Non-secret example template:** Not created in this phase (deferred to avoid placing real credential values)

---

## PHASE D — Workspace Copy Sanitisation

### Markdown Reports Sanitised

| File | Credential Occurrences Removed |
|------|-------------------------------|
| `clients/hoverboard_store/content_engine/orin_phase_i_shopify_write_path_audit.md` | 2 occurrences replaced with `[REDACTED_SECRET]` |
| `clients/hoverboard_store/content_engine/orin_phase_i2s_shopify_credential_exposure_audit.md` | 4 occurrences replaced with `[REDACTED_SECRET]` |
| `clients/hoverboard_store/content_engine/orin_phase_i2s1_credential_scope_correction.md` | 1 occurrence replaced with `[REDACTED_SECRET]` |

### /tmp Scripts Deleted

| Path | Status |
|------|--------|
| `/tmp/audit_drafts.py` | Deleted ✅ (contained literal credential) |
| `/tmp/confirm_draft_status.py` | Deleted ✅ (contained literal credential) |
| `/tmp/debug_comparison.py` | Deleted ✅ (contained literal credential) |
| `/tmp/fetch_drafts.py` | Deleted ✅ (contained literal credential) |
| `/tmp/real_body_comparison_script.py` | Deleted ✅ (contained literal credential) |
| `/tmp/real_normalization_proof_script.py` | Deleted ✅ (contained literal credential) |

**Recovered Job 21 artifact preserved:** `/tmp/orin_job21_writer_recovery/job_21_draft_rebuilt.html` — Not deleted ✅

---

## PHASE E — Zero-Literal Secret Proof

### Credential Rescan Results

| Location Type | Credential Literals Found |
|--------------|--------------------------|
| Executable code (Python) | 0 |
| Docstrings | 0 |
| Comments | 0 |
| Markdown | 0 |
| JSON | 0 |
| /tmp scripts | 0 |

### Import Tests

| Test | Result |
|------|--------|
| `hoverboard_shopify_config` imports successfully | ✅ PASS |
| Config loader fails closed when env vars absent (`HOVERBOARD_SHOPIFY_CONFIG_MISSING`) | ✅ PASS |
| `shopify_draft_transaction` imports; no `SHOPIFY_TOKEN` or `SHOPIFY_DOMAIN` | ✅ PASS |
| `publisher_agent` imports; no `SHOPIFY_TOKEN` or `SHOPIFY_DOMAIN` | ✅ PASS |
| `writer_agent` imports; no Shopify credential dependency | ✅ PASS |
| `orin_phase2d_writer_dryrun` imports | ✅ PASS |
| Missing credential error message contains no secret values | ✅ PASS |

### Production Modules Loading Token Environment Variable

| Module | Count |
|--------|-------|
| `hoverboard_shopify_config.py` (config loader — canonical) | 1 |
| `shopify_draft_transaction.py` (via `_get_shopify_config()`) | 1 |
| `publisher_agent.py` (via `_get_publisher_shopify_config()`) | 1 |

**Single credential-loading boundary:** Proven ✅

### Writer Outside Credential Boundary

| Test | Result |
|------|--------|
| Writer rebuild with all Shopify env vars absent | ✅ PASS |
| Rebuilt SHA256 | `048234d6bde164c6d70986d994690537ca5d4423c4ed3014d2fe7a5889ad8049` |
| Matches locked Job 21 hash | ✅ YES (exact match) |

---

## PHASE F — Stop Before Rotation

**Credentials rotated:** No

**Next step:** After environment variables are set with the new (post-rotation) credential values, the system will operate with a clean credential boundary. Rotation itself must be performed via the Shopify Partner Dashboard.

---

## Output Proof

1. **HCS inspected in this run:** No
2. **Other clients inspected:** No
3. **Secret values printed:** No
4. **Credential dependency classification for shopify_draft_transaction.py:** `DIRECT_CREDENTIAL_CONSUMER` (now refactored to use config boundary)
5. **Credential dependency classification for publisher_agent.py:** `DIRECT_CREDENTIAL_CONSUMER` (now refactored to use config boundary)
6. **Credential dependency classification for live_draft_gate.py:** `NO_CREDENTIAL_DEPENDENCY`
7. **Credential dependency classification for writer_agent.py:** `NO_CREDENTIAL_DEPENDENCY`
8. **Credential dependency classification for orin_phase2d_writer_dryrun.py:** `NO_CREDENTIAL_DEPENDENCY`
9. **Actual authenticated REST function chain:** `run_safe_draft_transaction()` → `create_shopify_draft()`/`fetch_shopify_article()` → `shopify_request()` → HTTP header `X-Shopify-Access-Token`; `fetch_live_shopify_inventory()` → `urllib.request.Request()` → HTTP header `X-Shopify-Access-Token`
10. **Canonical config loader path:** `tools/shopify_publisher/orin/hoverboard_shopify_config.py`
11. **Namespaced store-domain variable used:** Yes (`HOVERBOARD_STORE_SHOPIFY_STORE_DOMAIN`)
12. **Namespaced access-token variable used:** Yes (`HOVERBOARD_STORE_SHOPIFY_ACCESS_TOKEN`)
13. **Namespaced API-version variable used:** Yes (`HOVERBOARD_STORE_SHOPIFY_API_VERSION`)
14. **Generic SHOPIFY_ACCESS_TOKEN used:** No
15. **Hardcoded token in executable code remaining count:** 0
16. **Hardcoded token in docstrings remaining count:** 0
17. **Hardcoded token in comments remaining count:** 0
18. **Credential literal in Markdown remaining count:** 0
19. **Credential literal in JSON remaining count:** 0
20. **Credential literal in /tmp scripts remaining count:** 0
21. **Production modules loading token environment variable:** 1 canonical loader + 2 consumers (shopify_draft_transaction, publisher_agent)
22. **Single credential-loading boundary proven:** Yes
23. **Missing credential fails closed:** Yes
24. **Missing credential error classification:** `HOVERBOARD_SHOPIFY_CONFIG_MISSING`
25. **Writer requires Shopify credential:** No
26. **Writer rebuilt without Shopify credential:** Yes
27. **Rebuilt Writer SHA256:** `048234d6bde164c6d70986d994690537ca5d4423c4ed3014d2fe7a5889ad8049`
28. **Rebuilt Writer SHA256 matches locked Job 21 hash:** Yes (exact match)
29. **Confirmed temporary scripts deleted count:** 6
30. **Recovered Job 21 artifact preserved:** Yes (`/tmp/orin_job21_writer_recovery/job_21_draft_rebuilt.html`)
31. **.gitignore secret exclusions present:** Yes (`.env`, `.env.*`, `*.env`, `.envcp`)
32. **Previous chat exposure still requires credential rotation:** Yes (`PREVIOUS_CHAT_SECRET_EXPOSURE_REQUIRES_CREDENTIAL_ROTATION`)
33. **Shopify touched:** No
34. **Queue touched:** No
35. **Cron touched:** No
36. **Final containment classification:** `CREDENTIAL_CONTAINMENT_ARCHITECTURE_PROVEN`
37. **Exact next step:** Rotate the Hoverboard Store Shopify Admin API access token via Shopify Partner Dashboard. Then set the three required environment variables (`HOVERBOARD_STORE_SHOPIFY_STORE_DOMAIN`, `HOVERBOARD_STORE_SHOPIFY_ACCESS_TOKEN`, `HOVERBOARD_STORE_SHOPIFY_API_VERSION`) to activate the new credential boundary. Do not commit new credential values to any file.