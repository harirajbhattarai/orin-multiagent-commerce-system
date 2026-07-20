#!/usr/bin/env python3
import os
import json
import re
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime

BASE_DIR = Path("/data/.openclaw/workspace")
if not BASE_DIR.exists():
    BASE_DIR = Path("/root/.openclaw/workspace")

ENV_PATH = BASE_DIR / "tools" / "shopify_publisher" / ".env"
CONTENT_DIR = BASE_DIR / "clients" / "hoverboard_store" / "content_engine"
LOG_PATH = CONTENT_DIR / "published_log.md"

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
        raise SystemExit(f"Shopify API error {e.code} for {url}\n{body}")
    except urllib.error.URLError as e:
        raise SystemExit(f"Connection error for {url}\n{e}")

def extract_meta(html):
    meta = {
        "seo_title": "",
        "meta_title": "",
        "meta_description": "",
        "url_slug": "",
    }

    comment = re.search(r"<!--(.*?)-->", html, flags=re.S)
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

    h1 = re.search(r"<h1[^>]*>(.*?)</h1>", html, flags=re.S | re.I)
    if h1 and not meta["seo_title"]:
        title = re.sub(r"<[^>]+>", "", h1.group(1)).strip()
        meta["seo_title"] = title

    return meta

def get_blog_id():
    data = shopify_request("GET", "/blogs.json?limit=250")
    blogs = data.get("blogs", [])

    if not blogs:
        raise SystemExit("No Shopify blogs found.")

    for blog in blogs:
        if blog.get("title", "").lower() == "journal insights":
            return blog["id"], blog.get("title"), blog.get("handle")

    blog = blogs[0]
    return blog["id"], blog.get("title"), blog.get("handle")

def append_log(title, handle, article_id, status):
    if not LOG_PATH.exists():
        LOG_PATH.write_text(
            "# Hoverboard Store — Published Log\n\n"
            "| Date | Title | URL Slug | Topic | Status | Shopify Article ID | Notes |\n"
            "|---|---|---|---|---|---|---|\n"
        )

    line = f"| {datetime.utcnow().date()} | {title} | {handle} | test/manual | {status} | {article_id} | Created by ORIN draft publisher |\n"
    with LOG_PATH.open("a") as f:
        f.write(line)

def main():
    load_env(ENV_PATH)

    if len(os.sys.argv) < 2:
        raise SystemExit("Usage: python3 publish_blog_draft.py path/to/article.html")

    article_path = Path(os.sys.argv[1])
    if not article_path.exists():
        raise SystemExit(f"Article file not found: {article_path}")

    html = article_path.read_text()
    meta = extract_meta(html)

    title = meta["seo_title"] or meta["meta_title"]
    if not title:
        raise SystemExit("No title found. Add SEO Title or H1.")

    handle = meta["url_slug"]
    if not handle:
        handle = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")

    blog_id, blog_title, blog_handle = get_blog_id()

    payload = {
        "article": {
            "title": title,
            "author": "Hoverboard Store",
            "body_html": html,
            "handle": handle,
            "published": False,
            "tags": "ORIN Draft, SEO Blog"
        }
    }

    result = shopify_request("POST", f"/blogs/{blog_id}/articles.json", payload)
    article = result.get("article", {})

    append_log(
        article.get("title", title),
        article.get("handle", handle),
        article.get("id", ""),
        "draft"
    )

    print("Draft article created successfully.")
    print(f"Blog: {blog_title} ({blog_handle})")
    print(f"Title: {article.get('title')}")
    print(f"Handle: {article.get('handle')}")
    print(f"Article ID: {article.get('id')}")
    print("Status: draft")

if __name__ == "__main__":
    main()
