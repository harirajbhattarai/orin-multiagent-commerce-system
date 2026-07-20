import os
#!/usr/bin/env python3
"""
HCS Gadgets Content Phase 0.5A — Duplicate Merge and Redirect Dry-Run Plan
READ-ONLY: Fetches both articles, compares, prepares plan.
No Shopify edits. No redirects. No publishing.
"""
import urllib.request
import json
import re
from datetime import datetime

HCS_DOMAIN = "hcsgadgets-com.myshopify.com"
TOKEN = os.environ.get("HCS_SHOPIFY_TOKEN")
if not TOKEN:
    raise RuntimeError("HCS_SHOPIFY_TOKEN is missing; refusing Shopify operation.")
BASE = f"https://{HCS_DOMAIN}/admin/api/2026-01"
HEADERS = {"Content-Type": "application/json", "X-Shopify-Access-Token": TOKEN}

ARTICLE_A_ID = 1000525496694
ARTICLE_B_ID = 1000575172982

def api_get(path):
    req = urllib.request.Request(BASE + path, headers=HEADERS, method="GET")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())

def strip_html(html):
    if not html:
        return ""
    text = re.sub(r'<[^>]+>', ' ', html)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def word_count(html):
    return len(strip_html(html).split())

def get_h2_sections(html):
    return re.findall(r'<h2[^>]*>([^<]+)</h2>', html, re.IGNORECASE)

def get_h3_sections(html):
    return re.findall(r'<h3[^>]*>([^<]+)</h3>', html, re.IGNORECASE)

def extract_section_content(html, section_title):
    """Extract the content under a specific H2 section"""
    pattern = re.compile(
        r'<h2[^>]*>' + re.escape(section_title) + r'</h2>(.*?)(?=<h2|<h3|\Z)',
        re.IGNORECASE | re.DOTALL
    )
    match = pattern.search(html)
    if match:
        return strip_html(match.group(1))[:800]
    return ""

