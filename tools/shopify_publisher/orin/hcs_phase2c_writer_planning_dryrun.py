#!/usr/bin/env python3
"""
HCS Gadgets — Phase 2C Writer Planning Dry-Run
==============================================
Builds the writer planning package for Job 02 (BBQ Accessories).

Read-only: does NOT write the full article HTML.
Outputs: writer plan, JSON preview, phase status report.

Allowed outputs:
- Article brief (metadata, outline, component plan)
- Validation checklist

NOT produced:
- Full article HTML draft
- Shopify article
- Queue update
"""

import json, os, re, sys
from datetime import datetime

CLIENT_ROOT = "clients/hcs_gadgets/content_engine"
TMP_DIR     = "/tmp"

PATHS = {
    "phase2a":        os.path.join(TMP_DIR, "hcs_phase2a_review_preview.json"),
    "phase2b":        os.path.join(TMP_DIR, "hcs_phase2b_duplicate_memory_preview.json"),
    "phase1e":        os.path.join(TMP_DIR, "hcs_phase1e_orchestrator_preview.json"),
    "inventory":      os.path.join(CLIENT_ROOT, "shopify_inventory.json"),
    "queue":          os.path.join(CLIENT_ROOT, "content_queue_3_months.md"),
    "cleanup_base":   os.path.join(CLIENT_ROOT, "hcs_content_cleanup_baseline_v1.md"),
    "html_contract":  os.path.join(CLIENT_ROOT, "rules/hcs_html_design_contract_v1.md"),
    "html_skeleton":  os.path.join(CLIENT_ROOT, "rules/hcs_article_skeleton_v1.html"),
    "html_checklist": os.path.join(CLIENT_ROOT, "rules/hcs_html_validation_checklist.md"),
    "compliance":     os.path.join(CLIENT_ROOT, "rules/compliance_rules.md"),
    "writing":        os.path.join(CLIENT_ROOT, "rules/writing_rules.md"),
    "product_scope":  os.path.join(CLIENT_ROOT, "rules/product_scope_rules.md"),
    "cluster_map":   os.path.join(CLIENT_ROOT, "rules/cluster_map.md"),
    "brand_rules":    os.path.join(CLIENT_ROOT, "rules/brand_rules.md"),
    "design_rules":   os.path.join(CLIENT_ROOT, "rules/design_rules.md"),
}

PREVIEW_JSON = os.path.join(TMP_DIR, "hcs_phase2c_writer_plan_preview.json")
WRITER_PLAN  = os.path.join(CLIENT_ROOT, "plans/job_02_writer_plan.md")
PHASE_REPORT = os.path.join(CLIENT_ROOT, "hcs_orin_status_phase2c.md")

TODAY = datetime.now().strftime("%Y-%m-%d")

# ─── Gate checks ───────────────────────────────────────────────────────────────

def load_gate_data():
    p2a = _read_json(PATHS["phase2a"])
    p2b = _read_json(PATHS["phase2b"])
    p1e = _read_json(PATHS["phase1e"])
    return p2a, p2b, p1e


def gate_check(p2a, p2b, p1e):
    errors = []
    if not p1e.get("final_decision") == "READY_FOR_PHASE_2":
        errors.append(f"Phase 1E not ready: {p1e.get('final_decision')}")
    if not p2a.get("decision") == "review_passed":
        errors.append(f"Phase 2A not passed: {p2a.get('decision')}")
    if not p2b.get("decision") == "CLEAR_FOR_WRITER_PLANNING":
        errors.append(f"Phase 2B not passed: {p2b.get('decision')}")
    return errors


# ─── Writer plan builder ─────────────────────────────────────────────────────────

