#!/usr/bin/env python3
"""
HCS Gadgets — HTML Article Design Contract Validator v2.0

Validates an HTML article file against the HCS HTML Design Contract v2.
Supports both structural validation and product truth validation.

Usage:
    python3 hcs_html_contract_validator.py --file <path>
    python3 hcs_html_contract_validator.py --file <path> --strict
    python3 hcs_html_contract_validator.py --file <path> --json

Product Truth Mode:
    python3 hcs_html_contract_validator.py --file <path> \
        --product-catalog <product_catalog.json> \
        --collections <collections_inventory.json> \
        --link-map <hcs_verified_link_map.json>

Version 2.0 changes:
    - hcs-table-scroll is now mandatory around every hcs-table
    - Rejects full HTML document wrappers (DOCTYPE, html, head, body)
    - CTA URL must be verified when link map is supplied
    - FAQ must use static div.hcs-faq-item (no details/summary)
    - Schema content consistency checks (headline ↔ H1, FAQ questions ↔ schema)
    - Product truth validation mode with link map
    - Avoids false closing-article detection from comments
"""
import argparse
import json
import re
import sys
from datetime import datetime

VERSION = "2.0"
CONTRACT_VERSION = "hcs_html_design_contract_v2.md"

# ANSI colours
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
RESET = "\033[0m"
BOLD = "\033[1m"

def log(msg, level="INFO"):
    prefix = {
        "INFO": "[INFO]",
        "WARN": f"{YELLOW}[WARN]{RESET}",
        "FAIL": f"{RED}[FAIL]{RESET}",
        "PASS": f"{GREEN}[PASS]{RESET}"
    }
    print(f"{prefix.get(level, '[INFO]')} {msg}")


# ─── Product-Data Policy ─────────────────────────────────────────────────────

RESTRICTED_PRODUCT_FIELDS = {
    # Commerce fields — NEVER in article copy
    # Matches: "price: £22.99", "price is £22.99", "price was £22.99", "costs £22.99", "costs just £22"
    # Single currency amounts (must catch £X.XX appearing alone in JSON-LD, FAQ answers, etc.)
    "price":            [
        r'\bprice\b\s*(?::?\s*|is\s+|was\s+)*[£$€]',   # price: £22.99 / price is £22.99
        r'\bcosts\s+[£$€]',                                   # costs £22.99
        r'[£$€]\s*\d+(?:\.\d{2})?',                        # £19.99 or £19 in any context
    ],
    "display_price":    [r'\bdisplay_price\b'],
    "price_min":        [r'\bprice_min\b'],
    "price_max":        [r'\bprice_max\b'],
    "price_range":      [r'\bprice_range\b',
                         r'[£$€]\s*\d+\s*(?:to|\-|–)\s*[£$€]\s*\d+'],  # £8 to £23
    "compare_at_price": [r'\bcompare_at_price\b',
                         r'was\s+[£$€]\s*\d+'],
    "inventory_quantity": [r'\binventory_quantity\b',
                           r'\d+\s+in\s+stock\b',
                           r'\bonly\s+\d+\s+left\b'],
    "stock_status":     [r'\bin\s+stock\b', r'\blown\s+stock\b',
                         r'\blow\s+stock\b', r'\bout\s+of\s+stock\b'],
    "sku":              [r'\bsku\s*[:\-]?\s*\w+',
                         r'\bSKU\s*[:\-]?\s*\w+'],
    "barcode":          [r'\bbarcode\s*[:\-]?\s*\d+',
                         r'\bEAN\s*[:\-]?\s*\d+',
                         r'\bGTIN\s*[:\-]?\s*\d+',
                         r'\bUPC\s*[:\-]?\s*\d+'],
    "variant_id":       [r'\bvariant_id\s*[:\-]?\s*\d+',
                         r'\bvariantId\s*[:\-]?\s*\d+',
                         r'\bvariant_id\s*[:\-]?\s*[A-Za-z0-9]+',   # alphanumeric IDs
                         r'\bvariantId\s*[:\-]?\s*[A-Za-z0-9]+'],
    "product_id":       [r'\bproduct_id\s*[:\-]?\s*\d+',
                         r'\bproductId\s*[:\-]?\s*\d+',
                         r'\bproduct_id\s*[:\-]?\s*[A-Za-z0-9]+',   # alphanumeric IDs
                         r'\bproductId\s*[:\-]?\s*[A-Za-z0-9]+'],
    # Internal / supplier identifiers
    "internal_vendor":  [r'\bSUPPLIER[_\-]\d+\b',
                         r'\bVENDOR[_\-]\d+\b'],
    "hoverboard_store_as_supplier": [r'Hoverboard\s+Store\s+as\s+supplier'],
    "catalogue_tag":    [r'\bwholesale\b', r'\bbulk_order\b'],
}


# ─── Restricted-Commerce JSON-LD Field Paths ────────────────────────────────
# These JSON-LD / structured-data field paths indicate commerce data
# that must NEVER appear in HCS article copy, even inside schema blocks.
JSON_LD_COMMERCE_FIELDS = {
    "price", "priceSpecification", "lowPrice", "highPrice",
    "sku", "gtin", "gtin8", "gtin14", "ean", "upc",
    # product ID variants (camelCase and snake_case)
    "productID", "productId", "product_id",
    # variant ID variants
    "variantID", "variantId", "variant_id",
    # inventory variants
    "inventory", "inventoryLevel", "inventoryCount", "inventory_level",
    "brand"  # brand can appear in copy but not as structured @type Brand
}
# Field paths nested under priceSpecification that count as restricted
PRICE_SPEC_FIELDS = {"price", "minPrice", "maxPrice", "value"}
# Structured-data @type values that represent commerce objects
COMMERCE_SCHEMA_TYPES = {
    "Product", "Offer", "AggregateOffer", "IndividualProduct",
    "SomeProduct", "SoftwareApplication"
}

