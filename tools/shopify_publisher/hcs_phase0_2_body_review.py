import os
#!/usr/bin/env python3
"""
HCS Gadgets Content Phase 0.2 — Body Review Script
READ-ONLY: Pulls article bodies for duplicate pair and risky Free Delivery article.
No Shopify edits, no queue changes, no publishing.
Uses urllib (stdlib) — no external dependencies.
"""
import urllib.request
import urllib.error
import json
import re
from datetime import datetime

# === HCS Gadgets Shopify Credentials ===
HCS_DOMAIN = "hcsgadgets-com.myshopify.com"
HCS_TOKEN = os.environ.get("HCS_SHOPIFY_TOKEN")
if not HCS_TOKEN:
    raise RuntimeError("HCS_SHOPIFY_TOKEN is missing; refusing Shopify operation.")
API_VERSION = "2026-01"

# === Article IDs ===
ARTICLE_A_ID = 1000525496694  # Older duplicate (Feb 2026)
ARTICLE_B_ID = 1000575172982  # Newer duplicate (May 2026) — recommended canonical
FREE_DELIVERY_ID = 1001799811446  # Risky "Free Delivery" article

BASE_URL = f"https://{HCS_DOMAIN}/admin/api/{API_VERSION}"

def api_get(path):
    """Make authenticated Shopify API GET request using urllib"""
    req = urllib.request.Request(
        BASE_URL + path,
        headers={
            "Content-Type": "application/json",
            "X-Shopify-Access-Token": HCS_TOKEN
        },
        method="GET"
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))

def strip_html(html):
    """Strip HTML tags for text comparison"""
    if not html:
        return ""
    text = re.sub(r'<[^>]+>', ' ', html)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def word_count(html):
    return len(strip_html(html).split())

def extract_links(html):
    """Extract internal links and product links from HTML"""
    if not html:
        return [], [], []
    hrefs = re.findall(r'href=["\']([^"\']+)["\']', html)
    internal = [h for h in hrefs if 'hcsgadgets' in h.lower() or (h.startswith('/') and not h.startswith('//'))]
    product_links = [h for h in hrefs if '/products/' in h]
    external = [h for h in hrefs if h not in internal and not h.startswith('/')]
    return internal, external, product_links

def summarise_body(html):
    """Extract key structural and content signals from body HTML"""
    if not html:
        return {}
    text = strip_html(html)
    h2s = re.findall(r'<h2[^>]*>([^<]+)</h2>', html, re.IGNORECASE)
    h3s = re.findall(r'<h3[^>]*>([^<]+)</h3>', html, re.IGNORECASE)
    h4s = re.findall(r'<h4[^>]*>([^<]+)</h4>', html, re.IGNORECASE)
    free_delivery_count = len(re.findall(r'free\s+delivery', text, re.IGNORECASE))
    cats = re.findall(r'hoverboard|scooter|gadget|bbq|garden|kitchen|home', text, re.IGNORECASE)
    cats = list(set([c.lower() for c in cats]))
    outdated = re.findall(r'\b(202[0-4])\b', text)
    outdated = list(set(outdated))
    faq_in_html = bool(re.search(r'<table[^>]*faq|faqauthor|faqschema|questionanswer', html, re.IGNORECASE))
    has_cta = bool(re.search(r'shop\s+now|buy\s+now|check\s+out|browse|view\s+products', text, re.IGNORECASE))
    prices = re.findall(r'£[\d]+(?:[.,]\d{2})?', text)
    return {
        "word_count": word_count(html),
        "h2_sections": [h.strip() for h in h2s],
        "h3_sections": [h.strip() for h in h3s],
        "h4_sections": [h.strip() for h in h4s],
        "free_delivery_mentions": free_delivery_count,
        "product_categories_mentioned": cats,
        "year_references": outdated,
        "has_faq_schema": faq_in_html,
        "has_cta": has_cta,
        "price_mentions": prices[:10],
        "preview": text[:600] + "..." if len(text) > 600 else text,
    }

def get_article(article_id):
    return api_get(f"/articles/{article_id}.json")

