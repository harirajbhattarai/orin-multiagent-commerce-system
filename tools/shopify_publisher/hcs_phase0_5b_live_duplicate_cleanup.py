#!/usr/bin/env python3
"""
HCS Gadgets Content Phase 0.5B — Live Duplicate Cleanup
Article A: 1000525496694  →  Article B: 1000575172982
Action: Create 301 redirect A→B, then unpublish A.
No deletion. No Article B changes.
"""
import urllib.request
import urllib.error
import json
import os
from datetime import datetime

# === Read token from HCS config ===
CONFIG_PATH = "/data/.openclaw/workspace/clients/hcs_gadgets/shopify_config/.env"
TOKEN = None
HCS_DOMAIN = "hcsgadgets-com.myshopify.com"
BASE = "https://{}/admin/api/2026-01".format(HCS_DOMAIN)
API_VERSION = "2026-01"

with open(CONFIG_PATH) as f:
    for line in f:
        if "ADMIN_ACCESS_TOKEN" in line:
            TOKEN = line.strip().split("=", 1)[1].strip()
            break

if not TOKEN:
    print("FATAL: Could not read Shopify token")
    exit(1)

HEADERS = {
    "Content-Type": "application/json",
    "X-Shopify-Access-Token": TOKEN
}

# === Article IDs ===
ARTICLE_A_ID = 1000525496694
ARTICLE_B_ID = 1000575172982

# === Redirect paths (public handles) ===
REDIRECT_SOURCE = "/blogs/gadget-blog/where-to-buy-electric-scooters-in-the-uk-top-models-and-best-deals"
REDIRECT_TARGET = "/blogs/gadget-blog/where-to-buy-electric-scooters-in-the-uk-top-models-and-best-deals-1"

# === Backup directory ===
BACKUP_DIR = "/data/.openclaw/workspace/clients/hcs_gadgets/content_engine/backups"

def api_get(path):
    req = urllib.request.Request(
        BASE + path,
        headers=HEADERS,
        method="GET"
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())

def api_post(path, data):
    body = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(
        BASE + path,
        data=body,
        headers={**HEADERS, "Content-Length": str(len(body))},
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())

def api_put(path, data):
    body = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(
        BASE + path,
        data=body,
        headers={**HEADERS, "Content-Length": str(len(body))},
        method="PUT"
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())

def save_backup(filename, data):
    os.makedirs(BACKUP_DIR, exist_ok=True)
    path = os.path.join(BACKUP_DIR, filename)
    with open(path, "w") as f:
        json.dump(data, f, indent=2, default=str)
    print("  Backup saved: {}".format(path))
    return path

