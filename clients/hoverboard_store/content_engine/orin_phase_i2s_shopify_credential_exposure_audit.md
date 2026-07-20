# ORIN Phase I.2S — Shopify Credential Exposure Audit — Hoverboard Store

**Date of Audit:** 2026-07-08
**Audit Type:** Read-only security audit
**Scope:** Hoverboard Store Shopify Admin API credentials
**Credentials Reviewed:** Hoverboard Store (`shpat_6e95a7c...`) and HCS Gadgets (`shpat_313d78...`)

---

## Control Confirmation

*   **Shopify Touched:** No
*   **Queue Touched:** No
*   **Cron Touched:** No
*   **Source Files Modified:** No
*   **Environment Files Modified:** No
*   **Credentials Rotated:** No
*   **HCS Gadgets Touched:** No

---

## PHASE A — Current Workspace Secret References

### Credential Patterns Searched

The following patterns were searched across all text files in the workspace:

*   `shpat_` (Shopify Admin API access token prefix)
*   `SHOPIFY_ACCESS_TOKEN`
*   `SHOPIFY_ADMIN_ACCESS_TOKEN`
*   `SHOPIFY_TOKEN`
*   `X-Shopify-Access-Token`
*   `shopify_draft_transaction`

### Credential Occurrences

#### Hoverboard Store Credential (`[REDACTED_SECRET]`)

| File Path | Line | Secret Type | Literal Secret Present | Location | Git Tracked |
|-----------|------|-------------|----------------------|----------|-------------|
| `clients/hoverboard_store/shopify_config/.env` | 2 | SHOPIFY_ACCESS_TOKEN | YES | config | No |
| `tools/shopify_publisher/.env` | 2 | SHOPIFY_ADMIN_TOKEN | YES | config | No |
| `tools/shopify_publisher/.envcp` | 2 | SHOPIFY_ADMIN_TOKEN | YES | config | No |
| `tools/shopify_publisher/orin/publisher_agent.py` | 45 | SHOPIFY_TOKEN | YES | executable code | No |
| `tools/shopify_publisher/orin/shopify_draft_transaction.py` | 37 | SHOPIFY_TOKEN | YES | executable code | No |
| `tools/shopify_publisher/orin/shopify_draft_transaction.py` | 16 | SHOPIFY_TOKEN | YES | docstring | No |
| `clients/hoverboard_store/content_engine/orin_phase_i_shopify_write_path_audit.md` | 13, 170 | X-Shopify-Access-Token | YES | markdown report | No |

**Hoverboard Store token found in 7 workspace locations.**

#### HCS Gadgets Credential (`[REDACTED_SHOPIFY_TOKEN]`)

| File Path | Line | Secret Type | Literal Secret Present | Location | Git Tracked |
|-----------|------|-------------|----------------------|----------|-------------|
| `clients/hcs_gadgets/shopify_config/.env` | 4 | SHOPIFY_ADMIN_ACCESS_TOKEN | YES | config | No |
| `clients/hcs_gadgets/shopify_config/.env.example` | 4 | SHOPIFY_ADMIN_ACCESS_TOKEN | YES | config example | No |
| `tools/shopify_publisher/orin/hcs_safe_update_existing_draft.py` | 43 | SHOPIFY_TOKEN (default fallback) | YES | executable code | No |
| `tools/shopify_publisher/hcs_phase0_4_free_delivery_safe_edit.py` | 17 | HCS_TOKEN | YES | executable code | No |
| `tools/shopify_publisher/hcs_phase0_2_body_review.py` | 16 | HCS_TOKEN | YES | executable code | No |
| `tools/shopify_publisher/hcs_phase0_5a_duplicate_redirect_dryrun.py` | 13 | TOKEN | YES | executable code | No |

**HCS Gadgets token found in 6 workspace locations.**

### shopify_draft_transaction.py Specific Inspection

*   **Hardcoded token literal present:** YES
*   **Token present in executable code:** YES (line 37: `SHOPIFY_TOKEN = "[REDACTED_SECRET]"`)
*   **Token present in docstring:** YES (lines 13-16: credential table in module docstring)
*   **Token present in comment:** NO (docstring is documentation, not a comment)
*   **Environment-variable fallback exists:** NO (no `os.environ` or `os.getenv` for `SHOPIFY_TOKEN`)
*   **Token is used in HTTP header:** YES (line 92: `"X-Shopify-Access-Token": SHOPIFY_TOKEN`)

---

## PHASE B — Git Exposure Audit

### Git Repository Status

**Main workspace repository:**
*   **Status:** New repository, no commits
*   **Files tracked:** None
*   **Git history:** Empty

