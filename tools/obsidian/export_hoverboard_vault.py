#!/usr/bin/env python3
from pathlib import Path
from datetime import datetime
import shutil
import re

BASE = Path("clients/hoverboard_store")
CONTENT = BASE / "content_engine"
COMPLIANCE = BASE / "compliance"
SEARCH_CONSOLE = BASE / "search_console"

VAULT = BASE / "obsidian_vault" / "Hoverboard Store Content System"

FILES_TO_COPY = {
    CONTENT / "content_queue_3_months.md": "Content Queue.md",
    CONTENT / "draft_inventory.md": "Draft Inventory.md",
    CONTENT / "published_inventory.md": "Published Inventory.md",
    CONTENT / "latest_cron_status.md": "Latest Cron Status.md",
    CONTENT / "cron_runs.md": "Cron Runs.md",
    CONTENT / "publishing_rules.md": "Publishing Rules.md",
    CONTENT / "cluster_map.md": "Cluster Map.md",
    CONTENT / "cluster_rules.md": "Cluster Rules.md",
    CONTENT / "safe_topic_rules.md": "Safe Topic Rules.md",
    CONTENT / "topic_opportunities.md": "Topic Opportunities.md",
    COMPLIANCE / "uk_product_compliance_rules.md": "UK Product Compliance Rules.md",
    SEARCH_CONSOLE / "gsc_topic_opportunities.md": "GSC Topic Opportunities.md",
}

def copy_or_placeholder(src, dst_name):
    dst = VAULT / dst_name

    if src.exists():
        shutil.copy2(src, dst)
    else:
        title = dst_name.replace(".md", "")
        dst.write_text(
            f"# {title}\n\nSource file not found yet:\n\n`{src}`\n",
            encoding="utf-8"
        )

def status_summary():
    queue = CONTENT / "content_queue_3_months.md"

    if not queue.exists():
        return {}

    text = queue.read_text(errors="ignore")
    statuses = re.findall(r"(?m)^Status:\s*(\S+)", text)

    counts = {}
    for status in statuses:
        counts[status] = counts.get(status, 0) + 1

    return counts

def next_planned_jobs(limit=8):
    queue = CONTENT / "content_queue_3_months.md"

    if not queue.exists():
        return []

    text = queue.read_text(errors="ignore")
    blocks = re.split(r"(?m)^## Job ", text)
    jobs = []

    for block in blocks[1:]:
        lines = block.splitlines()
        if not lines:
            continue

        job_no = lines[0].strip()

        status = re.search(r"(?m)^Status:\s*(.+)$", block)
        topic = re.search(r"(?m)^Topic:\s*(.+)$", block)
        date = re.search(r"(?m)^Date target:\s*(.+)$", block)
        cluster = re.search(r"(?m)^Cluster:\s*(.+)$", block)

        if status and status.group(1).strip() == "planned":
            jobs.append({
                "job": job_no,
                "date": date.group(1).strip() if date else "unknown",
                "cluster": cluster.group(1).strip() if cluster else "unknown",
                "topic": topic.group(1).strip() if topic else "unknown",
            })

    return jobs[:limit]

def latest_cron_snapshot():
    status_file = CONTENT / "latest_cron_status.md"

    if not status_file.exists():
        return "Latest cron status file not found yet."

    return status_file.read_text(errors="ignore").strip()

def build_dashboard():
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    counts = status_summary()
    next_jobs = next_planned_jobs()
    cron_text = latest_cron_snapshot()

    lines = []
    lines.append("# Hoverboard Store Content System")
    lines.append("")
    lines.append(f"Last exported: {now}")
    lines.append("")
    lines.append("## Quick Links")
    lines.append("")
    lines.append("- [[Content Queue]]")
    lines.append("- [[Draft Inventory]]")
    lines.append("- [[Published Inventory]]")
    lines.append("- [[Latest Cron Status]]")
    lines.append("- [[Cron Runs]]")
    lines.append("- [[Publishing Rules]]")
    lines.append("- [[Cluster Map]]")
    lines.append("- [[Cluster Rules]]")
    lines.append("- [[Safe Topic Rules]]")
    lines.append("- [[Topic Opportunities]]")
    lines.append("- [[UK Product Compliance Rules]]")
    lines.append("- [[GSC Topic Opportunities]]")
    lines.append("")
    lines.append("## Queue Status Summary")
    lines.append("")

    if counts:
        for key, value in sorted(counts.items()):
            lines.append(f"- **{key}**: {value}")
    else:
        lines.append("- No queue statuses found.")

    lines.append("")
    lines.append("## Next Planned Jobs")
    lines.append("")

    if next_jobs:
        for job in next_jobs:
            lines.append(
                f"- **Job {job['job']}** — {job['date']} — {job['cluster']} — {job['topic']}"
            )
    else:
        lines.append("- No planned jobs found.")

    lines.append("")
    lines.append("## Latest Cron Snapshot")
    lines.append("")
    lines.append("```text")
    lines.append(cron_text)
    lines.append("```")
    lines.append("")
    lines.append("## Operating Rules")
    lines.append("")
    lines.append("- OpenClaw cron creates local HTML only.")
    lines.append("- Manual terminal workflow creates hidden Shopify drafts.")
    lines.append("- Human review is required before live publishing.")
    lines.append("- Existing published Shopify articles are read-only unless explicitly approved.")
    lines.append("- Cron jobs must not call Shopify API.")
    lines.append("- Compliance warnings must be reviewed before live publishing.")

    (VAULT / "Dashboard.md").write_text("\n".join(lines), encoding="utf-8")

def main():
    VAULT.mkdir(parents=True, exist_ok=True)

    for src, dst_name in FILES_TO_COPY.items():
        copy_or_placeholder(src, dst_name)

    build_dashboard()

    print(f"Obsidian vault exported to: {VAULT}")
    print("Open this folder in Obsidian or copy it to your Mac.")

if __name__ == "__main__":
    main()