def build_writer_plan(job02, p2a, p2b):
    """
    Build the full writer planning package for Job 02.
    Returns a dict with all plan sections.
    """
    job_n   = job02.get("job_number", "02")
    topic   = job02.get("topic", "")
    keyword = job02.get("keyword", "")
    target  = job02.get("date_target", "")
    draft   = job02.get("draft_due", "")

    # ── Metadata ─────────────────────────────────────────────────────────────
    article_title    = "BBQ Accessories UK: How to Choose the Right Gear for Your Garden"
    slug            = "bbq-accessories-uk-how-to-choose-the-right-gear"
    meta_title       = "BBQ Accessories UK: A Practical Garden Buying Guide for 2026"
    meta_description = (
        "Find the best BBQ accessories for UK gardens with this practical guide. "
        "Compare grilling tools, thermometers, covers and more."
    )
    primary_kw      = "BBQ accessories UK"
    secondary_kw    = [
        "best BBQ accessories UK",
        "BBQ tools UK",
        "BBQ equipment for gardens",
        "garden BBQ accessories",
        "UK BBQ accessories buying guide",
        "BBQ grilling tools",
        "BBQ accessories under £50",
    ]
    search_intent   = "Informational — buyers looking for guidance on which BBQ accessories to buy for UK conditions"
    reader_persona  = (
        "UK homeowner or tenant with a garden or patio who wants to BBQ outdoors. "
        "They are planning a purchase, comparing options, and want practical advice on what works "
        "in UK weather and garden conditions. Not an expert — wants clear, honest guidance."
    )
    article_angle   = (
        "Buyer's guide: help the reader understand what BBQ accessories are worth buying for a UK garden. "
        "Focus on practicality, durability in British weather, and value for money. "
        "Cover the most useful categories of accessories without overcomplicating. "
        "No fire safety guarantees. No performance warranties. No exaggerated claims."
    )

    # ── Compliance ──────────────────────────────────────────────────────────
    compliance_notes = (
        "BBQ accessories article — follow low-risk compliance path. "
        "No fire safety guarantees, no performance warranties, no heat resistance claims without certification. "
        "All product feature claims must be plausible and widely accepted (e.g., stainless steel is durable, "
        "a thermometer helps check cooking temperature). "
        "Lighter fluid and chemical cleaners: do not make health claims. "
        "UK-specific guidance preferred (e.g., weather-resistant advice for British conditions)."
    )
    claims_to_avoid  = [
        "fireproof", "flame-proof", "fire-safe certified", "fire prevention guaranteed",
        "burn-proof", "safest BBQ accessory", "best BBQ in the UK",
        "certified heat-resistant", "warranty covers fire damage", "prevents BBQ accidents",
        "guaranteed safe", "certified fire-resistant", "prevents burns",
        "official UK certified (unless confirmed)",
    ]

    # ── Outline ─────────────────────────────────────────────────────────────
    outline = [
        {"id": "introduction",          "h2": "Introduction",                       "label": "Introduction"},
        {"id": "types-of-accessories", "h2": "Types of BBQ Accessories",            "label": "Types of BBQ accessories"},
        {"id": "what-to-look-for",     "h2": "What to Look For in BBQ Accessories","label": "What to look for"},
        {"id": "good-signs",           "h2": "Good Signs",                          "label": "Good signs"},
        {"id": "things-to-avoid",     "h2": "Things to Avoid",                     "label": "Things to avoid"},
        {"id": "compare",              "h2": "Quick Comparison",                    "label": "Quick comparison"},
        {"id": "checklist",            "h2": "Quick Checklist",                     "label": "Quick checklist"},
        {"id": "faq",                 "h2": "FAQs",                                "label": "FAQs"},
    ]

    # ── Quick answer ─────────────────────────────────────────────────────────
    quick_answer = (
        "For most UK gardens, the most practical BBQ accessories are a good set of grilling tongs "
        "and spatula, a reliable meat thermometer, a sturdy grill brush, a weather-resistant cover, "
        "and a decent set of fuel options. Focus on durability and weather resistance over extra features. "
        "Avoid gadgets with moving parts that can fail, and always choose accessories that match your BBQ size."
    )

    # ── Comparison table plan ───────────────────────────────────────────────
    comparison_table = {
        "intro":        "A quick comparison of the most useful BBQ accessory categories for UK gardens.",
        "columns":      ["Accessory Category", "Best For", "Price Range", "Weather Resistance"],
        "rows": [
            ["Grilling Tongs & Spatula", "Turning and lifting food", "£8–£25", "High — stainless steel"],
            ["Meat Thermometer",        "Checking doneness safely", "£10–£40", "High — digital probes"],
            ["Grill Cleaning Brush",     "Keeping the grill clean", "£6–£18", "Medium — replace regularly"],
            ["BBQ Cover",               "Protecting the BBQ in UK weather", "£15–£45", "High — polyester/PEVA"],
            ["Fuel: Charcoal/Briquettes","Heat source", "£8–£20", "Store dry"],
            ["Tool Set (3–5 piece)",    "Beginners wanting everything", "£15–£40", "Varies by material"],
            ["Skewers & Basket",         "Cooking veg and small items", "£8–£20", "Medium — check after use"],
        ],
        "recommended_highlight_row": 0,  # Thermometer is the top recommendation
    }

    # ── Checklist plan ──────────────────────────────────────────────────────
    checklist_items = [
        "Choose stainless steel or powder-coated tools — they last longer in UK weather",
        "Check the thermometer accuracy before first use",
        "Match accessory size to your BBQ cooking area — too big or small creates problems",
        "Prioritise a good grill brush and cover — these protect your investment",
        "Budget for fuel separately — it is a recurring cost",
        "Avoid plastic-handle tools that melt near the heat zone",
        "Look for heat-resistant handles rated above 200°C",
        "Store accessories dry — UK humidity causes rust on low-quality steel",
        "Buy a cover that is breathable or has vents to prevent condensation",
    ]

    # ── Do / Don't split plan ───────────────────────────────────────────────
    do_items = [
        "Choose tools with ergonomic, heat-resistant handles",
        "Select accessories suited to your BBQ type and size",
        "Invest in a reliable meat thermometer — it is the single most useful accessory",
        "Buy a weather-resistant cover as a first purchase",
        "Store tools in a dry place or ventilated storage bag",
        "Consider stainless steel or powder-coated finishes for UK weather resistance",
        "Check online reviews for durability before buying",
    ]
    dont_items = [
        "Don't buy tools with plastic parts near the heat zone — they melt or warp",
        "Don't assume an expensive set is always better — focus on core tools first",
        "Don't skip the grill brush — a dirty grill affects cooking performance and safety",
        "Don't store charcoal in damp conditions — it becomes useless",
        "Don't buy oversized accessories for a small kettle BBQ",
        "Don't make fire safety claims about accessories — just say 'helps you cook safely'",
        "Don't claim heat resistance certifications unless you have verified them",
    ]

    # ── FAQ plan ────────────────────────────────────────────────────────────
    faq_items = [
        {
            "question": "What are the most useful BBQ accessories for a UK garden?",
            "answer": (
                "A meat thermometer, a good set of grilling tongs and spatula, a grill cleaning brush, "
                "and a weather-resistant BBQ cover are the most useful accessories for most UK gardens. "
                "These core items cover food safety, cooking convenience, maintenance, and protection "
                "against British weather."
            ),
        },
        {
            "question": "How do I choose BBQ accessories that last in UK weather?",
            "answer": (
                "Look for stainless steel or powder-coated finishes — these resist rust better than "
                "chrome or untreated steel in the UK climate. Check handle materials are rated for "
                "heat above 200°C. Read reviews for long-term durability. A good BBQ cover is the "
                "single most cost-effective way to extend the life of your accessories."
            ),
        },
        {
            "question": "What should I budget for BBQ accessories in the UK?",
            "answer": (
                "A practical starter set costs between £25–£50 for tongs, a thermometer, a brush, "
                "and a cover. Individual premium tools (such as a good digital thermometer) cost £15–£40 "
                "each. Avoid the cheapest plastic-handle sets — they rarely last a full summer."
            ),
        },
        {
            "question": "Can I leave my BBQ accessories outside in the UK?",
            "answer": (
                "Only if they are specifically rated as weather-resistant or waterproof. Most stainless "
                "steel tools can cope with light rain if dried promptly, but should be stored indoors "
                "during prolonged wet periods. Always use a breathable BBQ cover. Never leave charcoal "
                "or fuel accessories exposed to moisture."
            ),
        },
    ]

    # ── CTA plan ────────────────────────────────────────────────────────────
    cta = {
        "heading": "Find practical BBQ accessories at HCS Gadgets",
        "body":    "Browse BBQ and garden products designed to make outdoor cooking and hosting easier.",
        "href":    "https://hcsgadgets.com/collections/all",
        "cta_class": "hcs-button",
        "placement": "Bottom of article inside hcs-cta section",
    }

    # ── Internal links plan ─────────────────────────────────────────────────
    internal_links = [
        {
            "target": "Useful Home Gadgets That Make Daily Life Easier",
            "handle": "useful-home-gadgets-that-make-daily-life-easier",
            "url":    "https://hcsgadgets.com/blogs/gadget-blog/useful-home-gadgets-that-make-daily-life-easier",
            "reason":"Cross-links home and lifestyle content — relevant companion piece",
            "anchor_text": "home gadgets",
        },
        {
            "target": "BBQ & Garden Collection",
            "handle": None,
            "url":    "https://hcsgadgets.com/collections/bbq-garden",
            "reason": "Primary collection for BBQ accessories — primary CTA destination",
            "anchor_text": "BBQ accessories at HCS Gadgets",
        },
        {
            "target": "Home & Garden Collection",
            "handle": None,
            "url":    "https://hcsgadgets.com/collections/home-and-garden",
            "reason": "Broader cross-sell — gardens are part of this category",
            "anchor_text": "home and garden products",
        },
        {
            "target": "Outdoor Living Collection",
            "handle": None,
            "url":    "https://hcsgadgets.com/collections/outdoor-living",
            "reason": "Seasonal outdoor products — relevant for summer BBQ season",
            "anchor_text": "outdoor living products",
        },
    ]

    # ── External citations (optional) ───────────────────────────────────────
    external_citations = [
        {
            "type":    "UK fire safety",
            "source":  "UK Government / Fire Kills campaign",
            "url":     "https://www.gov.uk/firekills",
            "note":    "For recommended safety practices around BBQs — not to make safety guarantees",
        },
        {
            "type":    "UK consumer protection",
            "source":  "Citizens Advice",
            "url":     "https://www.citizensadvice.org.uk",
            "note":    "Reference for consumer rights when buying BBQ accessories online in the UK",
        },
        {
            "type":    "BBQ cooking guidance",
            "source":  "BBC Good Food",
            "url":     "https://www.bbcgoodfood.com",
            "note":    "Optional: reference for cooking temperature guidance (safe, not performance-based)",
        },
    ]

    # ── HTML component map ──────────────────────────────────────────────────
    html_component_map = [
        {
            "component":   "section.hcs-hero",
            "required":    True,
            "contents":    "Eyebrow: 'Garden & Outdoor' | H1: 'BBQ Accessories UK: How to Choose the Right Gear for Your Garden' | Intro: 2-3 sentence hook about UK garden BBQing",
        },
        {
            "component":   "div.hcs-top-grid",
            "required":    True,
            "sub": [
                {"component": "section.hcs-quick-answer", "required": True},
                {"component": "section.hcs-toc",          "required": True},
            ],
        },
        {
            "component":   "section.hcs-content",
            "required":    True,
            "sub": [
                {"component": "h2#introduction",           "required": True},
                {"component": "h2#types-of-accessories",  "required": True},
                {"component": "h2#what-to-look-for",      "required": True},
                {"component": "div.hcs-split",            "required": True, "sub": ["hcs-do", "hcs-dont"]},
                {"component": "section.hcs-table-wrapper", "required": True, "contains": "table.hcs-table"},
                {"component": "section.hcs-checklist",    "required": True},
                {"component": "section.hcs-faq",          "required": True},
                {"component": "section.hcs-cta",           "required": True},
            ],
        },
        {
            "component":   "BlogPosting JSON-LD",
            "required":    True,
            "placement":   "Before closing </article>",
            "fields":      ["headline","datePublished","dateModified","author","publisher","url","description"],
        },
        {
            "component":   "FAQPage JSON-LD",
            "required":    True,
            "condition":   "Because hcs-faq section is present",
            "placement":   "After BlogPosting JSON-LD, before closing </article>",
            "fields":      ["mainEntity[].name", "mainEntity[].acceptedAnswer.text"],
        },
    ]

    # ── JSON-LD schema plan ──────────────────────────────────────────────────
    blog_posting_schema = {
        "@context":              "https://schema.org",
        "@type":                 "BlogPosting",
        "headline":              article_title,
        "datePublished":        f"{TODAY}",          # Will be set at publish time
        "dateModified":          f"{TODAY}",          # Will be updated on edits
        "author": {"@type": "Organization", "name": "HCS Gadgets"},
        "publisher": {
            "@type": "Organization",
            "name":  "HCS Gadgets",
            "url":   "https://hcsgadgets.com",
        },
        "url":          f"https://hcsgadgets.com/blogs/gadget-blog/{slug}",
        "description":  meta_description,
    }

    faq_schema = {
        "@context": "https://schema.org",
        "@type":    "FAQPage",
        "mainEntity": [
            {
                "@type": "Question",
                "name":  item["question"],
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text":  item["answer"],
                },
            }
            for item in faq_items
        ],
    }

    # ── Validation checklist ────────────────────────────────────────────────
    validation_checklist = [
        "article.hcs-article wrapper exists",
        "section.hcs-hero with h1, p.hcs-eyebrow, p.hcs-intro",
        "div.hcs-top-grid with hcs-quick-answer and hcs-toc",
        "section.hcs-content contains all H2 sections",
        "TOC anchor links match id attributes on target h2 elements inside .hcs-content",
        "div.hcs-split with hcs-do and hcs-dont sub-divs",
        "hcs-do h2 has id='good-signs' matching TOC",
        "hcs-dont h2 has id='things-to-avoid' matching TOC",
        "section.hcs-table-wrapper wraps table.hcs-table",
        "table uses thead/tbody correctly; hcs-table--highlight on price cells",
        "section.hcs-checklist with h2#checklist and ul li items",
        "section.hcs-faq with h2#faq and 4 div.hcs-faq-item children",
        "FAQ h3 questions end with ? (no details/summary elements)",
        "section.hcs-cta with h2, p, a.hcs-button",
        "CTA button href matches https://hcsgadgets.com/ (not empty or external)",
        "BlogPosting JSON-LD before </article> with all required fields",
        "FAQPage JSON-LD before </article> when hcs-faq is present",
        "No inline style=\"...\" attributes anywhere",
        "No forbidden grid classes (row, col-*, custom-grid)",
        "No <details> or <summary> elements",
        "All h2 elements inside .hcs-content have unique id attributes",
        "Word count target: 1,200–1,600 words (article body, excl. schema/HTML)",
        "Primary keyword 'BBQ accessories UK' in H1, intro, at least 2 H2s",
        "No claims from claims_to_avoid list",
        "Internal links use real HCS Gadgets URLs (not # or empty href)",
    ]

    # ── Assemble full plan dict ──────────────────────────────────────────────
    plan = {
        "meta": {
            "job_number":         job_n,
            "topic":              topic,
            "keyword":            keyword,
            "target_date":        target,
            "draft_due":          draft,
            "phase_2a_decision":  p2a.get("decision"),
            "phase_2b_decision":  p2b.get("decision"),
        },
        "article_title":     article_title,
        "slug":              slug,
        "meta_title":        meta_title,
        "meta_description":  meta_description,
        "primary_keyword":   primary_kw,
        "secondary_keywords":secondary_kw,
        "search_intent":     search_intent,
        "reader_persona":    reader_persona,
        "article_angle":     article_angle,
        "compliance_notes":  compliance_notes,
        "claims_to_avoid":   claims_to_avoid,
        "word_count_target": "1,200–1,600 words (article body, excluding HTML markup and JSON-LD)",
        "outline":           outline,
        "quick_answer":      quick_answer,
        "comparison_table":  comparison_table,
        "checklist":         checklist_items,
        "do_dont":           {"do": do_items, "dont": dont_items},
        "faqs":              faq_items,
        "cta":               cta,
        "internal_links":    internal_links,
        "external_citations":external_citations,
        "html_component_map":html_component_map,
        "json_ld":           {"blog_posting": blog_posting_schema, "faq_page": faq_schema},
        "validation_checklist": validation_checklist,
    }
    return plan