# ─── Helpers ─────────────────────────────────────────────────────────────────

def _violation(field: str, snippet: str, source: str = "article HTML") -> str:
    """Format a violation message with context."""
    clean = snippet.replace("\n", " ").strip()
    return (f"[product-data-policy] RESTRICTED field '{field}' "
            f"in {source}: ...{clean}...")

def _scan_text_for_restricted(text: str, source: str = "HTML") -> list[str]:
    """
    Scan raw text for restricted product-data patterns.
    Returns (field, snippet) pairs.
    """
    violations = []
    for field, patterns in RESTRICTED_PRODUCT_FIELDS.items():
        for pat in patterns:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                start = max(0, m.start() - 40)
                end = min(len(text), m.end() + 40)
                snippet = text[start:end]
                violations.append(_violation(field, snippet, source))
                break
    return violations

def _extract_json_ld_blocks(html: str) -> list[tuple[str, str]]:
    """
    Extract all JSON-LD script blocks.
    Returns list of (raw_json_string, schema_type_if_detected).
    """
    blocks = []
    pattern = r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>'
    for m in re.finditer(pattern, html, re.DOTALL | re.IGNORECASE):
        raw = m.group(1).strip()
        blocks.append((raw, ""))
    return blocks

def _check_json_ld_commerce_fields(raw_json: str) -> list[str]:
    """
    Parse a JSON-LD block and check its structured fields against
    restricted commerce fields. Detects Product/Offer schema commerce data.
    """
    violations = []
    try:
        obj = json.loads(raw_json)
    except (json.JSONDecodeError, ValueError):
        # Not valid JSON — fall back to regex scan
        return _scan_text_for_restricted(raw_json, "JSON-LD")

    def walk(node, path=""):
        if not isinstance(node, (dict, list)):
            return
        if isinstance(node, dict):
            # Detect commerce schema @type
            type_val = node.get("@type", "")
            if isinstance(type_val, str) and type_val in COMMERCE_SCHEMA_TYPES:
                violations.append(
                    f"[product-data-policy] RESTRICTED @type '{type_val}' "
                    f"in JSON-LD (Product/Offer schema)"
                )
            # Check field names against restricted set
            for key in node:
                full_path = f"{path}.{key}" if path else key
                if key in JSON_LD_COMMERCE_FIELDS:
                    val = node[key]
                    if isinstance(val, (str, int, float)):
                        violations.append(
                            f"[product-data-policy] RESTRICTED commerce field "
                            f"'{full_path}' = {repr(val)} in JSON-LD"
                        )
                    elif isinstance(val, dict):
                        for sub in PRICE_SPEC_FIELDS:
                            if sub in val and isinstance(val[sub], (str, int, float)):
                                violations.append(
                                    f"[product-data-policy] RESTRICTED field "
                                    f"'{full_path}.{sub}' = {repr(val[sub])} in JSON-LD"
                                )
            # Recurse
            for key, val in node.items():
                if isinstance(val, (dict, list)):
                    walk(val, f"{path}.{key}" if path else key)
        elif isinstance(node, list):
            for i, item in enumerate(node):
                walk(item, f"{path}[{i}]")

    walk(obj)
    return violations

def check_article_product_data_policy(html: str) -> list[str]:
    """
    Scan article HTML for restricted product-data field values.

    Scans THREE layers:
      1. Visible article copy (strip class attrs only, keep text)
      2. JSON-LD schema blocks (parsed + field-path checked)
      3. HTML comments and data-* attribute values

    Returns a list of violation messages (empty = clean).
    False positives from CSS class names are avoided by stripping
    class= attributes before scanning visible HTML.
    """
    violations = []

    # ── Layer 1: Visible HTML text ─────────────────────────────────────
    # Strip class= attrs (CSS class names are not article content)
    visible = re.sub(r'\bclass="[^"]*"', '', html)
    # Strip DOCTYPE/html/head/body wrappers (boilerplate, not article)
    visible = re.sub(r'<(?:!DOCTYPE|html|head|body)[^>]*>', '', visible, flags=re.IGNORECASE)
    # Strip tags, keep text
    text_only = re.sub(r'<[^>]+>', ' ', visible)
    violations.extend(_scan_text_for_restricted(text_only, "article copy"))

    # ── Layer 2: JSON-LD schema blocks ──────────────────────────────────
    for raw_json, _ in _extract_json_ld_blocks(html):
        violations.extend(_check_json_ld_commerce_fields(raw_json))
        # Also regex-scan the raw JSON in case structured parsing missed anything
        violations.extend(_scan_text_for_restricted(raw_json, "JSON-LD raw"))

    # ── Layer 3: HTML comments ──────────────────────────────────────────
    for m in re.finditer(r'<!--(.*?)-->', html, re.DOTALL):
        comment_text = m.group(1)
        violations.extend(_scan_text_for_restricted(comment_text, "HTML comment"))

    # ── Layer 4: data-* attribute names and values ─────────────────────────
    # Restricted field names appearing in data-* attribute names are blocked.
    # Attribute names are normalised (hyphens→underscores, camelCase→underscore)
    # before matching against RESTRICTED_PRODUCT_FIELDS field names.
    import re as _re
    def _norm(s):
        s = s.lower()
        s = s.replace("-", "_")
        # strip leading/trailing underscores
        s = _re.sub(r"_+", "_", s)
        s = s.strip("_")
        return s

    RESTRICTED_FIELD_NAMES = set(RESTRICTED_PRODUCT_FIELDS.keys())

    for m in _re.finditer(r'\b(data-[\w-]+)="([^"]*)"', html):
        attr_name = m.group(1)       # e.g. "data-variant-id"
        val = m.group(2)
        normalised = _norm(attr_name)
        # Extract the field portion after "data_" prefix: "data_variant_id" → "variant_id"
        if normalised.startswith("data_"):
            field_candidate = normalised[5:]  # strip "data_"
        else:
            field_candidate = normalised
        if field_candidate in RESTRICTED_FIELD_NAMES:
            violations.append(
                f"[product-data-policy] RESTRICTED field '{field_candidate}' "
                f"in data-* attribute name '{attr_name}'"
            )
        # Also scan attribute values for restricted patterns
        violations.extend(_scan_text_for_restricted(val, "data-* attribute value"))

    return violations


