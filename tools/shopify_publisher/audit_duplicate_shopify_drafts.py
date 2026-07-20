#!/usr/bin/env python3
import csv
import html
import json
import os
import re
import sys
import urllib.request
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path

WORKSPACE = Path("/data/.openclaw/workspace")
OUT_DIR = WORKSPACE / "clients/hoverboard_store/content_engine/duplicate_audit"
VAULT_DIR = WORKSPACE / "clients/hoverboard_store/obsidian_vault/Hoverboard Store Content System"
OUT_DIR.mkdir(parents=True, exist_ok=True)
VAULT_DIR.mkdir(parents=True, exist_ok=True)

ENV_PATHS = [
    WORKSPACE / "tools/shopify_publisher/.env",
    WORKSPACE / "tools/shopify_publisher/.envcp",
    WORKSPACE / "clients/hoverboard_store/.env",
    WORKSPACE / ".env",
]

def load_env():
    env = dict(os.environ)
    for path in ENV_PATHS:
        if not path.exists():
            continue
        for line in path.read_text(errors="ignore").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            if line.startswith("export "):
                line = line.replace("export ", "", 1)
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env

def get_config():
    env = load_env()
    domain = (
        env.get("SHOPIFY_STORE_DOMAIN")
        or env.get("SHOPIFY_SHOP_DOMAIN")
        or env.get("SHOPIFY_DOMAIN")
        or env.get("SHOPIFY_STORE")
        or env.get("SHOPIFY_SHOP")
        or ""
    )
    token = (
        env.get("SHOPIFY_ADMIN_API_ACCESS_TOKEN")
        or env.get("SHOPIFY_ACCESS_TOKEN")
        or env.get("SHOPIFY_ADMIN_TOKEN")
        or env.get("SHOPIFY_TOKEN")
        or ""
    )
    api_version = env.get("SHOPIFY_API_VERSION", "2025-01")

    domain = domain.replace("https://", "").replace("http://", "").strip("/")
    if not domain or not token:
        print("ERROR: Shopify domain or admin token not found.")
        print("Checked env files:")
        for p in ENV_PATHS:
            print(f"- {p}")
        print("")
        print("Run this to inspect existing env names:")
        print("grep -Rni 'SHOPIFY_' tools/shopify_publisher clients/hoverboard_store .env 2>/dev/null | head -80")
        sys.exit(1)

    return domain, token, api_version

