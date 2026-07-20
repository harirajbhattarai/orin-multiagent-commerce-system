#!/usr/bin/env python3
"""
HCS Gadgets — Product Knowledge Profile Builder v1.0

Reads Shopify raw product data and produces structured Product Knowledge Profiles
and a writer-safe Public Content View.

Usage:
    python3 hcs_product_knowledge_builder.py \
        --raw-catalog clients/hcs_gadgets/content_engine/product_catalog_raw.json \
        --catalog clients/hcs_gadgets/content_engine/product_catalog.json \
        --link-map clients/hcs_gadgets/content_engine/hcs_verified_link_map.json \
        --output-dir clients/hcs_gadgets/content_engine/

Outputs:
    product_knowledge_profiles.json
    product_knowledge_profiles.md
    product_content_view.json
    product_content_view.md
"""
import argparse
import json
import re
import sys
from datetime import datetime

VERSION = "1.0"

# ─── Claim Categories ─────────────────────────────────────────────────────────

CAT_A_STABLE = "stable_factual"
CAT_B_MARKETING = "marketing"
CAT_C_SAFETY = "safety_compliance"
CAT_D_VOLATILE = "volatile"
CAT_E_INTERNAL = "internal"

CONFIDENCE_HIGH = "high"
CONFIDENCE_MEDIUM = "medium"
CONFIDENCE_LOW = "low"

STABILITY_STABLE = "stable"
STABILITY_VOLATILE = "volatile"

EXPOSURE_PUBLIC = "public"
EXPOSURE_INTERNAL = "internal"
EXPOSURE_REVIEW = "review"

COMPLIANCE_LOW = "low"
COMPLIANCE_MEDIUM = "medium"
COMPLIANCE_HIGH = "high"

# ─── HTML Stripping ───────────────────────────────────────────────────────────

def strip_html(html):
    """Remove HTML tags and CSS to extract plain text from Shopify body_html."""
    if not html:
        return ""
    html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r'<style[^>]*>', '', html, flags=re.IGNORECASE)
    html = re.sub(r'<meta[^>]*>', '', html, flags=re.IGNORECASE)
    html = re.sub(r'<[^>]+>', ' ', html)
    html = re.sub(r'&nbsp;', ' ', html)
    html = re.sub(r'&amp;', '&', html)
    html = re.sub(r'&lt;', '<', html)
    html = re.sub(r'&gt;', '>', html)
    html = re.sub(r'\s+', ' ', html).strip()
    return html

# ─── Claim Extraction ─────────────────────────────────────────────────────────