# ─── HTML Extraction Helpers ───────────────────────────────────────────────

def get_section_content(html, cls):
    """Extract inner content of a section or div with the given class."""
    for tag in ['section', 'div']:
        pattern = r'<' + tag + r'[^>]*\bclass=["\']' + re.escape(cls) + r'["\'][^>]*>(.*?)</' + tag + '>'
        m = re.search(pattern, html, re.DOTALL | re.IGNORECASE)
        if m:
            return m.group(1)
    return ""


def find_elements(html, tag, cls=None, wrapper_cls=None):
    """Find all elements matching tag[.cls] inside wrapper_cls."""
    if wrapper_cls:
        content = get_section_content(html, wrapper_cls)
    else:
        content = html

    if cls:
        pattern = r'<' + tag + r'[^>]*\bclass=["\'][^"\']*' + re.escape(cls) + r'[^"\']*["\'][^>]*>(.*?)</' + tag + '>'
    else:
        pattern = r'<' + tag + r'[^>]*>(.*?)</' + tag + '>'

    results = []
    for m in re.finditer(pattern, content, re.DOTALL | re.IGNORECASE):
        results.append((m.group(0), m.group(1)))
    return results


def extract_h2_ids_in_article(html):
    """Extract ALL h2 id attributes from the article wrapper (avoids comment false matches)."""
    article_match = re.search(
        r'<article[^>]*class=["\']hcs-article["\'][^>]*>(.*?)</article>',
        html,
        re.DOTALL | re.IGNORECASE
    )
    if not article_match:
        return []
    article_content = article_match.group(1)
    pattern = r'<h2\b[^>]*\bid=["\']([^"\']+)["\'][^>]*>'
    return re.findall(pattern, article_content, re.IGNORECASE)


def extract_h2_ids_inside_content(html):
    """Extract all h2 id attributes from inside section.hcs-content."""
    content = get_section_content(html, "hcs-content")
    if not content:
        return []
    pattern = r'<h2\b[^>]*\bid=["\']([^"\']+)["\'][^>]*>'
    return re.findall(pattern, content, re.IGNORECASE)


def get_json_ld_blocks(html):
    """Extract all JSON-LD script blocks from inside the article."""
    article_match = re.search(
        r'<article[^>]*class=["\']hcs-article["\'][^>]*>(.*?)</article>',
        html,
        re.DOTALL | re.IGNORECASE
    )
    if not article_match:
        return []
    article_content = article_match.group(1)
    pattern = r'<script[^>]*\btype=["\']application/ld\+json["\'][^>]*>(.*?)</script>'
    return re.findall(pattern, article_content, re.DOTALL | re.IGNORECASE)


def count_elements(html, tag, cls):
    return len(find_elements(html, tag, cls))


def json_has_field_strict(block, dotpath):
    """Strict check using string search for nested JSON-LD fields."""
    if "." not in dotpath:
        return ('"' + dotpath + '"') in block
    parts = dotpath.split(".")
    nested_pat = r'"' + parts[0] + r'"\s*:\s*\{[^}]*?"' + parts[1] + r'"\s*:'
    return bool(re.search(nested_pat, block, re.IGNORECASE))


def load_link_map(path):
    """Load verified link map JSON."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        verified = set()
        for p in data.get("verified_products", []):
            if p.get("url"):
                verified.add(p["url"])
        for c in data.get("verified_collections", []):
            if c.get("url"):
                verified.add(c["url"])
        for b in data.get("verified_blog_articles", []):
            if b.get("url"):
                verified.add(b["url"])
        return verified, data.get("fallback_url", "https://hcsgadgets.com/collections/all-product")
    except Exception as e:
        return None, None


def load_product_catalog(path):
    """Load product catalog JSON."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        products = {}
        for p in data.get("products", []):
            products[p.get("handle", "")] = p
            products[p.get("title", "")] = p
        return products
    except Exception:
        return {}


