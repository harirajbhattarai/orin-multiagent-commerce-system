#!/usr/bin/env python3
import os
import json
import re
import urllib.request
import urllib.error
from pathlib import Path

BASE_DIR = Path("/data/.openclaw/workspace")
if not BASE_DIR.exists():
    BASE_DIR = Path("/root/.openclaw/workspace")

ENV_PATH = BASE_DIR / "tools" / "shopify_publisher" / ".env"

def load_env(path):
    if not path.exists():
        raise SystemExit(f"Missing .env file: {path}")
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ[key.strip()] = value.strip().strip('"').strip("'")

def shopify_request(method, path, payload=None):
    store = os.environ["SHOPIFY_STORE_DOMAIN"]
    token = os.environ["SHOPIFY_ADMIN_TOKEN"]
    version = os.environ.get("SHOPIFY_API_VERSION", "2025-10")
    url = f"https://{store}/admin/api/{version}{path}"

    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "X-Shopify-Access-Token": token,
            "Content-Type": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise SystemExit(f"Shopify API error {e.code}\n{body}")

def extract_meta(html):
    meta = {"seo_title": "", "meta_title": "", "url_slug": ""}

    comment = re.search(r"<!--(.*?)-->", html, flags=re.S)
    if comment:
        block = comment.group(1)
        for key, pattern in {
            "seo_title": r"SEO Title:\s*(.+)",
            "meta_title": r"Meta Title:\s*(.+)",
            "url_slug": r"URL slug:\s*(.+)",
        }.items():
            m = re.search(pattern, block)
            if m:
                meta[key] = m.group(1).strip()

    h1 = re.search(r"<h1[^>]*>(.*?)</h1>", html, flags=re.S | re.I)
    if h1 and not meta["seo_title"]:
        meta["seo_title"] = re.sub(r"<[^>]+>", "", h1.group(1)).strip()

    return meta

def get_blog_id():
    data = shopify_request("GET", "/blogs.json?limit=250")
    for blog in data.get("blogs", []):
        if blog.get("title", "").lower() == "journal insights":
            return blog["id"], blog.get("title"), blog.get("handle")
    raise SystemExit("Journal Insights blog not found.")

def main():
    load_env(ENV_PATH)

    if len(os.sys.argv) < 3:
        raise SystemExit("Usage: python3 update_blog_article_preserve_status.py ARTICLE_ID path/to/article.html")

    article_id = os.sys.argv[1]
    article_path = Path(os.sys.argv[2])

    if not article_path.exists():
        raise SystemExit(f"Article file not found: {article_path}")

    html = article_path.read_text()
    meta = extract_meta(html)

    title = meta["seo_title"] or meta["meta_title"]
    if not title:
        raise SystemExit("No title found. Add SEO Title or H1.")

    handle = meta["url_slug"] or re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")

    blog_id, blog_title, blog_handle = get_blog_id()

    payload = {
        "article": {
            "id": int(article_id),
            "title": title,
            "author": "Hoverboard Store",
            "body_html": html,
            "handle": handle,
            "tags": "ORIN Draft, SEO Blog"
        }
    }

    result = shopify_request("PUT", f"/blogs/{blog_id}/articles/{article_id}.json", payload)
    article = result.get("article", {})

    print("Article updated successfully without changing publish status.")
    print(f"Blog: {blog_title} ({blog_handle})")
    print(f"Title: {article.get('title')}")
    print(f"Handle: {article.get('handle')}")
    print(f"Article ID: {article.get('id')}")
    print(f"Published at: {article.get('published_at')}")

if __name__ == "__main__":
    main()