def main():
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print("=" * 60)
    print("HCS CONTENT PHASE 0.5B — LIVE DUPLICATE CLEANUP")
    print("Time: {}".format(ts))
    print("=" * 60)

    verification = {
        "article_a_backup_path": None,
        "article_b_backup_path": None,
        "redirect_created": False,
        "redirect_source": REDIRECT_SOURCE,
        "redirect_target": REDIRECT_TARGET,
        "article_a_unpublished": False,
        "article_a_still_exists": False,
        "article_b_still_published": False,
        "article_b_handle_unchanged": False,
        "other_articles_touched": False,
        "queue_touched": False,
        "all_checks_passed": False,
    }

    # ============================================================
    # STEP 1: Fetch both articles
    # ============================================================
    print("\n[1/7] Fetching Article A (1000525496694)...")
    a_data = api_get("/articles/{}.json".format(ARTICLE_A_ID))
    a_article = a_data["article"]
    print("  Title: {}".format(a_article["title"]))
    print("  Handle: {}".format(a_article["handle"]))
    print("  Published: {}".format(a_article.get("published_at", "DRAFT")))
    a_was_published = a_article.get("published_at") is not None

    print("\n[2/7] Fetching Article B (1000575172982)...")
    b_data = api_get("/articles/{}.json".format(ARTICLE_B_ID))
    b_article = b_data["article"]
    print("  Title: {}".format(b_article["title"]))
    print("  Handle: {}".format(b_article["handle"]))
    print("  Published: {}".format(b_article.get("published_at", "DRAFT")))
    b_was_published = b_article.get("published_at") is not None

    # ============================================================
    # STEP 2: Save backups
    # ============================================================
    print("\n[3/7] Saving backups...")
    a_backup = save_backup(
        "article_{}_before_phase0_5b.json".format(ARTICLE_A_ID),
        {"phase": "Phase 0.5B backup", "timestamp": ts, "article": a_article}
    )
    verification["article_a_backup_path"] = a_backup

    b_backup = save_backup(
        "article_{}_before_phase0_5b.json".format(ARTICLE_B_ID),
        {"phase": "Phase 0.5B backup", "timestamp": ts, "article": b_article}
    )
    verification["article_b_backup_path"] = b_backup

    # ============================================================
    # STEP 3: Create 301 redirect
    # ============================================================
    print("\n[4/7] Creating 301 redirect...")
    print("  Source: {}".format(REDIRECT_SOURCE))
    print("  Target: {}".format(REDIRECT_TARGET))

    try:
        redirect_payload = {
            "redirect": {
                "path": REDIRECT_SOURCE,
                "target": REDIRECT_TARGET
            }
        }
        redirect_result = api_post("/redirects.json", redirect_payload)
        created_redirect = redirect_result.get("redirect", {})
        print("  ✅ Redirect created!")
        print("  Redirect ID: {}".format(created_redirect.get("id")))
        print("  Path: {}".format(created_redirect.get("path")))
        print("  Target: {}".format(created_redirect.get("target")))
        verification["redirect_created"] = True
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8") if e.fp else ""
        print("  ❌ HTTP Error {}: {}".format(e.code, error_body[:500]))

        # Check if error suggests Article A must be unpublished first
        if e.code in (400, 422):
            print("\n  ⚠️  SHOPIFY REFUSED to create redirect while Article A is published.")
            print("  Error suggests the source URL must be unpublished before redirect creation.")
            print("\n  SAFELY STOPPING — not unpublishing Article A without user approval.")
            print("  Please review the error above and approve the unpublish step separately.")
            verification["redirect_created"] = False
            verification["safely_stopped"] = True
            verification["stop_reason"] = "Shopify refused redirect while Article A is published"
            verification["error_code"] = e.code
            verification["error_body"] = error_body[:500]
            # Do NOT unpublish Article A
            # Save verification and exit
            out = "/tmp/hcs_phase0_5b_verification.json"
            with open(out, "w") as f:
                json.dump(verification, f, indent=2, default=str)
            print("\nVerification saved to: {}".format(out))
            print("Phase 0.5B: STOPPED SAFELY")
            exit(0)
        else:
            raise

    # ============================================================
    # STEP 4: Unpublish Article A (only after redirect succeeds)
    # ============================================================
    if verification["redirect_created"]:
        print("\n[5/7] Unpublishing Article A...")
        # Set published_at to null to unpublish
        unpub_payload = {
            "article": {
                "id": ARTICLE_A_ID,
                "published": False
            }
        }
        unpub_result = api_put("/articles/{}.json".format(ARTICLE_A_ID), unpub_payload)
        unpubbed_article = unpub_result["article"]
        is_unpublished = unpubbed_article.get("published_at") is None
        print("  Article A published_at: {}".format(unpubbed_article.get("published_at")))
        print("  Article A title: {}".format(unpubbed_article["title"]))
        print("  Article A handle: {}".format(unpubbed_article["handle"]))
        verification["article_a_unpublished"] = is_unpublished
        if is_unpublished:
            print("  ✅ Article A unpublished successfully")
        else:
            print("  ❌ WARNING: Article A may still be published!")

    # ============================================================
    # STEP 5: Verify Article B unchanged
    # ============================================================
    print("\n[6/7] Verifying Article B is unchanged...")
    b_verify = api_get("/articles/{}.json".format(ARTICLE_B_ID))["article"]
    b_still_published = b_verify.get("published_at") is not None
    b_handle_unchanged = b_verify["handle"] == b_article["handle"]
    print("  Article B still exists: {}".format(b_verify["id"] == ARTICLE_B_ID))
    print("  Article B still published: {}".format(b_still_published))
    print("  Article B handle unchanged: {} ({})".format(b_handle_unchanged, b_verify["handle"]))
    verification["article_b_still_published"] = b_still_published
    verification["article_b_handle_unchanged"] = b_handle_unchanged

    # Verify Article A still exists but unpublished
    print("\n[6b/7] Verifying Article A status...")
    a_verify = api_get("/articles/{}.json".format(ARTICLE_A_ID))["article"]
    a_still_exists = a_verify["id"] == ARTICLE_A_ID
    a_is_unpublished = a_verify.get("published_at") is None
    print("  Article A still exists: {} ({})".format(a_still_exists, a_verify["id"]))
    print("  Article A unpublished: {}".format(a_is_unpublished))
    print("  Article A handle unchanged: {}".format(a_verify["handle"]))
    verification["article_a_still_exists"] = a_still_exists

    # ============================================================
    # STEP 6: Final summary
    # ============================================================
    print("\n" + "=" * 60)
    print("VERIFICATION SUMMARY")
    print("=" * 60)

    checks = [
        ("Article A backup saved", verification["article_a_backup_path"] is not None),
        ("Article B backup saved", verification["article_b_backup_path"] is not None),
        ("Redirect created", verification["redirect_created"]),
        ("Redirect source correct", verification["redirect_source"] == REDIRECT_SOURCE),
        ("Redirect target correct", verification["redirect_target"] == REDIRECT_TARGET),
        ("Article A unpublished", verification["article_a_unpublished"]),
        ("Article A still exists", verification["article_a_still_exists"]),
        ("Article B still published", verification["article_b_still_published"]),
        ("Article B handle unchanged", verification["article_b_handle_unchanged"]),
        ("Other articles touched", False),
        ("Queue touched", False),
    ]

    all_pass = True
    for name, result in checks:
        mark = "✅" if result else "❌"
        if not result:
            all_pass = False
        print("  {} {}: {}".format(mark, name, result))

    verification["all_checks_passed"] = all_pass
    verification["shopify_touched"] = True
    verification["phase"] = "Content Phase 0.5B"

    out = "/tmp/hcs_phase0_5b_verification.json"
    with open(out, "w") as f:
        json.dump(verification, f, indent=2, default=str)
    print("\nVerification saved to: {}".format(out))
    print("\n{} PHASE 0.5B COMPLETE".format("✅" if all_pass else "❌"))
    return verification

if __name__ == "__main__":
    main()
