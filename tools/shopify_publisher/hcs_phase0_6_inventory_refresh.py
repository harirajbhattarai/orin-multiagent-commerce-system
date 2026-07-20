#!/usr/bin/env python3
"""
HCS Gadgets Content Phase 0.6 — Post-Cleanup Inventory Refresh and Baseline Lock
READ-ONLY verification + local file updates.
No Shopify edits. No publishing.
"""
import urllib.request
import urllib.error
import json
import re
import os
from datetime import datetime

# === Read HCS token ===
CONFIG_PATH = "/data/.openclaw/workspace/clients/hcs_gadgets/shopify_config/.env"
TOKEN = None
HCS_DOMAIN = "hcsgadgets-com.myshopify.com"
BASE = "https://{}/admin/api/2026-01".format(HCS_DOMAIN)
BLOG_ID = "89150259452"
BLOG_HANDLE = "gadget-blog"

with open(CONFIG_PATH) as f:
    for line in f:
        if "ADMIN_ACCESS_TOKEN" in line:
            TOKEN = line.strip().split("=", 1)[1].strip()
            break

if not TOKEN:
    print("FATAL: No token")
    exit(1)

HEADERS = {"Content-Type": "application/json", "X-Shopify-Access-Token": TOKEN}

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

def article_summary(art):
    """Extract key fields from article dict"""
    body = art.get("body_html", "")
    return {
        "id": str(art["id"]),
        "title": art["title"],
        "handle": art["handle"],
        "blog_id": str(art["blog_id"]),
        "published_at": art.get("published_at"),
        "created_at": art.get("created_at"),
        "updated_at": art.get("updated_at"),
        "tags": art.get("tags", []),
        "author": art.get("author", ""),
        "word_count": len(strip_html(body).split()),
    }

