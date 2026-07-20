# HCS Gadgets — Product Claim Extraction Rules

**Version:** 1.0
**Date:** 2026-07-04
**Phase:** Product Intelligence Phase 0 — PHASE C
**Status:** APPROVED — All claim extraction must follow these rules

---

## Core Principle

**Product description is source material, not automatic truth.**

The Shopify `body_html` product description is written by suppliers or transferred from manufacturer listings. It contains a mixture of:
- Useful, verifiable product facts
- Marketing language and superlatives
- Volatile commercial information (prices, offers, stock)
- Safety and compliance claims that may be unsupported
- Stale or outdated specifications
- Internal operational data

**No claim from a product description may be added to the writer-safe Public Content View without passing the Claim Classification process below.**

---

## Claim Classification

Every extracted claim must be classified into one of five categories.

---

### Category A — Stable Factual Claims

**Definition:** Objective product facts that are unlikely to change, directly stated in the source, and not contradicted by other fields.

**Examples of Stable Factual Claims:**
- Dimensions: `dimensions of 85 x 85 x 73 cm`
- Capacity: `capacity of 415L`
- Material: `made from stainless steel`
- Included items: `includes 3 soy wax melts`
- Product function: `heats to 45°C`
- Supported features: `features Bluetooth connectivity`
- Weight: `weighs 5.0 kg`
- Power rating: `1500W motor`
- Battery type: `4400mAh Li-Ion battery`

**Evidence standard for Category A:**
- Must be explicitly stated in the source
- Must not be contradicted by another structured field
- Must not be a marketing interpretation of a vague statement

**Stability:** `stable`

**Writer exposure:** `public` (after conflict check)

---

### Category B — Marketing Claims

**Definition:** Superlatives, brand-value language, and persuasive phrasing that characterises the product rather than specifying it.

**Examples of Marketing Claims:**
- `Experience the ultimate in personal transport`
- `premium quality`
- `revolutionary design`
- `unmatched performance`
- `world's best`
- `leading brand`
- `award-winning`
- `innovative technology`
- `powerful motor` (vague — what does powerful mean numerically?)
- `fast charging` (vague without stated time)
- `perfect for` (subjective)
- `designed for those who` (lifestyle framing)
- `bold` / `refined` / `unforgettable` (brand tone, not facts)

**Evidence standard for Category B:**
- Marketing claims must NOT become verified factual claims without additional supporting data
- Words like `ultimate`, `premium`, `best`, `powerful`, `innovative` are NOT factual specifications
- A vague marketing claim can be upgraded to Category A only if a specific, measurable claim accompanies it

**Example of upgrade:**
- ❌ `powerful motor` → Not a stable fact (what wattage?)
- ✅ `250W motor` + `powerful` (marketing) → The `250W` is Category A, `powerful` is ignored

**Stability:** N/A — not used as facts

**Writer exposure:** `review` or excluded entirely

---

### Category C — Safety and Compliance Claims

**Definition:** Claims about product safety, certifications, regulatory compliance, or hazard mitigation.

**Examples of Safety/Compliance Claims:**
- `UK safety certified`
- `certified to BS EN standards`
- `fireproof`
- `waterproof` / `IPX rated`
- `child-safe`
- `non-toxic`
- `flame-retardant`
- `road legal`
- `UK approved`
- `CE marked`
- `safe indoor use`
- `prevents accidents`
- `fail-safe`

**Evidence standard for Category C:**
- These require the strongest evidence because they carry regulatory and liability implications
- A statement like `UK safety certified` without a specific standard number (e.g., `BS EN 14682`) is an unsupported claim
- If a specific standard is named and verifiable, the claim may be accepted as `medium` confidence with compliance flag
- If no standard is named, the claim must be excluded or marked `compliance_risk: high`

**Required actions for Category C:**
1. If a specific standard is cited (e.g., `BS EN 14682`) → record with `compliance_risk: medium`, require standard confirmation
2. If no specific standard is cited → classify as `claims_needing_review`, do not include in writer-safe view
3. Never include safety claims that cannot be verified against a named standard

**Stability:** N/A — requires human review

**Writer exposure:** `review` (only after human approval)

---

### Category D — Volatile Claims

**Definition:** Commercial and operational information that changes frequently and must never appear in evergreen article content.

**Examples of Volatile Claims:**
- Price: `£8.99`, `save 50%`, `was £19.99`
- Sale/discount: `% off`, `special offer`, `today only`
- Availability: `in stock`, `selling fast`, `only 3 left`, `limited units`
- Delivery: `free delivery`, `next day delivery`, `order now`
- Offer language: `free with purchase`, `bonus item`, `buy one get one`

**Rule:** Volatile claims must never be added to the writer-safe Public Content View under any circumstances.

**Exception:** `price` may be used only for explicitly price-led content (e.g., "Best hoverboards under £100") and only after fetching current verified price data at the time of writing.

**Stability:** `volatile`

**Writer exposure:** `internal` — excluded from writer view

---

### Category E — Internal and Operational Fields

**Definition:** Shopify-internal fields that must never appear in any customer-facing content.

