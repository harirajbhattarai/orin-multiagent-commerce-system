#!/usr/bin/env python3
"""
ORIN Phase 2C — Writer Agent Planning Dry-Run

Phase 2C responsibility: WRITER PLANNING ONLY.
Produces the writer plan JSON from selected-job context.

Production selected-job path:
  Reads /tmp/orin_selected_job_context.json (canonical selected job)
  -> builds dynamic writer plan via WriterAgent._build_dynamic_writer_plan()
  -> outputs /tmp/orin_selected_job_writer_plan.json

Phase 2D (Writer Execution) is a SEPARATE stage:
  Use orin_phase2d_writer_dryrun.py to generate the HTML draft.

Backward-compatible path (no job context):
  Scans queue for next planned job -> returns candidate info.

Mode: Read-only — no articles, HTML drafts, Shopify updates, or queue edits.

Usage:
  python3 tools/shopify_publisher/orin/orin_phase2c_writer_planning_dryrun.py
  python3 tools/shopify_publisher/orin/orin_phase2c_writer_planning_dryrun.py --as-of-date 2026-07-04
"""

import json
import os
import sys
from pathlib import Path

from workspace_paths import workspace_root, writable_report_path

sys.path.insert(0, str(Path(__file__).parent))
from business_time import get_business_today_from_args
from writer_agent import WriterAgent
from job_context import read_job_context

# Keep this module runnable from a clean clone. The deployment may override
# the workspace explicitly, but the source default is this repository root.
BASE_DIR = workspace_root()

CURRENT_DATE_STR = get_business_today_from_args(sys.argv[1:]).isoformat()

SELECTED_JOB_WRITER_PLAN_PATH = Path("/tmp/orin_selected_job_writer_plan.json")
SELECTED_JOB_CONTEXT_PATH = Path("/tmp/orin_selected_job_context.json")
STATUS_REPORT_PATH = writable_report_path(
    artifact_name="orin_status_phase2c.md",
    workspace_relative_path=(
        "clients/hoverboard_store/content_engine/orin_status_phase2c.md"
    ),
)


def flines(items):
    return "\n".join(["- " + item for item in items]) if items else "N/A"