def compare_pair(a_data, b_data):
    a_body = a_data.get("article", {}).get("body_html", "")
    b_body = b_data.get("article", {}).get("body_html", "")
    a_sum = summarise_body(a_body)
    b_sum = summarise_body(b_body)
    a_int, a_ext, a_prods = extract_links(a_body)
    b_int, b_ext, b_prods = extract_links(b_body)
    a_words = set(strip_html(a_body).lower().split())
    b_words = set(strip_html(b_body).lower().split())
    overlap = len(a_words & b_words) / max(len(a_words | b_words), 1)
    a_sections = set(a_sum.get("h2_sections", []))
    b_sections = set(b_sum.get("h2_sections", []))
    return {
        "word_count_a": a_sum["word_count"],
        "word_count_b": b_sum["word_count"],
        "content_overlap_pct": round(overlap * 100, 1),
        "common_h2_sections": sorted(list(a_sections & b_sections)),
        "unique_h2_sections_a": sorted(list(a_sections - b_sections)),
        "unique_h2_sections_b": sorted(list(b_sections - a_sections)),
        "internal_links_a": a_int[:8],
        "internal_links_b": b_int[:8],
        "product_links_a": a_prods[:5],
        "product_links_b": b_prods[:5],
        "free_delivery_a": a_sum["free_delivery_mentions"],
        "free_delivery_b": b_sum["free_delivery_mentions"],
        "year_refs_a": a_sum["year_references"],
        "year_refs_b": b_sum["year_references"],
        "has_faq_schema_a": a_sum["has_faq_schema"],
        "has_faq_schema_b": b_sum["has_faq_schema"],
        "has_cta_a": a_sum["has_cta"],
        "has_cta_b": b_sum["has_cta"],
        "price_mentions_a": a_sum["price_mentions"],
        "price_mentions_b": b_sum["price_mentions"],
        "preview_a": a_sum["preview"],
        "preview_b": b_sum["preview"],
    }

