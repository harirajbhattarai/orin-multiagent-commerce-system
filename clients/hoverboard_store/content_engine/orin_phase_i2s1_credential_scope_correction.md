# ORIN Phase I.2S.1 — Credential Exposure Scope Correction — Hoverboard Store

**Date of Audit:** 2026-07-08
**Audit Type:** Read-only security audit — Hoverboard Store only
**Scope:** Hoverboard Store Shopify Admin API credential only
**HCS Gadgets:** Not inspected (out of scope)

---

## Control Confirmation

*   **HCS Gadgets inspected:** No
*   **Secret values printed:** No
*   **Shopify Touched:** No
*   **Queue Touched:** No
*   **Cron Touched:** No
*   **Source files modified:** No
*   **Environment files modified:** No
*   **Credentials rotated:** No
*   **Files deleted:** No

---

## PHASE A — Git Repository Status

**Git repository found:** Yes
**Repository root:** `/data/.openclaw/workspace/.git`
**.git directory present:** Yes
**Current branch:** `master` (ref: `refs/heads/master`)
**Total Git commit count:** 0
**HEAD commit:** None (repository has zero commits)

### Git Audit Capability Classification

`GIT_REPOSITORY_WITH_NO_COMMITS`

The repository exists and is properly initialised, but contains zero commits. No historical data is available for inspection. The absence of Git history cannot be interpreted as evidence that credentials were never committed. This classification is distinct from `NO_GIT_REPOSITORY` because a Git repository is present.

---

## PHASE B — Hoverboard-Only Current Workspace Scan

### Scoped Search Paths

The following paths were searched:
*   `tools/shopify_publisher/orin/` — ORIN agent modules
*   `tools/shopify_publisher/` — Publisher tooling
*   `clients/hoverboard_store/` — Hoverboard Store client files

The following paths were explicitly excluded:
*   `clients/hcs_gadgets/` — Out of scope

### Credential Occurrences — Hoverboard Store Token (`[REDACTED_SECRET]`)

| File Path | Line | Literal Secret Present | Context Type | Git Tracked |
|-----------|------|----------------------|-------------|-------------|
| `tools/shopify_publisher/orin/shopify_draft_transaction.py` | 16 | YES | DOCSTRING | No |
| `tools/shopify_publisher/orin/shopify_draft_transaction.py` | 37 | YES | EXECUTABLE_CODE | No |
| `tools/shopify_publisher/orin/publisher_agent.py` | 45 | YES | EXECUTABLE_CODE | No |
| `tools/shopify_publisher/.env` | 2 | YES | CONFIG | No |
| `tools/shopify_publisher/.envcp` | 2 | YES | CONFIG | No |
| `clients/hoverboard_store/shopify_config/.env` | 2 | YES | CONFIG | No |
| `clients/hoverboard_store/content_engine/orin_phase_i_shopify_write_path_audit.md` | 13 | YES | MARKDOWN | No |
| `clients/hoverboard_store/content_engine/orin_phase_i_shopify_write_path_audit.md` | 170 | YES | MARKDOWN | No |
| `clients/hoverboard_store/content_engine/orin_phase_i2s_shopify_credential_exposure_audit.md` | 6 | YES | MARKDOWN | No |
| `clients/hoverboard_store/content_engine/orin_phase_i2s_shopify_credential_exposure_audit.md` | 28 | YES | MARKDOWN | No |
| `clients/hoverboard_store/content_engine/orin_phase_i2s_shopify_credential_exposure_audit.md` | 37 | YES | MARKDOWN | No |
| `clients/hoverboard_store/content_engine/orin_phase_i2s_shopify_credential_exposure_audit.md` | 51 | YES | MARKDOWN | No |
| `clients/hoverboard_store/content_engine/orin_phase_i2s_shopify_credential_exposure_audit.md` | 67 | YES | MARKDOWN | No |
| `clients/hoverboard_store/content_engine/orin_phase_i2s_shopify_credential_exposure_audit.md` | 141 | YES | MARKDOWN | No |
| `clients/hoverboard_store/content_engine/orin_phase_i2s_shopify_credential_exposure_audit.md` | 149 | YES | MARKDOWN | No |

**Total Hoverboard Store credential occurrences in workspace: 15**
**Unique Hoverboard files containing credential: 8**

