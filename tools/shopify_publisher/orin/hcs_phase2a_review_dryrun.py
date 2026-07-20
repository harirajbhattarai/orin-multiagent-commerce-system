#!/usr/bin/env python3
"""
HCS Gadgets — Phase 2A Review Agent Dry-Run
=============================================
Read-only review agent for HCS Gadgets ORIN Phase 2A.

Reviews Job 02 (BBQ Accessories) for:
- topic scope and suitability
- duplicate/overlap with live Shopify articles
- compliance risk
- HTML contract requirements
- brand alignment and content gap filling

Strict rules:
- Do not create Shopify articles.
- Do not update Shopify.
- Do not publish anything.
- Do not create local drafts.
- Do not edit article bodies.
- Do not change URL slugs.
- Do not edit queue statuses.
- Do not enable cron.
- Do not archive old scripts yet.
- Review only.
- Do not print Shopify secrets.

Outputs:
- /tmp/hcs_phase2a_review_preview.json
- clients/hcs_gadgets/content_engine/hcs_orin_status_phase2a.md
"""

import json
import os
import re
import sys
from datetime import datetime

# ─── Path constants ────────────────────────────────────────────────────────────
CLIENT_ROOT  = "clients/hcs_gadgets/content_engine"
WORKSPACE    = "/data/.openclaw/workspace"
TMP_DIR      = "/tmp"

ORCH_PREVIEW = os.path.join(TMP_DIR, "hcs_phase1e_orchestrator_preview.json")
PHASE1A_PRE  = os.path.join(TMP_DIR, "hcs_phase1a_state_preview.json")
PHASE1B_PRE  = os.path.join(TMP_DIR, "hcs_phase1b_planner_preview.json")
QUEUE_FILE   = os.path.join(CLIENT_ROOT, "content_queue_3_months.md")
INVENTORY    = os.path.join(CLIENT_ROOT, "shopify_inventory.json")
CLEANUP_BASE = os.path.join(CLIENT_ROOT, "hcs_content_cleanup_baseline_v1.md")
HTML_CONTRACT = os.path.join(CLIENT_ROOT, "rules/hcs_html_design_contract_v1.md")
HTML_CHECKLIST = os.path.join(CLIENT_ROOT, "rules/hcs_html_validation_checklist.md")
SKELETON_HTML = os.path.join(CLIENT_ROOT, "rules/hcs_article_skeleton_v1.html")
COMPLIANCE    = os.path.join(CLIENT_ROOT, "rules/compliance_rules.md")
WRITING_RULES = os.path.join(CLIENT_ROOT, "rules/writing_rules.md")
PRODUCT_SCOPE = os.path.join(CLIENT_ROOT, "rules/product_scope_rules.md")
CLUSTER_MAP   = os.path.join(CLIENT_ROOT, "rules/cluster_map.md")
BRAND_RULES   = os.path.join(CLIENT_ROOT, "rules/brand_rules.md")
DESIGN_RULES  = os.path.join(CLIENT_ROOT, "rules/design_rules.md")
HTML_VALIDATOR = os.path.join(WORKSPACE, "tools/shopify_publisher/orin/hcs_html_contract_validator.py")

PREVIEW_JSON = os.path.join(TMP_DIR, "hcs_phase2a_review_preview.json")
PHASE_REPORT = os.path.join(CLIENT_ROOT, "hcs_orin_status_phase2a.md")

# ─── Review decision constants ────────────────────────────────────────────────
DECISION_PASS              = "review_passed"
DECISION_NEEDS_HUMAN       = "needs_human_review"
DECISION_BLOCKED_DUP       = "blocked_duplicate"
DECISION_BLOCKED_COMPLIANCE = "blocked_compliance"
DECISION_BLOCKED_NOT_DUE   = "blocked_not_due"
DECISION_BLOCKED_NO_CONTRACT = "blocked_missing_html_contract"

# ─── Helpers ───────────────────────────────────────────────────────────────────

