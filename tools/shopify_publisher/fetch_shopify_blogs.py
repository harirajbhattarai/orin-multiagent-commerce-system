#!/usr/bin/env python3
import os
import json
import re
import html
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path

BASE_DIR = Path("/data/.openclaw/workspace")
if not BASE_DIR.exists():
    BASE_DIR = Path("/root/.openclaw/workspace")

ENV_PATH = BASE_DIR / "tools" / "shopify_publisher" / ".env"
OUT_DIR = BASE_DIR / "clients" / "hoverboard_store" / "content_engine"

def load_env(path):
    if not path.exists():
        raise SystemExit(f"Missing .env file: {path}\nCreate it from .env.example first.")
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ[key.strip()] = value.strip().strip('"').strip("'")

def shopify_get(path):
    store = os.environ["SHOPIFY_STORE_DOMAIN"]
    token = os.environ["SHOPIFY_ADMIN_TOKEN"]
    version = os.environ.get("SHOPIFY_API_VERSION", "2026-01")
    url = f"https://{store}/admin/api/{version}{path}"
    req = urllib.request.Request(
        url,
        headers={
            "X-Shopify-Access-Token": token,
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read().decode("utf-8")
            return json.loads(data), dict(resp.headers)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise SystemExit(f"Shopify API error {e.code} for {url}\n{body}")
    except urllib.error.URLError as e:
        raise SystemExit(f"Connection error for {url}\n{e}")

def strip_html(raw_html):
    if not raw_html:
        return ""
    text = re.sub(r"<script.*?</script>", " ", raw_html, flags=re.S | re.I)
    text = re.sub(r"<style.*?</style>", " ", text, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text

def word_count(text):
    return len(re.findall(r"\b[\w'-]+\b", text))

def extract_h1(body_html):
    if not body_html:
        return ""
    m = re.search(r"<h1[^>]*>(.*?)</h1>", body_html, flags=re.S | re.I)
    return strip_html(m.group(1)) if m else ""

def extract_h2s(body_html):
    if not body_html:
        return []
    matches = re.findall(r"<h2[^>]*>(.*?)</h2>", body_html, flags=re.S | re.I)
    return [strip_html(x) for x in matches]

def extract_faq_questions(body_html):
    if not body_html:
        return []
    # Works with your hs-faq-q class and normal h3 FAQ headings
    matches = re.findall(r'<h3[^>]*class=["\'][^"\']*hs-faq-q[^"\']*["\'][^>]*>(.*?)</h3>', body_html, flags=re.S | re.I)
    return [strip_html(x) for x in matches]

def fetch_all_articles(blog_id):
    articles = []
    page_info = None

    while True:
        if page_info:
            path = f"/blogs/{blog_id}/articles.json?limit=250&page_info={page_info}"
        else:
            path = f"/blogs/{blog_id}/articles.json?limit=250"

        data, headers = shopify_get(path)
        articles.extend(data.get("articles", []))

        link = headers.get("Link", "")
        next_match = re.search(r'<[^>]*[?&]page_info=([^&>]+)[^>]*>;\s*rel="next"', link)
        if not next_match:
            break
        page_info = next_match.group(1)

    return articles

def make_markdown_inventory(items):
    lines = []
    lines.append("# Hoverboard Store — Shopify Blog Content Inventory")
    lines.append("")
    lines.append(f"Generated: {datetime.utcnow().isoformat()}Z")
    lines.append("")
    lines.append("| Status | Blog | Title | Slug | Words | H1 | Updated |")
    lines.append("|---|---|---|---|---:|---|---|")
    for item in items:
        status = "published" if item.get("published_at") else "draft"
        lines.append(
            f"| {status} | {item.get('blog_title','')} | {item.get('title','').replace('|','/')} | "
            f"{item.get('handle','')} | {item.get('word_count',0)} | "
            f"{item.get('h1','').replace('|','/')} | {item.get('updated_at','')} |"
        )
    lines.append("")
    return "\n".join(lines)

def main():
    load_env(ENV_PATH)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    blogs_data, _ = shopify_get("/blogs.json?limit=250")
    blogs = blogs_data.get("blogs", [])

    if not blogs:
        raise SystemExit("No Shopify blogs found.")

    inventory = []
    raw = {"fetched_at": datetime.utcnow().isoformat() + "Z", "blogs": []}

    for blog in blogs:
        blog_id = blog["id"]
        blog_title = blog.get("title", "")
        handle = blog.get("handle", "")
        articles = fetch_all_articles(blog_id)

        raw_blog = {
            "id": blog_id,
            "title": blog_title,
            "handle": handle,
            "articles": articles,
        }
        raw["blogs"].append(raw_blog)

        for article in articles:
            body_html = article.get("body_html") or ""
            clean_text = strip_html(body_html)
            inventory.append({
                "blog_id": blog_id,
                "blog_title": blog_title,
                "blog_handle": handle,
                "article_id": article.get("id"),
                "title": article.get("title", ""),
                "handle": article.get("handle", ""),
                "tags": article.get("tags", ""),
                "author": article.get("author", ""),
                "published_at": article.get("published_at"),
                "created_at": article.get("created_at"),
                "updated_at": article.get("updated_at"),
                "summary_html": article.get("summary_html", ""),
                "body_html": body_html,
                "clean_text": clean_text,
                "word_count": word_count(clean_text),
                "h1": extract_h1(body_html),
                "h2s": extract_h2s(body_html),
                "faq_questions": extract_faq_questions(body_html),
            })

    inventory_sorted = sorted(inventory, key=lambda x: (x.get("published_at") or "", x.get("updated_at") or ""), reverse=True)

    (OUT_DIR / "shopify_inventory_raw.json").write_text(json.dumps(raw, indent=2, ensure_ascii=False))
    (OUT_DIR / "shopify_inventory.json").write_text(json.dumps(inventory_sorted, indent=2, ensure_ascii=False))
    (OUT_DIR / "shopify_inventory.md").write_text(make_markdown_inventory(inventory_sorted))

    published = [x for x in inventory_sorted if x.get("published_at")]
    drafts = [x for x in inventory_sorted if not x.get("published_at")]

    (OUT_DIR / "published_inventory.md").write_text(make_markdown_inventory(published))
    (OUT_DIR / "draft_inventory.md").write_text(make_markdown_inventory(drafts))

    print("Shopify blog audit complete.")
    print(f"Blogs found: {len(blogs)}")
    print(f"Articles found: {len(inventory_sorted)}")
    print(f"Published: {len(published)}")
    print(f"Drafts: {len(drafts)}")
    print(f"Saved to: {OUT_DIR}")

if __name__ == "__main__":
    main()