### shopify_draft_transaction.py Specific Inspection

*   **Hardcoded token literal in executable code:** Yes (line 37: `SHOPIFY_TOKEN = "shpat_[REDACTED]..."`)
*   **Hardcoded token literal in docstring:** Yes (line 16: credential table)
*   **Hardcoded token literal in comment:** No
*   **Environment variable loading exists:** No
*   **Mandatory environment-only token loading:** No
*   **Hardcoded token fallback exists:** No fallback — token is a pure hardcoded string literal

---

## PHASE C — Hoverboard Temporary and Generated Artifacts

### /tmp Scripts Containing Credential

| Path | Context |
|------|---------|
| `/tmp/audit_drafts.py` | Python script |
| `/tmp/confirm_draft_status.py` | Python script |
| `/tmp/debug_comparison.py` | Python script |
| `/tmp/fetch_drafts.py` | Python script |
| `/tmp/real_body_comparison_script.py` | Python script |
| `/tmp/real_normalization_proof_script.py` | Python script |

**Total /tmp scripts: 6**

### Hoverboard Store Reports Containing Credential

| Path | Context |
|------|---------|
| `clients/hoverboard_store/content_engine/orin_phase_i_shopify_write_path_audit.md` | Markdown audit report |
| `clients/hoverboard_store/content_engine/orin_phase_i2s_shopify_credential_exposure_audit.md` | Markdown audit report (this report also contains credential data) |

**Total report files: 2**

### Previous Conversation Output Exposure

**Previous chat secret exposure reported by operator:** Yes

The operator has confirmed that a previous OpenClaw run displayed the Hoverboard Store Shopify credential in conversation output. This is treated as a confirmed exposure event.

---

## PHASE D — Git History

### Git History Secret Exposure Result

**Git history capability:** `GIT_REPOSITORY_WITH_NO_COMMITS`

Since the repository contains zero commits, no historical inspection is possible. The Hoverboard Store credential may or may not have been previously committed and later removed. This cannot be determined from the available Git data.

**git_history_secret_exposure:** `UNPROVEN`

The credential is not confirmed to have been committed to Git, but Git history absence is not proof of non-exposure. The repository was created with zero initial commits — this is a new or scrubbed repository state.

---

## PHASE E — Production Dependency Proof

### Direct Credential Dependencies

Modules that directly define, assign, or use the `SHOPIFY_TOKEN` constant:

| Module | Role | Direct Credential Use |
|--------|------|---------------------|
| `tools/shopify_publisher/orin/shopify_draft_transaction.py` | Canonical safe draft transaction | Defines `SHOPIFY_TOKEN = "[LITERAL]"` and uses it in HTTP headers |
| `tools/shopify_publisher/orin/publisher_agent.py` | Publisher preflight agent | Defines `SHOPIFY_TOKEN = "[LITERAL]"` and uses it in HTTP headers |

### Indirect Credential Dependencies

Modules that import from direct credential dependencies but do not themselves define the token:

| Module | Role | Dependency Type |
|--------|------|----------------|
| `tools/shopify_publisher/orin/live_draft_gate.py` | Live draft approval gate | Imports from `shopify_draft_transaction` |
| `tools/shopify_publisher/orin/writer_agent.py` | Writer orchestration agent | Imports from `publisher_agent` |
| `tools/shopify_publisher/orin/orin_phase2d_writer_dryrun.py` | Phase 2D dry-run writer | Imports from `shopify_draft_transaction` |

---

## PHASE F — Security Classification

### Final Classification

`HOVERBOARD_CREDENTIAL_EXPOSED_GIT_UNPROVEN`

**Rationale:**
*   Hardcoded literal credential confirmed in 8 workspace files across 4 context types (executable code, docstring, config, markdown)
*   Credential confirmed in 6 /tmp scripts
*   Previous conversation output exposure confirmed by operator
*   Git repository has zero commits — Git history exposure cannot be confirmed or ruled out
*   Credential is classified as exposed and must be treated as compromised

---

## Hoverboard-Only Remediation Order

### Step 1 — Rotate the Hoverboard Store Credential (Critical — Immediate)

Rotate the Hoverboard Store Shopify Admin API access token immediately via the Shopify Partner Dashboard or store admin. Generate a new token.