def main():
    print("=" * 60)
    print("HCS CONTENT PHASE 0.2 — BODY REVIEW")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("Mode: READ-ONLY")
    print("=" * 60)

    print(f"\n[1/3] Fetching Article A ({ARTICLE_A_ID}) — older duplicate...")
    a_data = get_article(ARTICLE_A_ID)
    a_article = a_data["article"]
    print(f"  Title: {a_article['title']}")
    print(f"  Handle: {a_article['handle']}")
    print(f"  Published: {a_article.get('published_at', 'DRAFT')}")

    print(f"\n[2/3] Fetching Article B ({ARTICLE_B_ID}) — newer duplicate (canonical)...")
    b_data = get_article(ARTICLE_B_ID)
    b_article = b_data["article"]
    print(f"  Title: {b_article['title']}")
    print(f"  Handle: {b_article['handle']}")
    print(f"  Published: {b_article.get('published_at', 'DRAFT')}")

    print(f"\n[3/3] Fetching Free Delivery Article ({FREE_DELIVERY_ID})...")
    fd_data = get_article(FREE_DELIVERY_ID)
    fd_article = fd_data["article"]
    print(f"  Title: {fd_article['title']}")
    print(f"  Handle: {fd_article['handle']}")
    print(f"  Published: {fd_article.get('published_at', 'DRAFT')}")

    # --- Duplicate Pair Comparison ---
    print("\n" + "=" * 60)
    print("DUPLICATE PAIR ANALYSIS")
    print("=" * 60)
    comp = compare_pair(a_data, b_data)
    print(f"\n[A] Word count: {comp['word_count_a']} | [B] Word count: {comp['word_count_b']}")
    print(f"Content overlap (word-based): {comp['content_overlap_pct']}%")
    print(f"FAQ/schema — A: {comp['has_faq_schema_a']} | B: {comp['has_faq_schema_b']}")
    print(f"CTA present — A: {comp['has_cta_a']} | B: {comp['has_cta_b']}")
    print(f"Free delivery mentions — A: {comp['free_delivery_a']} | B: {comp['free_delivery_b']}")
    print(f"Year refs — A: {comp['year_refs_a']} | B: {comp['year_refs_b']}")
    print(f"\nCommon H2 sections ({len(comp['common_h2_sections'])}): {comp['common_h2_sections']}")
    print(f"Unique to A ({len(comp['unique_h2_sections_a'])}): {comp['unique_h2_sections_a']}")
    print(f"Unique to B ({len(comp['unique_h2_sections_b'])}): {comp['unique_h2_sections_b']}")
    print(f"\nProduct links A: {comp['product_links_a']}")
    print(f"Product links B: {comp['product_links_b']}")
    print(f"\nPrice mentions A: {comp['price_mentions_a']}")
    print(f"Price mentions B: {comp['price_mentions_b']}")

    # --- Free Delivery Article ---
    print("\n" + "=" * 60)
    print("FREE DELIVERY ARTICLE ANALYSIS")
    print("=" * 60)
    fd_body = fd_article.get("body_html", "")
    fd_sum = summarise_body(fd_body)
    fd_int, fd_ext, fd_prods = extract_links(fd_body)
    print(f"\nArticle ID: {FREE_DELIVERY_ID}")
    print(f"Title: {fd_article['title']}")
    print(f"Handle: {fd_article['handle']}")
    print(f"Word count: {fd_sum['word_count']}")
    print(f"Free delivery mentions in body: {fd_sum['free_delivery_mentions']}")
    print(f"H2 sections: {fd_sum['h2_sections']}")
    print(f"H3 sections: {fd_sum['h3_sections']}")
    print(f"Product links: {fd_prods[:5]}")
    print(f"Has FAQ/schema: {fd_sum['has_faq_schema']}")
    print(f"Has CTA: {fd_sum['has_cta']}")
    text = strip_html(fd_body)
    fd_contexts = []
    for match in re.finditer(r'.{0,100}free\s+delivery.{0,100}', text, re.IGNORECASE):
        fd_contexts.append(match.group(0).strip())
    print(f"\n'Free Delivery' context ({len(fd_contexts)} occurrences):")
    for ctx in fd_contexts[:3]:
        print(f"  ...{ctx}...")

    # --- Save structured data ---
    result = {
        "phase": "Content Phase 0.2",
        "client": "hcs_gadgets",
        "status": "BODY_REVIEW_COMPLETE",
        "timestamp": datetime.now().isoformat(),
        "article_a": {
            "id": str(ARTICLE_A_ID),
            "title": a_article["title"],
            "handle": a_article["handle"],
            "published_at": a_article.get("published_at"),
            "updated_at": a_article.get("updated_at"),
            "tags": a_article.get("tags", []),
            "author": a_article.get("author", "") if isinstance(a_article.get("author"), str) else a_article.get("author", {}).get("name"),
        },
        "article_b": {
            "id": str(ARTICLE_B_ID),
            "title": b_article["title"],
            "handle": b_article["handle"],
            "published_at": b_article.get("published_at"),
            "updated_at": b_article.get("updated_at"),
            "tags": b_article.get("tags", []),
            "author": b_article.get("author", "") if isinstance(b_article.get("author"), str) else b_article.get("author", {}).get("name"),
        },
        "free_delivery_article": {
            "id": str(FREE_DELIVERY_ID),
            "title": fd_article["title"],
            "handle": fd_article["handle"],
            "published_at": fd_article.get("published_at"),
            "word_count": fd_sum["word_count"],
            "free_delivery_mentions": fd_sum["free_delivery_mentions"],
            "free_delivery_contexts": fd_contexts[:5],
            "h2_sections": fd_sum["h2_sections"],
            "h3_sections": fd_sum["h3_sections"],
            "product_links": fd_prods[:10],
            "has_faq_schema": fd_sum["has_faq_schema"],
            "has_cta": fd_sum["has_cta"],
            "is_title_compliant": "free delivery" not in fd_article["title"].lower(),
        },
        "comparison": comp,
        "shopify_touched": False,
        "queue_touched": False,
    }
    out_path = "/tmp/hcs_phase0_2_body_review_data.json"
    with open(out_path, "w") as f:
        json.dump(result, f, indent=2, default=str)
    print(f"\n✅ Full data saved to {out_path}")
    print(f"Shopify touched: NO | Queue touched: NO")
    return result

if __name__ == "__main__":
    main()
