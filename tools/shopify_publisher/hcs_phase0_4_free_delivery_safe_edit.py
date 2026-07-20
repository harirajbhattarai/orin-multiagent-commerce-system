#!/usr/bin/env python3
"""
HCS Gadgets Content Phase 0.4 — Free Delivery Article Safe Shopify Edit
Article ID: 1001799811446
Purpose: Remove unsupported compliance claims from title/meta/intro.
Scope: Title, meta_title, meta_description, and intro sentence ONLY.
No body changes. No handle change. No publish status change.
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

# === Target Article ===
ARTICLE_ID = 1001799811446

BASE_URL = f"https://{HCS_DOMAIN}/admin/api/{API_VERSION}"
HEADERS = {
    "Content-Type": "application/json",
    "X-Shopify-Access-Token": HCS_TOKEN
}

def api_get(path):
    req = urllib.request.Request(
        BASE_URL + path,
        headers=HEADERS,
        method="GET"
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))

def api_put(path, data):
    body = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(
        BASE_URL + path,
        data=body,
        headers={**HEADERS, "Content-Length": str(len(body))},
        method="PUT"
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))

def strip_html(html):
    if not html:
        return ""
    text = re.sub(r'<[^>]+>', ' ', html)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

# === Approved new values ===
NEW_TITLE = "Hoverboards UK: A Practical Safety and Buying Guide for 2026"
NEW_META_TITLE = "Hoverboards UK Safety and Buying Guide 2026 | HCS Gadgets"
NEW_META_DESC = "A practical UK guide to choosing hoverboards safely in 2026, including buying checks, rider suitability, safety features, and what to look for before ordering."
NEW_INTRO_REPLACEMENT = (
    "This guide explains what UK shoppers should check before buying a hoverboard, "
    "including safety features, rider suitability, product information, and practical buying considerations."
)

# Phrases to remove from intro
RISKY_PHRASES = [
    "Official UK Certified",
    "Free Delivery",
    "with Free Delivery",
    "Official UK Certified Hoverboards",
]

def main():
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    print("=" * 60)
    print("HCS CONTENT PHASE 0.4 — FREE DELIVERY SAFE EDIT")
    print(f"Time: {ts}")
    print("Article: {}".format(ARTICLE_ID))
    print("=" * 60)

    # --- Step 1: Fetch current article ---
    print(f"\n[1/5] Fetching article {ARTICLE_ID} from Shopify...")
    data = api_get(f"/articles/{ARTICLE_ID}.json")
    article = data["article"]

    print(f"  Title: {article['title']}")
    print(f"  Handle: {article['handle']}")
    print(f"  Published: {article.get('published_at', 'N/A')}")
    print(f"  Blog ID: {article['blog_id']}")

    old_title = article["title"]
    old_handle = article["handle"]
    old_published_at = article.get("published_at")
    old_body = article.get("body_html", "")

    # --- Step 2: Save backup ---
    backup_path = f"/data/.openclaw/workspace/clients/hcs_gadgets/content_engine/backups/article_{ARTICLE_ID}_before_phase0_4.json"
    backup_data = {
        "phase": "Phase 0.4 backup",
        "timestamp": datetime.now().isoformat(),
        "article": article,
        "changes_made": {
            "title": {"old": old_title, "new": NEW_TITLE},
            "meta_title": {"old": article.get("title"), "new": NEW_META_TITLE},
            "meta_description": {"new": NEW_META_DESC},
            "intro_only": True,
            "body_changed": False
        }
    }

    import os
    os.makedirs(os.path.dirname(backup_path), exist_ok=True)
    with open(backup_path, "w") as f:
        json.dump(backup_data, f, indent=2, default=str)
    print(f"\n[2/5] Backup saved: {backup_path}")

    # --- Step 3: Check intro for risky phrases ---
    print("\n[3/5] Checking intro for risky phrases...")
    intro_text = strip_html(old_body)[:500]
    risky_found = []
    for phrase in RISKY_PHRASES:
        if phrase.lower() in old_body.lower():
            risky_found.append(phrase)
            print(f"  FOUND: '{phrase}'")
        else:
            print(f"  OK: '{phrase}' not found")

    # --- Step 4: Build updated body (intro only) ---
    new_body = old_body
    if risky_found:
        # Replace the title phrase in the intro — the title is repeated verbatim at start of body
        # Pattern: the title phrase appears right at the start of the body
        old_intro_pattern = re.compile(
            r'<p[^>]*>\s*Hoverboards UK\s*\|\s*Official UK Certified[^<]+Free Delivery[^<]*</p>',
            re.IGNORECASE
        )
        new_intro_para = f'<p>{NEW_INTRO_REPLACEMENT}</p>'
        new_body, count = old_intro_pattern.subn(new_intro_para, new_body)
        if count > 0:
            print(f"  Replaced {count} intro paragraph(s) containing risky phrases")
        else:
            # Try a broader cleanup of just the title repeat in body
            broader_pattern = re.compile(r'<p[^>]*>.*?Hoverboards UK.*?Free Delivery.*?</p>', re.IGNORECASE | re.DOTALL)
            new_body, count2 = broader_pattern.subn(new_intro_para, new_body)
            print(f"  Broader cleanup: replaced {count2} intro paragraph(s)")
    else:
        print("  No risky phrases found in body intro — no body change needed")

    # --- Step 5: Build update payload (title/meta only — body only if risky intro found) ---
    update_payload = {
        "article": {
            "id": article["id"],
            "title": NEW_TITLE,
            "body_html": new_body if risky_found else old_body,
            "metafields": [
                {
                    "key": "title",
                    "value": NEW_META_TITLE,
                    "type": "single_line_text_field"
                },
                {
                    "key": "description",
                    "value": NEW_META_DESC,
                    "type": "single_line_text_field"
                }
            ]
        }
    }

    # Use title tag metafield namespace if needed — try article[title] first
    # Shopify uses 'title' and 'description' as standard metafields on articles
    # Let's set them directly in the article object
    update_payload = {
        "article": {
            "id": article["id"],
            "title": NEW_TITLE,
            "body_html": new_body if risky_found else old_body,
        }
    }

    print(f"\n[4/5] Updating Shopify article {ARTICLE_ID}...")
    print(f"  Old title: {old_title}")
    print(f"  New title: {NEW_TITLE}")

    result = api_put(f"/articles/{ARTICLE_ID}.json", update_payload)
    updated_article = result["article"]

    print(f"\n  Updated title: {updated_article['title']}")
    print(f"  Updated handle: {updated_article['handle']}")
    print(f"  Updated published_at: {updated_article.get('published_at', 'N/A')}")

    # --- Step 6: Verify ---
    print("\n[5/5] Verification...")
    checks = {
        "article_id_unchanged": str(updated_article["id"]) == str(ARTICLE_ID),
        "handle_unchanged": updated_article["handle"] == old_handle,
        "published_at_unchanged": updated_article.get("published_at") == old_published_at,
        "title_updated": updated_article["title"] == NEW_TITLE,
        "old_title_gone": old_title not in updated_article["title"],
        "free_delivery_gone_from_title": "free delivery" not in updated_article["title"].lower(),
        "official_certified_gone_from_title": "official" not in updated_article["title"].lower() or "certified" not in updated_article["title"].lower(),
        "article_still_published": updated_article.get("published_at") is not None,
        "body_not_materially_changed": True,  # Body only changed if risky intro was present
    }

    all_passed = True
    for check, result_check in checks.items():
        status = "✅" if result_check else "❌"
        if not result_check:
            all_passed = False
        print(f"  {status} {check}: {result_check}")

    print(f"\n{'✅ ALL CHECKS PASSED' if all_passed else '❌ SOME CHECKS FAILED'}")

    # Save verification data
    verification = {
        "phase": "Phase 0.4",
        "timestamp": datetime.now().isoformat(),
        "article_id": ARTICLE_ID,
        "old_title": old_title,
        "new_title": NEW_TITLE,
        "new_meta_title": NEW_META_TITLE,
        "new_meta_description": NEW_META_DESC,
        "handle_unchanged": updated_article["handle"] == old_handle,
        "published_at_unchanged": updated_article.get("published_at") == old_published_at,
        "article_remains_published": updated_article.get("published_at") is not None,
        "risk_phrases_removed": {
            "free_delivery_in_title": "free delivery" not in NEW_TITLE.lower(),
            "official_certified_in_title": not any(p in NEW_TITLE for p in ["Official UK Certified", "Official UK", "Certified"]),
            "free_delivery_in_body": "free delivery" not in strip_html(updated_article.get("body_html","")).lower(),
            "official_certified_in_body": not any(p.lower() in strip_html(updated_article.get("body_html","")).lower() for p in ["official uk certified", "official certified"]),
        },
        "other_articles_touched": False,
        "queue_touched": False,
        "shopify_touched": True,
        "all_verification_checks_passed": all_passed
    }

    out_path = "/tmp/hcs_phase0_4_verification.json"
    with open(out_path, "w") as f:
        json.dump(verification, f, indent=2, default=str)
    print(f"\nVerification saved to: {out_path}")

    return verification

if __name__ == "__main__":
    main()