### Step 2 — Implement Mandatory Environment-Variable Loading (Required)

Update `shopify_draft_transaction.py` (line 37) and `publisher_agent.py` (line 45) to use mandatory environment-variable lookup with no hardcoded fallback:

```python
import os
SHOPIFY_TOKEN = os.environ["SHOPIFY_ACCESS_TOKEN"]
```

### Step 3 — Add .env to .gitignore (Required)

Create or update `.gitignore` in the workspace root:

```
*.env
.env
.envcp
```

### Step 4 — Update All 5 Dependent Modules (Required)

Update all Hoverboard Store ORIN modules to use the new environment-variable pattern:
*   `tools/shopify_publisher/orin/shopify_draft_transaction.py`
*   `tools/shopify_publisher/orin/publisher_agent.py`
*   `tools/shopify_publisher/orin/live_draft_gate.py`
*   `tools/shopify_publisher/orin/writer_agent.py`
*   `tools/shopify_publisher/orin/orin_phase2d_writer_dryrun.py`

### Step 5 — Remove Credential from Markdown Reports (Required)

Remove literal credentials from:
*   `clients/hoverboard_store/content_engine/orin_phase_i_shopify_write_path_audit.md` (lines 13 and 170)
*   `clients/hoverboard_store/content_engine/orin_phase_i2s_shopify_credential_exposure_audit.md` (multiple lines)

Replace all literal token occurrences with `[HOVERBOARD_STORE_SHOPIFY_TOKEN]` or `[REDACTED]`.

### Step 6 — Clear /tmp Scripts (Advisory)

Delete the 6 credential-containing /tmp scripts:
*   `/tmp/audit_drafts.py`
*   `/tmp/confirm_draft_status.py`
*   `/tmp/debug_comparison.py`
*   `/tmp/fetch_drafts.py`
*   `/tmp/real_body_comparison_script.py`
*   `/tmp/real_normalization_proof_script.py`

### Step 7 — Re-run Phase I.2S After Remediation (Required)

After completing all remediation steps, re-run a full Phase I.2S audit to confirm:
*   Zero hardcoded literals in source code
*   Zero literals in /tmp artifacts
*   Git history clean or repository rebuilt from scratch

---

## Proof Summary

1. **HCS inspected in this run:** No
2. **Secret values printed:** No
3. **Git repository found:** Yes
4. **Git repository root:** `/data/.openclaw/workspace/.git`
5. **Git history capability classification:** `GIT_REPOSITORY_WITH_NO_COMMITS`
6. **Total Git commit count:** 0
7. **Current Hoverboard/ORIN literal secret matches count:** 15
8. **Hoverboard/ORIN files containing literal secrets count:** 8
9. **Hardcoded token executable code:** Yes
10. **Hardcoded token docstring:** Yes
11. **Environment variable loading exists:** No
12. **Mandatory environment-only token loading:** No
13. **Hardcoded token fallback exists:** No
14. **Hoverboard /tmp secret-containing paths:** 6 scripts (audit_drafts.py, confirm_draft_status.py, debug_comparison.py, fetch_drafts.py, real_body_comparison_script.py, real_normalization_proof_script.py)
15. **Hoverboard report/preview secret-containing paths:** 2 files (orin_phase_i_shopify_write_path_audit.md, orin_phase_i2s_shopify_credential_exposure_audit.md)
16. **Previous chat secret exposure reported by operator:** Yes
17. **Git history secret exposure result:** `UNPROVEN` (zero commits — Git history not available)
18. **Direct production credential dependencies:** 2 (shopify_draft_transaction.py, publisher_agent.py)
19. **Indirect production credential dependencies:** 3 (live_draft_gate.py, writer_agent.py, orin_phase2d_writer_dryrun.py)
20. **Shopify touched:** No
21. **Queue touched:** No
22. **Cron touched:** No
23. **Final security classification:** `HOVERBOARD_CREDENTIAL_EXPOSED_GIT_UNPROVEN`
24. **Exact Hoverboard-only remediation order:** Rotate credential → Implement mandatory env-var loading → Add .gitignore → Update 5 dependent modules → Remove credentials from 2 markdown reports → Delete 6 /tmp scripts → Re-run Phase I.2S audit after remediation