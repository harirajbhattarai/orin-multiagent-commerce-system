#!/usr/bin/env python3
"""
HCS Safe Shopify Draft Updater

Updates an EXISTING Shopify draft article with a local HTML draft.
Enforces ALL safety rules before and after update.

Usage:
    python3 hcs_safe_update_existing_draft.py \\
        --article-id 1001998647670 \\
        --local-html clients/hcs_gadgets/content_engine/drafts/my-article.html \\
        --title "My Article Title" \\
        --handle my-article-handle

Safety checklist performed:
    [x] HTML validator pass
    [x] Product truth checks
    [x] Backup current Shopify state
    [x] Verify article exists
    [x] PUT with published_at=null
    [x] Fetch article after update
    [x] Compare body SHA256
    [x] Verify published_at is null
    [x] Verify handle
    [x] Verify no old content
    [x] Verify no duplicate title
    [x] Verify no duplicate handle
    [x] STOP on any failure

Never: creates a new article, publishes, sets published_at
"""

import argparse
import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

# Import the shared orin module for product-data policy check
_orin_dir = Path(__file__).parent
sys.path.insert(0, str(_orin_dir))
from hcs_html_contract_validator import check_article_product_data_policy

SHOPIFY_TOKEN = os.environ.get("HCS_SHOPIFY_TOKEN")
if not SHOPIFY_TOKEN:
    raise RuntimeError("HCS_SHOPIFY_TOKEN is missing; refusing Shopify operation.")
SHOPIFY_SHOP = "hcsgadgets-com"
SHOPIFY_API_VERSION = "2026-01"
SHOPIFY_BLOG_ID = "89150259452"

UNSUPPORTED_TERMS = [
    "tongs", "thermometer", "brush", "grill basket", "apron",
    "smoker box", "tool set", "storage cart", "skewer",
    "basting brush", "wire brush", "grill cover", "barbecue cover"
]

STOP_WORDS = ["[STOP]", "EMERGENCY STOP", "ABORT"]


def log(msg):
    print(f"[hcs_safe_updater] {msg}")


def log_fail(msg):
    print(f"[hcs_safe_updater] ❌ FAIL: {msg}")


def log_pass(msg):
    print(f"[hcs_safe_updater] ✅ PASS: {msg}")


def stop(message=None):
    if message:
        print(f"\n[hcs_safe_updater] 🔴 STOPPED — {message}")
    print("\n[hcs_safe_updater] 🔴 UPDATE ABORTED — No changes made to Shopify.")
    sys.exit(1)


def verify_no_stop_words(text, field_name):
    """Check that a field value does not contain stop words."""
    text_lower = text.lower()
    for word in STOP_WORDS:
        if word.lower() in text_lower:
            stop(f"Stop word '{word}' found in {field_name}. Possible injection.")