def run_writer_planning_dry_run():
    writer = WriterAgent(str(BASE_DIR), CURRENT_DATE_STR)

    # Read canonical selected-job context
    job_ctx = None
    if SELECTED_JOB_CONTEXT_PATH.exists():
        try:
            job_ctx = json.loads(SELECTED_JOB_CONTEXT_PATH.read_text())
        except (json.JSONDecodeError, OSError):
            pass

    # Build writer plan
    planning_result = writer.plan_writing(job_ctx=job_ctx)
    writer_plan = planning_result.get("writer_plan")

    # Serialise writer plan to JSON
    if writer_plan:
        plan_for_json = writer_plan.copy()
        plan_for_json["proposed_local_file_path"] = str(
            plan_for_json.get("proposed_local_file_path", "")
        )
        SELECTED_JOB_WRITER_PLAN_PATH.write_text(
            json.dumps(plan_for_json, indent=2, default=str)
        )

    # Build report variables
    if job_ctx:
        job_number = job_ctx.get("job_number", "unknown")
        topic = job_ctx.get("topic", "unknown")
        target_keyword = job_ctx.get("target_keyword", "")
        target_date = job_ctx.get("target_date", "")
        expected_draft_date = job_ctx.get("expected_draft_date", "")
        queue_status = job_ctx.get("queue_status", "")
        approved_handle = (writer_plan or {}).get("approved_handle", "not set")
    else:
        job_number = "none"
        topic = "no selected job context"
        target_keyword = ""
        target_date = ""
        expected_draft_date = ""
        queue_status = ""
        approved_handle = "not applicable"

    if writer_plan:
        wp = writer_plan
        h2_ids = [h["id"] for h in wp.get("h2_outline", [])]
        faq_items = wp.get("faq_plan", [])
        int_links = wp.get("internal_link_plan", [])
        claims = wp.get("claims_to_avoid", [])
        word_count = wp.get("recommended_word_count", 0)
        article_angle = wp.get("article_angle", "")
        toc_labels = [t["label"] for t in wp.get("toc_plan", [])]
        cta_heading = (wp.get("cta_plan") or {}).get("heading", "")
        cluster = wp.get("cluster", "")
        html_reqs = wp.get("html_structure_requirements", [])
        compliance_notes = wp.get("compliance_notes", "")
        faq_count = len(faq_items)
        int_link_count = len(int_links)
        claims_count = len(claims)
    else:
        h2_ids = []
        faq_items = []
        int_links = []
        claims = []
        word_count = 0
        article_angle = ""
        toc_labels = []
        cta_heading = ""
        cluster = ""
        html_reqs = []
        compliance_notes = ""
        faq_count = 0
        int_link_count = 0
        claims_count = 0

    # FAQ text
    faq_text_lines = []
    for faq in faq_items:
        q = faq.get("question", "")
        faq_text_lines.append("**Q: " + q + "**")
    faq_text = "\n".join(faq_text_lines) if faq_text_lines else "No FAQ plan available."

    # Internal links text
    int_link_lines = []
    for link in int_links:
        anchor = link.get("anchor_text", "")
        url = link.get("url", "")
        reason = link.get("reason", "")
        int_link_lines.append("- [" + anchor + "](" + url + ") — " + reason)
    int_link_text = "\n".join(int_link_lines) if int_link_lines else "N/A"

    # Claims text
    claims_text = flines(claims) if claims else "N/A"

    # HTML reqs text
    html_reqs_text = flines(html_reqs) if html_reqs else "N/A"

    # Report
    decision = planning_result.get("writer_decision", "unknown")
    selected = planning_result.get("selected_job", "none")
    plan_source = planning_result.get("writer_plan_source", "none")

    report_lines = [
        "# ORIN Phase 2C — Writer Agent Planning Dry-Run Report",
        "",
        "**Run date:** " + CURRENT_DATE_STR,
        "**Phase:** 2C (Writer Agent planning dry-run)",
        "**Mode:** Read-only — no articles, HTML drafts, Shopify updates, or queue edits.",
        "",
        "---",
        "",
        "## Purpose",
        "",
        "Phase 2C builds a writer plan for the canonical selected job from Phase 1B.",
        "It uses the selected-job context from /tmp/orin_selected_job_context.json to",
        "produce a full article planning package.",
        "",
        "---",
        "",
        "## Selected Job Context",
        "",
        "| Field | Value |",
        "|-------|-------|",
        "| Job number | " + str(job_number) + " |",
        "| Topic | " + topic + " |",
        "| Target keyword | " + target_keyword + " |",
        "| Cluster | " + cluster + " |",
        "| Target date | " + target_date + " |",
        "| Expected draft date | " + expected_draft_date + " |",
        "| Queue status | " + queue_status + " |",
        "| Approved handle | `" + approved_handle + "` |",
        "",
        "---",
        "",
        "## Writer Agent Decision",
        "",
        "- **Writer decision:** " + decision,
        "- **Selected job for writing:** " + str(selected),
        "- **Writer plan source:** " + plan_source,
        "- **Job context provided:** " + ("yes" if job_ctx else "no"),
        "",
        "---",
        "",
        "## Writer Plan",
        "",
        "**Job Number:** " + str(job_number),
        "**Approved Handle:** `" + approved_handle + "`",
        "**Target Keyword:** " + target_keyword,
        "**Cluster:** " + cluster,
        "",
        "### Article Angle",
        "",
        article_angle,
        "",
        "### Recommended Word Count",
        "",
        str(word_count) + " words",
        "",
        "### H2 Outline (" + str(len(h2_ids)) + " sections)",
        "",
        flines(h2_ids),
        "",
        "### TOC Plan (" + str(len(toc_labels)) + " entries)",
        "",
        flines(toc_labels),
        "",
        "### FAQ Plan (" + str(faq_count) + " FAQs)",
        "",
        faq_text,
        "",
        "### Claims to Avoid (" + str(claims_count) + " items)",
        "",
        claims_text,
        "",
        "### Internal Links (" + str(int_link_count) + " links)",
        "",
        int_link_text,
        "",
        "### CTA",
        "",
        "**Heading:** " + cta_heading,
        "",
        "### Compliance Notes",
        "",
        compliance_notes if compliance_notes else "N/A",
        "",
        "### HTML Structure Requirements",
        "",
        html_reqs_text,
        "",
        "---",
        "",
        "## Summary of Actions (Dry-Run Only)",
        "",
        "- **HTML draft created:** No",
        "- **Shopify touched:** No",
        "- **Content queue edited:** No",
        "- **Production job_state.json written:** No",
        "- **URL slugs changed:** No",
        "- **Phase 2C Planning Passed:** "
        + ("Yes" if writer_plan else "No — no writer plan generated"),
        "",
        "---",
        "",
        "## Next Steps",
        "",
        "Safe to proceed to Phase 2D (Writer Agent local-draft creation) when:",
        "- Selected job context exists",
        "- Writer plan is present",
        "- Phase 2A review has passed for selected job (or is scoped out)",
        "",
        "---",
        "",
        "## Files Created in this Dry-Run",
        "",
        "- `tools/shopify_publisher/orin/orin_phase2c_writer_planning_dryrun.py` (this runner script)",
        "- `clients/hoverboard_store/content_engine/orin_status_phase2c.md` (this report)",
        "- `/tmp/orin_selected_job_writer_plan.json` (JSON writer plan — only when selected job context exists)",
        "",
        "---",
        "",
        "**Exact Command to Re-Run:**",
        "",
        "```bash",
        "cd /data/.openclaw/workspace && python3 tools/shopify_publisher/orin/orin_phase2c_writer_planning_dryrun.py",
        "```",
        "",
        "*Report generated by ORIN Phase 2C Writer Agent planning dry-run — no production files were modified.*",
    ]

    STATUS_REPORT_PATH.write_text("\n".join(report_lines))

    print("Writer Agent Planning Dry-Run Complete.")
    if writer_plan:
        print("Writer plan written to: " + str(SELECTED_JOB_WRITER_PLAN_PATH))
    print("Status report written to: " + str(STATUS_REPORT_PATH))
    print("Selected job: " + str(job_number or "none"))
    print("Writer plan source: " + plan_source)
    print("Writer decision: " + decision)


if __name__ == "__main__":
    run_writer_planning_dry_run()
