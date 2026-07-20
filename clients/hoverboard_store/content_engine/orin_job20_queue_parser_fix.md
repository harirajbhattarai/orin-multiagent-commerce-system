# ORIN Job 20 Queue Parser Fix — Repair Report

**Date:** 2026-07-06
**Phase:** C — Queue Parser Fix
**Status:** ✅ COMPLETE

---

## Root Cause

Queue notes use two different formats for recording Shopify Article IDs:

| Format | Used by |
|---|---|
| `Article ID: 123` | Jobs 15–19 (historical) |
| `Shopify article ID: 1006845985116` | Job 20 onwards |

The original regex `r"Article ID:\s*(\S+)"` was looking for `Article ID:` as a literal substring. Since `"Shopify article ID:"` is not the same string as `"Article ID:"`, the regex returned `None` for Job 20.

**Evidence:**
```
Queue notes for Job 20:
Shopify article ID: 1006845985116

Regex: r"Article ID:\s*(\S+)"
Result: None  ← No match
```

**False positive triggered:**
- `shopify_id_from_notes = None` (parsed)
- `resolve_shopify_article()` falls back to `KNOWN_IDS` (no Job 20 entry)
- `shopify_article_id=None` → `detect_state="unknown"`
- Category 3 false positive: "local draft exists without Shopify article ID" warning

---

## Fix Applied

### File 1: `tools/shopify_publisher/orin/state_agent.py`

Function: `read_queue()` → `shopify_id_note` regex

```python
# Before:
shopify_id_note = re.search(r"Article ID:\s*(\S+)", notes)

# After:
shopify_id_note = re.search(r"(?:Shopify\s+)?Article\s+ID:\s*(\S+)", notes, re.IGNORECASE)
```

**Pattern breakdown:**
- `(?:Shopify\s+)?` — optional `Shopify ` prefix (non-capturing)
- `Article\s+ID:` — flexible whitespace between words
- `\s*(\S+)` — optional whitespace then capture the ID

**Also fixed `shopify_handle` regex similarly:**
```python
# Before:
shopify_handle_note = re.search(r"Shopify handle:\s*(.+?)(?:\n|$)", notes)

# After:
shopify_handle_note = re.search(r"(?:Shopify\s+)?handle:\s*(.+?)(?:\n|$)", notes, re.IGNORECASE)
```

**Added trailing period stripping** for handles stored with trailing `.` in queue notes.

### File 2: `tools/shopify_publisher/orin/cron_entrypoint.py`

Duplicate `read_queue()` function (local copy in cron entrypoint) also updated with same fix.

---

## Verification

### Before Fix
```
Job 20 parsed Shopify Article ID: None
Job 20 detected_state: unknown
Recovery items: 1 (false positive — Category 3)
```

### After Fix
```
Job 20 parsed Shopify Article ID: 1006845985116
Job 20 detected_state: clean_draft_created
Recovery items: 0 (false positive eliminated)
```

### Both Formats Supported
```
Input: "Article ID: 123"      → parsed: "123" ✅
Input: "Shopify article ID: 1006845985116" → parsed: "1006845985116" ✅
```

---

## Shopify Verification

Shopify article ID `1006845985116` confirmed:
- Exists in Shopify (live inventory)
- Status: `draft` (`published_at: null`)
- Handle: `best-hoverboard-accessories-safer-riding-uk-2026`
- Title: "Best Hoverboard Accessories for Safer Riding UK 2026"
- Present in `shopify_inventory.json` (35 articles)

**Queue status:** `draft_created` (correct — article exists in Shopify as draft)

**Classification after fix:** `ALREADY_CREATED_QUEUE_ALREADY_CORRECT`

No recovery action needed for Job 20.
