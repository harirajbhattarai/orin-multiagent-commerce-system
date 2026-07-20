# ORIN Duplicate Incident — Job 20 Shopify Draft

## Incident Summary

**Date:** 2026-06-30
**Job:** Job 20 — Best Hoverboard Accessories for Safer Riding
**Incident:** Duplicate Shopify draft created and later deleted
**Severity:** Medium — non-canonical article existed in Shopify with wrong slug and old content

---

## Timeline

| Time | Event |
|---|---|
| ~10:21 | Duplicate draft created at wrong handle (Phase 2D pre-flight confusion — different slug attempted) |
| 10:21–16:20 | Duplicate draft sat in Shopify as unpublished draft with old content |
| 16:20 | Phase 2F canonical draft pushed — Article ID 1006845985116, handle `best-hoverboard-accessories-safer-riding-uk-2026` |
| ~16:21 | Duplicate draft still in Shopify |
| 19:15 | Phase 2F baseline locked (duplicate not detected at that point) |
| 19:52 | Emergency audit detected duplicate |
| 20:12 | Manual deletion approved and executed |
| 20:32 | Phase 2G preflight hardening completed |

---

## Articles Involved

### Canonical (KEPT)
| Field | Value |
|---|---|
| Article ID | 1006845985116 |
| Handle | best-hoverboard-accessories-safer-riding-uk-2026 |
| Title | Best Hoverboard Accessories for Safer Riding UK 2026 |
| Content | Improved — "one of the most important safety accessories", no old risky wording |
| Status | draft |
| published_at | null |
| Queue recorded | YES |

### Duplicate (DELETED)
| Field | Value |
|---|---|
| Article ID | 1006842446172 |
| Handle | best-hoverboard-accessories-**FOR**-safer-riding-uk-2026 |
| Title | Best Hoverboard Accessories for Safer Riding UK 2026 |
| Content | OLD — "single most effective", "less fall risk than standing alone" |
| Status | draft |
| created_at | 2026-06-30T10:21:38+01:00 |
| Queue recorded | NO |

---

## Root Cause Analysis

**Two failures combined:**

### Failure 1: Stale local inventory
The Phase 2E dry-run read from a local `shopify_inventory.json` snapshot that did not include the duplicate draft created at 10:21. The duplicate draft existed in Shopify but was not in the local inventory file. Publisher Agent preflight only checked exact handle — the duplicate had a **different handle** (wrong slug with "for" inserted), so it was not caught by the handle check.

### Failure 2: Exact-handle-only preflight
The Phase 2E Publisher Agent preflight logic only checked:
- Exact handle match → blocked if found
- Similar title overlap (word-level) → flagged for review

It did **not** check:
- Exact title match with a different handle → would have caught duplicate immediately
- Near-handle variants (e.g. same slug with "for" inserted) → would have caught the wrong slug

The duplicate had an **identical title** but a **different handle** — both failure modes combined to let it through.

---

## Fix Applied: Phase 2G

### 1. Live inventory refresh before every preflight
`fetch_live_shopify_inventory()` now runs as Step 4 of every Publisher Agent preflight.
No longer relies on stale local snapshot.

### 2. Exact title check (different handle = block)
`analyse_shopify_conflicts()` now checks:
- `exact_title_match`: article with identical title but different handle → immediate BLOCK

### 3. Near-handle variant detection
`_is_near_handle()` detects slug variants differing by a single small token (e.g. "for" inserted).
Blocked with `blocked_near_handle_conflict`.

### 4. Self-match detection
If canonical article is already in Shopify and matches queue article ID → `ALREADY_CREATED` decision.
Not a block — acknowledged as already done.

### 5. Blocking priority
In priority order:
1. ALREADY_CREATED (self-match) → pass
2. BLOCKED — exact title match with different handle → block
3. BLOCKED — near-handle conflict → block
4. BLOCKED — exact handle exists → block
5. Other checks (queue, compliance, quality) → block/fail as appropriate

---

## Lessons

1. **Always refresh live inventory** before any live Shopify write. Local snapshots are unreliable.
2. **Check exact title** alongside exact handle. Duplicate content can exist under different slugs.
3. **Near-handle detection** catches slug typos and variants (e.g. "for" inserted).
4. **Queue article ID** is the canonical anchor — self-match prevents double-push on already-created articles.
5. **Stale inventory + single-check = duplicate risk.** Multi-check + live inventory = hardened.

---

## Verification

After Phase 2G fix applied:
- Live inventory refreshed: ✅ (35 articles — duplicate deleted)
- Exact handle match: ✅ Article ID 1006845985116
- Exact title match (different handle): ✅ NONE
- Near-handle variants: ✅ NONE
- Self-match: ✅ TRUE — matches queue article ID
- Decision: `ALREADY_CREATED` — correct ✅

---

_Locked: 2026-06-30 20:32 GMT+1_