def main():
    ts = datetime.now().isoformat()
    print("=" * 60)
    print("HCS PHASE 0.5A — DUPLICATE MERGE + REDIRECT DRY-RUN")
    print(f"Time: {ts}")
    print("=" * 60)

    # --- Fetch both articles ---
    print(f"\n[1/6] Fetching Article A ({ARTICLE_A_ID})...")
    a_data = api_get(f"/articles/{ARTICLE_A_ID}.json")["article"]
    print(f"  Title: {a_data['title']}")
    print(f"  Handle: {a_data['handle']}")
    print(f"  Blog ID: {a_data['blog_id']}")
    print(f"  Published: {a_data.get('published_at','DRAFT')}")

    print(f"\n[2/6] Fetching Article B ({ARTICLE_B_ID})...")
    b_data = api_get(f"/articles/{ARTICLE_B_ID}.json")["article"]
    print(f"  Title: {b_data['title']}")
    print(f"  Handle: {b_data['handle']}")
    print(f"  Blog ID: {b_data['blog_id']}")
    print(f"  Published: {b_data.get('published_at','DRAFT')}")

    # --- Basic comparison ---
    print("\n" + "=" * 60)
    print("BASIC COMPARISON")
    print("=" * 60)
    a_body = a_data.get("body_html", "")
    b_body = b_data.get("body_html", "")
    a_wc = word_count(a_body)
    b_wc = word_count(b_body)
    a_h2s = get_h2_sections(a_body)
    b_h2s = get_h2_sections(b_body)
    a_h3s = get_h3_sections(a_body)
    b_h3s = get_h3_sections(b_body)

    print(f"\nArticle A — word count: {a_wc} | H2s: {len(a_h2s)} | H3s: {len(a_h3s)}")
    print(f"Article B — word count: {b_wc} | H2s: {len(b_h2s)} | H3s: {len(b_h3s)}")
    print(f"\nA H2 sections: {a_h2s}")
    print(f"B H2 sections: {b_h2s}")

    # --- Check if Article A accessory section is unique to A ---
    print("\n" + "=" * 60)
    print("ACCESSORY SECTION ANALYSIS")
    print("=" * 60)
    accessory_in_a = "Electric Scooter Accessories" in a_h2s
    print(f"Article A has 'Electric Scooter Accessories' section: {accessory_in_a}")

    if accessory_in_a:
        a_accessory_content = extract_section_content(a_body, "Electric Scooter Accessories")
        print(f"\nArticle A accessory content preview ({len(a_accessory_content)} chars):")
        print(f"  {a_accessory_content[:400]}...")

        # Check if B covers accessories
        accessory_keywords = ["helmet", "knee pad", "elbow pad", "protective gear", "accessory",
                             "bag", "cover", "carry case", "light", "bell"]
        b_text_lower = strip_html(b_body).lower()
        accessory_coverage_in_b = [kw for kw in accessory_keywords if kw in b_text_lower]
        print(f"\nArticle B accessory-related keywords found: {accessory_coverage_in_b}")

        # Check B's H2s for accessories
        b_has_accessory_section = any(
            "accessor" in h.lower() or "helmet" in h.lower() or "protect" in h.lower()
            for h in b_h2s
        )
        print(f"Article B has an accessories section: {b_has_accessory_section}")
        print(f"Article B H2 sections: {b_h2s}")

        # Is A's accessory content unique?
        # Check if any specific accessory items from A are in B
        accessory_items_a = re.findall(r'<li[^>]*>(.*?)</li>', a_accessory_content, re.DOTALL)
        unique_accessory_items = []
        for item in accessory_items_a:
            item_text = strip_html(item).lower()
            if item_text and item_text not in b_text_lower:
                unique_accessory_items.append(strip_html(item))
        print(f"\nUnique accessory items in A not in B: {unique_accessory_items[:5]}")

    # --- Redirect plan ---
    print("\n" + "=" * 60)
    print("REDIRECT PLAN")
    print("=" * 60)
    a_handle = a_data["handle"]
    b_handle = b_data["handle"]
    a_blog_id = a_data["blog_id"]
    b_blog_id = b_data["blog_id"]
    print(f"Article A handle: {a_handle}")
    print(f"Article B handle: {b_handle}")
    print(f"Article A blog_id: {a_blog_id}")
    print(f"Article B blog_id: {b_blog_id}")
    print(f"Same blog: {a_blog_id == b_blog_id}")
    # Canonical path format in Shopify
    a_path = f"/blogs/{a_blog_id}/articles/{a_handle}"
    b_path = f"/blogs/{b_blog_id}/articles/{b_handle}"
    print(f"\nSource redirect path: {a_path}")
    print(f"Target redirect path: {b_path}")

    # --- Merge decision ---
    print("\n" + "=" * 60)
    print("MERGE DECISION")
    print("=" * 60)
    if accessory_in_a and unique_accessory_items:
        merge_needed = True
        proposed_merge_section = f"""<!-- Section merged from Article A (ID: {ARTICLE_A_ID}) — merged {datetime.now().strftime('%Y-%m-%d')} -->
<h2>Electric Scooter Accessories</h2>
<p>These accessories can enhance your riding experience and safety:</p>
<ul>
{chr(10).join('<li>' + item + '</li>' for item in unique_accessory_items[:6])}
</ul>
<p>Browse the full range at <a href="https://hcsgadgets.com/collections/sports-outdoor">HCS Gadgets sports and outdoor range</a>.</p>"""
        print("MERGE NEEDED: YES")
        print(f"\nProposed merge section ({len(proposed_merge_section)} chars):")
        print(proposed_merge_section[:600] + "...")
    else:
        merge_needed = False
        proposed_merge_section = None
        print("MERGE NEEDED: NO — Article B already covers accessories adequately")
        print("Article A accessory content is either not unique or too thin to merge")

    # --- Article A disposition ---
    print("\n" + "=" * 60)
    print("ARTICLE A DISPOSITION")
    print("=" * 60)
    print("Recommended approach (safer than delete):")
    print("1. Backup Article A JSON before any changes")
    print("2. Create 301 redirect: Article A handle → Article B handle")
    print("3. Verify redirect works")
    print("4. Unpublish Article A (don't delete — redirects need live source)")
    print("5. Delete Article A only after redirect is verified working")
    print("")
    print("Why unpublish instead of delete immediately:")
    print("- Shopify redirects require the source URL to return 404 or redirect response")
    print("- If you delete Article A immediately, the URL returns 404 directly")
    print("- A 404 means Google loses all link equity from the old URL")
    print("- A 301 redirect preserves ~90% of link equity to the canonical article")
    print("- Once redirect is confirmed working, you can safely delete Article A")

    # --- Save structured data ---
    result = {
        "phase": "Content Phase 0.5A",
        "status": "DRYRUN_COMPLETE",
        "timestamp": ts,
        "article_a": {
            "id": str(ARTICLE_A_ID),
            "title": a_data["title"],
            "handle": a_data["handle"],
            "blog_id": a_data["blog_id"],
            "published_at": a_data.get("published_at"),
            "word_count": a_wc,
            "h2_sections": a_h2s,
            "h3_sections": a_h3s,
        },
        "article_b": {
            "id": str(ARTICLE_B_ID),
            "title": b_data["title"],
            "handle": b_data["handle"],
            "blog_id": b_data["blog_id"],
            "published_at": b_data.get("published_at"),
            "word_count": b_wc,
            "h2_sections": b_h2s,
            "h3_sections": b_h3s,
        },
        "same_blog": a_blog_id == b_blog_id,
        "merge_needed": merge_needed,
        "proposed_merge_section": proposed_merge_section,
        "redirect_plan": {
            "source_path": a_path,
            "source_handle": a_handle,
            "target_path": b_path,
            "target_handle": b_handle,
            "recommended_action": "301 redirect A → B, then unpublish A (do not delete immediately)",
            "reason_unpublish_not_delete": "Redirects need live source URL; deleting immediately causes 404 and loses link equity"
        },
        "article_a_disposition": "unpublish_after_redirect_verification",
        "shopify_touched": False,
        "queue_touched": False,
    }

    out = "/tmp/hcs_phase0_5a_dryrun_data.json"
    with open(out, "w") as f:
        json.dump(result, f, indent=2, default=str)
    print(f"\n✅ Data saved to {out}")
    return result

if __name__ == "__main__":
    main()