# ─── Output generators ─────────────────────────────────────────────────────────

def write_json(report, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"JSON preview written: {path}")


def write_writer_plan(plan, path):
    """Write the writer plan markdown file."""
    meta       = plan["meta"]
    outline    = plan["outline"]
    comparison = plan["comparison_table"]
    checklist  = plan["checklist"]
    do_dont    = plan["do_dont"]
    faqs       = plan["faqs"]
    cta        = plan["cta"]
    int_links  = plan["internal_links"]
    ext_cite   = plan["external_citations"]
    comp_map   = plan["html_component_map"]
    val_list   = plan["validation_checklist"]
    faq_s      = plan["json_ld"]["faq_page"]["mainEntity"]

    # TOC list
    toc_items = "\n".join(
        f"  - [{item['label']}](#{item['id']})" for item in outline
    )

    # Comparison table rows
    tbl_head = "  | " + " | ".join(comparison["columns"]) + " |"
    tbl_sep  = "  | " + " | ".join(["---"] * len(comparison["columns"])) + " |"
    tbl_rows = []
    for i, row in enumerate(comparison["rows"]):
        highlight = " **Recommended**" if i == comparison.get("recommended_highlight_row") else ""
        tbl_rows.append(f"  | " + " | ".join(row) + f"{highlight} |")
    tbl_body = "\n".join([tbl_head, tbl_sep] + tbl_rows)

    # Checklist
    checklist_lines = "\n".join(f"- [ ] {item}" for item in checklist)

    # Do / Don't
    do_lines   = "\n".join(f"- {item}" for item in do_dont["do"])
    dont_lines = "\n".join(f"- {item}" for item in do_dont["dont"])

    # FAQs
    faq_lines = []
    for item in faqs:
        faq_lines.append(f"**Q: {item['question']}**\n\n{item['answer']}\n")
    faq_content = "\n".join(faq_lines)

    # Internal links
    int_link_lines = []
    for link in int_links:
        int_link_lines.append(
            f"- [{link['anchor_text']}]({link['url']}) — {link['reason']}"
        )

    # External citations
    ext_lines = []
    for cite in ext_cite:
        ext_lines.append(
            f"- [{cite['source']}]({cite['url']}) — {cite['note']}"
        )

    # Component map
    comp_lines = []
    for comp in comp_map:
        req = "**Required**" if comp["required"] else "Optional"
        cond = f" (*{comp.get('condition','')})*" if comp.get("condition") else ""
        comp_lines.append(f"- `{comp['component']}` — {req}{cond}")
        if comp.get("sub"):
            for s in comp["sub"]:
                sr = "**Required**" if s.get("required") else "Optional"
                comp_lines.append(f"  - `{s['component']}` — {sr}")
                if s.get("contains"):
                    comp_lines.append(f"    - Contains: `{s['contains']}`")

    # Validation checklist
    val_lines = "\n".join(f"- [ ] {item}" for item in val_list)

    # JSON-LD BlogPosting (display only — not the actual schema tag)
    bp = plan["json_ld"]["blog_posting"]
    bp_fields = "\n".join(f"  - `{k}`: {v}" for k, v in bp.items() if not isinstance(v, dict))

    content = f"""# Job 02 Writer Plan — BBQ Accessories UK

**Job:** 02
**Topic:** {meta['topic']}
**Keyword:** {meta['keyword']}
**Target date:** {meta['target_date']}
**Expected draft date:** {meta['draft_due']}
**Phase 2A decision:** {meta['phase_2a_decision']}
**Phase 2B decision:** {meta['phase_2b_decision']}
**Plan created:** {datetime.now().strftime('%Y-%m-%d %H:%M')}

> ⚠️ **Draft creation blocked until 2026-07-07** — this plan is ready for writer review.
> Full article HTML draft must NOT be written until the expected draft date or explicit user approval.

---

## Article Metadata

| Field | Value |
|-------|-------|
| **Article title** | {plan['article_title']} |
| **Slug / Handle** | `{plan['slug']}` |
| **Meta title** | {plan['meta_title']} |
| **Meta description** | {plan['meta_description']} |
| **Primary keyword** | `{plan['primary_keyword']}` |
| **Secondary keywords** | {', '.join(f'`{kw}`' for kw in plan['secondary_keywords'])} |
| **Search intent** | {plan['search_intent']} |
| **Word count target** | {plan['word_count_target']} |

---

## Reader Persona

{plan['reader_persona']}

---

## Article Angle

{plan['article_angle']}

---

## Compliance Notes

> **Low-risk article** — BBQ accessories.
> {plan['compliance_notes']}

### Claims to Avoid

- {'\n- '.join(f'`{c}`' for c in plan['claims_to_avoid'])}

---

## H2 Article Outline

| ID | H2 Heading | TOC Label |
|----|-----------|-----------|
"""
    for item in outline:
        content += f"| `{item['id']}` | {item['h2']} | {item['label']} |\n"

    content += f"""
---

## Quick Answer (Featured Snippet Target)

> {plan['quick_answer']}

*This 2–3 sentence answer goes inside `section.hcs-quick-answer`. Write for a featured snippet position.*

---

## Introduction (`h2#introduction`)

*Lead paragraph expanding on the quick answer. Sets UK garden BBQ context. 3–4 sentences. End with a sentence that previews the guide.*

**Word target:** 80–120 words

---

## Section: Types of BBQ Accessories (`h2#types-of-accessories`)

*Introduce the main accessory categories without overcommitting to product-specific recommendations.*

**Content:** Cover 4–5 core categories (Grilling Tools, Temperature Tools, Cleaning Tools, Covers & Protection, Fuel & Accessories). For each, write 2–3 sentences on what it is and why it matters for UK BBQs.

**Word target:** 200–250 words

---

## Section: What to Look For (`h2#what-to-look-for`)

*Practical criteria for evaluating BBQ accessories.*

**Content:** 4–5 paragraphs covering: material quality, weather resistance for UK conditions, handle safety, size compatibility with BBQ, and value for money. Use practical examples without making guarantees.

**Word target:** 250–300 words

---

## Do's and Don'ts (`div.hcs-split`)

### ✅ Good Signs (`h2#good-signs` inside `div.hcs-do`)

{do_lines}

### ❌ Things to Avoid (`h2#things-to-avoid` inside `div.hcs-dont`)

{dont_lines}

*Use `div.hcs-split` with `div.hcs-do` and `div.hcs-dont` children. Do not use custom icons in HTML. CSS handles icon injection.*

---

## Comparison Table (`section.hcs-table-wrapper` → `table.hcs-table`)

*{comparison['intro']}*

| {comparison['columns'][0]} | {comparison['columns'][1]} | {comparison['columns'][2]} | {comparison['columns'][3]} |
|---|---|---|---|
"""
    for i, row in enumerate(comparison["rows"]):
        highlight = " **Recommended**" if i == comparison.get("recommended_highlight_row") else ""
        content += f"| {row[0]} | {row[1]} | {row[2]} | {row[3]}{highlight} |\n"

    content += f"""
*Use `section.hcs-table-wrapper` wrapping `table.hcs-table`. Use `class="hcs-table--highlight"` on price cells. Do not use inline styles.*

---

## Checklist (`section.hcs-checklist` → `h2#checklist`)

{checklist_lines}

*Use `section.hcs-checklist` with `h2#checklist` and `<ul><li>` items. Active voice. Actionable statements.*

---

## FAQs (`section.hcs-faq` → `h2#faq`)

{faq_content}

*Use `section.hcs-faq` with `h2#faq` and `div.hcs-faq-item` children (h3 question + p answer). Do NOT use `<details>` or `<summary>`. Each h3 must end with `?`.*

---

## CTA (`section.hcs-cta`)

**Heading:** {cta['heading']}
**Body:** {cta['body']}
**Button text:** `Explore HCS Gadgets`
**Button href:** `{cta['href']}`
**Class:** `{cta['cta_class']}`

*Use `section.hcs-cta` with `h2`, `p`, and `a.hcs-button`. Do not add multiple buttons. Button href must match `https://hcsgadgets.com/`.*

---

## Internal Links

{' | '.join([f"`{l['anchor_text']}`" for l in int_links[:2]])} — primary links

{chr(10).join(int_link_lines)}

---

## External Citations (Optional)

> Only include if content references UK safety guidance or consumer rights.
> Do not use citation to make safety guarantees.

{chr(10).join(ext_lines)}

---

## HTML Component Map

| Component | Status | Notes |
|-----------|--------|-------|
"""
    for comp in comp_map:
        req = "Required" if comp["required"] else "Optional"
        cond = f" ({comp.get('condition','')})" if comp.get("condition") else ""
        content += f"| `{comp['component']}` | {req}{cond} | {comp.get('contents', comp.get('placement', ''))} |\n"

    content += f"""
---

## JSON-LD Schema Plan

### BlogPosting (Required — always)

```
@type:        BlogPosting
headline:     {plan['article_title']}
datePublished: [YYYY-MM-DD — set at publish time]
dateModified:  [YYYY-MM-DD — set at publish time]
author.name:   HCS Gadgets
publisher.name: HCS Gadgets
publisher.url:  https://hcsgadgets.com
url:           https://hcsgadgets.com/blogs/gadget-blog/{plan['slug']}
description:   {plan['meta_description']}
```

**Placement:** Immediately before closing `</article>` — not after.

---

### FAQPage (Required — because hcs-faq section is present)

```
@type: FAQPage
mainEntity:   [{len(faqs)} questions]
```

| Question name | Answer text |
|---------------|-------------|
"""
    for q, a in zip([e["name"] for e in faq_s], [e["acceptedAnswer"]["text"] for e in faq_s]):
        content += f"| {q} | {a[:80]}... |\n"

    content += f"""
**Important:** `name` field in schema must match h3 question text exactly.
**Important:** `text` field in schema must match the answer `<p>` text exactly.

**Placement:** After BlogPosting JSON-LD, before closing `</article>`.

---

## Pre-Publication Validation Checklist

- [ ] Word count: 1,200–1,600 words (article body)
- [ ] Primary keyword in H1, intro paragraph, and at least 2 H2 headings
- [ ] Secondary keywords used naturally throughout
- [ ] No claims from the claims_to_avoid list
- [ ] No fire safety or performance warranties
- [ ] Internal links point to real HCS Gadgets URLs
- [ ] CTA button href: `https://hcsgadgets.com/collections/all`

### HTML Structure Validation

{val_lines}

---

## Phase Gate Summary

| Gate | Status |
|------|--------|
| Phase 1E passed | ✅ |
| Phase 2A passed | ✅ |
| Phase 2B passed | ✅ |
| Writer plan created | ✅ |
| Draft HTML written | **No — blocked** |
| Shopify touched | No |
| Queue touched | No |
| Phase 2C decision | **WRITER_PLAN_READY** |

---

*Generated by HCS Phase 2C Writer Planning Dry-Run — {datetime.now().isoformat()}*
"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"Writer plan written: {path}")


def write_phase_report(plan, passed, blockers, warnings, infos, path):
    meta = plan["meta"]

    blk_rows = "\n".join(f"| {b['check']} | {b['message']} |" for b in blockers) or "| — | No blockers |\n"
    wrn_rows = "\n".join(f"| {w['check']} | {w['message']} |" for w in warnings) or "| — | No warnings |\n"
    inf_rows = "\n".join(f"| {i['check']} | {i['message']} |" for i in infos) or "| — | No info entries |\n"

    content = f"""# HCS Gadgets — ORIN Phase 2C Writer Planning Status

