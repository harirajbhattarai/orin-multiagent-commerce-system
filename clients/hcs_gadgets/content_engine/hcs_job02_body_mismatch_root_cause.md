# HCS Job 02 — Body Mismatch Root Cause Analysis

**Date:** 2026-07-03
**Incident:** Phase 0.2 Shopify PUT appeared to succeed but body_html was not updated
**Article ID:** 1001998647670
**Status:** Root cause identified — permanent safeguards created

---

## Timeline

| Time | Event |
|------|-------|
| Phase 0.2 | ORIN ran Shopify PUT to update Article ID 1001998647670 with new title, handle, body_html, and published_at: null |
| Phase 0.2 proof | Claimed success based on PUT response — title appeared correct |
| Later review | Operator/user noted body content looked like the old generic BBQ accessories guide |
| Emergency fix (20:34) | Fetched live Shopify body, compared SHA256 to local draft — bodies did NOT match |
| Emergency fix (20:34) | Saved backup, validated local draft, PUT correct body_html, verified hash match |
| Post-fix baseline | All checks pass — Shopify now matches local draft |

---

## What Failed

### Primary Failure: Body HTML Not Updated

The Phase 0.2 PUT request returned a success response with the correct title, but the body_html in Shopify was NOT replaced with the local draft HTML.

**Shopify body SHA256 before emergency fix:** `b17d1f3c151400f6c98c29eebac21960c39e87adfa4429c7a97d70c321b23533`
**Local draft SHA256:** `40f1e0c14434c6166dc8c29561f16f5fd0010ba1aedb7c02a2fc9a5930e987f1`

These hashes are different. The body content did not match.

**Confirmed old content still present in Shopify before fix:**
- "BBQ Accessories UK" (old title text)
- "tongs" (unsupported accessory)
- "thermometer" (unsupported accessory)
- "grilling tongs" (unsupported accessory)
- "How to Choose the Right Gear" (old subtitle)

### Secondary Failure: published_at Was Set

The Shopify article had `published_at: 2026-07-03T19:25:23+01:00` when it should have been `null` (draft).

This suggests either:
- The Phase 0.2 update included an accidental publish step, OR
- Something else set published_at after the update

### Tertiary Failure: Handle Not Updated

The handle remained `bbq-accessories-uk-how-to-choose-the-right-gear` instead of being updated to `portable-bbq-chimney-starter-guide-uk-gardens`.

This means title, handle, AND body were all partially or fully incorrect.

---

## Why Previous Proof Was Insufficient

### Phase 0.2 Proof Was a False Positive

The Phase 0.2 proof relied on:

1. **PUT response** — assumed if the server returned a 200 with correct title, the whole update succeeded
2. **No body hash comparison** — SHA256 of Shopify body was never computed and compared to SHA256 of local draft
3. **No post-update fetch** — Shopify was never re-fetched after the update to verify the body was actually written
4. **No published_at check** — did not verify published_at was null
5. **No duplicate handle check** — did not verify the handle had actually been updated

**The PUT response told us the title was correct. It told us nothing about whether the body was correct.**

---

## Permanent Rule: Never Trust Update Response Alone

A Shopify API PUT response confirms the server accepted the request. It does NOT confirm:
- That body_html was written correctly
- That published_at was set as requested
- That the handle was updated
- That the update succeeded in any way beyond the fields the response reflects

**The ONLY way to verify a Shopify update is to:**
1. Fetch the article from Shopify after the update
2. Compare body_html SHA256 to the local draft SHA256
3. Verify published_at is null
4. Verify the handle is correct
5. Verify no old content remains

---

## What the Emergency Fix Did

1. **Fetched Shopify** — confirmed body mismatch and wrong handle
2. **Saved backup** — `backups/article_1001998647670_before_body_mismatch_fix.json`
3. **Validated local draft** — 42/42 HTML validator pass, all product truth checks pass
4. **PUT correct body_html** — with correct handle and published_at: null
5. **Re-fetched Shopify** — confirmed SHA256 now matches local draft exactly
6. **Verified published_at** — confirmed null
7. **Verified handle** — confirmed updated

---

## Summary of Hashes

| Stage | Body SHA256 |
|-------|-------------|
| Shopify before emergency fix (old body) | b17d1f3c151400f6c98c29eebac21960c39e87adfa4429c7a97d70c321b23533 |
| Local draft HTML | 40f1e0c14434c6166dc8c29561f16f5fd0010ba1aedb7c02a2fc9a5930e987f1 |
| Shopify after emergency fix | 40f1e0c14434c6166dc8c29561f16f5fd0010ba1aedb7c02a2fc9a5930e987f1 ✅ MATCH |

---

## Safeguards Now In Place

| Safeguard | File |
|-----------|------|
| Safety rules for future updates | `rules/hcs_shopify_draft_update_safety_rules.md` |
| Safe updater script | `tools/shopify_publisher/orin/hcs_safe_update_existing_draft.py` |

---

## Lessons Learned

1. **API responses are not proof of correctness** — always fetch and verify
2. **published_at must be explicitly checked** — never assume draft status
3. **Body hash comparison is mandatory** — SHA256 compare is definitive
4. **Handle update must be verified** — cannot assume it was set correctly
5. **Proof must include post-update verification** — not just request-response

---

*Root cause analysis by ORIN — 2026-07-03*
