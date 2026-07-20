#!/usr/bin/env python3
import re
from pathlib import Path

BASE_DIR = Path("/data/.openclaw/workspace")
if not BASE_DIR.exists():
    BASE_DIR = Path("/root/.openclaw/workspace")

CONTENT_DIR = BASE_DIR / "clients" / "hoverboard_store" / "content_engine"
QUEUE_PATH = CONTENT_DIR / "content_queue_3_months.md"
PUBLISHED_INV = CONTENT_DIR / "published_inventory.md"
DRAFT_INV = CONTENT_DIR / "draft_inventory.md"
PROMPT_OUT = CONTENT_DIR / "next_openclaw_prompt.md"

def read(path):
    return path.read_text(errors="ignore") if path.exists() else ""

def field(block, name):
    m = re.search(rf"^{re.escape(name)}:\s*(.+)$", block, flags=re.M)
    return m.group(1).strip() if m else ""

def normalise(text):
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()

def parse_jobs(text):
    jobs = []
    pattern = r"(?ms)^## Job\s+(\d+)\s*(.*?)(?=^## Job\s+\d+|\Z)"

    for m in re.finditer(pattern, text):
        job_no = m.group(1)
        block = m.group(2)

        notes_match = re.search(r"Notes:\s*(.*?)(?=\n## |\n---|\Z)", block, flags=re.S)

        jobs.append({
            "job_no": job_no,
            "date_target": field(block, "Date target"),
            "cluster": field(block, "Cluster"),
            "decision": field(block, "Decision"),
            "status": field(block, "Status"),
            "topic": field(block, "Topic"),
            "target_keyword": field(block, "Target keyword"),
            "file": field(block, "File"),
            "notes": notes_match.group(1).strip() if notes_match else "",
        })

    return jobs

def inventory_has(topic, file_path):
    inv = read(PUBLISHED_INV) + "\n" + read(DRAFT_INV)
    inv_norm = normalise(inv)

    topic_norm = normalise(topic)
    slug_norm = normalise(Path(file_path).stem.replace("-", " ")) if file_path else ""

    return (topic_norm and topic_norm in inv_norm) or (slug_norm and slug_norm in inv_norm)

def make_prompt(job):
    return f"""CLIENT: Hoverboard Store

TASK TYPE:
Create upcoming Shopify blog article as a local HTML file only.

IMPORTANT:
Do NOT publish to Shopify.
Do NOT update Shopify.
Do NOT call Shopify API.
Do NOT edit existing published articles.
Only create the local HTML draft file.

QUEUE JOB:
Job {job['job_no']}

TOPIC:
{job['topic']}

TARGET KEYWORD:
{job['target_keyword']}

CLUSTER:
{job['cluster']}

DECISION:
{job['decision']}

TARGET FILE:
{job['file']}

NOTES:
{job['notes']}

READ THESE RULE FILES BEFORE WRITING:
- agents/orin_core/rules.md
- agents/orin_seo/rules.md
- agents/orin_content/rules.md
- agents/orin_guard/rules.md
- clients/hoverboard_store/business.md
- clients/hoverboard_store/brand.md
- clients/hoverboard_store/seo.md
- clients/hoverboard_store/rules.md
- clients/hoverboard_store/content_engine/html_blocks.md
- clients/hoverboard_store/content_engine/cluster_map.md
- clients/hoverboard_store/content_engine/cluster_rules.md
- clients/hoverboard_store/content_engine/safe_topic_rules.md
- clients/hoverboard_store/content_engine/topic_opportunities.md
- clients/hoverboard_store/content_engine/publishing_rules.md
- clients/hoverboard_store/compliance/uk_product_compliance_rules.md
- clients/hoverboard_store/content_engine/published_inventory.md
- clients/hoverboard_store/content_engine/draft_inventory.md

STRICT RULES:
- Existing published Shopify articles are read-only.
- New articles must become hidden Shopify drafts only after checks.
- Do not create duplicate content.
- Do not mention ORIN, AISEO, TOOXIC, ChatGPT, AI author, or autonomous SEO system in public article content.
- Public byline must be: By Hoverboard Store
- Authority section must say: Hoverboard Store Team
- SEO metadata must only appear inside an HTML comment at the top.
- Do not show SEO Title, Meta Title, Meta Description, or URL Slug visibly in the article body.

FAQ FORMAT:
Use this exact FAQ format:

<div class="hs-faq-item">
  <div class="hs-faq-q">Question text only</div>
  <div class="hs-faq-a">Answer text only</div>
</div>

Do NOT use:
- <h3 class="hs-faq-q">
- <p class="hs-faq-a">
- manual FAQPage JSON-LD

COMPLIANCE:
- Avoid unsupported public-road, pavement, cycle-lane, commuting, or legal-use claims.
- Do not invent product specs, certifications, warranty, stock, or delivery claims.
- Use careful wording if anything needs verification.

ARTICLE STRUCTURE:
Use the Hoverboard Store hs-article design system:
1. SEO metadata comment
2. <div class="hs-article">
3. <div class="hs-container">
4. H1
5. hs-meta
6. hs-quick-answer
7. intro paragraphs
8. hs-highlights
9. H2/H3 sections
10. FAQ section
11. related guides
12. soft CTA
13. hs-authority

OUTPUT:
Use the write tool to create:
{job['file']}

After writing, reply with:
1. File created path
2. Meta title
3. Meta description
4. URL slug
5. Guard check summary
6. Compliance warnings if any
7. Verification needed before Shopify draft publishing

Do not publish.
"""

def main():
    queue_text = read(QUEUE_PATH)
    if not queue_text:
        raise SystemExit(f"Queue file not found or empty: {QUEUE_PATH}")

    jobs = parse_jobs(queue_text)

    selected = None
    skipped_inventory = []

    for job in jobs:
        if job["status"].strip().lower() != "planned":
            continue

        if inventory_has(job["topic"], job["file"]):
            skipped_inventory.append(job)
            continue

        selected = job
        break

    print("Next Blog Job Reader")
    print("====================")
    print(f"Jobs found: {len(jobs)}")
    print(f"Skipped planned jobs already in inventory: {len(skipped_inventory)}")
    print("")

    if not selected:
        print("No safe planned job found.")
        return

    prompt = make_prompt(selected)
    PROMPT_OUT.write_text(prompt)

    print("NEXT SAFE JOB")
    print("-------------")
    print(f"Job: {selected['job_no']}")
    print(f"Date target: {selected['date_target']}")
    print(f"Cluster: {selected['cluster']}")
    print(f"Decision: {selected['decision']}")
    print(f"Status: {selected['status']}")
    print(f"Topic: {selected['topic']}")
    print(f"Target keyword: {selected['target_keyword']}")
    print(f"File: {selected['file']}")
    print("")
    print(f"OpenClaw prompt saved to: {PROMPT_OUT}")
    print("")
    print("View prompt with:")
    print(f"cat {PROMPT_OUT}")

if __name__ == "__main__":
    main()
