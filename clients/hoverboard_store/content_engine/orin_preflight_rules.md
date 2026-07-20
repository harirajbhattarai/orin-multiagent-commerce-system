# ORIN Preflight Rules — Hoverboard Store

These rules govern how ORIN handles Shopify article updates and draft creation. They exist to prevent silent overwrites and ensure every structural decision is deliberate and logged.

---

## Handle Preservation Rule

**When updating an existing Shopify draft, the orchestrator must not silently change the Shopify handle.**

Before any update:

1. Read the existing Shopify article handle from `shopify_inventory.md` or `shopify_inventory_raw.json`.
2. Read the local draft's `url_slug` metadata from the HTML comment block.
3. If they differ, **stop and require an explicit decision** before proceeding.
4. Never change a live or draft URL slug automatically.

If the user chooses to keep the Shopify handle:
- The update payload must preserve the existing Shopify handle.

If the user chooses to change the handle:
- Log the reason clearly in the queue notes.

**Approved handles (locked):**

| Job | Article ID | Approved Handle |
|-----|-----------|----------------|
| Job 15 | `1006811971932` | `how-to-store-a-hoverboard-battery-safely-hoverboard-store` |
| Job 16 | `1006814593372` | `6-5-vs-8-5-inch-hoverboards-for-kids-simple-buying-guide-hoverboard-store` |
| Job 17 | `1006818689372` | `hoverboard-won-t-turn-on-safe-checks-before-you-replace-it` |
| Job 18 | `1006819246428` | `hoverboard-weight-limit-guide-for-parents` |
| Job 19 | `1006822064476` | `christmas-hoverboard-gift-guide-for-kids-uk` |

---

## Draft Creation Rule

Before creating a new Shopify draft, verify:

1. The topic does not already exist in `shopify_inventory.md`.
2. No duplicate handle exists in Shopify.
3. Queue notes are updated with article ID and handle after creation.

---

## Update Payload Rules

- Always pass `published: false` to preserve draft status unless explicit publish is requested.
- Always extract title from local draft `seo_title` or `meta_title` metadata, falling back to H1.
- Never omit `author` field — always set to `Hoverboard Store`.
- Tags field must include `ORIN Draft` for all drafted content.

---

## Queue Update Rules

After any Shopify action, update the queue notes with:

- Shopify article ID
- Shopify handle
- Timestamp
- Any override decisions and reasons

---

*Last updated: 2026-06-28*
