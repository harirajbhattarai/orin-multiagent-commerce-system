# HCS Gadgets Content Phase 0.5A — Live Action Approval Checklist

**Date:** 2026-07-01
**Phase:** Content Phase 0.5A — Live Action Checklist
**Client:** HCS Gadgets
**Status:** APPROVAL CHECKLIST — No Shopify Changes Made Yet

---

## Before You Approve

| Item | Value |
|------|-------|
| Canonical article | 1000575172982 |
| Non-canonical article | 1000525496694 |
| Redirect type | 301 Permanent Redirect |
| Merge needed | ❌ NO — accessory section too thin |
| Article A disposition | Unpublish after redirect, delete later |

---

## LIVE ACTION CHECKLIST

Complete each step in order. Do not skip steps 1–3.

---

### STEP 1: Backup Article A

**Action:** Save full Article A JSON to local file
**Path:** `clients/hcs_gadgets/content_engine/backups/article_1000525496694_before_redirect.json`

**Verification:** File exists and contains `"id": "1000525496694"`

---

### STEP 2: Backup Article B

**Action:** Save full Article B JSON to local file
**Path:** `clients/hcs_gadgets/content_engine/backups/article_1000575172982_before_redirect.json`

**Verification:** File exists and contains `"id": "1000575172982"`

---

### STEP 3: Create 301 Redirect in Shopify

**Action:** Create URL redirect in Shopify admin

| Field | Value |
|-------|-------|
| Source URL | `/blogs/gadget-blog/where-to-buy-electric-scooters-in-the-uk-top-models-and-best-deals` |
| Target URL | `/blogs/gadget-blog/where-to-buy-electric-scooters-in-the-uk-top-models-and-best-deals-1` |
| Redirect type | 301 Permanent |

**Via Shopify Admin:**
1. Go to Shopify Admin → Navigation → URL Redirects
2. Click "Add URL redirect"
3. Enter source path (without domain): `/blogs/gadget-blog/where-to-buy-electric-scooters-in-the-uk-top-models-and-best-deals`
4. Enter target path (without domain): `/blogs/gadget-blog/where-to-buy-electric-scooters-in-the-uk-top-models-and-best-deals-1`
5. Confirm 301 is selected
6. Save

**Verification (after redirect created):**
- [ ] Source URL returns HTTP 301
- [ ] Source URL Location header points to target URL
- [ ] Target URL is live and returns HTTP 200

---

### STEP 4: Verify Redirect Works

**Action:** Test the redirect

**Checks:**
- [ ] `curl -I https://hcsgadgets-com.myshopify.com/blogs/gadget-blog/where-to-buy-electric-scooters-in-the-uk-top-models-and-best-deals` returns 301
- [ ] The Location header points to the canonical URL
- [ ] Following the redirect lands on the canonical article

---

### STEP 5: Verify Article B Still Published

**Action:** Check Article B status

**Checks:**
- [ ] Article B (1000575172982) is still published
- [ ] Article B is accessible at its handle URL
- [ ] Article B handle unchanged: `where-to-buy-electric-scooters-in-the-uk-top-models-and-best-deals-1`

---

### STEP 6: Unpublish Article A

**Action:** Set Article A (1000525496694) to draft/unpublished

**Note:** Do not delete. Unpublishing keeps the article URL live so the redirect continues to function.

**Via Shopify Admin:**
1. Go to Articles → find Article A
2. Change status from Published to Draft (or unpublish)
3. Save

**Via API (if preferred):**
```bash
curl -X PUT https://hcsgadgets-com.myshopify.com/admin/api/2026-01/articles/1000525496694.json \
  -H "X-Shopify-Access-Token: [TOKEN]" \
  -H "Content-Type: application/json" \
  -d '{"article": {"published": false}}'
```

**Checks:**
- [ ] Article A is no longer visible in the blog listing
- [ ] Article A URL still returns 301 redirect (not 404)
- [ ] Article A ID unchanged: 1000525496694

---

### STEP 7: Final Verification

| Check | Expected | Verified |
|-------|---------|---------|
| Source URL (Article A) | 301 redirect to B | ⬜ |
| Target URL (Article B) | 200, published | ⬜ |
| Article A unpublished | No live content at A URL | ⬜ |
| Article B published | Live and accessible | ⬜ |
| No queue changes | Queue untouched | ⬜ |
| No other articles changed | Only Article A touched | ⬜ |

---

### STEP 8: Optional — Delete Article A Later

**When:** After redirect is confirmed working for at least 48 hours (gives Google time to update index)

**Action:** Delete Article A from Shopify

**Before deleting:**
- [ ] Confirm redirect has been live for 48+ hours
- [ ] Check Google Search Console for any crawl errors
- [ ] Verify no other internal links point specifically to Article A handle

**Note:** Once deleted, the URL will return 404. The 301 redirect will stop working. Only delete if you're confident the redirect has fully transferred link equity.

---

## What NOT to Do

| Action | Why Not |
|--------|--------|
| Do not delete Article A before creating redirect | URL will 404 immediately, losing all link equity |
| Do not delete Article A without verifying redirect first | No safety net if redirect is wrong |
| Do not update Article B body | Merge not needed — unnecessary risk |
| Do not change Article B handle | Canonical URL must remain stable |
| Do not change the queue | Unrelated to duplicate cleanup |
| Do not publish new content | This phase is cleanup only |

---

## Summary

| Step | Action | Blocking |
|------|--------|---------|
| 1 | Backup Article A JSON | ✅ |
| 2 | Backup Article B JSON | ✅ |
| 3 | Create 301 redirect in Shopify | ⏳ Needs approval |
| 4 | Verify redirect works | ⏳ After step 3 |
| 5 | Verify Article B still published | ⏳ After step 3 |
| 6 | Unpublish Article A | ⏳ After step 4 |
| 7 | Final verification | ⏳ After step 6 |
| 8 | Optional: Delete Article A later | Optional |

---

## Output Proof

| Item | Result |
|------|--------|
| Shopify touched | ❌ NO — checklist only |
| Queue touched | ❌ NO |
| Live action approved | ⏳ Awaiting your approval to proceed |
| Steps defined | 8 steps |
| Blocking steps | 2 (approval + redirect creation) |