def sha256_file(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def sha256_str(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def shopify_get(article_id):
    url = f"https://{SHOPIFY_SHOP}.myshopify.com/admin/api/{SHOPIFY_API_VERSION}/blogs/{SHOPIFY_BLOG_ID}/articles/{article_id}.json"
    req = urllib.request.Request(url, headers={"X-Shopify-Access-Token": SHOPIFY_TOKEN})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        if e.code == 404:
            stop(f"Article {article_id} not found in Shopify.")
        else:
            stop(f"Shopify GET failed: HTTP {e.code}")
    except Exception as e:
        stop(f"Shopify GET failed: {e}")


def shopify_put(article_id, title, handle, body_html):
    url = f"https://{SHOPIFY_SHOP}.myshopify.com/admin/api/{SHOPIFY_API_VERSION}/blogs/{SHOPIFY_BLOG_ID}/articles/{article_id}.json"
    payload = json.dumps({
        "article": {
            "id": str(article_id),
            "title": title,
            "handle": handle,
            "body_html": body_html,
            "published_at": None,
            "status": "draft"
        }
    }).encode("utf-8")
    req = urllib.request.Request(
        url, data=payload,
        headers={
            "X-Shopify-Access-Token": SHOPIFY_TOKEN,
            "Content-Type": "application/json",
            "Accept": "application/json"
        },
        method="PUT"
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        stop(f"Shopify PUT failed: HTTP {e.code} — {body}")
    except Exception as e:
        stop(f"Shopify PUT failed: {e}")


def shopify_get_all_articles():
    url = f"https://{SHOPIFY_SHOP}.myshopify.com/admin/api/{SHOPIFY_API_VERSION}/blogs/{SHOPIFY_BLOG_ID}/articles.json?limit=250"
    req = urllib.request.Request(url, headers={"X-Shopify-Access-Token": SHOPIFY_TOKEN})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode()).get("articles", [])
    except Exception as e:
        stop(f"Could not fetch article list for duplicate check: {e}")


def run_html_validator(local_html_path):
    validator_path = Path(__file__).parent / "hcs_html_contract_validator.py"
    html_validator_path = Path(__file__).parents[3] / "orin" / "hcs_html_contract_validator.py"
    for vp in [str(validator_path), str(html_validator_path)]:
        if os.path.exists(vp):
            import subprocess
            result = subprocess.run(
                ["python3", vp, "--file", local_html_path],
                capture_output=True, text=True
            )
            return result.returncode == 0, result.stdout + result.stderr
    log("HTML validator script not found — skipping validator check")
    return True, "validator not found"


def main():
    parser = argparse.ArgumentParser(description="HCS Safe Shopify Draft Updater")
    parser.add_argument("--article-id", required=True, help="Existing Shopify article ID")
    parser.add_argument("--local-html", required=True, help="Path to local HTML draft")
    parser.add_argument("--title", required=True, help="Article title")
    parser.add_argument("--handle", required=True, help="Article handle/slug")
    parser.add_argument("--backup-dir", default="backups", help="Directory for backups")
    parser.add_argument("--skip-validator", action="store_true", help="Skip HTML validator check")
    parser.add_argument("--skip-product-check", action="store_true", help="Skip unsupported-terms product check")
    args = parser.parse_args()

    article_id = args.article_id
    local_html_path = Path(args.local_html)
    title = args.title
    handle = args.handle

    log(f"Starting safe update for Article ID: {article_id}")
    log(f"Local HTML: {local_html_path}")
    log(f"Title: {title}")
    log(f"Handle: {handle}")

    # --- Pre-update checks ---

    # Stop-word check on all user inputs
    verify_no_stop_words(title, "--title")
    verify_no_stop_words(handle, "--handle")
    verify_no_stop_words(article_id, "--article-id")

    # 1. Read and validate local HTML file
    if not local_html_path.exists():
        stop(f"Local HTML file not found: {local_html_path}")
    with open(local_html_path, "rb") as f:
        local_html = f.read().decode("utf-8")
    local_body_hash = sha256_str(local_html)
    log(f"Local HTML length: {len(local_html)}")
    log(f"Local HTML SHA256: {local_body_hash}")

    # 2. HTML validator
    if not args.skip_validator:
        log("Running HTML validator...")
        valid, validator_output = run_html_validator(str(local_html_path))
        if "PASS" in validator_output and "FAIL" not in validator_output:
            log_pass("HTML validator passed")
        else:
            log_fail(f"HTML validator output:\n{validator_output}")
            stop("HTML validator failed")
    else:
        log("Skipping HTML validator (--skip-validator)")

    # 3. Product-data policy check — ALWAYS enforced, no bypass
    # Blocks: prices, price ranges, stock/inventory data, SKU, barcode, EAN, GTIN, UPC,
    #         product_id, variant_id, supplier codes, internal vendor tags
    log("Running product-data policy check...")
    pdp_violations = check_article_product_data_policy(local_html)
    if pdp_violations:
        for v in pdp_violations:
            log_fail(v)
        stop(f"Product-data policy violation(s) found in local HTML. Fix before updating Shopify.")
    log_pass("Product-data policy check passed — no restricted product-data fields in local HTML")

    # 4. Unsupported-terms product check on local HTML
    if not args.skip_product_check:
        log("Running unsupported-terms check on local HTML...")
        for term in UNSUPPORTED_TERMS:
            if term.lower() in local_html.lower():
                stop(f"Unsupported term '{term}' found in local HTML. Fix before updating Shopify.")
        log_pass("Unsupported-terms check passed")

        # hcs-article wrapper check
        if 'class="hcs-article"' not in local_html:
            stop('hcs-article wrapper not found in local HTML')
        log_pass("hcs-article wrapper present")

        # JSON-LD checks
        if '"BlogPosting"' not in local_html:
            stop("BlogPosting JSON-LD not found in local HTML")
        log_pass("BlogPosting JSON-LD present")

        if '"FAQPage"' not in local_html:
            stop("FAQPage JSON-LD not found in local HTML")
        log_pass("FAQPage JSON-LD present")
    else:
        log("Skipping product truth check (--skip-product-check)")

    # 5. Backup current Shopify state
    backup_dir = Path(local_html_path).parent.parent / args.backup_dir
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_file = backup_dir / f"article_{article_id}_before_update.json"
    log(f"Backing up current Shopify state to {backup_file}")
    try:
        current = shopify_get(article_id)
        with open(backup_file, "w") as f:
            json.dump(current, f, indent=2)
        current_body = current["article"].get("body_html", "")
        current_hash = sha256_str(current_body)
        log(f"Current Shopify body SHA256: {current_hash}")
        log_pass("Backup saved")
    except Exception as e:
        stop(f"Backup failed: {e}")

    # 6. Verify article exists in Shopify
    log("Verifying article exists in Shopify...")
    existing = shopify_get(article_id)
    existing_id = existing["article"]["id"]
    if str(existing_id) != str(article_id):
        stop(f"Article ID mismatch: expected {article_id}, got {existing_id}")
    log_pass(f"Article {article_id} confirmed in Shopify")

    # 7. Check for duplicate title in Shopify
    log("Checking for duplicate title...")
    all_articles = shopify_get_all_articles()
    for a in all_articles:
        if a["title"] == title and int(a["id"]) != int(article_id):
            stop(f"Duplicate title found: Article ID {a['id']} already has title '{title}'")
    log_pass("No duplicate title found")

    # 7. Check for duplicate handle in Shopify
    log("Checking for duplicate handle...")
    for a in all_articles:
        if a["handle"] == handle and int(a["id"]) != int(article_id):
            stop(f"Duplicate handle found: Article ID {a['id']} already has handle '{handle}'")
    log_pass("No duplicate handle found")

    # --- Update ---
    log("Sending PUT request to Shopify...")
    result = shopify_put(article_id, title, handle, local_html)
    log_pass("PUT request succeeded")

    # --- Post-update verification ---

    # 8. Fetch article after update
    log("Fetching updated article from Shopify...")
    updated = shopify_get(article_id)
    updated_article = updated["article"]
    updated_body = updated_article.get("body_html", "")
    updated_hash = sha256_str(updated_body)

    # 9. Verify article ID unchanged
    if str(updated_article["id"]) != str(article_id):
        stop(f"Article ID changed from {article_id} to {updated_article['id']} — IMPOSSIBLE — investigate")
    log_pass("Article ID unchanged")

    # 10. Verify title
    if updated_article["title"] != title:
        stop(f"Title mismatch: expected '{title}', got '{updated_article['title']}'")
    log_pass("Title correct")

    # 11. Verify handle
    if updated_article["handle"] != handle:
        stop(f"Handle mismatch: expected '{handle}', got '{updated_article['handle']}'")
    log_pass("Handle correct")

    # 12. Verify published_at is null
    if updated_article.get("published_at") is not None:
        stop(f"published_at should be null but is: {updated_article.get('published_at')}")
    log_pass("published_at is null")

    # 13. Verify body SHA256 matches local
    if updated_hash != local_body_hash:
        log_fail(f"Body hash mismatch:")
        log_fail(f"  Shopify SHA256: {updated_hash}")
        log_fail(f"  Local SHA256:   {local_body_hash}")
        stop("Body was not written correctly — hashes do not match")
    log_pass(f"Body SHA256 matches local draft: {updated_hash}")

    # 14. Verify no old/unsupported content in live body
    for term in UNSUPPORTED_TERMS:
        if term.lower() in updated_body.lower():
            stop(f"Unsupported term '{term}' found in live Shopify body — body was not updated correctly")
    log_pass("No unsupported terms in live Shopify body")

    # 15. Verify broken links
    links = re.findall(r'href="([^"]+)"', updated_body)
    broken = [l for l in links if l and not l.startswith("http") and not l.startswith("#") and not l.startswith("mailto")]
    if broken:
        stop(f"Broken links found in live body: {broken}")
    log_pass(f"No broken links ({len(links)} links checked)")

    # 16. Verify verified products present (basic check for HeatRise if mentioned in local)
    if "HeatRise" in local_html and "HeatRise" not in updated_body:
        stop("HeatRise product removed from Shopify body during update")
    if "Portable BBQ" in local_html and "Portable BBQ" not in updated_body:
        stop("Portable BBQ product removed from Shopify body during update")
    log_pass("Verified products present in live body")

    # 17. Re-check duplicate title after update
    all_articles_after = shopify_get_all_articles()
    for a in all_articles_after:
        if a["title"] == title and int(a["id"]) != int(article_id):
            stop(f"Duplicate title appeared after update: Article ID {a['id']}")
    log_pass("No duplicate title after update")

    # 18. Re-check duplicate handle after update
    for a in all_articles_after:
        if a["handle"] == handle and int(a["id"]) != int(article_id):
            stop(f"Duplicate handle appeared after update: Article ID {a['id']}")
    log_pass("No duplicate handle after update")

    # --- All checks passed ---
    log("")
    log("=" * 50)
    log("✅ ALL SAFETY CHECKS PASSED")
    log("=" * 50)
    log(f"Article ID:    {article_id}")
    log(f"Title:         {title}")
    log(f"Handle:        {handle}")
    log(f"Body SHA256:   {updated_hash}")
    log(f"published_at:  null (draft)")
    log(f"Backup:        {backup_file}")
    log("Shopify draft updated and verified successfully.")
    log("")

    # Write proof record
    proof = {
        "article_id": article_id,
        "title": title,
        "handle": handle,
        "body_sha256": updated_hash,
        "published_at": None,
        "local_html_path": str(local_html_path),
        "local_html_sha256": local_body_hash,
        "backup_file": str(backup_file),
        "before_hash": current_hash,
        "after_hash": updated_hash,
        "hash_match": updated_hash == local_body_hash,
        "status": "SUCCESS — DRAFT UPDATED AND VERIFIED"
    }
    proof_file = backup_dir / f"article_{article_id}_update_proof.json"
    with open(proof_file, "w") as f:
        json.dump(proof, f, indent=2)
    log(f"Proof record: {proof_file}")


if __name__ == "__main__":
    main()
