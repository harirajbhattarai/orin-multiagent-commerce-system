#!/usr/bin/env python3
from pathlib import Path
from html import unescape
import json
import re
import sys
import urllib.request
import urllib.error

ROOT = Path("/data/.openclaw/workspace")
ENV_PATH = ROOT / "clients/hcs_gadgets/shopify_config/.env"
STATUS_PATH = ROOT / "clients/hcs_gadgets/content_engine/latest_shopify_draft_status.json"

BLOCKED_TERMS = [
    "swiss army",
    "knife",
    "weapon",
    "alcohol",
    "nicotine",
    "vape",
    "supplement",
    "prescription",
    "gambling",
    "adult product",
]

def load_env(path):
    data = {}
    if not path.exists():
        raise SystemExit(f"Missing env file: {path}")
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        data[k.strip()] = v.strip().strip('"').strip("'")
    return data

def strip_tags(value):
    value = re.sub(r"<[^>]+>", "", value)
    return unescape(value).strip()

def shopify_request(method, url, token, payload=None):
    body = None
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "X-Shopify-Access-Token": token,
            "Content-Type": "application/json",
        },
        method=method,
    )

    try:
        with urllib.request.urlopen(req, timeout=45) as res:
            return json.loads(res.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        print(f"Shopify API error: {e.code}")
        print(e.read().decode("utf-8")[:1500])
        raise SystemExit(1)

def existing_article_check(store, version, token, blog_id, title, handle):
    url = f"https://{store}/admin/api/{version}/blogs/{blog_id}/articles.json?limit=250"
    data = shopify_request("GET", url, token)
    articles = data.get("articles", [])

    title_l = title.strip().lower()
    handle_l = handle.strip().lower()

    for article in articles:
        a_title = str(article.get("title", "")).strip().lower()
        a_handle = str(article.get("handle", "")).strip().lower()
        if a_title == title_l or a_handle == handle_l:
            status = "published" if article.get("published_at") else "draft"
            raise SystemExit(
                f"BLOCKED: article already exists in Shopify. "
                f"Title={article.get('title')} Handle={article.get('handle')} Status={status}"
            )

def main():
    if len(sys.argv) < 2:
        raise SystemExit("Usage: python3 tools/shopify_publisher/hcs_publish_blog_draft.py path/to/article.html")

    article_path = ROOT / sys.argv[1] if not Path(sys.argv[1]).is_absolute() else Path(sys.argv[1])

    if not article_path.exists():
        raise SystemExit(f"Article file not found: {article_path}")

    html = article_path.read_text()

    if "hcs-article" not in html:
        raise SystemExit("BLOCKED: article does not contain hcs-article wrapper.")

    low = html.lower()
    found = [term for term in BLOCKED_TERMS if term in low]
    if found:
        raise SystemExit(f"BLOCKED: risky/off-scope terms found: {', '.join(found)}")

    h1 = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.S | re.I)
    if not h1:
        raise SystemExit("BLOCKED: no H1 found.")

    title = strip_tags(h1.group(1))
    handle = article_path.stem

    env = load_env(ENV_PATH)

    store = (
        env.get("SHOPIFY_STORE_DOMAIN")
        or env.get("SHOPIFY_SHOP_DOMAIN")
        or env.get("SHOPIFY_STORE")
        or ""
    ).replace("https://", "").replace("http://", "").strip("/")

    token = env.get("SHOPIFY_ADMIN_ACCESS_TOKEN") or env.get("SHOPIFY_ADMIN_TOKEN") or ""
    version = env.get("SHOPIFY_API_VERSION") or "2026-01"
    blog_id = env.get("SHOPIFY_BLOG_ID", "").strip()

    if not store or not token:
        raise SystemExit("Missing SHOPIFY_STORE_DOMAIN or SHOPIFY_ADMIN_ACCESS_TOKEN in HCS .env")

    if not blog_id:
        raise SystemExit("Missing SHOPIFY_BLOG_ID in HCS .env")

    existing_article_check(store, version, token, blog_id, title, handle)

    payload = {
        "article": {
            "title": title,
            "handle": handle,
            "body_html": html,
            "published": False
        }
    }

    url = f"https://{store}/admin/api/{version}/blogs/{blog_id}/articles.json"
    data = shopify_request("POST", url, token, payload)
    article = data.get("article", {})

    status = {
        "client": "hcs_gadgets",
        "status": "draft_created",
        "title": article.get("title"),
        "handle": article.get("handle"),
        "article_id": article.get("id"),
        "blog_id": blog_id,
        "published": article.get("published"),
        "source_file": str(article_path),
    }

    STATUS_PATH.write_text(json.dumps(status, indent=2))

    print("✅ HCS Shopify draft created successfully.")
    print(f'Title: {article.get("title")}')
    print(f'Handle: {article.get("handle")}')
    print(f'Article ID: {article.get("id")}')
    print("Status: draft / unpublished")

if __name__ == "__main__":
    main()