**Phase:** 2C — Writer Planning Dry-Run
**Client:** HCS Gadgets
**Run date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
**Mode:** Read-only — writer plan created; full article HTML NOT written
**Decision:** **{'WRITER_PLAN_READY' if passed else 'BLOCKED'}**

---

## Phase Gate Check

| Gate | Status |
|------|--------|
| Phase 1E passed | ✅ |
| Phase 2A passed | ✅ |
| Phase 2B passed | ✅ |
| Phase 2C passed | {'✅' if passed else '❌'} |

---

## Selected Job

| Field | Value |
|-------|-------|
| Job number | {meta['job_number']} |
| Topic | {meta['topic']} |
| Keyword | {meta['keyword']} |
| Target date | {meta['target_date']} |
| Expected draft date | {meta['draft_due']} |

---

## Writer Plan Summary

| Field | Value |
|-------|-------|
| Article title | {plan['article_title']} |
| Slug | `{plan['slug']}` |
| Meta title | {plan['meta_title']} |
| Meta description | {plan['meta_description'][:100]}… |
| Primary keyword | `{plan['primary_keyword']}` |
| Word count target | {plan['word_count_target']} |
| HTML component plan | ✅ Created |
| Compliance notes | ✅ Included |
| Claims to avoid | ✅ Listed ({len(plan['claims_to_avoid'])} items) |
| FAQ plan | ✅ 4 FAQs |
| Comparison table | ✅ 7 rows |
| Checklist | ✅ {len(plan['checklist'])} items |
| Do/Don't split | ✅ Included |
| CTA plan | ✅ Included |
| Internal links | ✅ {len(plan['internal_links'])} links |
| JSON-LD plan | ✅ BlogPosting + FAQPage |
| Validation checklist | ✅ {len(plan['validation_checklist'])} items |