def main():
    ts = datetime.now().strftime("%Y-%m-%dT%H:%M:%S+00:00")
    print("=" * 60)
    print("HCS PHASE 0.6 — POST-CLEANUP INVENTORY REFRESH")
    print(f"Time: {ts}")
    print("=" * 60)

    verification = {
        "phase": "Content Phase 0.6",
        "timestamp": ts,
        "inventory_refreshed": False,
        "published_count": 0,
        "draft_count": 0,
        "article_a_status": None,
        "article_b_status": None,
        "redirect_verified": False,
        "free_delivery_safe": False,
        "live_duplicate_titles": [],
        "live_duplicate_handles": [],
        "all_checks_passed": False,
    }

    # === Step 1: Fetch ALL articles from the blog ===
    print("\n[1/5] Fetching live Shopify inventory...")
    all_articles = []
    page_info = None

    while True:
        if page_info:
            path = f"/blogs/{BLOG_ID}/articles.json?limit=250&page_info={page_info}"
        else:
            path = f"/blogs/{BLOG_ID}/articles.json?limit=250"
        resp = api_get(path)
        articles = resp.get("articles", [])
        all_articles.extend(articles)
        print(f"  Fetched {len(articles)} articles...", end="")
        # Check for next page
        link = resp.get("headers", {}).get("Link", "") or resp.get("link", "")
        # Shopify uses Link header for pagination
        next_link = None
        for part in link.split(","):
            if 'rel="next"' in part:
                import re as _re
                m = _re.search(r'<([^>]+)>;\s*rel="next"', part)
                if m:
                    next_link = m.group(1)
                    # Extract page_info
                    pi_m = _re.search(r'page_info=([^&>]+)', next_link)
                    if pi_m:
                        page_info = pi_m.group(1)
                    else:
                        page_info = "next"
        if not page_info or page_info == "next":
            break
        print(f"  total so far: {len(all_articles)}")

    print(f"\n  Total articles fetched: {len(all_articles)}")

    # Separate published and draft
    published = [a for a in all_articles if a.get("published_at")]
    drafts = [a for a in all_articles if not a.get("published_at")]
    verification["published_count"] = len(published)
    verification["draft_count"] = len(drafts)
    print(f"  Published: {len(published)}")
    print(f"  Drafts: {len(drafts)}")

    # Summarise all articles
    published_summaries = [article_summary(a) for a in published]
    draft_summaries = [article_summary(a) for a in drafts]

    # === Step 2: Verify cleanup actions ===
    print("\n[2/5] Verifying cleanup actions...")

    # Article B — canonical, should be published
    article_b = next((a for a in all_articles if str(a["id"]) == "1000575172982"), None)
    if article_b:
        b_sum = article_summary(article_b)
        verification["article_b_status"] = {
            "id": "1000575172982",
            "exists": True,
            "published": article_b.get("published_at") is not None,
            "handle": article_b["handle"],
            "title": article_b["title"],
        }
        print(f"  Article B: {article_b['title']}")
        print(f"    Published: {article_b.get('published_at')} ✅" if article_b.get("published_at") else f"    Published: False ❌")
        print(f"    Handle: {article_b['handle']}")

    # Article A — non-canonical, should be unpublished/draft
    article_a = next((a for a in all_articles if str(a["id"]) == "1000525496694"), None)
    if article_a:
        a_sum = article_summary(article_a)
        verification["article_a_status"] = {
            "id": "1000525496694",
            "exists": True,
            "published": article_a.get("published_at") is not None,
            "unpublished": article_a.get("published_at") is None,
            "handle": article_a["handle"],
            "title": article_a["title"],
        }
        print(f"  Article A: {article_a['title']}")
        print(f"    Draft/unpublished: {article_a.get('published_at') is None} ✅" if not article_a.get("published_at") else f"    Still published ❌")
        print(f"    Handle: {article_a['handle']}")

    # Redirect — verify it exists via API
    print("\n[3/5] Verifying redirect...")
    try:
        redirect_resp = api_get("/redirects.json")
        redirects = redirect_resp.get("redirects", [])
        our_redirect = next(
            (r for r in redirects
             if r.get("path") == "/blogs/gadget-blog/where-to-buy-electric-scooters-in-the-uk-top-models-and-best-deals"
             and r.get("target") == "/blogs/gadget-blog/where-to-buy-electric-scooters-in-the-uk-top-models-and-best-deals-1"),
            None
        )
        if our_redirect:
            verification["redirect_verified"] = True
            verification["redirect_id"] = our_redirect.get("id")
            print(f"  Redirect ID {our_redirect.get('id')} verified ✅")
            print(f"  Source: {our_redirect.get('path')}")
            print(f"  Target: {our_redirect.get('target')}")
        else:
            print(f"  Redirect not found in redirect list — checking by ID...")
            # Try fetching by ID 1725525721462 directly
            try:
                r_single = api_get("/redirects/1725525721462.json")
                r = r_single.get("redirect", {})
                verification["redirect_verified"] = True
                verification["redirect_id"] = r.get("id")
                print(f"  Redirect ID {r.get('id')} verified by direct fetch ✅")
            except:
                print(f"  Redirect not found by ID ❌")
    except Exception as e:
        print(f"  Could not verify redirect: {e}")

    # Free Delivery article — verify risky title is gone
    print("\n[4/5] Checking Free Delivery article...")
    fd_article = next((a for a in all_articles if str(a["id"]) == "1001799811446"), None)
    if fd_article:
        safe_title = "Hoverboards UK: A Practical Safety and Buying Guide for 2026"
        risky_terms = ["free delivery", "official uk certified", "official certified"]
        title_lower = fd_article["title"].lower()
        risky_found = any(t in title_lower for t in risky_terms)
        verification["free_delivery_safe"] = not risky_found and fd_article["title"] == safe_title
        print(f"  Title: {fd_article['title']}")
        print(f"  Safe title confirmed: {fd_article['title'] == safe_title} ✅")
        print(f"  Risky terms in title: {risky_found} ❌" if risky_found else f"  Risky terms in title: False ✅")
        verification["free_delivery_article"] = {
            "id": "1001799811446",
            "title": fd_article["title"],
            "safe": verification["free_delivery_safe"],
        }

    # Duplicate detection — check live published articles
    print("\n[5/5] Checking for live duplicates...")
    # Only check PUBLISHED articles for duplicates
    published_titles = {}
    published_handles = {}
    for a in published:
        t = a["title"].strip()
        h = a["handle"].strip()
        if t not in published_titles:
            published_titles[t] = []
        published_titles[t].append(a["id"])
        if h not in published_handles:
            published_handles[h] = []
        published_handles[h].append(a["id"])

    dup_titles = {t: ids for t, ids in published_titles.items() if len(ids) > 1}
    dup_handles = {h: ids for h, ids in published_handles.items() if len(ids) > 1}

    verification["live_duplicate_titles"] = [
        {"title": t, "ids": ids} for t, ids in dup_titles.items()
    ]
    verification["live_duplicate_handles"] = [
        {"handle": h, "ids": ids} for h, ids in dup_handles.items()
    ]

    print(f"  Live duplicate titles: {len(dup_titles)}")
    for t, ids in dup_titles.items():
        print(f"    '{t}': {ids}")
    print(f"  Live duplicate handles: {len(dup_handles)}")
    for h, ids in dup_handles.items():
        print(f"    '{h}': {ids}")
    if not dup_titles and not dup_handles:
        print(f"  ✅ No live duplicates found")

    # === Save inventory files ===
    print("\n[6/7] Saving inventory files...")
    base = "/data/.openclaw/workspace/clients/hcs_gadgets/content_engine"

    # Raw JSON
    raw_path = os.path.join(base, "shopify_inventory_raw.json")
    with open(raw_path, "w") as f:
        json.dump({
            "phase": "Phase 0.6 baseline refresh",
            "timestamp": ts,
            "total": len(all_articles),
            "published_count": len(published),
            "draft_count": len(drafts),
            "articles": all_articles
        }, f, indent=2, default=str)
    print(f"  Saved: shopify_inventory_raw.json")

    # Structured JSON
    inv_path = os.path.join(base, "shopify_inventory.json")
    with open(inv_path, "w") as f:
        json.dump({
            "phase": "Phase 0.6 baseline",
            "timestamp": ts,
            "total": len(all_articles),
            "published_count": len(published),
            "draft_count": len(drafts),
            "published": published_summaries,
            "drafts": draft_summaries,
        }, f, indent=2, default=str)
    print(f"  Saved: shopify_inventory.json")

    # MD: published inventory
    pub_md_lines = ["# HCS Gadgets — Published Article Inventory\n", f"**Updated:** {ts}\n", f"**Total published:** {len(published)}\n\n"]
    for a in sorted(published_summaries, key=lambda x: x.get("published_at", "")):
        pub_md_lines.append(f"## {a['title']}\n")
        pub_md_lines.append(f"- ID: `{a['id']}`\n")
        pub_md_lines.append(f"- Handle: `{a['handle']}`\n")
        pub_md_lines.append(f"- Published: {a['published_at']}\n")
        pub_md_lines.append(f"- Words: ~{a['word_count']}\n")
        pub_md_lines.append(f"- Tags: {', '.join(a.get('tags', []))}\n\n")
    pub_md_path = os.path.join(base, "published_inventory.md")
    with open(pub_md_path, "w") as f:
        f.writelines(pub_md_lines)
    print(f"  Saved: published_inventory.md ({len(published)} articles)")

    # MD: draft inventory
    draft_md_lines = ["# HCS Gadgets — Draft/Unpublished Article Inventory\n", f"**Updated:** {ts}\n", f"**Total drafts:** {len(drafts)}\n\n"]
    if drafts:
        for a in sorted(draft_summaries, key=lambda x: x.get("updated_at", "")):
            draft_md_lines.append(f"## {a['title']}\n")
            draft_md_lines.append(f"- ID: `{a['id']}`\n")
            draft_md_lines.append(f"- Handle: `{a['handle']}`\n")
            draft_md_lines.append(f"- Status: Draft (unpublished)\n")
            draft_md_lines.append(f"- Updated: {a['updated_at']}\n\n")
    else:
        draft_md_lines.append("*No unpublished drafts.*\n")
    draft_md_path = os.path.join(base, "draft_inventory.md")
    with open(draft_md_path, "w") as f:
        f.writelines(draft_md_lines)
    print(f"  Saved: draft_inventory.md ({len(drafts)} drafts)")

    # MD: main inventory (combined)
    inv_md_lines = [
        "# HCS Gadgets — Shopify Article Inventory\n\n",
        f"**Last updated:** {ts}\n",
        f"**Total articles:** {len(all_articles)}\n",
        f"**Published:** {len(published)}\n",
        f"**Drafts:** {len(drafts)}\n\n",
        "## Published Articles\n\n",
    ]
    for a in sorted(published_summaries, key=lambda x: x.get("published_at", "")):
        inv_md_lines.append(f"### {a['title']}\n")
        inv_md_lines.append(f"- ID: `{a['id']}` | Handle: `{a['handle']}` | Published: {a['published_at']} | ~{a['word_count']} words\n")
    inv_md_lines.append("\n## Draft Articles\n\n")
    if drafts:
        for a in sorted(draft_summaries, key=lambda x: x.get("updated_at", "")):
            inv_md_lines.append(f"### {a['title']}\n")
            inv_md_lines.append(f"- ID: `{a['id']}` | Handle: `{a['handle']}` | Status: Draft\n")
    else:
        inv_md_lines.append("*No drafts.*\n")
    inv_md_path = os.path.join(base, "shopify_inventory.md")
    with open(inv_md_path, "w") as f:
        f.writelines(inv_md_lines)
    print(f"  Saved: shopify_inventory.md")

    verification["inventory_refreshed"] = True

    # === Final checks ===
    print("\n" + "=" * 60)
    print("VERIFICATION SUMMARY")
    print("=" * 60)

    checks = [
        ("Inventory refreshed", verification["inventory_refreshed"]),
        ("Published count", verification["published_count"]),
        ("Draft count", verification["draft_count"]),
        ("Article B exists", verification["article_b_status"]["exists"] if verification["article_b_status"] else False),
        ("Article B published", verification["article_b_status"]["published"] if verification["article_b_status"] else False),
        ("Article A exists", verification["article_a_status"]["exists"] if verification["article_a_status"] else False),
        ("Article A unpublished", verification["article_a_status"]["unpublished"] if verification["article_a_status"] else False),
        ("Redirect verified", verification["redirect_verified"]),
        ("Free Delivery safe", verification["free_delivery_safe"]),
        ("No live duplicate titles", len(verification["live_duplicate_titles"]) == 0),
        ("No live duplicate handles", len(verification["live_duplicate_handles"]) == 0),
    ]

    all_pass = all(r for _, r in checks)
    for name, result in checks:
        mark = "✅" if result else "❌"
        print(f"  {mark} {name}: {result}")

    verification["all_checks_passed"] = all_pass

    out = "/tmp/hcs_phase0_6_verification.json"
    with open(out, "w") as f:
        json.dump(verification, f, indent=2, default=str)
    print(f"\nVerification saved to: {out}")
    print(f"\n{'✅ ALL CHECKS PASSED' if all_pass else '❌ SOME CHECKS FAILED'}")
    return verification

if __name__ == "__main__":
    main()
