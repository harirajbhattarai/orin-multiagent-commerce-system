#!/usr/bin/env bash
set -euo pipefail

WORKSPACE="/data/.openclaw/workspace"
LOCK="/tmp/hbs_auto_article_to_shopify.lock"

cd "$WORKSPACE"

if [ -f "$LOCK" ]; then
  echo "Lock file exists. Another article automation may be running."
  echo "Lock: $LOCK"
  exit 1
fi

trap 'rm -f "$LOCK"' EXIT
echo "$$" > "$LOCK"

echo "HBS Auto Article → Shopify Draft"
echo "================================"
date
echo ""

echo "1. Creating next scheduled article..."
python3 tools/scheduler/next_blog_job.py

echo ""
echo "2. Processing latest cron article into Shopify draft..."
bash tools/scheduler/process_latest_cron_article.sh

echo ""
echo "3. Syncing updated Obsidian vault to GitHub..."
bash tools/github/sync_hbs_vault_to_github.sh

echo ""
echo "Done. Article draft workflow completed."
date