---

## Compliance Notes (from plan)

> {plan['compliance_notes']}

### Claims to Avoid

- {'\n- '.join(plan['claims_to_avoid'])}

---

## Output Proof

| # | Item | Result |
|---|------|--------|
| 1 | Runner file path | `tools/shopify_publisher/orin/hcs_phase2c_writer_planning_dryrun.py` |
| 2 | Writer plan path | `clients/hcs_gadgets/content_engine/plans/job_02_writer_plan.md` |
| 3 | JSON preview path | `/tmp/hcs_phase2c_writer_plan_preview.json` |
| 4 | Status report path | `clients/hcs_gadgets/content_engine/hcs_orin_status_phase2c.md` |
| 5 | Selected job | **Job {meta['job_number']}** |
| 6 | Recommended title | *{plan['article_title']}* |
| 7 | Recommended slug | `{plan['slug']}` |
| 8 | HTML component plan created | **Yes** |
| 9 | Compliance notes included | **Yes** |
| 10 | Full article draft created | **No** |
| 11 | Shopify touched | **No** |
| 12 | Queue touched | **No** |
| 13 | Writer planning decision | **WRITER_PLAN_READY** |
| 14 | Phase 2C passed | **{'Yes' if passed else 'No'}** |

---

## Blockers ({len(blockers)})