def api_get(url, token):
    req = urllib.request.Request(
        url,
        headers={
            "X-Shopify-Access-Token": token,
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=60) as res:
        body = res.read().decode("utf-8")
        link = res.headers.get("Link", "")
        return json.loads(body), link

def next_link(link_header):
    if not link_header:
        return None
    for part in link_header.split(","):
        if 'rel="next"' in part:
            m = re.search(r"<([^>]+)>", part)
            if m:
                return m.group(1)
    return None

def fetch_all(url, token, key):
    out = []
    while url:
        data, link = api_get(url, token)
        out.extend(data.get(key, []))
        url = next_link(link)
    return out

def strip_html(text):
    text = html.unescape(text or "")
    text = re.sub(r"<script.*?</script>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<style.*?</style>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text

def norm(text):
    text = strip_html(text).lower()
    text = re.sub(r"[^a-z0-9\s-]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text

def ratio(a, b):
    a, b = a or "", b or ""
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a[:5000], b[:5000]).ratio()

def recommend(draft, live, title_sim, handle_sim, body_sim):
    reasons = []

    if draft["handle"] and draft["handle"] == live["handle"]:
        reasons.append("same handle")
    if title_sim >= 0.96:
        reasons.append("near-identical title")
    if body_sim >= 0.90:
        reasons.append("near-identical body")
    if title_sim >= 0.85 and body_sim >= 0.70:
        reasons.append("same topic and similar body")

    if reasons:
        return "DELETE_CANDIDATE", "; ".join(reasons)

    if title_sim >= 0.72 or handle_sim >= 0.75 or body_sim >= 0.55:
        return "REVIEW_MERGE", "similar topic/article; compare manually"

    return "KEEP", "low similarity"

def main():
    domain, token, api_version = get_config()
    base = f"https://{domain}/admin/api/{api_version}"

    print("Shopify Duplicate Draft Audit")
    print("=============================")
    print(f"Store: {domain}")
    print(f"API version: {api_version}")
    print("Mode: READ ONLY — no articles will be deleted")
    print("")

    blogs = fetch_all(f"{base}/blogs.json?limit=250", token, "blogs")
    all_articles = []

    for blog in blogs:
        blog_id = blog["id"]
        blog_title = blog.get("title", "")
        blog_handle = blog.get("handle", "")
        url = f"{base}/blogs/{blog_id}/articles.json?limit=250&status=any"
        articles = fetch_all(url, token, "articles")
        for a in articles:
            a["_blog_id"] = blog_id
            a["_blog_title"] = blog_title
            a["_blog_handle"] = blog_handle
            all_articles.append(a)

    live = []
    drafts = []

    for a in all_articles:
        item = {
            "id": str(a.get("id", "")),
            "blog": a.get("_blog_title", ""),
            "blog_handle": a.get("_blog_handle", ""),
            "title": a.get("title", "") or "",
            "handle": a.get("handle", "") or "",
            "body": strip_html(a.get("body_html", "")),
            "created_at": a.get("created_at", ""),
            "updated_at": a.get("updated_at", ""),
            "published_at": a.get("published_at", ""),
        }
        if item["published_at"]:
            live.append(item)
        else:
            drafts.append(item)

    rows = []
    for d in drafts:
        best = None
        for l in live:
            title_sim = ratio(norm(d["title"]), norm(l["title"]))
            handle_sim = ratio(norm(d["handle"]), norm(l["handle"]))
            body_sim = ratio(norm(d["body"]), norm(l["body"]))
            score = max(title_sim, handle_sim, body_sim, (title_sim * 0.6 + body_sim * 0.4))
            rec, reason = recommend(d, l, title_sim, handle_sim, body_sim)

            candidate = {
                "draft_id": d["id"],
                "draft_title": d["title"],
                "draft_handle": d["handle"],
                "draft_updated_at": d["updated_at"],
                "live_id": l["id"],
                "live_title": l["title"],
                "live_handle": l["handle"],
                "live_published_at": l["published_at"],
                "title_similarity": round(title_sim, 3),
                "handle_similarity": round(handle_sim, 3),
                "body_similarity": round(body_sim, 3),
                "score": round(score, 3),
                "recommendation": rec,
                "reason": reason,
            }

            if best is None or candidate["score"] > best["score"]:
                best = candidate

        if best:
            rows.append(best)

    rows.sort(key=lambda r: (r["recommendation"] != "DELETE_CANDIDATE", r["recommendation"] != "REVIEW_MERGE", -r["score"]))

    csv_path = OUT_DIR / "shopify_duplicate_draft_audit.csv"
    md_path = OUT_DIR / "shopify_duplicate_draft_audit.md"
    vault_path = VAULT_DIR / "Shopify Duplicate Draft Audit.md"

    fields = [
        "recommendation", "score", "reason",
        "draft_id", "draft_title", "draft_handle", "draft_updated_at",
        "live_id", "live_title", "live_handle", "live_published_at",
        "title_similarity", "handle_similarity", "body_similarity",
    ]

    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for r in rows:
            writer.writerow({k: r.get(k, "") for k in fields})

    delete_candidates = [r for r in rows if r["recommendation"] == "DELETE_CANDIDATE"]
    review_merge = [r for r in rows if r["recommendation"] == "REVIEW_MERGE"]
    keep = [r for r in rows if r["recommendation"] == "KEEP"]

    def table(section_rows):
        if not section_rows:
            return "_None found._\n"
        lines = [
            "| Recommendation | Score | Draft | Matching Live | Reason |",
            "|---|---:|---|---|---|",
        ]
        for r in section_rows[:80]:
            lines.append(
                f"| {r['recommendation']} | {r['score']} | {r['draft_title']} `ID:{r['draft_id']}` | {r['live_title']} `ID:{r['live_id']}` | {r['reason']} |"
            )
        return "\n".join(lines) + "\n"

    report = f"""# Shopify Duplicate Draft Audit

Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

Store: `{domain}`

Mode: **READ ONLY** — this report does not delete anything.

## Summary

- Live articles checked: **{len(live)}**
- Draft articles checked: **{len(drafts)}**
- Delete candidates: **{len(delete_candidates)}**
- Review / merge candidates: **{len(review_merge)}**
- Keep / low-risk drafts: **{len(keep)}**

## What to delete

Delete only after manually checking inside Shopify.

{table(delete_candidates)}

## What to review or merge

These may be similar topics, not always exact duplicates.

{table(review_merge)}

## What to keep

Low similarity against live posts.

{table(keep[:40])}

## Rule

Do not delete automatically. First open Shopify blog drafts and compare title, handle, and content.
"""

    md_path.write_text(report, encoding="utf-8")
    vault_path.write_text(report, encoding="utf-8")

    print(f"Live articles: {len(live)}")
    print(f"Draft articles: {len(drafts)}")
    print(f"Delete candidates: {len(delete_candidates)}")
    print(f"Review/merge candidates: {len(review_merge)}")
    print(f"Keep candidates: {len(keep)}")
    print("")
    print(f"CSV saved: {csv_path}")
    print(f"Markdown saved: {md_path}")
    print(f"Obsidian note saved: {vault_path}")

if __name__ == "__main__":
    main()
