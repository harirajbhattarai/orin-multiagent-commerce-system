# ORIN Phase H1 — Live-Draft Gate Audit

**Report Date:** 2026-07-08
**Phase:** H1 — Existing Live-Draft Gate Audit

---

## Current Live-Draft Gate (cron_entrypoint.py)

### CLI Flag Definitions

```python
LIVE_DRAFT = "--live-draft" in sys.argv      # line 87
CONFIRM_LIVE_DRAFT = "--confirm-live-draft" in sys.argv  # line 88
```

### Gate Conditions (Lines 109-122)

```
if LIVE_DRAFT and not DRY_RUN and not CONFIRM_LIVE_DRAFT:
    → sys.exit(1): "--live-draft is not yet enabled."

if LIVE_DRAFT and not CONFIRM_LIVE_DRAFT:
    → sys.exit(1): "--live-draft mode is BLOCKED."

if LIVE_DRAFT and CONFIRM_LIVE_DRAFT:
    → print("[SAFETY GATE] --confirm-live-draft detected...")
    → continues to pipeline
```

### Hard Block at Pipeline End (Lines 548-552)

```python
# ── LIVE DRAFT (BLOCKED) ─────────────────────────────────────────────
return pipeline_blocked(
    "--live-draft is BLOCKED. Do not use until explicitly enabled."
)
```

### Classification

| Gate element | Classification |
|---|---|
| Lines 109-111: `--live-draft` without `--dry-run` + `--confirm-live-draft` exit | TEMPORARY_SAFETY_BLOCK |
| Lines 115-118: `--live-draft` without `--confirm-live-draft` exit | TEMPORARY_SAFETY_BLOCK |
| Lines 121-122: `--confirm-live-draft` safety message | CONTINUATION_POINT |
| Lines 548-552: `return pipeline_blocked(...)` | **PERMANENT_BLANKET_BLOCK** |

### Old Block Type

The block at line 548-552 is a **permanent blanket block** — it unconditionally refuses any live-draft path regardless of pipeline state. It is not gated on any safety check.

**It is not a Phase 3C temporary block.** It is a permanent production stop.

### Production Cron Command

```python
payload = {
    "kind": "agentTurn",
    "message": "cd /data/.openclaw/workspace && python3 tools/shopify_publisher/orin/cron_entrypoint.py --live-draft --confirm-live-draft"
}
```

Both `--live-draft` and `--confirm-live-draft` are present. However, the hard block at line 548-552 prevents any live-draft execution.

---

## Shopify Draft Creation Function

### Module

`tools/shopify_publisher/publish_blog_draft.py`

### Function

`main()` — accepts one argument: `path/to/article.html`

### Required Inputs

| Field | Source | Controllable |
|---|---|---|
| HTML file path | CLI argument | Yes |
| Title | Extracted from HTML SEO meta or H1 | Yes (via HTML meta) |
| Handle/slug | Extracted from HTML URL slug meta | Yes (via HTML meta) |
| Body HTML | Full HTML from file | Yes |
| Author | Hardcoded "Hoverboard Store" | No |
| `published` | Hardcoded `False` (draft mode) | No — always creates draft |
| Tags | Hardcoded "ORIN Draft, SEO Blog" | No |

### `published_at` Control

**Not sent in payload.** The script sets `published: False` which creates a draft. No `published_at` field is included. Articles are created as drafts by default.

### Post-Fetch Body Verification

**Not implemented.** The script does not fetch the created article to verify body content. It only logs success after creation.

This means `BLOCK_POST_FETCH_BODY_VERIFICATION_UNAVAILABLE` must be enforced until verification is added.

---

## Blocked Script Patterns

`cron_entrypoint.py` line 45:
```python
BLOCKED_SCRIPT_PATTERNS = [
    "tools/shopify_publisher/hcs_publish_blog_draft.py",
    "tools/shopify_publisher/publish_blog_draft.py",
    ...
]
```

`publish_blog_draft.py` is on the blocked list — it cannot be called by the pipeline even if the gate approves it. The actual Shopify write call path needs to be a non-blocked module.

---

## Gate v2 Required Changes

1. **Replace** the hard block at line 548-552 with a call to the new Live-Draft Gate v2
2. **Add** `live_draft_gate.py` module
3. **Implement** post-fetch body verification stub (returns unavailable until implemented)
4. **Keep** `--live-draft` and `--confirm-live-draft` flags active
5. **Remove** the old permanent block only after Gate v2 integration