def extract_claims(text, product_title, handle):
    """
    Extract and classify claims from description text.
    Returns (stable_claims, marketing_claims, safety_claims, volatile_claims).
    Each is a list of dicts with claim details.
    """
    stable = []
    marketing = []
    safety = []
    volatile = []

    text_lower = text.lower()
    sentences = re.split(r'[.]\s+', text)

    # ── Superlative/marketing patterns ──────────────────────────────────────
    marketing_patterns = [
        r'\bthe ultimate\b', r'\bpremium\b', r'\brevolutionary\b',
        r'\bunmatched\b', r'\bworld\'s best\b', r'\baward-winning\b',
        r'\btop rated\b', r'\bmost popular\b', r'\btop-selling\b',
        r'\bleading brand\b', r'\b game-changing\b', r'\bpowerful\b',
        r'\bbold\b', r'\brefined\b', r'\bunforgettable\b',
        r'\bdesigned for those who\b', r'\bperfect for\b',
        r'\bexperience the\b', r'\bcutting-edge\b', r'\binnovative\b',
        r'\bhigh-quality\b', r'\bmega sale\b',
    ]

    # ── Safety/compliance patterns ───────────────────────────────────────────
    safety_patterns = [
        (r'\bUK safety certified\b', 'UK safety certified (no standard named)'),
        (r'\bUK certified\b', 'UK certified (no standard named)'),
        (r'\bcertified to BS EN \d+\b', None),  # captured separately
        (r'\bBS EN \d+\b', None),  # captured separately
        (r'\bwaterproof\b', 'waterproof (no IPX rating)'),
        (r'\bIPX\d+\b', None),  # captured separately
        (r'\bfireproof\b', 'fireproof'),
        (r'\bflame-retardant\b', 'flame-retardant'),
        (r'\bnon-toxic\b', 'non-toxic'),
        (r'\broad legal\b', 'road legal'),
        (r'\bCE marked\b', 'CE marked'),
        (r'\bchild-safe\b', 'child-safe'),
        (r'\bsafe indoor use\b', 'safe indoor use'),
        (r'\bsafe\b(?!\s+(?:for|with|when|in))', 'generic safe claim'),  # 'safe' standalone
    ]

    # ── Volatile/commercial patterns ─────────────────────────────────────────
    volatile_patterns = [
        (r'£[\d,.]+', 'price reference'),
        (r'\$[\d,.]+', 'price reference'),
        (r'\bwas £[\d,.]+', 'original price'),
        (r'\bsave \d+%', 'discount claim'),
        (r'\b%d off', 'discount percentage'),
        (r'\bin stock\b', 'stock claim'),
        (r'\bout of stock\b', 'stock claim'),
        (r'\bavailable\b', 'availability claim'),
        (r'\bonly \d+ (?:left|remaining|units?)\b', 'stock urgency'),
        (r'\bselling fast\b', 'stock urgency'),
        (r'\bfree delivery\b', 'delivery claim'),
        (r'\bnext day delivery\b', 'delivery claim'),
        (r'\border now\b', 'urgency'),
        (r'\b今\b', 'non-English content'),
    ]

    # ── Extract numeric specifications ───────────────────────────────────────
    spec_patterns = [
        (r'(\d+(?:\.\d+)?)\s*[kK][wW]\b', 'power_kw', 'Power (kW)'),
        (r'(\d+(?:\.\d+)?)\s*[wW]\b(?!.*\bheat\b)', 'power_w', 'Power (W)'),
        (r'(\d+(?:\.\d+)?)\s*[mM][aA][hH]\b', 'battery_mah', 'Battery capacity (mAh)'),
        (r'(\d+(?:\.\d+)?)\s*[lL]\b', 'capacity_l', 'Capacity (L)'),
        (r'(\d+(?:\.\d+)?)\s*[mM][bB]\b', 'size_mb', 'Size (MB)'),
        (r'(\d+)\s*[gG][bB]\b', 'storage_gb', 'Storage (GB)'),
        (r'(\d+(?:\.\d+)?)\s*[kK][mM]\b', 'range_km', 'Range (km)'),
        (r'(\d+(?:\.\d+)?)\s*[kK][pP][hH]\b', 'speed_kph', 'Speed (km/h)'),
        (r'(\d+(?:\.\d+)?)\s*[mM][pP][hH]\b', 'speed_mph', 'Speed (mph)'),
        (r'(\d+(?:\.\d+)?)\s*°?[cC]\b', 'temperature_c', 'Temperature (°C)'),
        (r'(\d+(?:\.\d+)?)\s*[kK][gG]\b', 'weight_kg', 'Weight (kg)'),
        (r'(\d+(?:\.\d+)?)\s*[gG]\b(?!.*\b(?:grams?|weight)\b)', 'weight_g', 'Weight (g)'),
        (r'(\d+)\s*[hH][rR]\b', 'runtime_hr', 'Runtime (hours)'),
        (r'(\d+(?:\.\d+)?)\s*[hH][rR]\b', 'runtime_hr', 'Runtime (hours)'),
        (r'(\d+)\s*[mM][iI][nN]\b', 'charge_time_min', 'Charge time (minutes)'),
        (r'(\d+(?:\.\d+)?)\s*-\s*\d+\s*[hH][rR]\b', 'runtime_range', 'Runtime range'),
        (r'(\d+)\s*[iI][nN](?:ch|ches)?\b', 'screen_inch', 'Screen size (inches)'),
        (r'(\d+(?:\.\d+)?)\s*[iI][nN](?:ch|ches)?\b', 'dimension_inch', 'Dimension (inches)'),
        (r'(\d+(?:\.\d+)?)\s*[cC][mM]\s*[xX×]\s*[\d.]+\s*[cC][mM]', 'dimension_cm', 'Dimensions (cm)'),
    ]

    # ── Material and inclusion patterns ─────────────────────────────────────
    material_words = [
        'stainless steel', 'metal', 'steel', 'aluminum', 'aluminium',
        'plastic', 'abs plastic', 'polypropylene', 'ceramic', 'glass',
        'silicon', 'rubber', 'leather', 'fabric', 'cotton', 'polyester',
        'foam', 'memory foam', 'polyester fiber', 'carbon fiber',
        'copper', 'brass', 'iron', 'cast iron', 'wooden', 'bamboo',
        'ps abs', 'abs', 'ps', 'pu', 'tpu', 'pvc',
    ]
    inclusion_indicators = [
        'includes', 'included', 'comes with', 'contains', 'package includes',
        'what\'s included', 'supplied with', 'set includes',
    ]

    # Process sentences for stable facts
    for sent in sentences:
        sent_lower = sent.lower().strip()
        if not sent_lower or len(sent_lower) < 5:
            continue

        # Skip if mostly marketing
        is_marketing = any(re.search(p, sent_lower) for p in marketing_patterns)
        if is_marketing and not any(char.isdigit() for char in sent):
            marketing.append({
                "claim": sent.strip(),
                "reason": "marketing_language",
            })
            continue

        # Extract numeric specs
        for pattern, spec_type, label in spec_patterns:
            m = re.search(pattern, sent)
            if m:
                value_str = m.group(1)
                try:
                    value = float(value_str)
                    stable.append({
                        "claim": sent.strip(),
                        "value": value,
                        "unit_type": spec_type,
                        "value_str": value_str,
                        "label": label,
                        "reason": "numeric_specification",
                    })
                    break
                except ValueError:
                    pass

        # Check for material claims
        for mat in material_words:
            if mat in sent_lower:
                stable.append({
                    "claim": sent.strip(),
                    "material": mat,
                    "reason": "material_claim",
                })
                break

        # Check for inclusion claims
        for incl in inclusion_indicators:
            if incl in sent_lower:
                stable.append({
                    "claim": sent.strip(),
                    "reason": "inclusion_claim",
                })
                break

        # Check for safety claims
        for pat, label in safety_patterns:
            if re.search(pat, sent_lower):
                safety.append({
                    "claim": sent.strip(),
                    "label": label if label else pat,
                    "reason": "safety_compliance_claim",
                })

        # Check for volatile claims
        for pat, label in volatile_patterns:
            if re.search(pat, sent_lower):
                volatile.append({
                    "claim": sent.strip(),
                    "label": label,
                    "reason": "volatile_commercial",
                })

    return stable, marketing, safety, volatile


