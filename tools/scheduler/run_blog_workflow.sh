#!/usr/bin/env bash
set -e

ARTICLE_FILE="$1"

if [ -z "$ARTICLE_FILE" ]; then
  echo "Usage: bash tools/scheduler/run_blog_workflow.sh path/to/article.html"
  exit 1
fi

echo "1. Running UK compliance check..."
python3 tools/shopify_publisher/compliance_check.py "$ARTICLE_FILE"

echo ""
echo "2. Running HTML quality check..."
python3 tools/shopify_publisher/html_quality_check.py "$ARTICLE_FILE"

echo ""
echo "3. Running duplicate preflight check..."
python3 tools/shopify_publisher/preflight_article_check.py "$ARTICLE_FILE"

echo ""
echo "4. Publishing Shopify draft..."
python3 tools/shopify_publisher/publish_blog_draft.py "$ARTICLE_FILE"

echo ""
echo "5. Refreshing Shopify inventory..."
python3 tools/shopify_publisher/fetch_shopify_blogs.py

echo ""
echo "Workflow complete."
