#!/usr/bin/env python3
import sys
from pathlib import Path
from html import unescape
import json
import re
import urllib.request
import urllib.error

# Allow import of orin/ shared modules
sys.path.insert(0, str(Path(__file__).parent / "orin"))
from hcs_html_contract_validator import check_article_product_data_policy

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
    body = json.dumps(payload).encode("utf-8") if payload else None
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

def main():
    if len(sys.argv) < 2:
        raise SystemExit("Usage: hcs_update_blog_draft.py article.html [article_id]")

    article_path = Path(sys.argv[1])
    if not article_path.is_absolute():
        article_path = ROOT / article_path

    if not article_path.exists():
        raise SystemExit(f"Article file not found: {article_path}")

    html = article_path.read_text()

    required = [
        "hcs-article",
        "hcs-hero",
        "hcs-top-grid",
        "hcs-checklist",
        "hcs-cta",
        "hcs-faq",
        "FAQPage",
    ]

    missing = [x for x in required if x not in html]
    if missing:
        raise SystemExit(f"BLOCKED: missing required HCS structure: {', '.join(missing)}")

    low = html.lower()
    found = [term for term in BLOCKED_TERMS if term in low]
    if found:
        raise SystemExit(f"BLOCKED: risky/off-scope terms found: {', '.join(found)}")

    # Product-data policy check — blocks price, stock, SKU, barcode, etc.
    pdp_violations = check_article_product_data_policy(html)
    if pdp_violations:
        raise SystemExit(
            f"BLOCKED: product-data policy violation(s): "
            f"{' | '.join(pdp_violations[:3])}"
        )

    h1 = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.S | re.I)
    if not h1:
        raise SystemExit("BLOCKED: no H1 found.")

    title = strip_tags(h1.group(1))
    handle = article_path.stem

    env = load_env(ENV_PATH)

    store = env.get("SHOPIFY_STORE_DOMAIN", "").replace("https://", "").replace("http://", "").strip("/")
    token = env.get("SHOPIFY_ADMIN_ACCESS_TOKEN") or env.get("SHOPIFY_ADMIN_TOKEN") or ""
    version = env.get("SHOPIFY_API_VERSION") or "2026-01"
    blog_id = env.get("SHOPIFY_BLOG_ID", "").strip()

    if not store or not token or not blog_id:
        raise SystemExit("Missing Shopify store/token/blog ID in HCS .env")

    article_id = sys.argv[2].strip() if len(sys.argv) >= 3 else ""

    if not article_id and STATUS_PATH.exists():
        try:
            status = json.loads(STATUS_PATH.read_text())
            article_id = str(status.get("article_id", "")).strip()
        except Exception:
            article_id = ""

    if not article_id:
        article_id = "1001606873462"

    payload = {
        "article": {
            "id": article_id,
            "title": title,
            "handle": handle,
            "body_html": html,
            "published": False
        }
    }

    url = f"https://{store}/admin/api/{version}/blogs/{blog_id}/articles/{article_id}.json"
    data = shopify_request("PUT", url, token, payload)
    article = data.get("article", {})

    STATUS_PATH.write_text(json.dumps({
        "client": "hcs_gadgets",
        "status": "draft_updated",
        "title": article.get("title"),
        "handle": article.get("handle"),
        "article_id": article.get("id"),
        "blog_id": blog_id,
        "published": article.get("published"),
        "source_file": str(article_path),
    }, indent=2))

    print("✅ HCS Shopify draft updated successfully.")
    print(f"Title: {article.get('title')}")
    print(f"Handle: {article.get('handle')}")
    print(f"Article ID: {article.get('id')}")
    print("Status: draft / unpublished")

if __name__ == "__main__":
    main()