def build_claim_record(claim, source_type, source_field, source_evidence,
                       confidence, stability, exposure, compliance_risk, category):
    """Build a standardised ClaimRecord."""
    return {
        "claim": claim,
        "source_type": source_type,
        "source_field": source_field,
        "source_evidence": source_evidence,
        "confidence": confidence,
        "stability": stability,
        "exposure": exposure,
        "compliance_risk": compliance_risk,
        "category": category,
    }


def detect_conflicts(product, description_text):
    """
    Detect contradictions between structured fields and description content.
    Returns a list of ConflictRecord dicts.
    """
    conflicts = []
    title = product.get("title", "")
    desc_lower = description_text.lower()

    # Check for weight conflicts
    variants = product.get("variants", [])
    for v in variants:
        grams = v.get("grams")
        weight_kg = v.get("weight")
        weight_unit = v.get("weight_unit", "kg")

        if grams and weight_kg:
            computed_kg = grams / 1000
            if abs(computed_kg - weight_kg) > 0.1:
                conflicts.append({
                    "conflict_type": "weight_mismatch",
                    "conflicted_facts": [
                        f"variants[].grams = {grams}g",
                        f"variants[].weight = {weight_kg}",
                    ],
                    "source_a": "product_catalog_raw.json variants[].grams",
                    "source_b": "product_catalog_raw.json variants[].weight",
                    "resolution": "use grams as authoritative (more precise)",
                    "writer_action": "Note discrepancy; prefer grams value for weight",
                })

    # Check price in description vs variant
    price_in_desc = re.findall(r'£([\d,.]+)', desc_lower)
    for v in variants:
        variant_price = v.get("price", "")
        if price_in_desc:
            for pd in price_in_desc:
                if pd != variant_price:
                    conflicts.append({
                        "conflict_type": "price_mismatch",
                        "conflicted_facts": [
                            f"Description price: £{pd}",
                            f"Variant price: £{variant_price}",
                        ],
                        "source_a": "product_catalog_raw.json body_html",
                        "source_b": "product_catalog_raw.json variants[].price",
                        "resolution": "use current variant price; description price is stale",
                        "writer_action": "Do not use price from description; fetch current verified price",
                    })

    return conflicts