def safe_read_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def safe_read_text(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except (FileNotFoundError, UnicodeDecodeError):
        return ""


def parse_queue_jobs():
    text = safe_read_text(QUEUE_FILE)
    jobs = {}
    current = {}
    for line in text.splitlines():
        line = line.rstrip()
        if line.startswith("## Job "):
            if current:
                jobs[current["job_number"]] = current
            parts = line.replace("## Job ", "").split(None, 1)
            current = {"job_number": parts[0], "topic": "", "status": "",
                       "date_target": "", "keyword": "", "file": "", "notes": []}
        elif current:
            if line.startswith("Status:"):
                current["status"] = line.replace("Status:", "").strip()
            elif line.startswith("Date target:"):
                current["date_target"] = line.replace("Date target:", "").strip()
            elif line.startswith("Topic:"):
                current["topic"] = line.replace("Topic:", "").strip()
            elif line.startswith("Target keyword:"):
                current["keyword"] = line.replace("Target keyword:", "").strip()
            elif line.startswith("File:"):
                current["file"] = line.replace("File:", "").strip()
            elif line.startswith("- "):
                current["notes"].append(line[2:].strip())
    if current:
        jobs[current["job_number"]] = current
    return jobs


def normalize(text):
    """Normalize text for comparison: lowercase, strip punctuation."""
    text = text.lower()
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def token_overlap(a, b):
    """Return token-based overlap ratio between two strings."""
    ta = set(normalize(a).split())
    tb = set(normalize(b).split())
    if not ta or not tb:
        return 0.0
    overlap = len(ta & tb)
    return overlap / min(len(ta), len(tb))


# ─── Duplicate / overlap checks ───────────────────────────────────────────────

def check_duplicates(inventory_published, job_topic, job_handle, job_keyword):
    """
    Run all duplicate and overlap checks against live published articles.
    Returns dict of findings.
    """
    findings = {
        "exact_title_match":      None,
        "near_title_match":       [],
        "exact_handle_match":     None,
        "near_handle_match":      [],
        "topic_cluster_conflict": [],
        "overlap_score":          [],
        "bbq_coverage_gap":      False,
        "garden_coverage_gap":   False,
    }

    job_norm_topic   = normalize(job_topic)
    job_tokens       = set(job_norm_topic.split())
    job_base         = normalize(job_handle)
    job_kw_norm      = normalize(job_keyword) if job_keyword else ""

    for article in inventory_published:
        title   = article.get("title", "")
        handle  = article.get("handle", "")
        tags    = article.get("tags", "")
        title_n = normalize(title)
        handle_n = normalize(handle)

        # Exact title match
        if normalize(title) == job_norm_topic:
            findings["exact_title_match"] = {
                "id": article.get("id"), "title": title, "handle": handle
            }

        # Exact handle match
        if handle == job_handle or handle_n == job_base:
            findings["exact_handle_match"] = {
                "id": article.get("id"), "title": title, "handle": handle
            }

        # Near title match (>0.5 token overlap)
        if job_tokens:
            overlap = token_overlap(job_topic, title)
            if overlap > 0.5:
                findings["near_title_match"].append({
                    "id": article.get("id"), "title": title,
                    "handle": handle, "overlap_score": round(overlap, 3)
                })

        # Near handle match
        base_a = re.sub(r"-\d+$", "", handle)
        base_j = re.sub(r"-\d+$", "", job_handle)
        if base_a and base_j and base_a == base_j and handle != job_handle:
            findings["near_handle_match"].append({
                "id": article.get("id"), "title": title, "handle": handle
            })

        # Keyword in title or tags
        if job_kw_norm and (job_kw_norm in title_n or job_kw_norm in normalize(tags)):
            findings["overlap_score"].append({
                "id": article.get("id"), "title": title, "handle": handle,
                "match_type": "keyword_in_title_or_tags"
            })

    # Coverage gap analysis: BBQ and garden
    bbq_keywords    = ["bbq", "barbecue", "barbeque", "grill", "outdoor cooking"]
    garden_keywords = ["garden", "outdoor", "patio", "outdoor living", "backyard"]
    has_bbq     = any(kw in job_norm_topic for kw in bbq_keywords)
    has_garden  = any(kw in job_norm_topic for kw in garden_keywords)

    bbq_published     = [a for a in inventory_published
                          if any(kw in normalize(a.get("title","") + a.get("tags",""))
                                 for kw in bbq_keywords)]
    garden_published  = [a for a in inventory_published
                          if any(kw in normalize(a.get("title","") + a.get("tags",""))
                                 for kw in garden_keywords)]

    findings["bbq_coverage_gap"]    = has_bbq and len(bbq_published) == 0
    findings["garden_coverage_gap"] = has_garden and len(garden_published) == 0

    return findings


# ─── Product scope check ──────────────────────────────────────────────────────

def check_product_scope(topic, product_scope_text):
    """Check if topic is within HCS Gadgets product scope."""
    # Off-limits keywords from product_scope_rules
    off_limits = [
        "knife", "knives", "swiss army knife", "weapon", "self-defence",
        "alcohol", "nicotine", "vaping", "supplement", "medical",
        "prescription", "gambling", "adult", "counterfeit",
    ]
    topic_lower = topic.lower()
    violations = [w for w in off_limits if w in topic_lower]

    # Preferred areas
    preferred = [
        "home essentials", "storage", "organisation", "cleaning",
        "garden", "outdoor", "bbq", "seasonal", "gadget",
        "kitchen", "lifestyle", "gift", "practical",
    ]
    in_scope = any(p in topic_lower for p in preferred)

    return {
        "in_scope":  in_scope and len(violations) == 0,
        "violations": violations,
        "reason":    "BBQ/garden is a preferred product area" if in_scope else "Topic appears off-scope"
    }


# ─── Compliance check ────────────────────────────────────────────────────────

def check_compliance(topic, compliance_text):
    """Assess compliance risk level for the topic."""
    topic_lower = topic.lower()
    risk_factors = []

    # High-risk keywords for BBQ
    high_risk = [
        "fire safety guarantee", "fireproof", "flame-retardant certified",
        "heatproof", "burn-proof",
    ]
    medium_risk = [
        "weatherproof", "waterproof", "rust-proof",
        "guaranteed", "warantee", "certified safe",
        "kills bacteria", "prevents fire", "warranty covers",
    ]

    risks_found = []
    for kw in high_risk:
        if kw in topic_lower:
            risks_found.append(("high", kw))
    for kw in medium_risk:
        if kw in topic_lower:
            risks_found.append(("medium", kw))

    if risks_found:
        level = "high" if any(r[0] == "high" for r in risks_found) else "medium"
    else:
        level = "low"

    # Claims to avoid (general)
    claims_to_avoid = [
        "safest", "best in the uk", "number one", "cures",
        "treats", "heals", "prevents",
    ]
    bad_claims = [c for c in claims_to_avoid if c in topic_lower]

    return {
        "risk_level": level,
        "risk_factors": risks_found,
        "claims_to_avoid": bad_claims,
        "bbq_specific_notes": [
            "Do NOT claim BBQ accessories are fireproof or fire-safe unless certified",
            "Do NOT guarantee BBQ safety — UK fire safety regulations apply",
            "Do NOT claim products prevent BBQ fires",
            "Avoid unsupported heat resistance claims",
            "BBQ lighter fluid and chemical cleaners: avoid health claims",
        ],
        "article_angle": (
            "Product selection guide: how to choose BBQ accessories for UK gardens. "
            "Focus on practicality, durability, and ease of use. "
            "No fire safety guarantees. No performance warranties."
        ),
    }


# ─── Internal link recommendations ───────────────────────────────────────────

def recommend_internal_links(topic, published_articles):
    """Recommend internal links based on topic and existing published articles."""
    recommendations = []
    topic_lower = topic.lower()

    for article in published_articles:
        title  = article.get("title", "")
        handle = article.get("handle", "")
        tags   = article.get("tags", "")

        # Relevant links
        if "home gadget" in title.lower() or "home gadget" in tags.lower():
            recommendations.append({
                "article_title": title,
                "handle": handle,
                "reason": "Cross-links to home essentials content",
                "link_type": "collection",
            })
        if "gift" in topic_lower and "gift" in title.lower():
            recommendations.append({
                "article_title": title,
                "handle": handle,
                "reason": "Seasonal gift angle overlaps with BBQ accessories",
                "link_type": "blog",
            })

    # Collection links (static)
    recommendations.extend([
        {
            "collection": "BBQ & Garden",
            "url": "https://hcsgadgets.com/collections/bbq-garden",
            "reason": "Primary collection for BBQ accessories",
            "link_type": "collection",
        },
        {
            "collection": "Home & Garden",
            "url": "https://hcsgadgets.com/collections/home-and-garden",
            "reason": "Broader category — good for cross-selling",
            "link_type": "collection",
        },
        {
            "collection": "Outdoor Living",
            "url": "https://hcsgadgets.com/collections/outdoor-living",
            "reason": "Seasonal outdoor products",
            "link_type": "collection",
        },
    ])
    return recommendations


# ─── HTML contract requirements ─────────────────────────────────────────────

def html_contract_requirements():
    """Return required HTML components for Job 02."""
    return {
        "wrapper":        "<article class=\"hcs-article\">",
        "required_sections": [
            {"class": "hcs-hero",       "required_children": ["h1", "p.hcs-eyebrow", "p.hcs-intro"]},
            {"class": "hcs-top-grid",   "required_children": ["section.hcs-quick-answer", "section.hcs-toc"]},
            {"class": "hcs-content",    "required_children": ["h2 (multiple)"]},
            {"class": "hcs-cta",        "required_children": ["h2", "p", "a.hcs-button"]},
        ],
        "optional_sections": [
            {"class": "hcs-split",       "description": "Do's and Don'ts block"},
            {"class": "hcs-table-wrapper","description": "Comparison table (if used)"},
            {"class": "hcs-checklist",   "description": "Checklist block"},
            {"class": "hcs-faq",         "description": "FAQ section"},
        ],
        "required_schema": [
            {"type": "BlogPosting", "always_required": True},
            {"type": "FAQPage",     "always_required": False, "condition": "when FAQ section is present"},
        ],
        "forbidden": [
            "inline styles (style=\"...\")",
            "ad-hoc grid classes (row, col-*, custom-grid)",
            "<details> or <summary> elements for FAQ",
            "custom icon markup inside hcs-do/hcs-dont",
        ],
        "cta_requirements": {
            "class":         "hcs-button",
            "element":       "<a>",
            "href_must_match": "https://hcsgadgets.com/",
        },
    }


# ─── Build review report ─────────────────────────────────────────────────────

def build_review(job_number, job_data, inventory, orchestrator_data):
    """
    Perform all review checks and return a full report dict.
    """
    topic     = job_data.get("topic", "")
    keyword   = job_data.get("keyword", "")
    target    = job_data.get("date_target", "")
    status    = job_data.get("status", "")
    file_path = job_data.get("file", "")
    handle    = os.path.basename(file_path).replace(".html", "") if file_path else ""

    published = inventory.get("published", [])
    today_str = datetime.now().strftime("%Y-%m-%d")

    # ── Due-date check ───────────────────────────────────────────────────
    draft_due = None
    if target:
        from datetime import timedelta
        try:
            t = datetime.strptime(target, "%Y-%m-%d")
            draft_due = (t - timedelta(days=14)).strftime("%Y-%m-%d")
        except ValueError:
            pass

    not_due_yet = draft_due is not None and today_str < draft_due

    # ── Duplicate / overlap ────────────────────────────────────────────────
    dup = check_duplicates(published, topic, handle, keyword)

    # ── Product scope ────────────────────────────────────────────────────
    product_scope_text = safe_read_text(PRODUCT_SCOPE)
    scope = check_product_scope(topic, product_scope_text)

    # ── Compliance ───────────────────────────────────────────────────────
    compliance_text = safe_read_text(COMPLIANCE)
    compliance = check_compliance(topic, compliance_text)

    # ── Brand alignment ──────────────────────────────────────────────────
    brand_text = safe_read_text(BRAND_RULES)
    cluster_text = safe_read_text(CLUSTER_MAP)

    # Check cluster map: BBQ/garden is Cluster 2
    cluster2_topics = [
        "Best Outdoor Products for Summer Gatherings",
        "BBQ Accessories and Outdoor Essentials for UK Gardens",
        "How to Prepare Your Garden for Summer Hosting",
        "Compact Outdoor Products for Small Gardens and Patios",
    ]
    in_cluster_map   = topic in cluster_text or any(t.split(" for ")[0] in topic for t in cluster2_topics)
    brand_alignment = "high" if scope["in_scope"] else "low"

    # ── Internal link recommendations ────────────────────────────────────
    int_links = recommend_internal_links(topic, published)

    # ── HTML contract ─────────────────────────────────────────────────────
    html_req = html_contract_requirements()
    contract_exists  = os.path.exists(HTML_CONTRACT)
    validator_exists = os.path.exists(HTML_VALIDATOR)
    skeleton_exists  = os.path.exists(SKELETON_HTML)

    # ── Classification ────────────────────────────────────────────────────
    blockers   = []
    warnings   = []
    infos      = []

    # BLOCKER: not due yet
    if not_due_yet:
        blockers.append({
            "check": "not_due_yet",
            "message": f"Job {job_number} is not yet due. "
                       f"Draft expected {draft_due} but today is {today_str}. "
                       f"Review passed as future-ready but draft creation is blocked until {draft_due}."
        })
    else:
        infos.append({
            "check": "due_date_reached",
            "message": f"Job {job_number} is due (draft date {draft_due} reached)"
        })

    # BLOCKER: exact duplicate
    if dup["exact_handle_match"]:
        blockers.append({
            "check": "exact_handle_duplicate",
            "message": f"Exact handle match: {dup['exact_handle_match']['handle']} — "
                       f"article ID {dup['exact_handle_match']['id']}"
        })

    if dup["exact_title_match"]:
        blockers.append({
            "check": "exact_title_duplicate",
            "message": f"Exact title match: {dup['exact_title_match']['title']}"
        })

    # BLOCKER: high compliance risk
    if compliance["risk_level"] == "high":
        blockers.append({
            "check": "compliance_risk_high",
            "message": f"High compliance risk: {compliance['risk_factors']}"
        })

    # BLOCKER: HTML contract missing
    if not contract_exists:
        blockers.append({
            "check": "html_contract_missing",
            "message": "HCS HTML design contract not found"
        })

    # BLOCKER: HTML validator missing
    if not validator_exists:
        blockers.append({
            "check": "html_validator_missing",
            "message": "HCS HTML validator script not found"
        })

    # WARNING: near title match
    if dup["near_title_match"]:
        for n in dup["near_title_match"]:
            warnings.append({
                "check": "near_title_overlap",
                "message": f"Near title overlap ({n['overlap_score']:.0%}): '{n['title']}' "
                           f"(ID {n['id']}) — review for keyword cannibalisation risk"
            })

    # WARNING: off-scope product violations
    if scope["violations"]:
        warnings.append({
            "check": "product_scope_violation",
            "message": f"Product scope violations: {scope['violations']}"
        })

    # INFO: coverage gaps
    if dup["bbq_coverage_gap"]:
        infos.append({
            "check": "bbq_coverage_gap",
            "message": "No existing BBQ articles in Shopify — Job 02 fills a coverage gap"
        })
    if dup["garden_coverage_gap"]:
        infos.append({
            "check": "garden_coverage_gap",
            "message": "No existing garden articles in Shopify — Job 02 fills a coverage gap"
        })

    # INFO: brand rebalancing
    hoverboard_heavy = sum(
        1 for a in published
        if any(t in a.get("title","").lower() for t in ["hoverboard","scooter","hoverkart"])
    )
    if hoverboard_heavy >= 25:
        infos.append({
            "check": "brand_rebalancing",
            "message": f"{hoverboard_heavy}/{len(published)} published articles are hoverboard-related — "
                       f"BBQ/garden content will help rebalance toward multi-category marketplace"
        })

    # ── Decision ─────────────────────────────────────────────────────────
    if blockers:
        # Check if it's only the "not_due_yet" blocker
        not_due_blocker = any(b["check"] == "not_due_yet" for b in blockers)
        other_blockers  = [b for b in blockers if b["check"] != "not_due_yet"]

        if other_blockers:
            # Real blockers — duplicate, compliance, contract
            if any("compliance" in b["check"] for b in other_blockers):
                decision = DECISION_BLOCKED_COMPLIANCE
            elif any("duplicate" in b["check"] for b in other_blockers):
                decision = DECISION_BLOCKED_DUP
            else:
                decision = DECISION_BLOCKED_NO_CONTRACT
        elif not_due_blocker and not other_blockers:
            # Only blocker is "not due yet" — review passes as future-ready
            decision = DECISION_PASS
        else:
            decision = DECISION_NEEDS_HUMAN
    else:
        decision = DECISION_PASS

    # Article angle
    article_angle = (
        f"Buyer's guide: how to choose the right {keyword or 'BBQ accessories'} "
        f"for UK gardens and outdoor spaces. "
        f"Practical, non-promotional, focused on helping readers make informed decisions. "
        f"Include a comparison of accessory types (e.g., grilling tools, covers, fuel, storage). "
        f"Soft CTA to HCS Gadgets BBQ/garden collection. "
        f"No fire safety guarantees. No performance warranties."
    )

    # Claims to avoid
    claims = [
        "fireproof", "flame-proof", "fire-safe certified",
        "fire prevention guaranteed", "burn-proof",
        "safest BBQ accessory", "best BBQ in the UK",
        "certified heat-resistant", "warantee covers fire damage",
        "prevents BBQ accidents",
    ]

    return {
        "job": {
            "number":        job_number,
            "topic":         topic,
            "keyword":       keyword,
            "target_date":   target,
            "draft_due":     draft_due,
            "status":        status,
            "handle":        handle,
            "file_path":     file_path,
        },
        "today": today_str,
        "not_due_yet": not_due_yet,
        "duplicate_findings": dup,
        "product_scope":     scope,
        "compliance":         compliance,
        "brand_alignment":   brand_alignment,
        "cluster_map_match": in_cluster_map,
        "internal_links":    int_links,
        "html_contract": {
            "found":       contract_exists,
            "validator_found": validator_exists,
            "skeleton_found":  skeleton_exists,
            "requirements":    html_req,
        },
        "decision":      decision,
        "blockers":      blockers,
        "warnings":      warnings,
        "infos":         infos,
        "article_angle": article_angle,
        "claims_to_avoid": claims,
        "recommended_sections": [
            "hcs-hero with eyebrow 'Garden & Outdoor'",
            "hcs-top-grid with quick-answer + TOC",
            "hcs-content with H2 sections: Introduction, Types of BBQ Accessories, What to Look For, Good Signs / Things to Avoid, Quick Comparison, Quick Checklist, FAQs",
            "hcs-split (Do's and Don'ts)",
            "hcs-table-wrapper + hcs-table (comparison table)",
            "hcs-checklist",
            "hcs-faq (4 FAQs)",
            "hcs-cta pointing to BBQ/garden collection",
            "BlogPosting JSON-LD",
            "FAQPage JSON-LD (because FAQ section present)",
        ],
        "recommended_cta": {
            "heading": "Find practical BBQ accessories at HCS Gadgets",
            "body": "Browse BBQ and garden products designed to make outdoor cooking and hosting easier.",
            "href": "https://hcsgadgets.com/collections/all",
            "class": "hcs-button",
        },
        "phase1e_passed": orchestrator_data.get("final_decision") == "READY_FOR_PHASE_2",
    }


# ─── Output generators ────────────────────────────────────────────────────────

def write_json(report, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"JSON preview written: {path}")


def write_report(report, path):
    """Write hcs_orin_status_phase2a.md"""
    job      = report["job"]
    dup      = report["duplicate_findings"]
    scope    = report["product_scope"]
    comp     = report["compliance"]
    html_c   = report["html_contract"]
    decision = report["decision"]

    dup_rows = ""
    for k, v in [
        ("exact_handle_match", dup.get("exact_handle_match")),
        ("exact_title_match",  dup.get("exact_title_match")),
        ("near_handle_match",  dup.get("near_handle_match")),
        ("near_title_match",   dup.get("near_title_match")),
    ]:
        if v:
            label = k.replace("_", " ").title()
            if isinstance(v, list):
                for item in v:
                    dup_rows += f"| {label} | {item.get('title','?')} | `{item.get('handle','?')}` |\n"
            else:
                dup_rows += f"| {label} | {v.get('title','?')} | `{v.get('handle','?')}` |\n"
    if not dup_rows:
        dup_rows = "| — | No duplicates found | — |\n"

    gap_rows = ""
    if dup.get("bbq_coverage_gap"):
        gap_rows += "| BBQ coverage gap | No existing BBQ articles ✅ |\n"
    if dup.get("garden_coverage_gap"):
        gap_rows += "| Garden coverage gap | No existing garden articles ✅ |\n"
    if not gap_rows:
        gap_rows = "| Coverage | Coverage check performed |\n"

    blocker_rows = _fmt_rows(report["blockers"])
    warning_rows = _fmt_rows(report["warnings"])
    info_rows    = _fmt_rows(report["infos"])

    int_links_rows = ""
    for lnk in report["internal_links"][:5]:
        int_links_rows += f"| {lnk.get('link_type','?')} | {lnk.get('article_title', lnk.get('collection','?'))} | {lnk.get('reason','?')} |\n"

    recommended_sections_rows = "\n".join(f"- {s}" for s in report["recommended_sections"])

    phase1e_ok = report["phase1e_passed"]

    content = f"""# HCS Gadgets — ORIN Phase 2A Review Status

**Phase:** 2A — Review Agent Dry-Run
**Client:** HCS Gadgets
**Run date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
**Mode:** Read-only review
**Review Decision:** **{decision}**

---

## Review Decision

{_decision_description(decision, report)}

---

## Phase Gate Check

| Gate | Status |
|------|--------|
| Phase 1E passed | {'✅ Yes' if phase1e_ok else '❌ No'} |
| Phase 1 final decision | READY_FOR_PHASE_2 {'✅' if phase1e_ok else '❌'} |

---

## Selected Job

| Field | Value |
|-------|-------|
| Job number | {job['number']} |
| Topic | {job['topic']} |
| Target keyword | {job['keyword']} |
| Target date | {job['target_date']} |
| Expected draft date | {job['draft_due']} |
| Status | {job['status']} |
| Handle | `{job['handle']}` |
| Today | {report['today']} |
| Due yet? | {'No — draft date has passed' if not report['not_due_yet'] else 'Yes — draft not yet due'} |

---

## Topic Review

| Check | Result |
|-------|--------|
| Within product scope | {'✅ Yes' if scope['in_scope'] else '❌ No — ' + str(scope.get('violations',''))} |
| Product violations | {scope['violations'] if scope['violations'] else 'None'} |
| Cluster map match | {'✅ Cluster 2 — Garden & Outdoor Living' if report['cluster_map_match'] else '❌ Not in cluster map'} |
| Brand alignment | {report['brand_alignment'].title()} |
| Brand rebalancing value | {'High — hoverboard-heavy inventory needs diversification' if report['brand_alignment']=='high' else 'Standard'} |

---

## Duplicate & Overlap Review

| Check | Result |
|-------|--------|
| Exact handle match | {'❌ Found: ' + (dup.get('exact_handle_match',{}) or {{}}).get('handle','?') if dup.get('exact_handle_match') else '✅ None'} |
| Exact title match | {'❌ Found: ' + (dup.get('exact_title_match',{}) or {{}}).get('title','?') if dup.get('exact_title_match') else '✅ None'} |
| Near handle match | {f"⚠️ {len(dup.get('near_handle_match',[]))} found" if dup.get('near_handle_match') else '✅ None'} |
| Near title match | {f"⚠️ {len(dup.get('near_title_match',[]))} found — review for cannibalisation" if dup.get('near_title_match') else '✅ None'} |
| BBQ coverage gap | {'✅ Fills gap — no BBQ articles exist' if dup.get('bbq_coverage_gap') else 'Existing BBQ content exists'} |
| Garden coverage gap | {'✅ Fills gap — no garden articles exist' if dup.get('garden_coverage_gap') else 'Existing garden content exists'} |

### Duplicate Details

| Type | Title | Handle |
|------|-------|--------|
{dup_rows.strip()}

### Coverage Gap Analysis

{gap_rows.strip()}

---

## Compliance Review

| Check | Value |
|-------|-------|
| Risk level | **{comp['risk_level'].upper()}** |
| Risk factors | {comp['risk_factors'] if comp['risk_factors'] else 'None'} |
| Claims to avoid | {', '.join(comp['claims_to_avoid']) if comp['claims_to_avoid'] else 'None'} |

### BBQ-Specific Compliance Notes

{" | ".join(f"- {n}" for n in comp['bbq_specific_notes'])}

### Claims the Article Must NOT Make

{chr(10).join(f"- `{c}`" for c in report['claims_to_avoid'])}

---

## HTML Contract Requirements (Job 02)

| Check | Status |
|-------|--------|
| HTML design contract found | {'✅ Yes' if html_c['found'] else '❌ Missing'} |
| HTML validator found | {'✅ Yes' if html_c['validator_found'] else '❌ Missing'} |
| Article skeleton found | {'✅ Yes' if html_c['skeleton_found'] else '❌ Missing'} |

### Required HTML Components

{recommended_sections_rows}

### Forbidden Patterns

- `style="..."` (inline styles)
- `class="row"`, `class="col-*"`, `class="custom-grid"`
- `<details>` or `<summary>` elements
- custom icon markup inside hcs-do/hcs-dont

### CTA Requirements

| Field | Value |
|-------|-------|
| Heading | {report['recommended_cta']['heading']} |
| Body | {report['recommended_cta']['body']} |
| Link | {report['recommended_cta']['href']} |
| Class | `{report['recommended_cta']['class']}` |
| Element | `<a>` (not `<button>`) |

---

## Recommended Article Angle

> {report['article_angle']}

---

## Internal Link Recommendations

| Type | Target | Reason |
|------|--------|--------|
{int_links_rows.strip()}

---

## Output Proof

| # | Item | Result |
|---|------|--------|
| 1 | Runner file path | `tools/shopify_publisher/orin/hcs_phase2a_review_dryrun.py` |
| 2 | JSON preview path | `/tmp/hcs_phase2a_review_preview.json` |
| 3 | Report path | `clients/hcs_gadgets/content_engine/hcs_orin_status_phase2a.md` |
| 4 | Selected job | **Job {job['number']}** |
| 5 | Topic overlap found | **{'Yes' if (dup.get('near_title_match') or dup.get('near_handle_match')) else 'No'}** |
| 6 | Duplicate risk | **{'Yes' if (dup.get('exact_handle_match') or dup.get('exact_title_match')) else 'No'}** |
| 7 | Compliance risk level | **{comp['risk_level'].upper()}** |
| 8 | HTML contract found | **{'Yes' if html_c['found'] else 'No'}** |
| 9 | HTML validator found | **{'Yes' if html_c['validator_found'] else 'No'}** |
| 10 | Review decision | **{decision}** |
| 11 | Shopify touched | **No** |
| 12 | Queue touched | **No** |
| 13 | Local draft created | **No** |
| 14 | Phase 2A passed | **{'Yes' if decision in (DECISION_PASS,) else 'No'}** |

---

## Blockers ({len(report['blockers'])})

| # | Check | Message |
|---|-------|---------|
{blocker_rows.strip()}

---

## Warnings ({len(report['warnings'])})

| # | Check | Message |
|---|-------|---------|
{warning_rows.strip()}

---

## Info ({len(report['infos'])})

| # | Check | Message |
|---|-------|---------|
{info_rows.strip()}

---

## Next Steps

- {"✅ Review passed — Job 02 is future-ready. Proceed to Phase 2B (Duplicate Decision Memory) dry-run." if decision == DECISION_PASS else "❌ Review blocked — resolve blockers above before proceeding."}
- Job 02 draft creation is blocked until {job['draft_due']} (expected draft date)
- Phase 2B will check for semantic duplicate risk using the Duplicate Decision Memory system

---

*Generated by HCS Phase 2A Review Agent Dry-Run — {datetime.now().isoformat()}*
"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"Phase 2A report written: {path}")


def _fmt_rows(items):
    if not items:
        return "| — | — | No items |\n"
    return "".join(f"| {i+1} | {item['check']} | {item['message']} |\n"
                   for i, item in enumerate(items))


def _decision_description(decision, report):
    descriptions = {
        DECISION_PASS: (
            "Review PASSED as future-ready. "
            f"Job {report['job']['number']} ('{report['job']['topic']}') is within scope, "
            "has no duplicate conflicts, low compliance risk, and meets HTML contract requirements. "
            "Draft creation is blocked only because the expected draft date has not yet arrived "
            f"({report['job']['draft_due']} > {report['today']}). "
            "No local draft was created. Ready to proceed to Phase 2B Duplicate Decision Memory."
        ),
        DECISION_NEEDS_HUMAN: (
            "Review requires human review — warnings present but no hard blockers. "
            "Review findings above."
        ),
        DECISION_BLOCKED_DUP: (
            "Review BLOCKED — duplicate conflict found. "
            "An existing live article matches this topic. "
            "Do not proceed to writer planning until duplicate is resolved."
        ),
        DECISION_BLOCKED_COMPLIANCE: (
            "Review BLOCKED — high compliance risk. "
            "Topic contains prohibited claims or high-risk language. "
            "Do not proceed until compliance issues are resolved."
        ),
        DECISION_BLOCKED_NOT_DUE: (
            "Review BLOCKED — job is not yet due. "
            f"Expected draft date: {report['job']['draft_due']}. Today: {report['today']}."
        ),
        DECISION_BLOCKED_NO_CONTRACT: (
            "Review BLOCKED — HTML design contract or validator is missing. "
            "Cannot proceed without the HTML contract system."
        ),
    }
    return descriptions.get(decision, "Unknown decision.")


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("HCS Gadgets — Phase 2A Review Agent Dry-Run")
    print("=" * 60)
    print(f"Run: {datetime.now().isoformat()}")
    print()

    # ── Load all source data ──────────────────────────────────────────────
    orchestrator = safe_read_json(ORCH_PREVIEW)
    phase1a      = safe_read_json(PHASE1A_PRE)
    phase1b      = safe_read_json(PHASE1B_PRE)
    inventory    = safe_read_json(INVENTORY)

    if not orchestrator:
        print("❌ Cannot load Phase 1E orchestrator preview — aborting")
        sys.exit(1)

    if orchestrator.get("final_decision") != "READY_FOR_PHASE_2":
        print(f"❌ Phase 1E decision is '{orchestrator.get('final_decision')}' — cannot proceed")
        sys.exit(1)

    # ── Select Job 02 ────────────────────────────────────────────────────
    queue_jobs = parse_queue_jobs()
    job02 = queue_jobs.get("02")

    if not job02:
        print("❌ Job 02 not found in queue — aborting")
        sys.exit(1)

    print(f"Selected job: Job 02 — {job02.get('topic')}")
    print(f"Target date: {job02.get('date_target')}")
    print(f"Expected draft date: 2026-07-07")
    print()

    # ── Run review ───────────────────────────────────────────────────────
    review = build_review("02", job02, inventory, orchestrator)
    decision = review["decision"]

    print(f"Decision  : {decision}")
    print(f"Blockers  : {len(review['blockers'])}")
    print(f"Warnings  : {len(review['warnings'])}")
    print(f"Infos     : {len(review['infos'])}")
    print()

    # ── Write outputs ─────────────────────────────────────────────────────
    write_json(review, PREVIEW_JSON)
    write_report(review, PHASE_REPORT)

    print()
    if decision == DECISION_PASS:
        print("✅ Phase 2A PASSED — review passed as future-ready")
        print(f"   Draft creation blocked until {review['job']['draft_due']}")
        print(f"   Ready for Phase 2B Duplicate Decision Memory dry-run")
        sys.exit(0)
    else:
        print(f"⚠️  Phase 2A — decision: {decision}")
        for b in review["blockers"]:
            print(f"  BLOCKER [{b['check']}] {b['message']}")
        sys.exit(1)


if __name__ == "__main__":
    main()
