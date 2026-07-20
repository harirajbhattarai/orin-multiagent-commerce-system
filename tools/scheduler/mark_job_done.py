#!/usr/bin/env python3
from pathlib import Path
import argparse
import re
import shutil
from datetime import datetime

QUEUE_FILE = Path("clients/hoverboard_store/content_engine/content_queue_3_months.md")

ALLOWED_STATUSES = {
    "planned",
    "draft_created",
    "published_live",
    "needs_human_review",
    "skipped_duplicate",
    "failed",
    "created_local",
    "ready_for_review",
}

def main():
    parser = argparse.ArgumentParser(
        description="Update a job status inside content_queue_3_months.md"
    )
    parser.add_argument("job", help="Job number, e.g. 07 or 7")
    parser.add_argument("status", help="New status, e.g. draft_created")
    args = parser.parse_args()

    job_num = str(args.job).strip().zfill(2)
    new_status = args.status.strip()

    if new_status not in ALLOWED_STATUSES:
        raise SystemExit(
            f"Invalid status: {new_status}\n"
            f"Allowed: {', '.join(sorted(ALLOWED_STATUSES))}"
        )

    if not QUEUE_FILE.exists():
        raise SystemExit(f"Queue file not found: {QUEUE_FILE}")

    text = QUEUE_FILE.read_text()

    block_pattern = rf"(?ms)(^## Job {re.escape(job_num)}\b.*?)(?=^## Job \d+|\Z)"
    match = re.search(block_pattern, text)

    if not match:
        raise SystemExit(f"Job {job_num} not found in {QUEUE_FILE}")

    block = match.group(1)

    status_match = re.search(r"(?m)^Status:\s*(\S+)\s*$", block)
    if not status_match:
        raise SystemExit(f"Job {job_num} has no Status line.")

    old_status = status_match.group(1)

    if old_status == new_status:
        print(f"Job {job_num} already has status: {new_status}")
        return

    new_block = re.sub(
        r"(?m)^Status:\s*\S+\s*$",
        f"Status: {new_status}",
        block,
        count=1,
    )

    backup = QUEUE_FILE.with_suffix(
        QUEUE_FILE.suffix + f".bak.{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    )
    shutil.copy2(QUEUE_FILE, backup)

    updated_text = text[:match.start(1)] + new_block + text[match.end(1):]
    QUEUE_FILE.write_text(updated_text)

    print(f"Job {job_num} status updated.")
    print(f"Old status: {old_status}")
    print(f"New status: {new_status}")
    print(f"Backup saved: {backup}")

if __name__ == "__main__":
    main()
