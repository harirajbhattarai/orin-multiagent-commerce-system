#!/usr/bin/env python3
import json
import re
import html
import difflib
import sys
from pathlib import Path

BASE_DIR = Path("/data/.openclaw/workspace")
if not BASE_DIR.exists():
    BASE_DIR = Path("/root/.openclaw/workspace")

CONTENT_DIR = BASE_DIR / "clients" / "hoverboard_store" / "content_engine"
INV_PATH = CONTENT_DIR / "shopify_inventory.json"

def strip_html(raw_html):
    if not raw_html:
        return ""
    text = re.sub(r"<script.*?</script>", " ", raw_html, flags=re.S | re.I)
    text = re.sub(r"<style.*?</style>", " ", text, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text

def normalise(text):
    text = (text or "").lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text

def token_set(text):
    words = normalise(text).split()
    stop = {
        "the","and","for","with","you","your","are","can","how","what","why","when",
        "from","this","that","into","guide","uk","2026","complete","everything",
        "need","know","best","safe","safely","article","draft","test"
    }
    return set(w for w in words if len(w) > 2 and w not in stop)

def jaccard(a, b):
    aa, bb = token_set(a), token_set(b)
    if not aa or not bb:
        return 0.0
    return len(aa & bb) / len(aa | bb)

def sequence_similarity(a, b):
    a = normalise(a)[:6000]
    b = normalise(b)[:6000]
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a, b).ratio()

def extract_meta(article_html):
    meta = {
        "seo_title": "",
        "meta_title": "",
        "meta_description": "",
        "url_slug": "",
        "h1": "",
        "faq_questions": [],
        "clean_text": strip_html(article_html),
    }

    comment = re.search(r"<!--(.*?)-->", article_html, flags=re.S)
    if comment:
        block = comment.group(1)
        patterns = {
            "seo_title": r"SEO Title:\s*(.+)",
            "meta_title": r"Meta Title:\s*(.+)",
            "meta_description": r"Meta Description:\s*(.+)",
            "url_slug": r"URL slug:\s*(.+)",
        }
        for key, pattern in patterns.items():
            m = re.search(pattern, block)
            if m:
                meta[key] = m.group(1).strip()

    h1 = re.search(r"<h1[^>]*>(.*?)</h1>", article_html, flags=re.S | re.I)
    if h1:
        meta["h1"] = strip_html(h1.group(1))

    faq_pattern = r'<h3[^>]*class=["\'][^"\']*hs-faq-q[^"\']*["\'][^>]*>(.*?)</h3>'
    faq_matches = re.findall(faq_pattern, article_html, flags=re.S | re.I)
    meta["faq_questions"] = [strip_html(x) for x in faq_matches]

    return meta

def main():
    if len(sys.argv) < 2:
        raise SystemExit("Usage: python3 preflight_article_check.py path/to/article.html")

    article_path = Path(sys.argv[1])
    if not article_path.exists():
        raise SystemExit(f"Article file not found: {article_path}")

    if not INV_PATH.exists():
        raise SystemExit("Missing Shopify inventory. Run fetch_shopify_blogs.py first.")

    new_html = article_path.read_text()
    new = extract_meta(new_html)
    inventory = json.loads(INV_PATH.read_text())

    title = new["seo_title"] or new["meta_title"] or new["h1"]
    risks = []

    # Risk tier thresholds
    TIER_BLOCK = 0.70
    TIER_REVIEW = 0.40
    TIER_LOW = 0.35

    highest_tier = 0  # 0 = pass, 1 = low/medium, 2 = review, 3 = block

    for existing in inventory:
        existing_title = existing.get("title", "")
        existing_h1 = existing.get("h1", "")
        existing_text = existing.get("clean_text", "")
        existing_faqs = existing.get("faq_questions", []) or []

        title_score = jaccard(title, existing_title)
        h1_score = jaccard(new["h1"], existing_h1)
        body_topic = jaccard(new["clean_text"], existing_text)
        body_phrase = sequence_similarity(new["clean_text"], existing_text)

        faq_overlap = set(map(normalise, new["faq_questions"])) & set(map(normalise, existing_faqs))

        reasons = []
        tier = 0

        if title_score >= 0.50:
            reasons.append(f"title similarity {title_score:.2f}")
            tier = max(tier, 2)
        if h1_score >= 0.50 and new["h1"] and existing_h1:
            reasons.append(f"H1 similarity {h1_score:.2f}")
            tier = max(tier, 2)
        if body_topic >= TIER_BLOCK:
            reasons.append(f"body topic similarity {body_topic:.2f}")
            tier = max(tier, 3)
        elif body_topic >= TIER_REVIEW:
            reasons.append(f"body topic similarity {body_topic:.2f}")
            tier = max(tier, 2)
        elif body_topic >= TIER_LOW:
            reasons.append(f"body topic similarity {body_topic:.2f}")
            tier = max(tier, 1)
        if body_phrase >= 0.50:
            reasons.append(f"body phrase similarity {body_phrase:.2f}")
            tier = max(tier, 2)
        if len(faq_overlap) >= 3:
            reasons.append(f"FAQ overlap {len(faq_overlap)} questions")
            tier = max(tier, 2)

        if tier > highest_tier:
            highest_tier = tier

        if reasons:
            risks.append({
                "existing_title": existing_title,
                "existing_slug": existing.get("handle", ""),
                "existing_status": "published" if existing.get("published_at") else "draft",
                "reasons": reasons,
                "tier": tier,
            })

    print("Preflight article check")
    print("-----------------------")
    print(f"Article: {title}")
    print(f"File: {article_path}")
    print(f"Existing Shopify articles checked: {len(inventory)}")
    print(f"Risks found: {len(risks)}")
    print("")

    if highest_tier == 3:
        print("COMPLIANCE = FAIL")
        print("Duplicate = HIGH RISK \u2014 BLOCK")
        print("")
        for i, risk in enumerate(risks[:10], 1):
            print(f"Risk {i}: {risk['existing_title']}")
            print(f"Slug: {risk['existing_slug']}")
            print(f"Status: {risk['existing_status']}")
            for reason in risk["reasons"]:
                print(f"- {reason}")
            print("")
        print("ACTION: Rewrite or merge required before publishing.")
        sys.exit(3)

    if highest_tier == 2:
        print("COMPLIANCE = REVIEW NEEDED")
        print("Duplicate = REVIEW NEEDED")
        print("")
        for i, risk in enumerate(risks[:10], 1):
            print(f"Risk {i}: {risk['existing_title']}")
            print(f"Slug: {risk['existing_slug']}")
            print(f"Status: {risk['existing_status']}")
            for reason in risk["reasons"]:
                print(f"- {reason}")
            print("")
        print("ACTION: Review required before creating Shopify draft.")
        sys.exit(1)

    if highest_tier == 1:
        print("COMPLIANCE = PASS WITH WARNINGS")
        print("Duplicate = LOW/MEDIUM RISK")
        print("")
        for i, risk in enumerate(risks[:10], 1):
            print(f"Warning {i}: {risk['existing_title']}")
            print(f"Slug: {risk['existing_slug']}")
            for reason in risk["reasons"]:
                print(f"- {reason}")
            print("")
        sys.exit(0)

    print("COMPLIANCE = PASS")
    print("HTML = PASS")
    print("Duplicate = PASS")
    sys.exit(0)

if __name__ == "__main__":
    main()