def assess_profile_quality(description_text, stable_claims, conflict_count, safety_claims):
    """Assess overall profile quality."""
    desc_len = len(description_text.strip())
    has_description = desc_len > 50
    stable_count = len(stable_claims)
    has_safety_flags = len(safety_claims) > 0

    if has_description and stable_count >= 3 and conflict_count == 0:
        return "high"
    elif has_description and stable_count >= 1:
        return "medium"
    else:
        return "low"


def determine_topic_opportunities(product_type, title, vendor):
    """Determine relevant article topics for this product."""
    topics = []
    title_lower = title.lower()
    type_lower = (product_type or "").lower()

    if "hoverboard" in title_lower or "hoverboard" in type_lower:
        topics.append("hoverboard safety and buying guide")
        topics.append("hoverboard not turning on troubleshooting")
    if "scooter" in title_lower or "scooter" in type_lower:
        topics.append("electric scooter buying guide")
    if "hoverkart" in title_lower or "go-kart" in title_lower:
        topics.append("hoverkart guide")
    if "e-bike" in title_lower or "electric bike" in title_lower:
        topics.append("electric bike guide")
    if "wax melt" in title_lower:
        topics.append("wax melts guide")
    if "heater" in title_lower:
        topics.append("space heater safety guide")
    if "diffuser" in title_lower:
        topics.append("oil diffuser guide")
    if "ice bath" in title_lower or "cold plunge" in title_lower:
        topics.append("ice bath guide")
    if "bbq" in title_lower or "grill" in title_lower:
        topics.append("bbq starter guide")
    if "mop" in title_lower:
        topics.append("mop guide")

    if not topics:
        topics.append("product guide")

    return topics


# ─── Per-Product Profile Builder ──────────────────────────────────────────────

