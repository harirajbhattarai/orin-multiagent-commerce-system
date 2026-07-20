#!/usr/bin/env python3
from pathlib import Path
import json
import urllib.request
import urllib.error

ROOT = Path("/data/.openclaw/workspace")
ENV_PATH = ROOT / "clients/hcs_gadgets/shopify_config/.env"

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

def shopify_get(url, token):
    req = urllib.request.Request(
        url,
        headers={
            "X-Shopify-Access-Token": token,
            "Content-Type": "application/json",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as res:
            return json.loads(res.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        print(f"Shopify API error: {e.code}")
        print(e.read().decode("utf-8")[:1000])
        raise SystemExit(1)

env = load_env(ENV_PATH)

store = (
    env.get("SHOPIFY_STORE_DOMAIN")
    or env.get("SHOPIFY_SHOP_DOMAIN")
    or env.get("SHOPIFY_STORE")
    or ""
).replace("https://", "").replace("http://", "").strip("/")

token = env.get("SHOPIFY_ADMIN_ACCESS_TOKEN") or env.get("SHOPIFY_ADMIN_TOKEN") or ""
version = env.get("SHOPIFY_API_VERSION") or "2026-01"

if not store or not token:
    raise SystemExit("Missing SHOPIFY_STORE_DOMAIN or SHOPIFY_ADMIN_ACCESS_TOKEN in HCS .env")

url = f"https://{store}/admin/api/{version}/blogs.json"
data = shopify_get(url, token)
blogs = data.get("blogs", [])

print("HCS Shopify blogs found:")
print("========================")
for blog in blogs:
    print(f'{blog.get("id")} | {blog.get("title")} | handle={blog.get("handle")}')

if not blogs:
    print("No blogs found.")
