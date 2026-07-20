#!/usr/bin/env python3
"""
HTML Quality Checker — supports both Hoverboard Store (hs-*) and HCS Gadgets (hcs-*).

Auto-detects client from draft file path:
  clients/hcs_gadgets/...  → HCS Gadgets mode (hcs-*, HCS Gadgets byline, FAQ JSON-LD allowed)
  clients/hoverboard_store/... → Hoverboard Store mode (hs-*, Hoverboard Store byline)

Can also be forced with --hcs flag.
"""
import re
import sys
import os
from pathlib import Path


def strip_comments(html):
    return re.sub(r"<!--.*?-->", "", html, flags=re.S)


def detect_client_from_path(path_str):
    """Detect client from file path. Returns 'hcs_gadgets', 'hoverboard_store', or None."""
    parts = path_str.split("/")
    try:
        idx = parts.index("clients")
        return parts[idx + 1] if idx + 1 < len(parts) else None
    except ValueError:
        return None


def main():
    # Accept --brand argument for client-specific byline check
    # Accept --hcs flag to force HCS Gadgets mode
    brand_byline = "Hoverboard Store"  # default for backward compatibility
    force_hcs = False
    path_arg = None
    for arg in sys.argv[1:]:
        if arg == "--hcs":
            force_hcs = True
        elif arg.startswith("--brand="):
            brand_byline = arg.split("=", 1)[1]
        elif not arg.startswith("--"):
            path_arg = arg

    if not path_arg:
        raise SystemExit("Usage: python3 html_quality_check.py [--hcs] [--brand=BRAND] path/to/article.html")

    path = Path(path_arg)
    if not path.exists():
        raise SystemExit(f"File not found: {path}")

    html = path.read_text()
    visible_html = strip_comments(html)
    issues = []

    # Auto-detect HCS Gadgets from path (overridden only by --hcs flag)
    is_hcs = force_hcs or (detect_client_from_path(str(path)) == "hcs_gadgets")

    if is_hcs:
        # HCS Gadgets validation
        wrapper_article = 'class="hcs-article"'
        wrapper_container = 'class="hcs-container"'
        wrapper_quick = 'class="hcs-quick-answer"'
        brand_byline = "HCS Gadgets"
        allow_faq_jsonld = True
    else:
        # Hoverboard Store validation (default/backward compat)
        wrapper_article = 'class="hs-article"'
        wrapper_container = 'class="hs-container"'
        wrapper_quick = 'class="hs-quick-answer"'
        allow_faq_jsonld = False

    # Basic wrapper checks
    if wrapper_article not in html:
        issues.append(f"Missing {('hs' if not is_hcs else 'hcs')}-article wrapper.")

    if wrapper_container not in html:
        issues.append(f"Missing {('hs' if not is_hcs else 'hcs')}-container wrapper.")

    if not re.search(r"<h1[^>]*>.*?</h1>", html, flags=re.S | re.I):
        issues.append("Missing H1.")

    if wrapper_quick not in html:
        issues.append(f"Missing {('hs' if not is_hcs else 'hcs')}-quick-answer block.")

    # Bad tag checks
    if re.search(r"<di(\s|>)", html, flags=re.I):
        issues.append("Invalid HTML tag found: <di>. Use <div> or <p>.")

    if re.search(r"</di>", html, flags=re.I):
        issues.append("Invalid closing tag found: </di>. Use </div> or </p>.")

    if re.search(r"<p>\s*</p>", html, flags=re.I):
        issues.append("Empty paragraph tag found: <p></p>.")

    # Visible metadata checks
    visible_text = re.sub(r"<[^>]+>", " ", visible_html)
    visible_text = re.sub(r"\s+", " ", visible_text).strip()

    visible_meta_terms = [
        "SEO Title:",
        "Meta Title:",
        "Meta Description:",
        "URL Slug:",
        "URL slug:",
    ]

    for term in visible_meta_terms:
        if term in visible_text:
            issues.append(f"Visible metadata found in article body: {term}")

    # Public author checks
    blocked_author_terms = [
        "TOOXIC",
        "AISEO",
        "ChatGPT",
        "OpenAI",
        "ORIN Test",
        "autonomous SEO intelligence system",
    ]

    for term in blocked_author_terms:
        if term.lower() in visible_text.lower():
            issues.append(f"Blocked public author/system wording found: {term}")

    # HCS Gadgets uses JSON-LD for author/publisher — skip visible byline check
    if not is_hcs:
        if f"By {brand_byline}" not in visible_text:
            issues.append(f'Missing public byline: "By {brand_byline}".')
    # FAQ checks — HCS uses h3-based FAQ items, Hoverboard uses div.hs-faq-item
    if is_hcs:
        # HCS Gadgets: check for h3 within .hcs-faq section
        faq_section_present = 'class="hcs-faq"' in html
        hcs_faq_h3s = re.findall(r'<section[^>]*class=["\']hcs-faq["\'][^>]*>.*?<h3', html, flags=re.DOTALL | re.I)
        hcs_faq_items = len(re.findall(r'class=["\']hcs-faq-item["\']', html, flags=re.I))
        # Also count h3 items within hcs-faq section
        in_faq = False
        h3_count_in_faq = 0
        for line in re.findall(r'<section[^>]*class=["\']hcs-faq["\'][^>]*>(.*?)</section>', html, flags=re.DOTALL | re.I):
            h3_count_in_faq += len(re.findall(r'<h3', line, re.I))
        if not faq_section_present and h3_count_in_faq == 0:
            issues.append("No FAQ section found. HCS articles should include an hcs-faq section with FAQ items.")
        # HCS allows FAQPage JSON-LD
    else:
        # Hoverboard Store: check for div.hs-faq-item
        faq_item_count = len(re.findall(r'class=["\']hs-faq-item["\']', html, flags=re.I))
        faq_q_count = len(re.findall(r'<div\s+class=["\']hs-faq-q["\'][^>]*>', html, flags=re.I))
        faq_a_count = len(re.findall(r'<div\s+class=["\']hs-faq-a["\'][^>]*>', html, flags=re.I))
        old_q_count = len(re.findall(r'<h3\s+class=["\']hs-faq-q["\']', html, flags=re.I))
        old_a_count = len(re.findall(r'<p\s+class=["\']hs-faq-a["\']', html, flags=re.I))
        if old_q_count or old_a_count:
            issues.append("Old FAQ format found. Use div.hs-faq-q and div.hs-faq-a, not h3/p.")
        if faq_item_count > 0:
            if faq_q_count != faq_item_count:
                issues.append(f"FAQ question count mismatch: {faq_q_count} questions for {faq_item_count} FAQ items.")
            if faq_a_count != faq_item_count:
                issues.append(f"FAQ answer count mismatch: {faq_a_count} answers for {faq_item_count} FAQ items.")
        else:
            issues.append("No FAQ items found. This may be okay only if the article intentionally has no FAQ section.")
        # Manual FAQPage JSON-LD should not be inside article because Shopify theme generates it
        if re.search(r'"@type"\s*:\s*"FAQPage"', html, flags=re.I):
            issues.append("Manual FAQPage JSON-LD found inside article. Remove it because Shopify theme generates FAQ schema.")

    print("HTML Quality Check")
    print("==================")
    print(f"File: {path}")
    print(f"Issues found: {len(issues)}")
    print("")

    if issues:
        print("STATUS: FAIL - FIX BEFORE PUBLISHING")
        for issue in issues:
            print(f"- {issue}")
        raise SystemExit(1)

    print("STATUS: PASS - HTML structure looks safe")


if __name__ == "__main__":
    main()
