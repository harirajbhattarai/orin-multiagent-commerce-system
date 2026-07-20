#!/usr/bin/env bash
set -euo pipefail

WORKSPACE="/data/.openclaw/workspace"
STATUS_FILE="$WORKSPACE/clients/hoverboard_store/content_engine/latest_cron_status.md"
STATE_DIR="$WORKSPACE/clients/hoverboard_store/content_engine/automation_state"
LOG_DIR="$WORKSPACE/clients/hoverboard_store/content_engine/logs"
LOCK="/tmp/hbs_shopify_draft_watcher.lock"

DRY_RUN="${DRY_RUN:-0}"

cd "$WORKSPACE"

mkdir -p "$STATE_DIR" "$LOG_DIR"

echo "HBS Shopify Draft Watcher"
echo "========================="
date
echo ""

if [ -f "$LOCK" ]; then
  echo "SKIP: watcher lock exists. Another run may be active."
  exit 0
fi

trap 'rm -f "$LOCK"' EXIT
echo "$$" > "$LOCK"

if [ ! -f "$STATUS_FILE" ]; then
  echo "SKIP: latest_cron_status.md not found."
  exit 0
fi

JOB="$(grep -E '^\- \*\*Job:\*\*' "$STATUS_FILE" | head -1 | sed 's/.*\*\*Job:\*\*[[:space:]]*//' | tr -d '\r' || true)"
TOPIC="$(grep -E '^\- \*\*Topic:\*\*' "$STATUS_FILE" | head -1 | sed 's/.*\*\*Topic:\*\*[[:space:]]*//' | tr -d '\r' || true)"
TARGET="$(grep -E '^\- \*\*Target file:\*\*' "$STATUS_FILE" | head -1 | sed 's/.*\*\*Target file:\*\*[[:space:]]*//' | tr -d '\r' || true)"
RESULT="$(grep -E '^\- \*\*Result:\*\*' "$STATUS_FILE" | head -1 | sed 's/.*\*\*Result:\*\*[[:space:]]*//' | tr -d '\r' || true)"
SHOPIFY_CALLED="$(grep -E '^\- \*\*Shopify API called:\*\*' "$STATUS_FILE" | head -1 | sed 's/.*\*\*Shopify API called:\*\*[[:space:]]*//' | tr -d '\r' || true)"

echo "Job: ${JOB:-unknown}"
echo "Topic: ${TOPIC:-unknown}"
echo "Target: ${TARGET:-unknown}"
echo "Result: ${RESULT:-unknown}"
echo "Shopify API called: ${SHOPIFY_CALLED:-unknown}"
echo ""

if [ -z "$TARGET" ] || [ "$TARGET" = "none" ]; then
  echo "SKIP: no target article file found."
  exit 0
fi

if [ ! -f "$WORKSPACE/$TARGET" ]; then
  echo "SKIP: target article file does not exist:"
  echo "$WORKSPACE/$TARGET"
  exit 0
fi

if [ "$SHOPIFY_CALLED" != "No" ]; then
  echo "SKIP: Shopify API already called or status is not No."
  exit 0
fi

KEY="$(printf '%s' "$TARGET" | sha256sum | awk '{print $1}')"
DONE_MARKER="$STATE_DIR/shopify_draft_done_$KEY.txt"
BLOCK_MARKER="$STATE_DIR/shopify_draft_blocked_$KEY.txt"

if [ -f "$DONE_MARKER" ]; then
  echo "SKIP: this article was already successfully processed."
  cat "$DONE_MARKER"
  exit 0
fi

if [ -f "$BLOCK_MARKER" ]; then
  echo "SKIP: this article was already blocked before."
  cat "$BLOCK_MARKER"
  exit 0
fi

if [ "$DRY_RUN" = "1" ]; then
  echo "DRY RUN: would process article into Shopify draft:"
  echo "$TARGET"
  exit 0
fi

RUN_LOG="$LOG_DIR/shopify_draft_watcher_$(date +%Y%m%d_%H%M%S).log"

echo "Processing latest article into Shopify draft..."
echo "Log: $RUN_LOG"
echo ""

set +e
bash tools/scheduler/process_latest_cron_article.sh 2>&1 | tee "$RUN_LOG"
STATUS="${PIPESTATUS[0]}"
set -e

if [ "$STATUS" -eq 0 ]; then
  {
    echo "Processed successfully"
    echo "Date: $(date)"
    echo "Job: ${JOB:-unknown}"
    echo "Topic: ${TOPIC:-unknown}"
    echo "Target: $TARGET"
  } > "$DONE_MARKER"

  echo ""
  echo "Syncing Obsidian vault to GitHub..."
  bash tools/github/sync_hbs_vault_to_github.sh

  echo ""
  echo "DONE: Shopify draft workflow completed."
  exit 0
fi

if grep -qi "Duplicate = HIGH RISK\|HIGH RISK\|BLOCK" "$RUN_LOG"; then
  {
    echo "Blocked by duplicate/high-risk preflight"
    echo "Date: $(date)"
    echo "Job: ${JOB:-unknown}"
    echo "Topic: ${TOPIC:-unknown}"
    echo "Target: $TARGET"
    echo "Log: $RUN_LOG"
  } > "$BLOCK_MARKER"

  echo ""
  echo "BLOCKED: duplicate/high-risk article. Marker saved so watcher will not keep retrying."
  exit 0
fi

echo ""
echo "FAILED: process script failed, but no duplicate block detected."
echo "No marker saved, so a future watcher run can retry."
exit "$STATUS"