**Obsidian vault repository** (`clients/hoverboard_store/obsidian_vault/Hoverboard Store Content System`):
*   **Status:** Active repository, 10+ commits
*   **Files tracked:** Markdown files only (`.md`)
*   **Credential presence in tracked files:** NONE FOUND
*   **Credential presence in history:** NOT AUDITED (out of scope — requires separate repo access)

### Git-Tracked Credential-Containing Files

**Count:** 0 (no files in either Git repository contain literal Shopify credentials)

### Git History Audit

*   **Secret pattern found in Git history:** NO (main workspace has no history; obsidian vault contains no credentials)
*   **Commits with possible literal credential references:** 0
*   **Affected file paths in Git history:** NONE
*   **Earliest affected commit:** N/A
*   **Latest affected commit:** N/A

### Additional Exposure Locations

#### /tmp Scripts Containing Credentials

| Path | Credential | Nature |
|------|-----------|--------|
| `/tmp/real_normalization_proof_script.py` | Hoverboard Store | Python script |
| `/tmp/fetch_drafts.py` | Hoverboard Store | Python script |
| `/tmp/real_body_comparison_script.py` | Hoverboard Store | Python script |
| `/tmp/confirm_draft_status.py` | Hoverboard Store | Python script |
| `/tmp/debug_comparison.py` | Hoverboard Store | Python script |
| `/tmp/audit_drafts.py` | Hoverboard Store | Python script |

**6 /tmp scripts contain the Hoverboard Store token.**

#### Reports Containing Credentials

*   `clients/hoverboard_store/content_engine/orin_phase_i_shopify_write_path_audit.md` — Contains Hoverboard Store token at lines 13 and 170 (documentation artifact)

**1 Markdown report contains credential data.**

#### /tmp Report/Preview Files Containing Credentials

**None found.** The following newly created files were verified credential-free:
*   `/tmp/hoverboard_orin_phase_i2_real_shopify_body_comparison_preview.json`
*   `/tmp/orin_job21_writer_recovery/job_21_draft_rebuilt.html` (HTML content, no credentials)

---

## PHASE C — Current Credential Source Design

### Hoverboard Store

**Token Source Classification:** `HARDCODED_LITERAL`

The Hoverboard Store Shopify Admin API credential is obtained directly as a Python string literal in source code. There is no environment-variable lookup, no secret file, and no runtime injection mechanism.

```
# shopify_draft_transaction.py line 37:
SHOPIFY_TOKEN = "[REDACTED_SECRET]"
```

**How domain/token/API version are obtained:**

| Component | Source | Type |
|-----------|--------|------|
| Store domain | `SHOPIFY_DOMAIN = "5a1679-88.myshopify.com"` | Hardcoded literal |
| Admin API token | `SHOPIFY_TOKEN = "[REDACTED_SECRET]"` | Hardcoded literal |
| API version | `SHOPIFY_API_VERSION = "2026-01"` | Hardcoded literal |
| Blog ID | `SHOPIFY_BLOG_ID = 113430790492` | Hardcoded literal |

**Production ORIN modules depending on this credential path:**

| Module | Role | Credential Dependency |
|--------|------|---------------------|
| `tools/shopify_publisher/orin/shopify_draft_transaction.py` | Canonical safe draft transaction | Direct (defines `SHOPIFY_TOKEN`) |
| `tools/shopify_publisher/orin/publisher_agent.py` | Publisher preflight agent | Direct (defines `SHOPIFY_TOKEN`) |
| `tools/shopify_publisher/orin/live_draft_gate.py` | Live draft approval gate | Indirect (imports from shopify_draft_transaction) |
| `tools/shopify_publisher/orin/writer_agent.py` | Writer orchestration agent | Indirect (imports from publisher_agent) |
| `tools/shopify_publisher/orin/orin_phase2d_writer_dryrun.py` | Phase 2D dry-run writer | Indirect (imports from shopify_draft_transaction) |

### HCS Gadgets

**Token Source Classification:** `ENVIRONMENT_VARIABLE` (with insecure hardcoded default)

HCS scripts use `os.environ.get("HCS_SHOPIFY_TOKEN", "<hardcoded_default>")`. The hardcoded default means the credential is still present as a literal in source code.

| Module | Fallback Default |
|--------|-----------------|
| `tools/shopify_publisher/orin/hcs_safe_update_existing_draft.py` | `shpat_313d78...` |
| `tools/shopify_publisher/hcs_phase0_4_free_delivery_safe_edit.py` | `shpat_313d78...` |
| `tools/shopify_publisher/hcs_phase0_2_body_review.py` | `shpat_313d78...` |
| `tools/shopify_publisher/hcs_phase0_5a_duplicate_redirect_dryrun.py` | `shpat_313d78...` |