**Examples:**
- SKU: `BBQ-FIRE-STARTER`, `MINI1PROSCOOTER-BLUE`
- Shopify product ID: `15119636922742`
- Variant ID: `55385287917942`
- Inventory item ID: `53812303069558`
- `admin_graphql_api_id`: `gid://shopify/Product/...`
- Inventory quantity: `200 units in stock`
- `images_count`: `7`
- `compare_at_price`: `99.99`
- `old_inventory_quantity`: `0`
- `inventory_policy`: `deny`
- `fulfillment_service`: `manual`
- `inventory_management`: `shopify`

**Rule:** These fields must be explicitly listed in `prohibited_writer_fields` in every Product Knowledge Profile and must never appear in any writer-facing document.

**Stability:** N/A

**Writer exposure:** `internal` — strictly prohibited

---

## The MISSING DATA Rule

**MISSING DATA != PERMISSION TO INFER.**

If a fact is not supported by any source, the profile must record `unknown` — not guess.

Common missing facts that must NOT be inferred:

| Missing Fact | Required Action |
|-------------|-----------------|
| Maximum speed (hoverboard/scooter) | Record `unknown` — do not say "up to X km/h" unless stated |
| Battery range | Record `unknown` — do not infer from battery capacity |
| Age range | Record `unknown` unless stated — do not infer from product size |
| Maximum weight capacity | Record `unknown` unless stated |
| Certification standard | Record `unknown` unless a named standard is cited |
| Warranty period | Record `unknown` unless stated |
| Material | Record `unknown` unless stated — do not assume "stainless steel" |
| Waterproof rating | Record `unknown` unless IPX or specific rating is stated |
| Charging time | Record `unknown` unless stated — "fast charge" is not a specification |

---

## Extraction Process

For each product, follow this sequence:

1. **Strip HTML/CSS** from `body_html` to get plain text
2. **Identify factual claims** — look for specific numbers, units, materials, features
3. **Classify each claim** into Category A–E
4. **Cross-check** against structured fields (variants, title, product_type)
5. **Check for conflicts** — does the description contradict the structured data?
6. **Record provenance** — which source field confirmed each claim
7. **Flag for review** — any Category C or uncertain claims
8. **Build ClaimRecord** for each Category A claim

---

## Description Text Extraction Pattern Guide

**Extract as Category A (if specific):**
- Numbers with units: `1500W`, `4400mAh`, `85 x 85 x 73 cm`, `415L`, `5.0 kg`, `2 hours`, `2-3 hours`
- Stated materials: `stainless steel`, `ceramic`, `soy wax`, `metal`
- Stated inclusions: `includes X`, `comes with Y`
- Stated functions: `recharges via USB`, `waterless diffusion`
- Specific features: `Bluetooth enabled`, `LED lights`, `adjustable handlebar`

**Treat as Category B (ignore or downgrade):**
- Vague adjectives: `powerful`, `premium`, `ultimate`, `innovative`, `high-quality`
- Lifestyle framing: `designed for those who`, `perfect for`, `experience the`
- Brand tone: `bold`, `refined`, `unforgettable`, `game-changing`

**Treat as Category C (require evidence):**
- `safe`, `certified`, `UK approved`, `BS EN`, `road legal`, `waterproof`
- Requires specific named standard or explicit verification

**Treat as Category D (exclude):**
- Any `£` price or currency symbol
- `in stock`, `available`, `selling fast`, `limited`
- `free delivery`, `next day`, `order now`
- `% off`, `save`, `was`, `deal`

---

## Conflict Handling

If the same fact is stated differently in different sources:

| Conflict | Action |
|----------|--------|
| Title says X, description says Y | Record in `data_conflicts`, prefer structured field, mark `confidence: medium` |
| Description contradicts variant field | Prefer variant field, flag description as potentially stale |
| Two numbers in description don't match | Record in `data_conflicts`, do not guess which is correct |

**Never resolve a conflict by choosing the more impressive number.**

---

## Example: Claim Extraction

**Source:** Hoverboard description text:
> "Experience the ultimate in personal transport with our UK safety certified G1 Plus Hoverboard. Combining British safety standards with cutting-edge technology for a reliable, eco-friendly transport solution. Key Features: 4400mAh Li-Ion battery for extended use. Up to 2 hours continuous riding time. Quick 2-3 hour charge."

**Extracted claims:**

| Claim | Category | Confidence | Action |
|-------|----------|------------|--------|
| `UK safety certified` | C (safety/compliance) | low | Flag for review — no standard named |
| `4400mAh Li-Ion battery` | A (stable) | high | Add to verified_specifications |
| `Up to 2 hours continuous riding time` | A (stable) | medium | Add — time stated, but "up to" is optimistic qualifier |
| `Quick 2-3 hour charge` | A (stable) | medium | Add — range stated |
| `UK safety certified` without standard | C | low | Exclude from writer view, add to claims_needing_review |
| `ultimate in personal transport` | B (marketing) | N/A | Exclude — superlative |
| `eco-friendly` | B (marketing) | N/A | Exclude — vague marketing claim |
| `cutting-edge technology` | B (marketing) | N/A | Exclude — superlative |