def build_profile(product_raw, product_cat, link_map_verified, link_map_fallback):
    """Build a single Product Knowledge Profile."""

    title = product_raw.get("title", "")
    handle = product_raw.get("handle", "")
    vendor = product_raw.get("vendor", "")
    product_type = product_raw.get("product_type", "")
    body_html = product_raw.get("body_html", "") or ""
    description_text = strip_html(body_html)

    # Build public URL
    url = f"https://hcsgadgets.com/products/{handle}"
    if link_map_verified and url in link_map_verified:
        public_url = url
    else:
        public_url = url

    # Variant info
    raw_variants = product_raw.get("variants", [])
    cat_variants = product_cat.get("variants", []) if product_cat else []

    # Extract claims from description
    stable_claims_all, marketing_all, safety_all, volatile_all = extract_claims(
        description_text, title, handle
    )

    # Detect conflicts
    conflicts = detect_conflicts(product_raw, description_text)

    # Build verified features list
    verified_features = []
    verified_specs = []
    verified_dimensions = []
    verified_materials = []
    included_items = []
    claims_needing_review = []

    # Deduplicate stable claims by claim text
    seen_claims = set()
    for c in stable_claims_all:
        claim_text = c["claim"]
        if claim_text in seen_claims:
            continue
        seen_claims.add(claim_text)

        rec = build_claim_record(
            claim=claim_text,
            source_type="description",
            source_field="body_html",
            source_evidence=claim_text[:100],
            confidence=CONFIDENCE_MEDIUM,
            stability=STABILITY_STABLE,
            exposure=EXPOSURE_PUBLIC,
            compliance_risk=COMPLIANCE_LOW,
            category="feature" if not c.get("unit_type") else "specification",
        )

        if c.get("unit_type") in ("dimension_cm", "screen_inch", "dimension_inch"):
            verified_dimensions.append(rec)
        elif c.get("material"):
            verified_materials.append(rec)
        elif c.get("reason") == "inclusion_claim":
            included_items.append(rec)
        elif c.get("unit_type"):
            verified_specs.append(rec)
        else:
            verified_features.append(rec)

    # Safety claims → claims_needing_review
    for c in safety_all:
        claims_needing_review.append(build_claim_record(
            claim=c["claim"],
            source_type="description",
            source_field="body_html",
            source_evidence=c["claim"][:100],
            confidence=CONFIDENCE_LOW,
            stability=STABILITY_STABLE,
            exposure=EXPOSURE_REVIEW,
            compliance_risk=COMPLIANCE_HIGH,
            category="safety_compliance",
        ))

    # Build volatile fields list
    volatile_fields = ["price", "compare_at_price", "inventory_quantity"]
    internal_fields = [
        "admin_graphql_api_id", "id", "product_id", "inventory_item_id",
        "variant_id", "sku", "barcode", "inventory_quantity",
        "old_inventory_quantity", "images_count", "inventory_management",
        "fulfillment_service", "published_at", "published_scope",
        "template_suffix", "status", "tags",
    ]
    prohibited_writer_fields = [
        "sku", "inventory_quantity", "compare_at_price", "images_count",
        "product_id", "variant_id", "inventory_item_id",
        "admin_graphql_api_id", "inventory_policy", "fulfillment_service",
        "barcode", "old_inventory_quantity",
    ]

    # Build variant-derived facts
    support_facts = []
    for i, v in enumerate(raw_variants):
        if v.get("weight"):
            support_facts.append(build_claim_record(
                claim=f"Weight: {v['weight']} {v.get('weight_unit', 'kg')}",
                source_type="variant_field",
                source_field=f"variants[{i}].weight",
                source_evidence=f"{v['weight']} {v.get('weight_unit', 'kg')}",
                confidence=CONFIDENCE_HIGH,
                stability=STABILITY_STABLE,
                exposure=EXPOSURE_PUBLIC,
                compliance_risk=COMPLIANCE_LOW,
                category="specification",
            ))
        if v.get("requires_shipping") is not None:
            support_facts.append(build_claim_record(
                claim=f"Requires shipping: {v['requires_shipping']}",
                source_type="variant_field",
                source_field=f"variants[{i}].requires_shipping",
                source_evidence=str(v["requires_shipping"]),
                confidence=CONFIDENCE_HIGH,
                stability=STABILITY_STABLE,
                exposure=EXPOSURE_PUBLIC,
                compliance_risk=COMPLIANCE_LOW,
                category="specification",
            ))

    # Product purpose (from title and type)
    purpose = None
    title_lower = title.lower()
    if "hoverboard" in title_lower:
        purpose = "Self-balancing personal transport / recreational ride"
    elif "scooter" in title_lower:
        purpose = "Electric or push scooter for personal transport"
    elif "hoverkart" in title_lower or "go-kart" in title_lower:
        purpose = "Hoverboard accessory — converts hoverboard into go-kart"
    elif "e-bike" in title_lower or "electric bike" in title_lower:
        purpose = "Electrically assisted bicycle for urban and trail use"
    elif "wax melt" in title_lower:
        purpose = "Home fragrance — scented wax melt for tart warmers"
    elif "heater" in title_lower:
        purpose = "Indoor space heating for rooms and offices"
    elif "diffuser" in title_lower:
        purpose = "Aromatherapy — disperses essential oils into the air"
    elif "ice bath" in title_lower or "cold plunge" in title_lower:
        purpose = "Cold water immersion for recovery and wellness"
    elif "bbq" in title_lower or "chimney" in title_lower:
        purpose = "Outdoor cooking — charcoal BBQ lighting and cooking equipment"
    elif "mop" in title_lower:
        purpose = "Floor cleaning tool"

    profile = {
        "product_name": title,
        "product_handle": handle,
        "public_product_url": public_url,
        "public_brand_or_vendor": vendor if vendor not in ("HCS GADGETS", "hcsgadgets.com") else None,
        "product_category": product_type or "uncategorised",
        "product_type": product_type,
        "product_purpose": purpose,
        "verified_features": verified_features[:10],  # cap at 10
        "verified_specifications": verified_specs[:10],
        "verified_dimensions": verified_dimensions[:5],
        "verified_materials": verified_materials[:5],
        "included_items": included_items[:5],
        "verified_compatibility": [],
        "verified_use_cases": [],
        "care_guidance": [],
        "setup_guidance": [],
        "support_relevant_facts": support_facts[:5],
        "article_topic_opportunities": determine_topic_opportunities(product_type, title, vendor),
        "source_provenance": {
            "catalog_source": "product_catalog.json",
            "description_source": "product_catalog_raw.json body_html",
            "variant_source": "product_catalog_raw.json variants",
            "url_source": "hcs_verified_link_map.json + derived",
            "profile_generated": datetime.now().isoformat(),
        },
        "claims_needing_review": claims_needing_review[:10],
        "data_conflicts": conflicts[:5],
        "missing_important_fields": [],
        "volatile_fields": volatile_fields,
        "internal_fields": internal_fields,
        "prohibited_writer_fields": prohibited_writer_fields,
        "profile_quality": assess_profile_quality(description_text, verified_features + verified_specs, len(conflicts), safety_all),
        "profile_notes": None,
    }

    return profile