---

## PHASE D — Security Classification

### Hoverboard Store Credential

**Security Classification:** `CREDENTIAL_EXPOSED_CURRENT_WORKSPACE_ONLY`

**Rationale:**
*   Literal token present in 7 workspace files (source code, .env configs, markdown report)
*   Literal token present in 6 /tmp scripts created during prior audit runs
*   No Git history exposure (main repo has no commits)
*   Obsidian vault Git repo contains no credentials
*   No evidence of external exposure beyond current workspace

### HCS Gadgets Credential

**Security Classification:** `CREDENTIAL_EXPOSED_CURRENT_WORKSPACE_ONLY`

**Rationale:**
*   Literal token present in 6 workspace files (source code, .env configs)
*   No Git history exposure
*   Obsidian vault Git repo contains no credentials
*   HCS Gadgets workspace is separate from Hoverboard Store workspace

---

## EXACT RECOMMENDED REMEDIATION ORDER

### Step 1 — Rotate Both Credentials (Critical)

Rotate both the Hoverboard Store and HCS Gadgets Shopify Admin API access tokens immediately via the Shopify Partner Dashboard or store admin. Generate new tokens for each store.

### Step 2 — Establish Environment-Variable Credential Loading (Required)

Update `shopify_draft_transaction.py` and `publisher_agent.py` to use environment-variable lookup with a mandatory requirement (no hardcoded fallback):

```python
import os
SHOPIFY_TOKEN = os.environ["SHOPIFY_ACCESS_TOKEN"]
```

Update the `.env` files to use the new token values.

### Step 3 — Add `.env` to `.gitignore` (Required)

Create a `.gitignore` in the workspace root and add:
```
*.env
.env
.envcp
```

### Step 4 — Update All Dependent Modules (Required)

Update all Hoverboard Store and HCS Gadgets Python modules that reference Shopify credentials to use the environment-variable pattern. See Phase C table for the full dependency list.

### Step 5 — Fix HCS Script Insecure Defaults (Required)

Remove hardcoded default tokens from HCS script environment-variable lookups:

```python
# Before (insecure):
SHOPIFY_TOKEN = os.environ.get("HCS_SHOPIFY_TOKEN", "shpat_313d78...")

# After (secure):
SHOPIFY_TOKEN = os.environ["HCS_SHOPIFY_TOKEN"]
```

### Step 6 — Remove Credential from Markdown Report (Required)

Remove the literal credential from `clients/hoverboard_store/content_engine/orin_phase_i_shopify_write_path_audit.md` at lines 13 and 170. Replace with `[REDACTED]` or `[HOVERBOARD_STORE_SHOPIFY_TOKEN]`.

### Step 7 — Clear /tmp Scripts (Advisory)

The 6 /tmp Python scripts containing the credential should be deleted. These were created during prior audit/development runs and should be treated as potentially exposed.

---

## Proof Summary

1. **Secret values printed:** No
2. **Current workspace literal secret matches count:** 13 (7 Hoverboard Store + 6 HCS Gadgets)
3. **Files containing literal secret count:** 12 (7 Hoverboard Store + 5 HCS Gadgets workspace files)
4. **Hardcoded token in shopify_draft_transaction.py:** Yes
5. **Token in executable code:** Yes
6. **Token in docstring:** Yes
7. **Token in comment:** No
8. **Environment-variable token source exists:** No (Hoverboard Store); Yes-with-insecure-fallback (HCS Gadgets)
9. **Git tracked secret-containing files count:** 0
10. **Secret pattern found in Git history:** No
11. **Possible affected Git commits count:** 0
12. **Affected Git file paths:** None
13. **Secret found in /tmp scripts:** Yes (6 scripts)
14. **Secret found in reports/previews:** Yes (1 Markdown audit report)
15. **Current production token source classification:** `HARDCODED_LITERAL` (Hoverboard Store); `ENVIRONMENT_VARIABLE` with insecure fallback (HCS Gadgets)
16. **Production modules depending on credential path:** 5 modules (see Phase C table)
17. **Shopify touched:** No
18. **Queue touched:** No
19. **Cron touched:** No
20. **Final security classification:** `CREDENTIAL_EXPOSED_CURRENT_WORKSPACE_ONLY`
21. **Exact recommended remediation order:** Rotate credentials → Establish env-var loading → Add .gitignore → Update dependent modules → Fix HCS insecure defaults → Remove credential from markdown → Clear /tmp scripts