def load_collections(path):
    """Load collections inventory JSON."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        collections = {}
        for c in data.get("collections", []):
            collections[c.get("handle", "")] = c
        return collections
    except Exception:
        return {}


# ─── Core Validation ─────────────────────────────────────────────────────────

def run_checks(html, link_map_verified=None, link_map_fallback=None,
               product_catalog=None, collections_inv=None):
    """
    Run all v2 contract checks.
    Returns (failures, warnings, check_results).
    """
    failures = []
    warnings = []

    def check(name, passed, detail, expected="—"):
        result = bool(passed)
        if not result:
            failures.append(f"[{name}] {detail}")
        return (name, result, detail, expected)

    # Pre-compute
    has_inline_styles = bool(re.search(r'\sstyle=["\']', html))
    has_style_tags = bool(re.search(r'<style\b', html, re.IGNORECASE))

    article_match = re.search(
        r'<article[^>]*class=["\'][^"\']*hcs-article[^"\']*["\'][^>]*>(.*?)</article>',
        html,
        re.DOTALL | re.IGNORECASE
    )
    article_count = len(re.findall(
        r'<article[^>]*class=["\'][^"\']*hcs-article[^"\']*["\'][^>]*>',
        html,
        re.IGNORECASE
    ))

    all_h2_ids_in_content = extract_h2_ids_inside_content(html)
    all_h2_ids_in_article = extract_h2_ids_in_article(html)
    ld_blocks = get_json_ld_blocks(html)
    blog_blocks = [b for b in ld_blocks if '"BlogPosting"' in b]
    faq_blocks = [b for b in ld_blocks if '"FAQPage"' in b]

    has_faq_items = count_elements(html, "div", "hcs-faq-item") >= 1
    has_faq_section = count_elements(html, "section", "hcs-faq") >= 1

    checks = []

    # ── v2.1: Exactly one article.hcs-article wrapper ─────────────────────
    checks.append(check(
        "article.hcs-article wrapper (exactly one)",
        article_count == 1,
        f"Found {article_count} (expected 1)",
        "1"
    ))

    # ── v2.2: Document wrappers must NOT be present ────────────────────────
    has_doctype = bool(re.search(r'<!DOCTYPE', html, re.IGNORECASE))
    has_html_tag = bool(re.search(r'<html\b', html, re.IGNORECASE))
    has_head_tag = bool(re.search(r'<head\b', html, re.IGNORECASE))
    has_body_tag = bool(re.search(r'<body\b', html, re.IGNORECASE))
    doc_wrappers = []
    if has_doctype: doc_wrappers.append("DOCTYPE")
    if has_html_tag: doc_wrappers.append("html")
    if has_head_tag: doc_wrappers.append("head")
    if has_body_tag: doc_wrappers.append("body")
    checks.append(check(
        "No HTML document wrappers",
        len(doc_wrappers) == 0,
        f"Found: {', '.join(doc_wrappers)}" if doc_wrappers else "clean",
        "none"
    ))
    if doc_wrappers:
        failures.append(f"[document wrappers] Found <{doc_wrappers[0]}> — Shopify article must not contain document wrappers")

    # ── v2.3: No <style> tags ──────────────────────────────────────────────
    checks.append(check(
        "No <style> tags",
        not has_style_tags,
        "found" if has_style_tags else "clean",
        "0"
    ))
    if has_style_tags:
        failures.append("[style tags] Found <style> tag — all styling must be via CSS classes")

    # ── v2.4: No inline styles ─────────────────────────────────────────────
    inline_style_count = len(re.findall(r'\sstyle=[\'"]', html))
    checks.append(check(
        "No inline style attributes",
        not has_inline_styles,
        f"{inline_style_count} found",
        "0"
    ))
    if has_inline_styles:
        failures.append("[inline styles] Found inline style attribute(s) — forbidden by contract R1")

    # ── v2.5: section.hcs-hero ────────────────────────────────────────────
    checks.append(check(
        "section.hcs-hero exists",
        count_elements(html, "section", "hcs-hero") >= 1,
        f"Found {count_elements(html, 'section', 'hcs-hero')}",
        "≥1"
    ))

    # ── v2.6: h1 inside hero ──────────────────────────────────────────────
    hero_content = get_section_content(html, "hcs-hero")
    checks.append(check(
        "h1 inside hcs-hero",
        bool(re.search(r'<h1\b', hero_content, re.IGNORECASE)),
        "Found" if hero_content else "Missing",
        "≥1"
    ))

    # ── v2.7: p.hcs-eyebrow in hero ───────────────────────────────────────
    checks.append(check(
        "p.hcs-eyebrow inside hcs-hero",
        bool(re.search(r'<p[^>]*class=["\'][^"\']*hcs-eyebrow["\'][^>]*>', hero_content, re.IGNORECASE)),
        "Found",
        "≥1"
    ))

    # ── v2.8: p.hcs-intro in hero ─────────────────────────────────────────
    checks.append(check(
        "p.hcs-intro inside hcs-hero",
        bool(re.search(r'<p[^>]*class=["\'][^"\']*hcs-intro["\'][^>]*>', hero_content, re.IGNORECASE)),
        "Found",
        "≥1"
    ))

    # ── v2.9: div.hcs-top-grid ────────────────────────────────────────────
    checks.append(check(
        "div.hcs-top-grid exists",
        count_elements(html, "div", "hcs-top-grid") >= 1,
        f"Found {count_elements(html, 'div', 'hcs-top-grid')}",
        "≥1"
    ))

    # ── v2.10: section.hcs-quick-answer inside top-grid ──────────────────
    tg_content = get_section_content(html, "hcs-top-grid")
    qa_in_tg = bool(re.search(r'<section[^>]*class=["\'][^"\']*hcs-quick-answer["\'][^>]*>', tg_content, re.IGNORECASE))
    checks.append(check(
        "section.hcs-quick-answer inside hcs-top-grid",
        qa_in_tg,
        "Found" if qa_in_tg else "Missing",
        "≥1"
    ))

    # ── v2.11: section.hcs-toc inside top-grid ────────────────────────────
    toc_in_tg = bool(re.search(r'<section[^>]*class=["\'][^"\']*hcs-toc["\'][^>]*>', tg_content, re.IGNORECASE))
    checks.append(check(
        "section.hcs-toc inside hcs-top-grid",
        toc_in_tg,
        "Found" if toc_in_tg else "Missing",
        "≥1"
    ))

    # ── v2.12: section.hcs-content ─────────────────────────────────────────
    checks.append(check(
        "section.hcs-content exists",
        count_elements(html, "section", "hcs-content") >= 1,
        f"Found {count_elements(html, 'section', 'hcs-content')}",
        "≥1"
    ))

    # ── v2.13: h2 inside hcs-content have id attributes ──────────────────
    h2_tags_in_content = re.findall(
        r'<h2\b([^>]*)>',
        get_section_content(html, "hcs-content"),
        re.IGNORECASE
    )
    missing_ids = [tag.strip() for tag in h2_tags_in_content if 'id=' not in tag]
    checks.append(check(
        "All h2 inside hcs-content have id",
        len(missing_ids) == 0,
        f"{len(missing_ids)} missing ids",
        "0"
    ))
    if missing_ids:
        failures.append(f"[h2 id] h2 elements missing id attribute: {missing_ids[:3]}")

    # ── v2.14: h2 id uniqueness ────────────────────────────────────────────
    dup_ids = [i for i in all_h2_ids_in_article if all_h2_ids_in_article.count(i) > 1]
    checks.append(check(
        "All h2 id attributes are unique",
        len(dup_ids) == 0,
        f"{len(dup_ids)} duplicates: {set(dup_ids)}" if dup_ids else "all unique",
        "0"
    ))
    if dup_ids:
        failures.append(f"[h2 id] Duplicate h2 id attributes: {set(dup_ids)}")

    # ── v2.15: TOC links resolve to h2#id targets ─────────────────────────
    toc_content = get_section_content(html, "hcs-toc")
    toc_links = re.findall(r'<a[^>]*href=["\']#([^"\']+)["\'][^>]*>', toc_content, re.IGNORECASE)
    broken_links = [l for l in toc_links if l not in all_h2_ids_in_article]
    checks.append(check(
        "All TOC href anchors resolve to h2#id",
        len(broken_links) == 0,
        f"{len(broken_links)} broken: {broken_links}" if broken_links else "all valid",
        "0"
    ))
    if broken_links:
        failures.append(f"[TOC] TOC links with no matching h2 id: {broken_links}")

    # ── v2.16: IDs are lowercase hyphen-separated ─────────────────────────
    non_conforming = [i for i in all_h2_ids_in_article
                      if not re.match(r'^[a-z0-9]+(-[a-z0-9]+)*$', i)]
    checks.append(check(
        "IDs are lowercase hyphen-separated",
        len(non_conforming) == 0,
        f"{len(non_conforming)} non-conforming: {non_conforming[:3]}" if non_conforming else "ok",
        "0"
    ))
    if non_conforming:
        warnings.append(f"Non-conforming IDs (use lowercase-hyphen): {non_conforming[:3]}")

    # ── v2.17: hcs-split structure ─────────────────────────────────────────
    split_count = count_elements(html, "div", "hcs-split")
    if split_count > 0:
        do_count = count_elements(html, "div", "hcs-do")
        dont_count = count_elements(html, "div", "hcs-dont")
        checks.append(check(
            "hcs-split contains hcs-do and hcs-dont",
            do_count >= 1 and dont_count >= 1,
            f"do={do_count} dont={dont_count}",
            "≥1 each"
        ))
        if do_count == 0:
            failures.append("[hcs-split] No <div class='hcs-do'> found")
        if dont_count == 0:
            failures.append("[hcs-split] No <div class='hcs-dont'> found")
        # hcs-do must have id="good-bad"
        do_content = get_section_content(html, "hcs-do")
        has_good_bad_id = bool(re.search(r'<h2[^>]*\bid=["\']good-bad["\']', do_content, re.IGNORECASE))
        checks.append(check(
            "hcs-do h2 has id='good-bad'",
            has_good_bad_id,
            "present" if has_good_bad_id else "missing",
            "required"
        ))
        if not has_good_bad_id:
            failures.append("[hcs-do h2] Missing id='good-bad' on hcs-do h2 element")

    # ── v2.18: No custom icon markup in hcs-do/hcs-dont ───────────────────
    icon_issues = []
    icon_patterns = [
        r'&#x271[3-8]',  # ✓ ✗ ✔ ✘ ◆
        r'<img[^>]*\balt=["\'][^"\']*(?:tick|cross|check)',
        r'<svg[^>]*\b(?:class|id)=["\'][^"\']*(?:tick|cross|check|icon)',
    ]
    for pat in icon_patterns:
        if re.search(pat, html, re.IGNORECASE):
            icon_issues.append(pat[:30])
    checks.append(check(
        "No custom icon markup in hcs-do/hcs-dont",
        len(icon_issues) == 0,
        f"{len(icon_issues)} issues" if icon_issues else "clean",
        "0"
    ))
    if icon_issues:
        warnings.append(f"Possible custom icon markup: {icon_issues[:3]}")

    # ── v2.19: Mandatory hcs-table-scroll around every hcs-table ───────────
    all_tables = re.findall(r'<table\b[^>]*class=["\'][^"\']*hcs-table["\'][^>]*>', html, re.IGNORECASE)
    wrapped_tables = re.findall(
        r'<div[^>]*class=["\'][^"\']*hcs-table-scroll["\'][^>]*>.*?<table\b[^>]*class=["\'][^"\']*hcs-table["\'][^>]*>',
        html,
        re.DOTALL | re.IGNORECASE
    )
    checks.append(check(
        "Every hcs-table wrapped in hcs-table-scroll",
        len(wrapped_tables) >= len(all_tables),
        f"{len(wrapped_tables)}/{len(all_tables)} tables wrapped",
        "all"
    ))
    if len(wrapped_tables) < len(all_tables):
        failures.append(
            f"[hcs-table-scroll] {len(all_tables) - len(wrapped_tables)} bare hcs-table found without hcs-table-scroll wrapper — this is mandatory in v2"
        )

    # ── v2.20: Tables use hcs-table class ──────────────────────────────────
    table_with_class = len(re.findall(
        r'<table[^>]*class=["\'][^"\']*hcs-table["\'][^>]*>',
        html,
        re.IGNORECASE
    ))
    table_count = len(re.findall(r'<table\b', html, re.IGNORECASE))
    checks.append(check(
        "All tables use class='hcs-table'",
        table_with_class >= table_count,
        f"{table_with_class}/{table_count}",
        "all"
    ))
    if table_with_class < table_count:
        failures.append(f"[hcs-table class] Only {table_with_class}/{table_count} tables have class='hcs-table'")

    # ── v2.21: hcs-table--highlight advisory check ─────────────────────────
    highlight_count = len(re.findall(r'class=["\'][^"\']*hcs-table--highlight["\']', html, re.IGNORECASE))
    checks.append(check(
        "hcs-table--highlight used for cell emphasis (advisory)",
        True,
        f"{highlight_count} highlighted cells",
        "advisory"
    ))

    # ── v2.22: hcs-checklist structure ────────────────────────────────────
    checklist_count = count_elements(html, "section", "hcs-checklist")
    if checklist_count > 0:
        cl_content = get_section_content(html, "hcs-checklist")
        has_ul = bool(re.search(r'<ul\b', cl_content, re.IGNORECASE))
        checks.append(check(
            "hcs-checklist contains <ul>",
            has_ul,
            "present" if has_ul else "missing",
            "required"
        ))
        if not has_ul:
            failures.append("[hcs-checklist] Checklist section missing <ul>")

    # ── v2.23: FAQ — no <details> or <summary> ─────────────────────────────
    details_count = len(re.findall(r'<details\b', html, re.IGNORECASE))
    summary_count = len(re.findall(r'<summary\b', html, re.IGNORECASE))
    checks.append(check(
        "No <details> or <summary> in FAQ",
        details_count == 0 and summary_count == 0,
        f"details={details_count} summary={summary_count}",
        "0"
    ))
    if details_count > 0 or summary_count > 0:
        failures.append("[FAQ] FAQ uses <details>/<summary> — v2 requires static div.hcs-faq-item only")

    # ── v2.24: hcs-faq section exists when FAQ items present ──────────────
    checks.append(check(
        "section.hcs-faq exists when FAQ items present",
        not has_faq_items or has_faq_section,
        "Consistent" if (not has_faq_items or has_faq_section) else "FAQ items but no hcs-faq section",
        "N/A"
    ))

    # ── v2.25: FAQ items use h3 + p ────────────────────────────────────────
    if has_faq_section:
        faq_content = get_section_content(html, "hcs-faq")
        has_h3 = bool(re.search(r'<h3\b', faq_content, re.IGNORECASE))
        has_p = bool(re.search(r'<p\b', faq_content, re.IGNORECASE))
        checks.append(check(
            "hcs-faq-item uses h3 + p",
            has_h3 and has_p,
            "ok" if (has_h3 and has_p) else "broken",
            "N/A"
        ))
        if not has_h3:
            failures.append("[hcs-faq-item h3+p] FAQ items missing <h3> question element")
        if not has_p:
            failures.append("[hcs-faq-item h3+p] FAQ items missing <p> answer element")

    # ── v2.26: FAQ h3 questions end with ? ────────────────────────────────
    if has_faq_section:
        faq_h3s = re.findall(
            r'<h3[^>]*>([^<]+)</h3>',
            get_section_content(html, "hcs-faq"),
            re.IGNORECASE
        )
        non_question = [h for h in faq_h3s if not h.strip().endswith("?")]
        checks.append(check(
            "FAQ h3 questions end with '?'",
            len(non_question) == 0,
            f"{len(faq_h3s)} questions, {len(non_question)} missing ?" if non_question else f"{len(faq_h3s)} questions ok",
            "all"
        ))
        if non_question:
            warnings.append(f"FAQ h3 does not end with '?': {non_question[:2]}")

    # ── v2.27: CTA section and button ─────────────────────────────────────
    cta_count = count_elements(html, "section", "hcs-cta")
    checks.append(check(
        "section.hcs-cta exists",
        cta_count >= 1,
        f"Found {cta_count}",
        "≥1"
    ))

    cta_content = get_section_content(html, "hcs-cta")
    btn_in_cta = bool(re.search(r'<a[^>]*class=["\'][^"\']*hcs-button["\'][^>]*>', cta_content, re.IGNORECASE))
    checks.append(check(
        "a.hcs-button inside CTA",
        btn_in_cta,
        "Found" if btn_in_cta else "Missing",
        "≥1"
    ))
    if not btn_in_cta:
        failures.append("[CTA] No <a class='hcs-button'> found")

    # CTA button is <a> not <button>
    button_misuse = re.findall(r'<button[^>]*class=["\'][^"\']*hcs-button["\'][^>]*>', html, re.IGNORECASE)
    checks.append(check(
        "CTA button is <a> not <button>",
        len(button_misuse) == 0,
        f"{len(button_misuse)} misuse" if button_misuse else "ok",
        "0"
    ))
    if button_misuse:
        failures.append("[CTA] CTA uses <button class='hcs-button'> — must be <a class='hcs-button'>")

    # CTA URL verified against link map
    cta_hrefs = re.findall(
        r'<a[^>]*class=["\'][^"\']*hcs-button["\'][^>]*href=["\']([^"\']+)["\']',
        html,
        re.IGNORECASE
    )
    if cta_hrefs and link_map_verified is not None:
        for href in cta_hrefs:
            if href == link_map_fallback:
                continue  # fallback is always ok
            if href not in link_map_verified:
                failures.append(f"[CTA URL] '{href}' is not in the verified link map — use only URLs from hcs_verified_link_map.json")
                break

    # ── v2.28: Forbidden grid/layout classes ──────────────────────────────
    forbidden_grid = re.findall(
        r'class=["\'][^"\']*\b(row|col-?!|column|custom-grid|grid-layout|card-grid|layout-grid)\b[^"\']*["\']',
        html,
        re.IGNORECASE
    )
    checks.append(check(
        "No forbidden grid/layout classes",
        len(forbidden_grid) == 0,
        f"{len(forbidden_grid)} found: {set(forbidden_grid)}" if forbidden_grid else "clean",
        "0"
    ))
    if forbidden_grid:
        failures.append(f"[grid classes] Forbidden classes: {set(forbidden_grid)}")

    # ── v2.29: BlogPosting JSON-LD ──────────────────────────────────────────
    checks.append(check(
        "BlogPosting JSON-LD exists",
        len(blog_blocks) >= 1,
        f"Found {len(blog_blocks)}",
        "required"
    ))

    # BlogPosting fields
    if blog_blocks:
        blog = blog_blocks[0]
        required_fields = ["headline", "datePublished", "dateModified", "author.name", "publisher.name"]
        for field in required_fields:
            present = json_has_field_strict(blog, field)
            checks.append(check(
                f"BlogPosting has '{field}'",
                present,
                "present" if present else f"MISSING: '{field}'",
                "required"
            ))
            if not present:
                failures.append(f"[BlogPosting] Missing required field: '{field}'")

        # v2.30: BlogPosting headline matches H1
        h1_match = re.search(r'<h1\b[^>]*>([^<]+)</h1>', hero_content, re.IGNORECASE)
        if h1_match and blog:
            h1_text = h1_match.group(1).strip()
            schema_headline = re.search(r'"headline"\s*:\s*"([^"]+)"', blog)
            if schema_headline:
                schema_h = schema_headline.group(1).strip()
                headline_match = h1_text == schema_h
                checks.append(check(
                    "BlogPosting headline matches H1 exactly",
                    headline_match,
                    f"H1: '{h1_text[:60]}'" + (" ✓" if headline_match else f" ≠ Schema: '{schema_h[:60]}'"),
                    "exact match"
                ))
                if not headline_match:
                    failures.append(f"[schema consistency] BlogPosting headline does not match H1: H1='{h1_text[:80]}' Schema='{schema_h[:80]}'")

    # ── v2.31: FAQPage JSON-LD when FAQs exist ──────────────────────────────
    checks.append(check(
        "FAQPage JSON-LD present when FAQs exist",
        not has_faq_items or len(faq_blocks) > 0,
        "Consistent" if (not has_faq_items or len(faq_blocks) > 0) else "FAQ items but no FAQPage schema",
        "N/A"
    ))
    if has_faq_items and not faq_blocks:
        failures.append("[FAQPage JSON-LD] Article has FAQ items but no FAQPage schema")

    # FAQPage mainEntity
    if faq_blocks:
        faq_schema = faq_blocks[0]
        has_main_entity = '"mainEntity"' in faq_schema and '"Question"' in faq_schema
        checks.append(check(
            "FAQPage has mainEntity array",
            has_main_entity,
            "present" if has_main_entity else "MISSING",
            "required"
        ))
        if not has_main_entity:
            failures.append("[FAQPage] Missing 'mainEntity' array")

    # v2.32: FAQPage schema matches visible FAQ content
    if has_faq_section and faq_blocks:
        faq_schema = faq_blocks[0]
        faq_h3s = re.findall(
            r'<h3[^>]*>([^<]+)</h3>',
            get_section_content(html, "hcs-faq"),
            re.IGNORECASE
        )
        faq_ps = re.findall(
            r'<p[^>]*>([^<]+)</p>',
            get_section_content(html, "hcs-faq"),
            re.IGNORECASE
        )
        schema_names = re.findall(r'"name"\s*:\s*"([^"]+)"', faq_schema)
        for h3q in faq_h3s[:5]:
            if h3q.strip() not in schema_names:
                warnings.append(f"FAQ h3 not in FAQPage schema name: '{h3q[:60]}'")
        # Check answers
        schema_answers = re.findall(r'"text"\s*:\s*"([^"]+)"', faq_schema)
        for p_a in faq_ps[:5]:
            if p_a.strip() not in schema_answers:
                warnings.append(f"FAQ p answer not in FAQPage schema text: '{p_a[:60]}'")

    # ── v2.33: Schema inside article wrapper ───────────────────────────────
    if article_match and blog_blocks:
        inside = '"BlogPosting"' in article_match.group(1)
        checks.append(check(
            "BlogPosting schema inside hcs-article wrapper",
            inside,
            "inside" if inside else "OUTSIDE",
            "inside"
        ))
        if not inside:
            failures.append("[schema placement] BlogPosting JSON-LD found OUTSIDE <article class='hcs-article'>")

    if article_match and faq_blocks:
        inside = '"FAQPage"' in article_match.group(1)
        checks.append(check(
            "FAQPage schema inside hcs-article wrapper",
            inside,
            "inside" if inside else "OUTSIDE",
            "inside"
        ))
        if not inside:
            failures.append("[schema placement] FAQPage JSON-LD found OUTSIDE <article class='hcs-article'>")

    # ── v2.34: CTA href is HCS Gadgets URL (advisory when no link map) ────
    if cta_hrefs:
        invalid_hrefs = [h for h in cta_hrefs
                         if not h.startswith("https://hcsgadgets.com/")]
        checks.append(check(
            "CTA href is https://hcsgadgets.com/ URL",
            len(invalid_hrefs) == 0,
            f"{len(invalid_hrefs)} invalid: {invalid_hrefs}" if invalid_hrefs else "valid",
            "0"
        ))
        if invalid_hrefs:
            warnings.append(f"CTA href not starting with https://hcsgadgets.com/: {invalid_hrefs}")

    # ── Product Truth Checks (when link map supplied) ────────────────────
    pt_failures = []
    if link_map_verified is not None:
        # Find all internal links in the article
        internal_links = re.findall(
            r'<a[^>]*href=["\'](https://hcsgadgets\.com/[^"\']+)["\'][^>]*>',
            html,
            re.IGNORECASE
        )
        for link in internal_links:
            if link == link_map_fallback:
                continue
            if link not in link_map_verified:
                pt_failures.append(f"[product truth] Unverified internal link: {link}")
                failures.append(f"[product truth] Unverified internal link: {link}")

    # ── Product-Data Policy Check ──────────────────────────────────────────
    pdp_violations = check_article_product_data_policy(html)
    for v in pdp_violations:
        failures.append(v)

    return failures, warnings, checks


def main():
    parser = argparse.ArgumentParser(
        description=f"HCS Gadgets HTML Contract Validator v{VERSION} — {CONTRACT_VERSION}"
    )
    parser.add_argument("--file", required=True, help="Path to HTML file to validate")
    parser.add_argument("--strict", action="store_true", help="Treat warnings as failures")
    parser.add_argument("--json", action="store_true", help="Output JSON results")
    parser.add_argument("--product-catalog", dest="product_catalog",
                        help="Path to product_catalog.json for product truth validation")
    parser.add_argument("--collections", dest="collections",
                        help="Path to collections_inventory.json for product truth validation")
    parser.add_argument("--link-map", dest="link_map",
                        help="Path to hcs_verified_link_map.json for link and product truth validation")
    args = parser.parse_args()

    # Load optional product truth data
    link_map_verified = None
    link_map_fallback = None
    product_catalog = None
    collections_inv = None

    if args.link_map:
        link_map_verified, link_map_fallback = load_link_map(args.link_map)
        if link_map_verified is None:
            log(f"Warning: Could not load link map from {args.link_map}", "WARN")

    if args.product_catalog:
        product_catalog = load_product_catalog(args.product_catalog)

    if args.collections:
        collections_inv = load_collections(args.collections)

    try:
        with open(args.file, "r", encoding="utf-8") as f:
            html = f.read()
    except FileNotFoundError:
        print(f"{RED}[FATAL]{RESET} File not found: {args.file}")
        sys.exit(1)

    print(f"{BOLD}HCS Gadgets — HTML Contract Validator v{VERSION}{RESET}")
    print(f"Contract: {CONTRACT_VERSION}")
    print(f"File: {args.file}")
    print(f"Strict mode: {args.strict}")
    if link_map_verified is not None:
        print(f"Link map: {args.link_map} ({len(link_map_verified)} verified URLs)")
    print()
    print("=" * 60)

    failures, warnings, checks = run_checks(
        html,
        link_map_verified=link_map_verified,
        link_map_fallback=link_map_fallback,
        product_catalog=product_catalog,
        collections_inv=collections_inv
    )

    passed = sum(1 for _, r, _, _ in checks if r is True)
    total = len(checks)

    print(f"\nTotal checks: {total}")
    print(f"Passed: {GREEN}{passed}{RESET}")
    if warnings:
        print(f"Warnings: {YELLOW}{len(warnings)}{RESET}")
    if failures:
        print(f"{RED}Failures: {len(failures)}{RESET}")

    print()
    print(f"{BOLD}FAILURES:{RESET}")
    if failures:
        for i, f in enumerate(failures, 1):
            print(f"  {RED}{i}.{RESET} {f}")
    else:
        print("  None")

    if warnings and not args.strict:
        print()
        print(f"{BOLD}WARNINGS:{RESET}")
        for i, w in enumerate(warnings, 1):
            print(f"  {YELLOW}!{RESET} {w}")

    result = "PASS" if not failures and not (args.strict and warnings) else "FAIL"
    print()
    print("=" * 60)
    if result == "PASS":
        print(f"{GREEN}{BOLD}RESULT: PASS{RESET} — Article conforms to HCS HTML Design Contract v2")
    else:
        print(f"{RED}{BOLD}RESULT: FAIL — Article does not conform to HCS HTML Design Contract v2{RESET}")

    if args.json:
        output = {
            "validator_version": VERSION,
            "contract": CONTRACT_VERSION,
            "file": args.file,
            "timestamp": datetime.now().isoformat(),
            "result": result,
            "total_checks": total,
            "passed": passed,
            "failures": failures,
            "warnings": warnings,
            "strict": args.strict,
        }
        print()
        print(json.dumps(output, indent=2, default=str))

    sys.exit(0 if result == "PASS" else 1)


if __name__ == "__main__":
    main()
