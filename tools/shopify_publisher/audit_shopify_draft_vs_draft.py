#!/usr/bin/env python3
import csv, html, json, os, re, sys, urllib.request
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
        if path.exists():
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
    ).replace("https://", "").replace("http://", "").strip("/")

    token = (
        env.get("SHOPIFY_ADMIN_API_ACCESS_TOKEN")
        or env.get("SHOPIFY_ACCESS_TOKEN")
        or env.get("SHOPIFY_ADMIN_TOKEN")
        or env.get("SHOPIFY_TOKEN")
        or ""
    )

    api_version = env.get("SHOPIFY_API_VERSION", "2026-01")

    if not domain or not token:
        print("ERROR: Shopify domain/token not found.")
        sys.exit(1)

    return domain, token, api_version

def api_get(url, token):
    req = urllib.request.Request(url, headers={
        "X-Shopify-Access-Token": token,
        "Content-Type": "application/json",
    })
    with urllib.request.urlopen(req, timeout=60) as res:
        return json.loads(res.read().decode("utf-8")), res.headers.get("Link", "")

def next_link(link):
    if not link:
        return None
    for part in link.split(","):
        if 'rel="next"' in part:
            m = re.search(r"<([^>]+)>", part)
            if m:
                return m.group(1)
    return None

def fetch_all(url, token, key):
    rows = []
    while url:
        data, link = api_get(url, token)
        rows.extend(data.get(key, []))
        url = next_link(link)
    return rows

def strip_html(text):
    text = html.unescape(text or "")
    text = re.sub(r"<script.*?</script>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<style.*?</style>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()

def norm(text):
    text = strip_html(text).lower()
    text = re.sub(r"[^a-z0-9\s-]", " ", text)
    return re.sub(r"\s+", " ", text).strip()

def sim(a, b):
    a, b = a or "", b or ""
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a[:5000], b[:5000]).ratio()

def rec(a, b, title_sim, handle_sim, body_sim):
    if a["handle"] and a["handle"] == b["handle"]:
        return "DELETE_CANDIDATE", "same draft handle"
    if title_sim >= 0.96:
        return "DELETE_CANDIDATE", "near-identical draft title"
    if body_sim >= 0.92:
        return "DELETE_CANDIDATE", "near-identical draft body"
    if title_sim >= 0.85 and body_sim >= 0.65:
        return "DELETE_CANDIDATE", "same topic and similar body"
    if title_sim >= 0.72 or handle_sim >= 0.75 or body_sim >= 0.50:
        return "REVIEW_MERGE", "similar draft topic; compare manually"
    return "KEEP", "low similarity"

def main():
    domain, token, api_version = get_config()
    base = f"https://{domain}/admin/api/{api_version}"

    print("Shopify Draft vs Draft Audit")
    print("============================")
    print(f"Store: {domain}")
    print("Mode: READ ONLY — no drafts will be deleted")
    print("")

    blogs = fetch_all(f"{base}/blogs.json?limit=250", token, "blogs")
    drafts = []

    for blog in blogs:
        blog_id = blog["id"]
        blog_title = blog.get("title", "")
        articles = fetch_all(f"{base}/blogs/{blog_id}/articles.json?limit=250&status=any", token, "articles")

        for a in articles:
            if a.get("published_at"):
                continue
            drafts.append({
                "id": str(a.get("id", "")),
                "blog": blog_title,
                "title": a.get("title", "") or "",
                "handle": a.get("handle", "") or "",
                "body": strip_html(a.get("body_html", "")),
                "created_at": a.get("created_at", ""),
                "updated_at": a.get("updated_at", ""),
            })

    rows = []
    for i in range(len(drafts)):
        for j in range(i + 1, len(drafts)):
            a, b = drafts[i], drafts[j]
            title_sim = sim(norm(a["title"]), norm(b["title"]))
            handle_sim = sim(norm(a["handle"]), norm(b["handle"]))
            body_sim = sim(norm(a["body"]), norm(b["body"]))
            score = max(title_sim, handle_sim, body_sim, title_sim * 0.6 + body_sim * 0.4)
            recommendation, reason = rec(a, b, title_sim, handle_sim, body_sim)

            if recommendation == "KEEP" and score < 0.45:
                continue

            rows.append({
                "recommendation": recommendation,
                "score": round(score, 3),
                "reason": reason,
                "draft_a_id": a["id"],
                "draft_a_title": a["title"],
                "draft_a_handle": a["handle"],
                "draft_a_updated_at": a["updated_at"],
                "draft_b_id": b["id"],
                "draft_b_title": b["title"],
                "draft_b_handle": b["handle"],
                "draft_b_updated_at": b["updated_at"],
                "title_similarity": round(title_sim, 3),
                "handle_similarity": round(handle_sim, 3),
                "body_similarity": round(body_sim, 3),
            })

    rows.sort(key=lambda r: (r["recommendation"] != "DELETE_CANDIDATE", r["recommendation"] != "REVIEW_MERGE", -r["score"]))

    csv_path = OUT_DIR / "shopify_draft_vs_draft_audit.csv"
    md_path = OUT_DIR / "shopify_draft_vs_draft_audit.md"
    vault_path = VAULT_DIR / "Shopify Draft vs Draft Audit.md"

    fields = list(rows[0].keys()) if rows else [
        "recommendation", "score", "reason", "draft_a_id", "draft_a_title", "draft_b_id", "draft_b_title"
    ]

    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for r in rows:
            writer.writerow(r)

    delete_candidates = [r for r in rows if r["recommendation"] == "DELETE_CANDIDATE"]
    review_merge = [r for r in rows if r["recommendation"] == "REVIEW_MERGE"]

    def table(section_rows):
        if not section_rows:
            return "_None found._\n"
        lines = [
            "| Recommendation | Score | Draft A | Draft B | Reason |",
            "|---|---:|---|---|---|",
        ]
        for r in section_rows[:80]:
            lines.append(
                f"| {r['recommendation']} | {r['score']} | {r['draft_a_title']} `ID:{r['draft_a_id']}` | {r['draft_b_title']} `ID:{r['draft_b_id']}` | {r['reason']} |"
            )
        return "\n".join(lines) + "\n"

    report = f"""# Shopify Draft vs Draft Audit

Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

Store: `{domain}`

Mode: **READ ONLY** — this report does not delete anything.

## Summary

- Draft articles checked: **{len(drafts)}**
- Draft duplicate pairs found: **{len(rows)}**
- Delete candidates: **{len(delete_candidates)}**
- Review / merge candidates: **{len(review_merge)}**

## What to delete candidates

Delete only after manually checking inside Shopify.

{table(delete_candidates)}

## What to review or merge

These may be similar topics, not always exact duplicates.

{table(review_merge)}

## Rule

Do not delete automatically. First open both Shopify drafts and compare title, handle, and content.
"""

    md_path.write_text(report, encoding="utf-8")
    vault_path.write_text(report, encoding="utf-8")

    print(f"Draft articles checked: {len(drafts)}")
    print(f"Draft duplicate pairs found: {len(rows)}")
    print(f"Delete candidates: {len(delete_candidates)}")
    print(f"Review/merge candidates: {len(review_merge)}")
    print("")
    print(f"CSV saved: {csv_path}")
    print(f"Obsidian note saved: {vault_path}")

if __name__ == "__main__":
    main()