# ─── Main Builder ─────────────────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(description="HCS Product Knowledge Profile Builder v" + VERSION)
    parser.add_argument("--raw-catalog", required=True, help="Path to product_catalog_raw.json")
    parser.add_argument("--catalog", required=True, help="Path to product_catalog.json")
    parser.add_argument("--link-map", required=True, help="Path to hcs_verified_link_map.json")
    parser.add_argument("--output-dir", required=True, help="Output directory for generated files")
    args = parser.parse_args()

    # Load data
    with open(args.raw_catalog, "r", encoding="utf-8") as f:
        raw_data = json.load(f)
    with open(args.catalog, "r", encoding="utf-8") as f:
        cat_data = json.load(f)
    with open(args.link_map, "r", encoding="utf-8") as f:
        link_map = json.load(f)

    raw_products = {p["handle"]: p for p in raw_data.get("products", [])}
    cat_products = {p["handle"]: p for p in cat_data.get("products", [])}
    verified_urls = set()
    for p in link_map.get("verified_products", []):
        if p.get("url"):
            verified_urls.add(p["url"])

    fallback = link_map.get("fallback_url", "https://hcsgadgets.com/collections/all-product")

    print(f"HCS Product Knowledge Builder v{VERSION}")
    print(f"Products to process: {len(cat_products)}")

    profiles = []
    for handle, cat_p in cat_products.items():
        raw_p = raw_products.get(handle, {})
        profile = build_profile(raw_p, cat_p, verified_urls, fallback)
        profiles.append(profile)

    print(f"Generated {len(profiles)} profiles")

    # ── Write profiles JSON ───────────────────────────────────────────────────
    profiles_path = f"{args.output_dir.rstrip('/')}/product_knowledge_profiles.json"
    with open(profiles_path, "w", encoding="utf-8") as f:
        json.dump({
            "version": VERSION,
            "generated": datetime.now().isoformat(),
            "total": len(profiles),
            "profiles": profiles,
        }, f, indent=2, ensure_ascii=False)
    print(f"Written: {profiles_path}")

    # ── Write profiles MD ──────────────────────────────────────────────────────
    md_lines = [
        "# HCS Gadgets — Product Knowledge Profiles",
        "",
        f"**Generated:** {datetime.now().strftime('%Y-%m-%d')}  ",
        f"**Total products:** {len(profiles)}  ",
        "",
    ]
    for p in profiles:
        md_lines += [
            f"## {p['product_name']}",
            "",
            f"**Handle:** `{p['product_handle']}`  ",
            f"**Category:** {p['product_category']}  ",
            f"**Purpose:** {p.get('product_purpose') or 'unknown'}  ",
            f"**URL:** {p['public_product_url']}  ",
            f"**Quality:** {p['profile_quality']}  ",
            "",
            "### Verified Features",
        ]
        if p["verified_features"]:
            for f in p["verified_features"]:
                md_lines.append(f"- {f['claim']}")
        else:
            md_lines.append("_None confirmed — see claims needing review._")

        if p["verified_specifications"]:
            md_lines += ["", "### Verified Specifications"]
            for s in p["verified_specifications"]:
                md_lines.append(f"- {s['claim']}")

        if p["claims_needing_review"]:
            md_lines += ["", "### Claims Needing Review"]
            for c in p["claims_needing_review"]:
                md_lines.append(f"- ⚠️ {c['claim']} _(compliance risk: {c['compliance_risk']})_")

        if p["data_conflicts"]:
            md_lines += ["", "### Data Conflicts"]
            for c in p["data_conflicts"]:
                md_lines.append(f"- ⚠️ [{c['conflict_type']}] {', '.join(c['conflicted_facts'])}")

        md_lines += ["", "---\n"]

    md_path = f"{args.output_dir.rstrip('/')}/product_knowledge_profiles.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))
    print(f"Written: {md_path}")

    # ── Build Public Content View ─────────────────────────────────────────────
    print("Building writer-safe Public Content View...")

    public_view = []
    for p in profiles:
        # Build public product entry — only safe fields
        entry = {
            "product_name": p["product_name"],
            "product_handle": p["product_handle"],
            "public_product_url": p["public_product_url"],
            "public_brand_or_vendor": p.get("public_brand_or_vendor"),
            "product_category": p["product_category"],
            "product_type": p.get("product_type"),
            "product_purpose": p.get("product_purpose"),
            "verified_features": [c["claim"] for c in p["verified_features"]],
            "verified_specifications": [c["claim"] for c in p["verified_specifications"]],
            "verified_dimensions": [c["claim"] for c in p["verified_dimensions"]],
            "verified_materials": [c["claim"] for c in p["verified_materials"]],
            "included_items": [c["claim"] for c in p["included_items"]],
            "verified_compatibility": [c["claim"] for c in p["verified_compatibility"]],
            "verified_use_cases": p.get("verified_use_cases", []),
            "care_guidance": [c["claim"] for c in p.get("care_guidance", [])],
            "setup_guidance": [c["claim"] for c in p.get("setup_guidance", [])],
            "support_relevant_facts": [c["claim"] for c in p.get("support_relevant_facts", [])],
            "article_topic_opportunities": p.get("article_topic_opportunities", []),
            "profile_quality": p["profile_quality"],
        }
        public_view.append(entry)

    # Write public content view JSON
    pcv_json_path = f"{args.output_dir.rstrip('/')}/product_content_view.json"
    with open(pcv_json_path, "w", encoding="utf-8") as f:
        json.dump({
            "version": VERSION,
            "generated": datetime.now().isoformat(),
            "total": len(public_view),
            "description": "WRITER-SAFE PUBLIC CONTENT VIEW — Do not use product_catalog.json directly",
            "usage": "Use this file for article writing. Do not use price, stock, SKU, or inventory data.",
            "products": public_view,
        }, f, indent=2, ensure_ascii=False)
    print(f"Written: {pcv_json_path}")

    # Write public content view MD
    pcv_md_lines = [
        "# HCS Gadgets — Writer-Safe Public Content View",
        "",
        f"**Generated:** {datetime.now().strftime('%Y-%m-%d')}  ",
        f"**Total products:** {len(public_view)}  ",
        "",
        "## Usage Instructions",
        "",
        "**This is the only product data file HCS writers should use for article writing.**",
        "",
        "Do NOT use `product_catalog.json` directly for article content.",
        "",
        "Do NOT include in articles:",
        "- Price, compare_at_price, or any commercial pricing",
        "- Stock quantity, inventory, or availability",
        "- SKU, product ID, variant ID",
        "- Image counts",
        "",
        "---\n",
    ]

    for entry in public_view:
        pcv_md_lines += [
            f"## {entry['product_name']}",
            "",
            f"**Category:** {entry['product_category']}  ",
            f"**Purpose:** {entry.get('product_purpose') or 'unknown'}  ",
            f"**URL:** {entry['public_product_url']}  ",
            f"**Quality:** {entry['profile_quality']}  ",
            "",
        ]
        if entry["verified_features"]:
            pcv_md_lines += ["**Verified Features:**", ""]
            for f in entry["verified_features"]:
                pcv_md_lines.append(f"- {f}")
            pcv_md_lines.append("")

        if entry["verified_specifications"]:
            pcv_md_lines += ["**Verified Specifications:**", ""]
            for s in entry["verified_specifications"]:
                pcv_md_lines.append(f"- {s}")
            pcv_md_lines.append("")

        if entry["verified_dimensions"]:
            pcv_md_lines += ["**Dimensions:**", ""]
            for d in entry["verified_dimensions"]:
                pcv_md_lines.append(f"- {d}")
            pcv_md_lines.append("")

        if entry["verified_materials"]:
            pcv_md_lines += ["**Materials:**", ""]
            for m in entry["verified_materials"]:
                pcv_md_lines.append(f"- {m}")
            pcv_md_lines.append("")

        if entry["included_items"]:
            pcv_md_lines += ["**Included Items:**", ""]
            for i in entry["included_items"]:
                pcv_md_lines.append(f"- {i}")
            pcv_md_lines.append("")

        if entry["article_topic_opportunities"]:
            pcv_md_lines.append(f"**Article topics:** {', '.join(entry['article_topic_opportunities'])}")
            pcv_md_lines.append("")

        pcv_md_lines += ["---\n"]

    pcv_md_path = f"{args.output_dir.rstrip('/')}/product_content_view.md"
    with open(pcv_md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(pcv_md_lines))
    print(f"Written: {pcv_md_path}")

    print("\nDone.")


if __name__ == "__main__":
    main()