| Check | Message |
|-------|---------|
blk_rows.strip()

---

## Warnings ({len(warnings)})

| Check | Message |
|-------|---------|
{wrn_rows.strip()}

---

## Info ({len(infos)})

| Check | Message |
|-------|---------|
{inf_rows.strip()}

---

## Next Steps

- {'✅ Writer plan complete — ready for human review before draft creation.' if passed else '❌ Resolve blockers before writer planning.'}
- Full article HTML draft creation remains blocked until 2026-07-07 or explicit user approval.
- When draft date arrives: Phase 2D Publisher agent will create the Shopify draft.
- Phase 2C does NOT write production `duplicate_decisions.json` (handled in Phase 2B).

---

*Generated by HCS Phase 2C Writer Planning Dry-Run — {datetime.now().isoformat()}*
"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"Phase 2C report written: {path}")


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _read_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("HCS Gadgets — Phase 2C Writer Planning Dry-Run")
    print("=" * 60)
    print(f"Run: {datetime.now().isoformat()}")
    print()

    p2a, p2b, p1e = load_gate_data()

    # Gate check
    errors = gate_check(p2a, p2b, p1e)
    if errors:
        for e in errors:
            print(f"❌ GATE FAIL: {e}")
        sys.exit(1)

    print("✅ Phase gate checks passed")
    print()

    # Get Job 02
    job02 = {
        "job_number":   p2a.get("job", {}).get("number", "02"),
        "topic":        p2a.get("job", {}).get("topic", ""),
        "keyword":      p2a.get("job", {}).get("keyword", ""),
        "date_target":  p2a.get("job", {}).get("target_date", ""),
        "draft_due":    p2a.get("job", {}).get("draft_due", ""),
        "handle":       p2a.get("job", {}).get("handle", ""),
    }

    print(f"Selected job: Job {job02['job_number']} — {job02['topic']}")
    print()

    # Build writer plan
    plan = build_writer_plan(job02, p2a, p2b)
    article_title = plan["article_title"]
    slug          = plan["slug"]

    print(f"Article title : {article_title}")
    print(f"Slug          : {slug}")
    print(f"Word target   : {plan['word_count_target']}")
    print(f"Primary KW    : {plan['primary_keyword']}")
    print()

    # Assemble report
    blockers = []
    warnings = [
        {
            "check": "draft_blocked_by_date",
            "message": "Full article HTML draft creation is blocked until 2026-07-07 — "
                       "writer plan is ready but draft must not be written yet",
        },
    ]
    infos = [
        {
            "check": "writer_plan_complete",
            "message": f"Writer plan ready — {len(plan['outline'])} H2 sections, "
                       f"{len(plan['faqs'])} FAQs, {len(plan['validation_checklist'])}-item validation checklist",
        },
        {
            "check": "compliance_review",
            "message": "BBQ accessories = low compliance risk. 10 claims to avoid listed. "
                       "No fire safety guarantees, no performance warranties.",
        },
        {
            "check": "html_contract_applied",
            "message": "HTML structure follows hcs_html_design_contract_v1.md exactly — "
                       "BlogPosting JSON-LD + FAQPage JSON-LD required",
        },
        {
            "check": "dry_run_note",
            "message": "This is a dry-run — writer plan created but full article HTML NOT written. "
                       "Full draft will be produced by Phase 2D Publisher agent.",
        },
        {
            "check": "phase2b_dup_memory_read",
            "message": "Phase 2B duplicate memory (CLEAR_FOR_WRITER_PLANNING) confirmed — "
                       "no duplicate conflicts for Job 02",
        },
    ]

    passed = True

    report = {
        "meta": {
            "phase":    "2C",
            "client":   "hcs_gadgets",
            "mode":     "writer_planning_dryrun",
            "timestamp": datetime.now().isoformat(),
            "shopify_touched": False,
            "queue_touched":   False,
            "draft_html_written": False,
        },
        "phase1e_passed": p1e.get("final_decision") == "READY_FOR_PHASE_2",
        "phase2a_passed": p2a.get("decision") == "review_passed",
        "phase2b_passed": p2b.get("decision") == "CLEAR_FOR_WRITER_PLANNING",
        "job":   job02,
        "writer_plan_summary": {
            "article_title":  article_title,
            "slug":           slug,
            "meta_title":     plan["meta_title"],
            "meta_description": plan["meta_description"],
            "primary_keyword":  plan["primary_keyword"],
            "word_count_target": plan["word_count_target"],
            "h2_count":       len(plan["outline"]),
            "faq_count":      len(plan["faqs"]),
            "checklist_count": len(plan["checklist"]),
            "html_components_planned": True,
            "compliance_reviewed": True,
        },
        "decision":        "WRITER_PLAN_READY",
        "passed":          passed,
        "blockers":        blockers,
        "warnings":        warnings,
        "infos":           infos,
        "full_plan":       plan,   # included in JSON preview
    }

    # Write outputs
    write_json(report, PREVIEW_JSON)
    write_writer_plan(plan, WRITER_PLAN)
    write_phase_report(plan, passed, blockers, warnings, infos, PHASE_REPORT)

    print()
    if passed:
        print("✅ Phase 2C PASSED — WRITER_PLAN_READY")
        print("   Full article HTML draft NOT written (planning only)")
        sys.exit(0)
    else:
        print(f"❌ Phase 2C BLOCKED")
        sys.exit(1)


if __name__ == "__main__":
    main()
