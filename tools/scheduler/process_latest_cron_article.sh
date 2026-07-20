#!/usr/bin/env bash
set -euo pipefail

STATUS_FILE="clients/hoverboard_store/content_engine/latest_cron_status.md"
QUEUE_FILE="clients/hoverboard_store/content_engine/content_queue_3_months.md"

echo "Latest Cron Article Processor"
echo "============================="
echo ""

if [ ! -f "$STATUS_FILE" ]; then
  echo "ERROR: Status file not found: $STATUS_FILE"
  exit 1
fi

JOB="$(grep -E '^\- \*\*Job:\*\*' "$STATUS_FILE" | sed 's/.*Job:\*\* *//' | tr -d '\r' | awk '{print $1}')"
TOPIC="$(grep -E '^\- \*\*Topic:\*\*' "$STATUS_FILE" | sed 's/.*Topic:\*\* *//' | tr -d '\r')"
TARGET="$(grep -E '^\- \*\*Target file:\*\*' "$STATUS_FILE" | sed 's/.*Target file:\*\* *//' | tr -d '\r')"
RESULT="$(grep -E '^\- \*\*Result:\*\*' "$STATUS_FILE" | sed 's/.*Result:\*\* *//' | tr -d '\r')"
SHOPIFY_CALLED="$(grep -E '^\- \*\*Shopify API called:\*\*' "$STATUS_FILE" | sed 's/.*Shopify API called:\*\* *//' | tr -d '\r')"

echo "Job: ${JOB:-unknown}"
echo "Topic: ${TOPIC:-unknown}"
echo "Target: ${TARGET:-unknown}"
echo "Cron result: ${RESULT:-unknown}"
echo "Shopify API called by cron: ${SHOPIFY_CALLED:-unknown}"
echo ""

if [ -z "${JOB:-}" ] || [ "$JOB" = "none" ]; then
  echo "ERROR: No valid job number found in latest cron status."
  echo "Run: cat $STATUS_FILE"
  exit 1
fi

if [ -z "${TARGET:-}" ] || [ "$TARGET" = "none" ]; then
  echo "ERROR: No target file found in latest cron status."
  echo "Run: cat $STATUS_FILE"
  exit 1
fi

if [ ! -f "$TARGET" ]; then
  echo "ERROR: Target file does not exist yet:"
  echo "$TARGET"
  exit 1
fi

if [ "${SHOPIFY_CALLED:-No}" != "No" ]; then
  echo "ERROR: Cron status says Shopify API may already have been called."
  echo "Stopping for safety."
  exit 1
fi

echo "Running manual workflow..."
echo ""

bash tools/scheduler/run_blog_workflow.sh "$TARGET"

echo ""
echo "Workflow completed."
echo ""

if [ -f "$QUEUE_FILE" ]; then
  echo "Marking Job $JOB as draft_created..."
  python3 tools/scheduler/mark_job_done.py "$JOB" draft_created
else
  echo "WARNING: Queue file not found. Could not mark job status."
fi

echo ""
echo "Done."
