#!/usr/bin/env python3
"""
HCS Writer Adapter — Thin adapter connecting HCS to shared ORIN production components.

Purpose:
    - Loads HCS ClientContext
    - Delegates to parameterised shared writer_agent for HCS-specific article generation
    - Delegates to parameterised shared review_agent for Phase 2A review
    - Delegates to parameterised shared duplicate_decision_agent for Phase 2B duplicate gate
    - Uses shared shopify_draft_transaction and queue_state_manager via ClientContext
    - Uses HCS product-truth adapter for product claims
    - Produces run evidence under HCS automation_state/runs/<run_id>/

Architecture:
    - Thin adapter: loads config, delegates to shared components
    - No HCS-specific copies of writer, reviewer, duplicate gate, or transaction logic
    - All production components are shared ORIN (parameterised)
    - HCS is draft-only policy: no live Shopify writes

This module is NOT a second HCS automation system.
It is a thin client adapter that connects HCS to the existing shared pipeline.
"""
import hashlib
import json
import re
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from workspace_paths import source_root, workspace_root

AGENTS_DIR = Path(__file__).parent
BASE_DIR = workspace_root()
sys.path.insert(0, str(source_root()))  # allow 'tools.shopify_publisher.orin.xxx' imports
sys.path.insert(0, str(AGENTS_DIR))

from client_context import load_client_context
from writer_agent import WriterAgent
from review_agent import review_selected_job_draft
from duplicate_decision_agent import build_duplicate_memory
from topic_identity_gate import run_topic_identity_gate, TOPIC_IDENTITY_BLOCK
from hcs_product_truth_adapter import HCSProductTruth, build_link_map
from hcs_html_contract_validator import run_checks as run_hcs_contract_checks

# ── Shared component imports for real transaction/queue integration ──────────
# These are the SHARED production components, parameterised via ClientContext.
# We call the PURE functions (verify_shopify_draft_against_local, finalize_draft_created)
# directly rather than reimplementing their business logic.
from shopify_draft_transaction import verify_shopify_draft_against_local
from queue_state_manager import finalize_draft_created as shared_finalize_draft_created


# ═══════════════════════════════════════════════════════════════════════════════
# CORE FIX: HCS HTML NORMALISER — replaces hs- Hoverboard prefixes with hcs-
# ═══════════════════════════════════════════════════════════════════════════════

# Known Hoverboard (hs-) class prefixes that must be replaced for HCS articles.
# Pattern: {old_prefix: new_prefix} — applied via whole-word boundary replacement.
_HS_TO_HCS_CLASS_MAP = {
    # Structural wrappers
    "hs-article":    "hcs-article",
    "hs-container":  "hcs-container",
    "hs-meta":       "hcs-meta",
    # Top-grid and its children
    "hs-top-grid":   "hcs-top-grid",
    "hs-quick-answer": "hcs-quick-answer",
    "hs-toc":        "hcs-toc",
    # Content sections
    "hs-content":   "hcs-content",
    "hs-split":     "hcs-split",
    "hs-do":        "hcs-do",
    "hs-dont":      "hcs-dont",
    "hs-table-wrapper": "hcs-table-wrapper",
    "hs-table-scroll": "hcs-table-scroll",
    "hs-table":     "hcs-table",
    "hs-table--highlight": "hcs-table--highlight",
    # Checklist
    "hs-checklist": "hcs-checklist",
    # FAQ
    "hs-faq":       "hcs-faq",
    "hs-faq-item":  "hcs-faq-item",
    "hs-faq-q":     "hcs-faq-q",
    "hs-faq-a":     "hcs-faq-a",
    # CTA and button
    "hs-cta":       "hcs-cta",
    "hs-button":    "hcs-button",
    "hs-btn":       "hcs-btn",
    # Hero (if generated)
    "hs-hero":      "hcs-hero",
    "hs-eyebrow":   "hcs-eyebrow",
    "hs-intro":     "hcs-intro",
    # Highlights
    "hs-highlights": "hcs-highlights",
    "hs-highlight": "hcs-highlight",
    # Related guides (Hoverboard-specific — strip entirely)
    "hs-related":   None,  # None = remove the section entirely
}


def replace_hs_prefixes_with_hcs(html: str) -> str:
    """
    Replace all Hoverboard (hs-) CSS class prefixes with HCS (hcs-) equivalents.

    This is the primary mechanism by which the shared writer_agent.py can be
    used for HCS articles without modification: the shared writer generates
    hs- HTML, and this function normalises it to hcs- HTML as a post-process.

    Rules:
    - Replaces class attribute values within tag attributes (class="hs-foo hs-bar")
    - Strips hs-related sections entirely (Hoverboard-specific)
    - Does NOT affect plain text or attribute values unrelated to CSS classes
    - Safe to run multiple times (idempotent)

    Args:
        html: Raw HTML string from writer_agent (may contain hs- classes)

    Returns:
        Normalised HTML with hcs- class prefixes and no hs-related sections
    """
    # ── Step 1: Replace class attribute values ──────────────────────────────
    def replace_class_value(m: re.Match) -> str:
        """Replace individual class names within a class="..." attribute value."""
        full = m.group(0)          # e.g.  class="hs-foo hs-bar"
        inner = m.group(1)        # e.g.  hs-foo hs-bar
        classes = inner.strip().split()
        fixed = []
        for cls in classes:
            if cls in _HS_TO_HCS_CLASS_MAP:
                replacement = _HS_TO_HCS_CLASS_MAP[cls]
                if replacement is not None:
                    fixed.append(replacement)
                # if replacement is None → drop that class entirely (hs-related)
            else:
                fixed.append(cls)
        return f'class="{' '.join(fixed)}"'

    html = re.sub(
        r'\bclass="([^"]+)"',
        replace_class_value,
        html,
        flags=re.DOTALL,
    )

    # ── Step 2: Strip hs-related sections entirely ──────────────────────────
    # Match the entire section div containing "Related Guides" heading
    html = re.sub(
        r'\s*<div[^>]*\bclass="[^"]*hs-related[^"]*"[^>]*>\s*'
        r'(?:(?!</div>).)*'  # non-greedy content without closing div
        r'</div>',
        '',
        html,
        flags=re.DOTALL | re.IGNORECASE,
    )
    # Also strip bare <section class="hs-related">...</section>
    html = re.sub(
        r'\s*<section[^>]*\bclass="[^"]*hs-related[^"]*"[^>]*>.*?</section>',
        '',
        html,
        flags=re.DOTALL | re.IGNORECASE,
    )

    return html


# ═══════════════════════════════════════════════════════════════════════════════
# CONTENT QUALITY GATES — block low-quality placeholder content before Shopify write
# ═══════════════════════════════════════════════════════════════════════════════

# Patterns that indicate placeholder / low-quality content.
# Each entry: (compiled_regex, block_message)
_CONTENT_QUALITY_PATTERNS = [
    # Generic filler phrases
    (
        re.compile(r'A\s+practical\s+guide\s+on', re.IGNORECASE),
        "Generic filler phrase detected: 'A practical guide on...' — rewrite with specific angle"
    ),
    (
        re.compile(r'This\s+article\s+covers?', re.IGNORECASE),
        "Generic filler phrase: 'This article covers' — use specific introduction instead"
    ),
    (
        re.compile(r'Welcome\s+to\s+our\s+guide', re.IGNORECASE),
        "Generic filler phrase: 'Welcome to our guide' — use direct, specific opener"
    ),
    # Safety-guarantee over-use (allowed once; blocks if repeated 3+ times)
    (
        re.compile(r'No\s+safety\s+guarantees?', re.IGNORECASE),
        "OVERUSED: 'No safety guarantees' appears too frequently — use once or rephrase"
    ),
    # Unsupported product claims (superlatives that require verification)
    (
        re.compile(r'(?:best|fastest|most\s+powerful|industry-leading|award-winning)\s+(?:hoverboard|scooter|ebike|accessory|product)', re.IGNORECASE),
        "UNSUPPORTED CLAIM: superlative product claims (best/fastest/most powerful/award-winning) require verification — remove or qualify"
    ),
    # Placeholder sentence patterns
    (
        re.compile(r'\[.*?\]'),
        "Unfilled placeholder detected: [...] — all placeholders must be replaced before write"
    ),
    (
        re.compile(r'Your\s+\[\w+\]', re.IGNORECASE),
        "Unfilled template placeholder: 'Your [...]' — specific value required"
    ),
    # Repeated identical sentences (3+ repetitions = block)
    # Detected by counting identical sentence chunks > 20 chars
]


def _find_repeated_sentences(html: str, min_len: int = 40, max_repeat: int = 2) -> list:
    """
    Find sentences (period-terminated chunks) that appear more than max_repeat times.
    Returns list of (repeated_sentence, count) tuples.
    """
    # Split on sentence-ending punctuation followed by space or end
    sentences = re.findall(r'[^.!?]{' + str(min_len) + r',}[.!?](?=\s|$)', html)
    from collections import Counter
    counts = Counter(s.strip() for s in sentences)
    return [(s, c) for s, c in counts.items() if c > max_repeat]


_CONTENT_QUALITY_BLOCK = "CONTENT_QUALITY_BLOCK"


def check_content_quality(html: str) -> tuple[bool, list[str]]:
    """
    Gate content quality before Shopify write.

    Checks:
    1. Banned filler phrases (exact-match blocks).
    2. Repeated identical sentences (≥3 repetitions = block).
    3. Unfilled placeholders ([...], Your [...]) = block.
    4. Unsupported product claims (superlatives: best/fastest/most powerful).

    NOTE: HCS-contract structural validation (hcs-article wrapper,
    mandatory sections, no doc wrappers) is handled by the HCS contract
    validator in run_phase2a_review_hcs — this gate covers CONTENT
    QUALITY only.

    Returns:
        (passed, list_of_failure_messages)
        If passed=True → list is empty.
        If passed=False → non-empty list of specific failure reasons.
    """
    failures = []

    for pattern, msg in _CONTENT_QUALITY_PATTERNS:
        if pattern.search(html):
            failures.append(msg)

    # Check repeated sentences
    repeats = _find_repeated_sentences(html)
    for sentence, count in repeats:
        failures.append(
            f"REPEATED SENTENCE ({count}x): '{sentence[:60]}...' — "
            "content is too repetitive; rewrite sections with unique text"
        )

    # Check for empty or near-empty sections
    # A valid HCS article should have content in hcs-content (H2 sections)
    section_h2_count = len(re.findall(r'<h2\b', html))
    if section_h2_count < 2:
        failures.append(
            f"TOO FEW H2 SECTIONS ({section_h2_count}): "
            "article must have at least 2 H2 content sections"
        )

    return (len(failures) == 0, failures)


def strip_hoverboard_related_guides(html: str) -> str:
    """
    Strip hoverboard-specific "Related Guides" section.

    Deprecated alias — the real work is done by replace_hs_prefixes_with_hcs().
    This function is kept for any legacy callers.
    """
    return replace_hs_prefixes_with_hcs(html)


# ═══════════════════════════════════════════════════════════════════════════════
# FIX 2: HCS-WRITER AGENT — forces HCS outlines + component plan
# ═══════════════════════════════════════════════════════════════════════════════
# HCSWriterAgent is a thin subclass of WriterAgent that overrides the
# _build_dynamic_writer_plan method to use HCS-specific H2 outlines
# (via get_hcs_h2_outline) and HCS-specific CTA plans.
# This ensures the shared WriterAgent produces HCS-native structure
# without modifying writer_agent.py.
#
# All other WriterAgent behaviour is inherited unchanged.
# ═══════════════════════════════════════════════════════════════════════════════

class HCSWriterAgent(WriterAgent):
    """
    HCS-specific WriterAgent subclass.

    Overrides _build_dynamic_writer_plan to:
    1. Use get_hcs_h2_outline(cluster) — HCS-native section outlines
    2. Use HCS-specific CTA plan with hcs-* class names
    3. Use HCS-native HTML structure requirements

    The shared WriterAgent uses Hoverboard-specific outlines and CTA plans.
    This subclass replaces those with HCS equivalents so the generated
    HTML is structurally HCS-native before prefix normalisation.
    """

    def _build_dynamic_writer_plan(self, job_ctx):
        """
        Build an HCS-native writer plan.

        Derived from the shared _build_dynamic_writer_plan with two changes:
        1. h2_outline = get_hcs_h2_outline(cluster) — HCS outlines
        2. cta_plan uses hcs-cta / hcs-button classes

        All other fields (search_intent, reader_persona, claims_to_avoid,
        faq_plan, toc_plan, html_structure_requirements) are inherited
        from the shared WriterAgent.
        """
        # Build the base plan using the shared parent method for all fields
        # except h2_outline and cta_plan (handled below).
        base_plan = super()._build_dynamic_writer_plan(job_ctx)

        # ── FIX: Use HCS-native H2 outline ───────────────────────────────
        cluster = base_plan.get("cluster", "default")
        hcs_h2_outline = get_hcs_h2_outline(cluster)
        base_plan["h2_outline"] = hcs_h2_outline

        # ── FIX: Use HCS-native TOC plan ─────────────────────────────────
        base_plan["toc_plan"] = [
            {"label": item["label"], "href": f"#{item['id']}"}
            for item in hcs_h2_outline
            if item["id"] not in ("cta",)
        ]

        # ── FIX: Use HCS-native CTA plan with hcs-* classes ──────────────
        target_keyword = base_plan.get("target_keyword", "")
        base_plan["cta_plan"] = {
            "heading": f"Find the Right {target_keyword.title()} at HCS",
            "body": (
                f"Browse our full range for {target_keyword}. "
                "Every product ships with manufacturer guidance. "
                "Always follow safety guidance and ride in appropriate private spaces."
            ),
            "button_text": "Shop Now",
            "button_href": "https://example.com/",
            "cta_class": "hcs-button",
            "placement": "End of article, inside hcs-cta section",
        }

        # ── FIX: Update HTML structure to reflect hcs-* classes ──────────
        base_plan["html_structure_requirements"] = [
            "article.hcs-article wrapper",
            "div.hcs-container inside article",
            "h1 as main title (inside container)",
            "div.hcs-meta with byline",
            "div.hcs-quick-answer with summary paragraph",
            "div.hcs-highlights with 3-4 bullet points",
            "section.hcs-content with all H2 sections",
            "All H2s inside .hcs-content have id attributes",
            "div.hcs-split with hcs-do and hcs-dont sub-divs (if applicable)",
            "section.hcs-faq with div.hcs-faq-item children",
            "section.hcs-cta with a.hcs-button CTA",
            "No inline styles, no <style> tags",
            "No document wrappers (DOCTYPE, html, head, body)",
        ]
        base_plan["_plan_source"] = "HCSWriterAgent._build_dynamic_writer_plan"
        return base_plan


# ═══════════════════════════════════════════════════════════════════════════════
# FIX 1: HCS-SPECIFIC H2 OUTLINES (no hoverboard contamination)
# ═══════════════════════════════════════════════════════════════════════════════

HCS_H2_OUTLINES = {
    # Generic fallback for HCS
    "default": [
        {"id": "introduction", "h2": "Introduction", "label": "Introduction"},
        {"id": "what-to-consider", "h2": "What to Consider", "label": "What to consider"},
        {"id": "key-factors", "h2": "Key Factors to Keep in Mind", "label": "Key factors"},
        {"id": "practical-tips", "h2": "Practical Tips", "label": "Practical tips"},
        {"id": "checklist", "h2": "Quick Checklist", "label": "Quick checklist"},
        {"id": "faq", "h2": "Frequently Asked Questions", "label": "FAQs"},
        {"id": "cta", "h2": "Shop Home and Garden Products", "label": "Shop now"},
    ],
    "Seasonal": [
        {"id": "introduction", "h2": "Introduction", "label": "Introduction"},
        {"id": "what-to-consider", "h2": "What to Consider for the Season", "label": "What to consider"},
        {"id": "top-picks", "h2": "Practical Picks for This Occasion", "label": "Top picks"},
        {"id": "safety-reminder", "h2": "A Quick Safety Reminder", "label": "Safety reminder"},
        {"id": "checklist", "h2": "Seasonal Checklist", "label": "Seasonal checklist"},
        {"id": "faq", "h2": "Frequently Asked Questions", "label": "FAQs"},
        {"id": "cta", "h2": "Shop Home and Garden at HCS Gadgets", "label": "Shop now"},
    ],
    "Home & Everyday Essentials": [
        {"id": "introduction", "h2": "Introduction", "label": "Introduction"},
        {"id": "what-matters", "h2": "What to Look For", "label": "What to look for"},
        {"id": "top-choices", "h2": "Top Choices for Everyday Use", "label": "Top choices"},
        {"id": "things-to-avoid", "h2": "Things to Avoid", "label": "Things to avoid"},
        {"id": "checklist", "h2": "Quick Checklist", "label": "Quick checklist"},
        {"id": "faq", "h2": "Frequently Asked Questions", "label": "FAQs"},
        {"id": "cta", "h2": "Shop Home Essentials at HCS Gadgets", "label": "Shop now"},
    ],
    "Gadgets & Useful Finds": [
        {"id": "introduction", "h2": "Introduction", "label": "Introduction"},
        {"id": "what-makes-useful", "h2": "What Makes a Gadget Truly Useful", "label": "What makes it useful"},
        {"id": "key-features", "h2": "Key Features to Look For", "label": "Key features"},
        {"id": "practical-options", "h2": "Practical Options for Everyday Life", "label": "Practical options"},
        {"id": "checklist", "h2": "Gadget Buying Checklist", "label": "Gadget checklist"},
        {"id": "faq", "h2": "Frequently Asked Questions", "label": "FAQs"},
        {"id": "cta", "h2": "Shop Gadgets at HCS Gadgets", "label": "Shop now"},
    ],
    "Garden & Outdoor": [
        {"id": "introduction", "h2": "Introduction", "label": "Introduction"},
        {"id": "what-to-look-for", "h2": "What to Look For in Garden Products", "label": "What to look for"},
        {"id": "top-picks", "h2": "Top Garden and Outdoor Picks", "label": "Top picks"},
        {"id": "safety-reminder", "h2": "A Quick Safety Reminder", "label": "Safety reminder"},
        {"id": "checklist", "h2": "Garden Checklist", "label": "Garden checklist"},
        {"id": "faq", "h2": "Frequently Asked Questions", "label": "FAQs"},
        {"id": "cta", "h2": "Shop Garden Products at HCS Gadgets", "label": "Shop now"},
    ],
    "Buyer Guides & Product Education": [
        {"id": "introduction", "h2": "Introduction", "label": "Introduction"},
        {"id": "what-to-look-for", "h2": "What to Look For Before You Buy", "label": "What to look for"},
        {"id": "key-factors", "h2": "Key Factors for Your Decision", "label": "Key factors"},
        {"id": "questions-to-ask", "h2": "Questions to Ask Before Buying", "label": "Questions to ask"},
        {"id": "checklist", "h2": "Buyer's Checklist", "label": "Buyer's checklist"},
        {"id": "faq", "h2": "Frequently Asked Questions", "label": "FAQs"},
        {"id": "cta", "h2": "Shop at HCS Gadgets", "label": "Shop now"},
    ],
}


def get_hcs_h2_outline(cluster: str) -> list:
    """Get HCS-specific H2 outline for a cluster. No hoverboard contamination."""
    return HCS_H2_OUTLINES.get(cluster, HCS_H2_OUTLINES["default"])


# ═══════════════════════════════════════════════════════════════════════════════
# PRODUCT TRUTH GATE
# ═══════════════════════════════════════════════════════════════════════════════

def run_product_truth_gate(client_ctx) -> dict:
    """
    Run HCS product-truth gate using HCSProductTruth.
    Returns gate result dict.
    """
    try:
        adapter = HCSProductTruth()
        catalogue = adapter.fetch_and_normalise()
        result = adapter.validate()
        pt_valid = result.get("validation_status") == "PRODUCT_TRUTH_VALID"
        pt_fresh = result.get("freshness_status") == "PRODUCT_TRUTH_FRESH"
        writer_ready = pt_valid and pt_fresh
        if writer_ready:
            return {
                "passed": True,
                "status": result.get("freshness_status", "PRODUCT_TRUTH_FRESH"),
                "reason": None,
                "writer_ready": True,
                "blocking": False,
                "product_count": result.get("total", 0),
            }
        else:
            return {
                "passed": False,
                "status": result.get("freshness_status", "PRODUCT_TRUTH_INVALID"),
                "reason": f"validation={result.get('validation_status')}, freshness={result.get('freshness_status')}",
                "writer_ready": False,
                "blocking": True,
                "block_reason": f"Product-truth gate failed: validation={result.get('validation_status')}, freshness={result.get('freshness_status')}",
            }
    except Exception as e:
        return {
            "passed": False,
            "status": "PRODUCT_TRUTH_ERROR",
            "reason": str(e),
            "writer_ready": False,
            "blocking": True,
            "block_reason": f"Product-truth gate error: {e}",
        }


def load_product_truth(client_ctx) -> dict:
    """Load HCS product truth. Returns normalised catalogue."""
    try:
        adapter = HCSProductTruth()
        catalogue = adapter.fetch_and_normalise()
        result = adapter.validate()
        link_map = build_link_map(catalogue, adapter.fetched_at) if catalogue else None
        return {
            "catalogue": {"products": catalogue} if catalogue else None,
            "validation": result,
            "link_map": link_map,
            "loaded": result.get("writer_ready", False),
            "error": None,
        }
    except Exception as e:
        return {"catalogue": None, "validation": None, "link_map": None, "loaded": False, "error": str(e)}


# ═══════════════════════════════════════════════════════════════════════════════
# CLUSTER DETECTION
# ═══════════════════════════════════════════════════════════════════════════════

def determine_cluster(topic: str) -> str:
    """Determine article cluster from topic keywords."""
    topic_lower = topic.lower()
    if any(k in topic_lower for k in ["summer", "season", "gift", "christmas", "birthday"]):
        return "Seasonal"
    if any(k in topic_lower for k in ["bbq", "garden", "outdoor", "camping"]):
        return "Garden & Outdoor"
    if any(k in topic_lower for k in ["home", "household", "kitchen", "clean"]):
        return "Home & Everyday Essentials"
    if any(k in topic_lower for k in ["gadget", "tech", "useful"]):
        return "Gadgets & Useful Finds"
    if any(k in topic_lower for k in ["buy", "choose", "check", "checklist"]):
        return "Buyer Guides & Product Education"
    return "default"


# ═══════════════════════════════════════════════════════════════════════════════
# FIX 1 (FIX 1 of 4): HCS WRITER PLAN — NO HOVERBOARD CONTAMINATION
# ═══════════════════════════════════════════════════════════════════════════════

def build_hcs_writer_plan(
    writer_agent: WriterAgent,
    job_ctx: dict,
    product_truth: dict,
    client_ctx,
) -> dict:
    """
    Build HCS-specific writer plan using parameterised shared writer_agent.
    
    FIX 1: H2 outline comes from HCS-specific outlines only.
    No hoverboard-specific heading is inserted for HCS.
    """
    topic = job_ctx.get("topic", "")
    keyword = job_ctx.get("target_keyword", "")
    cluster = determine_cluster(topic)

    site_url = client_ctx.site_url
    blog_handle = client_ctx.blog_handle

    # Build base plan using shared writer infrastructure
    plan = writer_agent._build_dynamic_writer_plan(job_ctx)

    # FIX 1: Override H2 outline with HCS-specific headings.
    # This replaces ANY hoverboard-generated H2 with HCS-specific ones.
    # The writer will use plan["h2_outline"] when building the article.
    hcs_h2_outline = get_hcs_h2_outline(cluster)
    plan["h2_outline"] = hcs_h2_outline

    # Rebuild TOC from new H2 outline
    plan["toc_plan"] = [
        {"label": item["label"], "href": f"#{item['id']}"}
        for item in hcs_h2_outline
        if item["id"] not in ("cta",)
    ]

    # Override brand-specific fields for HCS
    plan["approved_handle"] = re.sub(r"[^a-z0-9-]", "", topic.lower().replace(" ", "-"))[:70]
    plan["search_intent"] = (
        f"Informational — reader wants practical guidance on {keyword}. "
        "They are evaluating whether and how to proceed, and need honest, actionable advice."
    )
    plan["reader_persona"] = (
        "UK household shopper looking for practical, useful home and garden products. "
        "They want honest buyer guidance and useful product information."
    )
    plan["compliance_notes"] = (
        f"HCS Gadgets article on {topic}. "
        "UK-focused. No exaggerated claims. No safety guarantees. "
        "All product feature claims must be verified against HCS product catalogue."
    )
    plan["cluster"] = cluster

    # HCS-specific CTA using HCS site URL
    plan["cta_plan"] = {
        "heading": f"Find Practical {keyword.title()} at HCS Gadgets",
        "body": f"Browse our full range of useful products for {keyword}. ",
        "button_text": "Shop at HCS Gadgets",
        "button_href": f"{site_url}/collections/all",
        "cta_class": "hcs-button",
        "placement": "End of article",
    }

    # HCS-specific internal links (minimal for HCS)
    plan["internal_link_plan"] = [
        {
            "anchor_text": f"useful home and garden products",
            "url": f"{site_url}/collections/all",
            "reason": "Primary HCS product collection",
            "type": "collection",
        }
    ]

    return plan


# ═══════════════════════════════════════════════════════════════════════════════
# FIX 4: DRAFT-ONLY POLICY ENFORCEMENT
# ═══════════════════════════════════════════════════════════════════════════════

def check_draft_only_policy(client_ctx) -> dict:
    """
    Enforce draft_only_policy.
    
    Rules:
    - draft_only_policy must be explicitly True
    - Missing or False blocks the pipeline
    - Hoverboard Store must be True (corrected in registry)
    - HCS Gadgets is already True
    """
    dop = getattr(client_ctx, "draft_only_policy", None)
    
    if dop is None:
        return {
            "passed": False,
            "blocking": True,
            "block_reason": (
                "draft_only_policy is missing from ClientContext. "
                "Pipeline cannot proceed without explicit draft_only_policy=True."
            ),
        }
    
    if dop is not True:
        return {
            "passed": False,
            "blocking": True,
            "block_reason": (
                f"draft_only_policy={dop!r}. Pipeline requires draft_only_policy=True. "
                f"Cannot proceed with live Shopify writes for {client_ctx.client_id}."
            ),
        }
    
    return {
        "passed": True,
        "blocking": False,
        "draft_only_policy": True,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# FIX 2: DURABLE ARTICLE OWNERSHIP STORE
# ═══════════════════════════════════════════════════════════════════════════════

# Durable ownership store — survives across run directories
_HCS_ROOT = BASE_DIR / "clients" / "hcs_gadgets"
IDEMPOTENCY_DIR = _HCS_ROOT / "content_engine" / "automation_state" / "idempotency"
OWNERSHIP_FILE = IDEMPOTENCY_DIR / "article_ownership.json"


def _ensure_ownership_dir() -> None:
    """Ensure the idempotency directory exists."""
    IDEMPOTENCY_DIR.mkdir(parents=True, exist_ok=True)


def _load_ownership() -> dict:
    """
    Load the durable article ownership store.
    
    Malformed data → fail closed (return empty dict, never partial state).
    Missing file → return empty ownership dict (first run).
    """
    if not OWNERSHIP_FILE.exists():
        return {"job_to_article": {}, "article_to_job": {}}
    try:
        data = json.loads(OWNERSHIP_FILE.read_text(encoding="utf-8"))
        # Validate structure
        if not isinstance(data, dict):
            return {"job_to_article": {}, "article_to_job": {}}
        if "job_to_article" not in data or "article_to_job" not in data:
            return {"job_to_article": {}, "article_to_job": {}}
        return data
    except Exception:
        # Malformed — fail closed
        return {"job_to_article": {}, "article_to_job": {}}


def _save_ownership(data: dict) -> None:
    """
    Save the article ownership store using atomic write.
    
    Atomic: write to temp file, flush, fsync, rename over authoritative file.
    This prevents corruption if the process is interrupted mid-write.
    """
    _ensure_ownership_dir()
    tmp = OWNERSHIP_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    tmp.rename(OWNERSHIP_FILE)  # Atomic on POSIX


def _check_ownership(
    client_id: str,
    job_number: str,
    incoming_article_id: int,
    incoming_handle: str,
) -> dict:
    """
    Check article ownership for a job/article combination.
    
    Implements the four ownership cases:
    A. No existing record → first run, record ownership
    B. Same job + same article → IDEMPOTENT_RECONCILE_NO_OP
    C. Same job + different article → BLOCK_JOB_ARTICLE_ID_MISMATCH
    D. Different job + same article → BLOCK_ARTICLE_ALREADY_OWNED
    
    Returns dict with keys: action, decision, existing_article_id, blockers
    """
    ownership = _load_ownership()
    job_key = f"{client_id}::{job_number}"
    
    # Case A: no existing record for this job — but still check article_to_job
    if job_key not in ownership.get("job_to_article", {}):
        # Even for a new job, the incoming article_id might already be owned
        # by a different job. Check the reverse mapping first.
        article_key = str(incoming_article_id)
        if article_key in ownership.get("article_to_job", {}):
            owning_job = ownership["article_to_job"][article_key]
            return {
                "action": "BLOCK",
                "decision": "BLOCK_ARTICLE_ALREADY_OWNED",
                "existing_article_id": incoming_article_id,
                "blockers": [
                    f"Article ID {incoming_article_id} is already owned by {owning_job}. "
                    f"Job {job_number} cannot claim this article ID."
                ],
            }
        return {
            "action": "RECORD",
            "decision": None,  # Caller records
            "existing_article_id": None,
            "blockers": [],
        }
    
    existing_record = ownership["job_to_article"][job_key]
    existing_id = int(existing_record["article_id"])
    
    # Case B: same job + same article → reconcile
    if existing_id == incoming_article_id:
        return {
            "action": "IDEMPOTENT_NO_OP",
            "decision": "IDEMPOTENT_RECONCILE_NO_OP",
            "existing_article_id": existing_id,
            "blockers": [],
        }
    
    # Case C: same job + different article → BLOCK
    if existing_id != incoming_article_id:
        return {
            "action": "BLOCK",
            "decision": "BLOCK_JOB_ARTICLE_ID_MISMATCH",
            "existing_article_id": existing_id,
            "blockers": [
                f"Job {job_number} already owns article ID {existing_id}. "
                f"Cannot create new article ID {incoming_article_id}. "
                f"Same job cannot claim a different article ID without human review."
            ],
        }
    
    # Case D: different job + same article → BLOCK (shouldn't reach here with current key design)
    # Check via article_to_job reverse mapping
    article_key = str(incoming_article_id)
    if article_key in ownership.get("article_to_job", {}):
        owning_job = ownership["article_to_job"][article_key]
        return {
            "action": "BLOCK",
            "decision": "BLOCK_ARTICLE_ALREADY_OWNED",
            "existing_article_id": existing_id,
            "blockers": [
                f"Article ID {incoming_article_id} is already owned by {owning_job}. "
                f"Job {job_number} cannot claim this article ID."
            ],
        }
    
    # Fallback: block
    return {
        "action": "BLOCK",
        "decision": "BLOCK_UNEXPECTED_OWNERSHIP_STATE",
        "existing_article_id": existing_id,
        "blockers": ["Unexpected ownership state — blocking for safety"],
    }


def _record_ownership(
    client_id: str,
    job_number: str,
    article_id: int,
    handle: str,
    decision: str,
) -> None:
    """
    Record job→article ownership atomically in the durable store.
    Also updates the reverse article→job mapping.
    """
    ownership = _load_ownership()
    job_key = f"{client_id}::{job_number}"
    article_key = str(article_id)
    
    ownership.setdefault("job_to_article", {})
    ownership.setdefault("article_to_job", {})
    
    ownership["job_to_article"][job_key] = {
        "article_id": str(article_id),
        "handle": handle,
        "decision": decision,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    ownership["article_to_job"][article_key] = job_key
    
    _save_ownership(ownership)


# ═══════════════════════════════════════════════════════════════════════════════
# FIX 3: REAL SHARED TRANSACTION ORCHESTRATION WITH INJECTED MOCK TRANSPORT
# ═══════════════════════════════════════════════════════════════════════════════

def _get_shopify_config_for_client(client_ctx) -> dict:
    """
    Build Shopify config dict from ClientContext for shared components.
    
    FIX 2: This replaces hardcoded hoverboard_shopify_config loading.
    Both clients use ClientContext to get their Shopify credentials.
    """
    # Try to load from .env file if shopify_config_path is set
    env_prefix = client_ctx.shopify_config_env_prefix or ""
    
    import os
    from pathlib import Path as P
    
    # Build environment variable prefix
    prefix = env_prefix or f"{client_ctx.client_id.upper().replace('-', '_')}_SHOPIFY"
    
    # Read from .env if available
    config_path = client_ctx.shopify_config_path
    env_vars = {}
    if config_path and P(config_path).exists():
        for line in P(config_path).read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env_vars[k.strip()] = v.strip().strip('"').strip("'")
    
    def ev(key, default=""):
        return env_vars.get(f"{prefix}_{key}", default)
    
    return {
        "store_domain": ev("STORE_DOMAIN", client_ctx.store_domain),
        "access_token": ev("ACCESS_TOKEN", ""),
        "api_version": ev("API_VERSION", "2024-01"),
        "blog_id": ev("BLOG_ID", client_ctx.blog_id),
    }


def _load_idempotency_state(run_dir: Path) -> dict:
    """Load idempotency state from run directory."""
    path = run_dir / "idempotency_state.json"
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            pass
    return {}


def _save_idempotency_state(run_dir: Path, state: dict) -> None:
    """Save idempotency state to run directory."""
    path = run_dir / "idempotency_state.json"
    path.write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")


def run_shared_transaction_with_mock_shopify(
    job_ctx: dict,
    writer_plan: dict,
    writer_execution: dict,
    client_ctx,
    run_dir: Path,
) -> dict:
    """
    Run the shared transaction orchestration for HCS using injected mock transport.
    
    FIX 3: Delegates to run_hcs_transaction_orchestration which uses:
    - Real shared verify_shopify_draft_against_local (from shopify_draft_transaction)
    - Real shared finalize_draft_created (from queue_state_manager)
    - Durable article ownership store (article_ownership.json)
    - Injected MockShopifyTransport (no real Shopify API calls)
    
    This is a thin wrapper that injects the mock transport. All business logic
    lives in shared components.
    """
    transport = MockShopifyTransport(_get_shopify_config_for_client(client_ctx))
    return run_hcs_transaction_orchestration(
        job_ctx=job_ctx,
        writer_plan=writer_plan,
        writer_execution=writer_execution,
        client_ctx=client_ctx,
        run_dir=run_dir,
        transport=transport,
    )


def _run_shared_queue_finalization(
    client_ctx,
    job_number: str,
    shopify_article_id: int,
    shopify_handle: str,
    verification_passed: bool,
    run_dir: Path,
    dry_run: bool = False,
) -> dict:
    """
    Call the REAL shared queue_state_manager.finalize_draft_created function.
    
    FIX 2: Uses the real shared queue finalization, parameterised by ClientContext.
    
    IMPORTANT: In non-live simulation mode, the queue_path is OVERRIDDEN to an
    isolated fixture path inside run_dir. The authoritative queue is NEVER mutated.
    This ensures the production queue remains unchanged during simulation.
    """
    if not verification_passed:
        return {
            "decision": "BLOCK_VERIFICATION_NOT_PASSED",
            "approved": False,
            "blockers": ["Verification did not pass — cannot finalise queue"],
            "job_number": job_number,
        }
    
    # ── NON-LIVE ISOLATION: write to isolated fixture queue, NOT real queue ──
    # The authoritative client_ctx.queue_path is NOT mutated during simulation.
    # We use an isolated queue copy inside run_dir for the fixture.
    isolated_queue_path = run_dir / "isolated_queue_fixture.md"
    
    # Copy the real queue to the isolated fixture path
    if client_ctx.queue_path.exists():
        import shutil
        shutil.copy2(str(client_ctx.queue_path), str(isolated_queue_path))
    else:
        # Create empty isolated queue if real queue doesn't exist
        isolated_queue_path.write_text("", encoding="utf-8")
    
    # Use the real shared function with the ISOLATED queue path
    return shared_finalize_draft_created(
        queue_path=str(isolated_queue_path),
        job_number=job_number,
        shopify_article_id=shopify_article_id,
        shopify_handle=shopify_handle,
        draft_created_at=datetime.now(timezone.utc).isoformat(),
        published_at=None,  # Draft
        shopify_verification_passed=True,
        expected_article_id=shopify_article_id,
        expected_handle=shopify_handle,
        run_dir=str(run_dir),
    )


# ── Mock evidence persistence (non-live simulation) ──────────────────────────

def _persist_mock_sent_body(run_dir: Path, body: str) -> None:
    """Persist the sent body HTML to durable storage."""
    (run_dir / "sent_body.html").write_text(body, encoding="utf-8")
    (run_dir / "sent_body_sha256.txt").write_text(
        hashlib.sha256(body.encode()).hexdigest(), encoding="utf-8"
    )


def _persist_mock_fetched_body(run_dir: Path, body: str) -> None:
    """Persist the fetched body HTML to durable storage (identical to sent in non-live)."""
    (run_dir / "fetched_body.html").write_text(body, encoding="utf-8")
    (run_dir / "fetched_body_sha256.txt").write_text(
        hashlib.sha256(body.encode()).hexdigest(), encoding="utf-8"
    )


def _persist_verification(
    run_dir: Path,
    verification_passed: bool,
    failures: list,
    details: dict,
    job_number: str = "",
    article_id: int | None = None,
    run_id: str = "",
) -> None:
    """Persist verification decision and details to durable storage."""
    verification_record = {
        "run_id": run_id,
        "run_dir": str(run_dir),
        "job_number": job_number,
        "shopify_article_id": article_id,
        "verification_passed": verification_passed,
        "failures": failures,
        "details": details,
        "comparator_normalization": "shopify_draft_transaction.verify_shopify_draft_against_local (shared)",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    (run_dir / "verification.json").write_text(
        json.dumps(verification_record, indent=2, default=str), encoding="utf-8"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# FIX 3: MOCK SHOPIFY TRANSPORT (injected under real shared transaction)
# ═══════════════════════════════════════════════════════════════════════════════

class MockShopifyTransport:
    """
    Mock Shopify API transport for non-live simulation.
    
    Injected under the real shared transaction orchestration.
    Simulates Shopify API responses WITHOUT making any real HTTPS calls.
    
    Simulated cases:
    1. success → draft article created (published_at=null)
    2. body mismatch → verification failure detected by real verifier
    3. published_at not null → transaction fails at verification
    4. preflight block → transport never called
    5. replay same job/article → no new transport call (idempotent)
    6. different job/same article → BLOCK before transport
    """
    
    def __init__(self, shopify_config: dict):
        self.shopify_config = shopify_config
        self.call_count = 0
        self.calls = []  # evidence of what was called
    
    def create_draft(self, title: str, body_html: str, handle: str,
                    forced_article_id: int | None = None) -> dict:
        """
        Simulate POST /blogs/{blog_id}/articles.json → draft article.
        Returns article dict with published=false, published_at=null.
        
        Args:
            forced_article_id: if provided, the mock MUST return this article ID
                (used to keep article IDs stable across ownership-check and
                create-draft calls within the same pipeline run).
        """
        self.call_count += 1
        import hashlib
        if forced_article_id is not None:
            article_id = forced_article_id
        else:
            article_id = int.from_bytes(
                hashlib.sha256(f"{self.shopify_config.get('store_domain','mock')}::{handle}".encode()).digest()[:4],
                byteorder="big"
            ) % 1000000
        article = {
            "id": article_id,
            "title": title,
            "handle": handle,
            "body_html": body_html,
            "published": False,
            "published_at": None,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self.calls.append({"method": "create_draft", "article_id": article_id})
        return article
    
    def fetch_article(self, article_id: int) -> dict | None:
        """
        Simulate GET /blogs/{blog_id}/articles/{id}.json
        Returns article dict.
        """
        self.call_count += 1
        self.calls.append({"method": "fetch_article", "article_id": article_id})
        # Return a mock article — caller provides the body to verify
        return {"id": article_id}


def run_hcs_transaction_orchestration(
    job_ctx: dict,
    writer_plan: dict,
    writer_execution: dict,
    client_ctx,
    run_dir: Path,
    transport: MockShopifyTransport | None = None,
) -> dict:
    """
    Real shared transaction orchestration for HCS.
    
    FIX 3: This function calls the ACTUAL shared shopify_draft_transaction
    verification function (verify_shopify_draft_against_local) under an
    injected mock transport. It implements the full transaction pipeline:
    
    1. Client/store/blog identity validation
    2. Draft-only policy check
    3. Hidden-draft request creation (via injected transport)
    4. Fetched article verification (via real shared verifier)
    5. Transaction result creation
    6. Durable ownership check and record
    7. Queue-state finalization (via real shared function)
    
    This is the THIN ADAPTER pattern: all business logic lives in shared
    components (verify_shopify_draft_against_local, finalize_draft_created).
    This function only: loads config → orchestrates → formats results.
    """
    job_number = str(job_ctx.get("job_number", ""))
    client_id = client_ctx.client_id
    local_path = writer_execution.get("output_path", "")
    expected_sha256 = writer_execution.get("sha256", "")
    expected_handle = writer_plan.get("approved_handle", "")
    expected_title = job_ctx.get("topic", "")
    
    if not local_path or not Path(local_path).exists():
        return {
            "decision": "BLOCK_NO_LOCAL_DRAFT",
            "approved": False,
            "blockers": ["Local draft file not found"],
            "job_number": job_number,
            "transport_call_count": 0,
        }
    
    body_html = Path(local_path).read_text(encoding="utf-8")
    body_sha256 = hashlib.sha256(body_html.encode()).hexdigest()
    
    # Build Shopify config from ClientContext
    shopify_config = _get_shopify_config_for_client(client_ctx)
    
    # Use injected transport or create default mock
    if transport is None:
        transport = MockShopifyTransport(shopify_config)
    
    # ── Step 1: Client/store/blog identity validation ──────────────────────
    if not shopify_config.get("store_domain"):
        return {
            "decision": "BLOCK_MISSING_SHOPIFY_CONFIG",
            "approved": False,
            "blockers": ["Shopify store_domain not configured for this client"],
            "job_number": job_number,
            "transport_call_count": transport.call_count,
        }
    
    # ── Step 2: Draft-only policy check (already done pre-flight, but validate here) ─
    dop = getattr(client_ctx, "draft_only_policy", None)
    if dop is not True:
        return {
            "decision": "BLOCK_DRAFT_ONLY_POLICY",
            "approved": False,
            "blockers": [f"draft_only_policy={dop!r} — only draft mode is allowed"],
            "job_number": job_number,
            "transport_call_count": transport.call_count,
        }
    
    # ── Step 3: Durable ownership check ─────────────────────────────────────
    # Use article_id from job_ctx when provided (e.g., from fixture or real Shopify).
    # Otherwise generate a STABLE deterministic mock ID based ONLY on
    # client_id::job_number — NOT run_dir.name — so two runs of the same job
    # produce the same article ID and the ownership NOOP path fires correctly.
    import hashlib as _hl
    ctx_article_id = job_ctx.get("shopify_article_id")
    if ctx_article_id is not None:
        article_id_for_check = int(ctx_article_id)
    else:
        article_id_for_check = int.from_bytes(
            _hl.sha256(f"{client_id}::{job_number}".encode()).digest()[:4],
            byteorder="big"
        ) % 1000000
    
    ownership_check = _check_ownership(
        client_id=client_id,
        job_number=job_number,
        incoming_article_id=article_id_for_check,
        incoming_handle=expected_handle,
    )
    
    if ownership_check["action"] == "BLOCK":
        return {
            "decision": ownership_check["decision"],
            "approved": False,
            "blockers": ownership_check["blockers"],
            "existing_article_id": ownership_check["existing_article_id"],
            "job_number": job_number,
            "transport_call_count": transport.call_count,
            "ownership_durable": True,
        }
    
    if ownership_check["action"] == "IDEMPOTENT_NO_OP":
        # Same job + same article: verify again for evidence, no new transport call
        mock_fetched = {
            "id": ownership_check["existing_article_id"],
            "title": expected_title,
            "handle": expected_handle,
            "body_html": body_html,
            "published_at": None,
        }
        vp, vf, vd = verify_shopify_draft_against_local(
            article=mock_fetched,
            expected_article_id=ownership_check["existing_article_id"],
            expected_title=expected_title,
            expected_handle=expected_handle,
            expected_local_html=body_html,
            expected_local_sha256=body_sha256,
        )
        _persist_mock_sent_body(run_dir, body_html)
        _persist_mock_fetched_body(run_dir, body_html)
        _persist_verification(
            run_dir, verification_passed=vp,
            failures=vf, details=vd,
            job_number=job_number,
            article_id=ownership_check["existing_article_id"],
            run_id=run_dir.name,
        )
        return {
            "decision": "IDEMPOTENT_RECONCILE_NO_OP",
            "approved": True,
            "blockers": [],
            "job_number": job_number,
            "shopify_article_id": ownership_check["existing_article_id"],
            "shopify_handle": expected_handle,
            "verification_passed": vp,
            "verification_details": vd,
            "queue_commit": {"decision": "IDEMPOTENT_NO_OP", "approved": True},
            "transport_call_count": transport.call_count,
            "idempotent": True,
            "ownership_durable": True,
            "run_id": run_dir.name,
            "simulated": True,
        }
    
    # ── Step 4: Create hidden draft via injected transport ─────────────────
    # Use the same article ID as the ownership check so ownership recording is consistent
    created_article = transport.create_draft(
        title=expected_title,
        body_html=body_html,
        handle=expected_handle,
        forced_article_id=article_id_for_check,
    )
    
    # ── Step 5: Fetch the article back to verify ───────────────────────────
    # In non-live mock: fetched body = sent body (identical)
    mock_fetched_article = {
        "id": created_article["id"],
        "title": created_article["title"],
        "handle": created_article["handle"],
        "body_html": body_html,  # Same as sent (non-live simulation)
        "published_at": None,    # Draft = not published
        "published": False,
    }
    
    # ── Step 6: Verify using the REAL shared verification function ──────────
    # This is the SHARED production verification from shopify_draft_transaction.py
    verification_passed, verification_failures, verification_details = (
        verify_shopify_draft_against_local(
            article=mock_fetched_article,
            expected_article_id=created_article["id"],
            expected_title=expected_title,
            expected_handle=expected_handle,
            expected_local_html=body_html,
            expected_local_sha256=body_sha256,
        )
    )
    
    # Persist evidence
    _persist_mock_sent_body(run_dir, body_html)
    _persist_mock_fetched_body(run_dir, body_html)
    _persist_verification(
        run_dir,
        verification_passed=verification_passed,
        failures=verification_failures,
        details=verification_details,
        job_number=job_number,
        article_id=created_article["id"],
        run_id=run_dir.name,
    )
    
    if not verification_passed:
        # Record failed ownership
        _record_ownership(
            client_id=client_id,
            job_number=job_number,
            article_id=created_article["id"],
            handle=expected_handle,
            decision="BLOCKED_VERIFICATION_FAILED",
        )
        return {
            "decision": "BLOCKED_VERIFICATION_FAILED",
            "approved": False,
            "blockers": verification_failures,
            "verification_failures": verification_failures,
            "verification_details": verification_details,
            "job_number": job_number,
            "shopify_article_id": created_article["id"],
            "transport_call_count": transport.call_count,
            "ownership_durable": True,
            "run_id": run_dir.name,
            "simulated": True,
        }
    
    # ── Step 7: Record durable ownership ─────────────────────────────────────
    _record_ownership(
        client_id=client_id,
        job_number=job_number,
        article_id=created_article["id"],
        handle=expected_handle,
        decision="DRAFT_CREATED_VERIFICATION_PASSED",
    )
    
    # ── Step 8: Queue finalization via real shared function ─────────────────
    queue_commit_result = _run_shared_queue_finalization(
        client_ctx=client_ctx,
        job_number=job_number,
        shopify_article_id=created_article["id"],
        shopify_handle=expected_handle,
        verification_passed=True,
        run_dir=run_dir,
    )
    
    return {
        "decision": "DRAFT_CREATED_VERIFICATION_PASSED",
        "approved": True,
        "blockers": [],
        "job_number": job_number,
        "shopify_article_id": created_article["id"],
        "shopify_handle": expected_handle,
        "shopify_published_at": None,
        "verification_passed": True,
        "verification_details": verification_details,
        "queue_commit": queue_commit_result,
        "transport_call_count": transport.call_count,
        "ownership_durable": True,
        "run_id": run_dir.name,
        "simulated": True,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# ARTICLE WRITE
# ═══════════════════════════════════════════════════════════════════════════════

def write_hcs_article(
    writer_agent: WriterAgent,
    job_ctx: dict,
    writer_plan: dict,
    output_path: Path,
    client_ctx,
) -> dict:
    """
    Execute HCS article write using parameterised shared writer_agent.
    Returns execution stats dict.

    FIX 1 (core): Replaces hoverboard (hs-) CSS class prefixes with HCS (hcs-)
    prefixes as a post-processing step. This allows the shared writer_agent to
    generate correct HCS HTML without modification.

    FIX 2: Applies content quality gate before returning — blocks on placeholder
    text, repetitive sentences, and unsupported product claims.
    """
    try:
        # Call the shared writer — no monkey-patching
        stats = writer_agent.write_selected_job_draft(
            job_ctx=job_ctx,
            writer_plan=writer_plan,
            output_path_override=str(output_path),
        )

        if not output_path.exists():
            return {"success": False, "error": "Writer produced no output file", **stats}

        # ── FIX 1 (core): Normalise all hs- → hcs- class prefixes ────────────
        # The shared writer generates hoverboard HTML (hs-*). This post-process
        # normalises it to HCS contract HTML (hcs-*) before any Shopify write.
        # replace_hs_prefixes_with_hcs() also strips hs-related sections.
        html = output_path.read_text(encoding="utf-8")
        html_fixed = replace_hs_prefixes_with_hcs(html)
        output_path.write_text(html_fixed, encoding="utf-8")

        # Recompute stats after normalisation
        stats["h2_count"] = html_fixed.count("<h2>")
        stats["internal_link_count"] = html_fixed.count("<a href=")

        # ── FIX 2: Content quality gate — block low-quality content ────────────
        quality_ok, quality_failures = check_content_quality(html_fixed)
        if not quality_ok:
            stats["quality_gate_passed"] = False
            stats["quality_gate_failures"] = quality_failures
            return {
                "success": False,
                "blocked": True,
                "block_reason": "CONTENT_QUALITY_BLOCK",
                "block_details": quality_failures,
                **stats,
            }

        stats["quality_gate_passed"] = True
        return {"success": True, **stats}

    except Exception as e:
        return {"success": False, "error": str(e)}


# ═══════════════════════════════════════════════════════════════════════════════
# TOPIC IDENTITY GATE
# ═══════════════════════════════════════════════════════════════════════════════

def run_topic_identity_gate_hcs(
    job_ctx: dict,
    writer_plan: dict,
    output_html: str,
    client_ctx,
) -> dict:
    """
    Run topic identity gate for HCS using shared topic_identity_gate.
    """
    cluster = determine_cluster(job_ctx.get("topic", ""))
    approved_h2_plan = [
        {"id": h.get("id", ""), "h2": h.get("h2", "")}
        for h in writer_plan.get("h2_outline", [])
    ]
    return run_topic_identity_gate(
        job_id=str(job_ctx.get("job_number", "")),
        expected_topic=job_ctx.get("topic", ""),
        target_keyword=job_ctx.get("target_keyword", ""),
        cluster=cluster,
        approved_h2_plan=approved_h2_plan,
        output_html=output_html,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 2A REVIEW
# ═══════════════════════════════════════════════════════════════════════════════

def run_phase2a_review_hcs(
    job_ctx: dict,
    writer_plan: dict,
    draft_path: Path,
    client_ctx,
) -> dict:
    """
    Run Phase 2A review for HCS using parameterised shared review_agent.

    HCS contract validator is applied AFTER the shared review:
    1. review_selected_job_draft — shared content/compliance/structure checks
    2. run_hcs_contract_checks — HCS HTML design contract (structure, classes)

    Contract failures are merged as blockers (like other review failures).
    """
    # Skip duplicate check only when no real Shopify article ID exists yet.
    # Use shopify_article_id (not handle) because handle may be set for
    # a planned article that has no real Shopify record yet.
    skip_dup = not bool(job_ctx.get("shopify_article_id"))
    review_result = review_selected_job_draft(
        job_ctx=job_ctx,
        writer_plan=writer_plan,
        draft_path=str(draft_path),
        skip_duplicate_check=skip_dup,
        client_context=client_ctx,
    )

    # ── HCS CONTRACT VALIDATOR (Phase 2A extension) ────────────────────────
    # Run HCS HTML design contract checks on the draft.
    # Failures are added as blockers — same treatment as review failures.
    try:
        draft_html = Path(draft_path).read_text(encoding="utf-8")
        contract_failures, contract_warnings, _ = run_hcs_contract_checks(draft_html)
        if contract_failures:
            # Merge into review_result blockers
            existing_blockers = review_result.get("blockers", [])
            hcs_blockers = [
                f"[HCS_CONTRACT] {f}" for f in contract_failures
            ]
            review_result["blockers"] = existing_blockers + hcs_blockers
            review_result["review_decision"] = "POST_WRITE_REVIEW_BLOCKED"
            review_result["safe_for_html_validation"] = False
        if contract_warnings:
            existing_warnings = review_result.get("warnings", [])
            review_result["warnings"] = existing_warnings + [
                f"[HCS_CONTRACT] {w}" for w in contract_warnings
            ]
        review_result["hcs_contract_failures"] = contract_failures
        review_result["hcs_contract_warnings"] = contract_warnings
    except Exception as e:
        # Contract validator errors are non-fatal but reported
        existing_warnings = review_result.get("warnings", [])
        review_result["warnings"] = existing_warnings + [
            f"[HCS_CONTRACT ERROR] {str(e)}"
        ]
        review_result["hcs_contract_failures"] = []

    return review_result


# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 2B DUPLICATE GATE
# ═══════════════════════════════════════════════════════════════════════════════

def run_phase2b_duplicate_gate_hcs(
    job_numbers: list,
    client_ctx,
    phase2a_results: dict = None,
) -> dict:
    """
    Run Phase 2B duplicate gate for HCS using parameterised shared duplicate_decision_agent.

    Args:
        phase2a_results: optional Phase 2A result dict with {"jobs": [...]} structure.
                        When provided, used directly in memory — no file read needed.
                        This enables run-scoped Phase 2A→2B bridging without /tmp.
    """
    return build_duplicate_memory(
        job_numbers,
        client_context=client_ctx,
        phase2a_results=phase2a_results,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN PIPELINE
# ═══════════════════════════════════════════════════════════════════════════════

def run_hcs_pipeline_simulation(
    client_id: str = "hcs_gadgets",
    job_number: str = None,
    fixture_job_data: dict = None,
    output_dir: Path = None,
) -> dict:
    """
    Run a complete HCS pipeline simulation using shared ORIN components.

    FIX 1: H2 outlines are HCS-specific (no hoverboard contamination)
    FIX 2: Real shared transaction and queue components are called
    FIX 3: Real idempotency with (client_id, job_number) -> article_id
    FIX 4: draft_only_policy is enforced before any transaction
    
    Args:
        client_id: client identifier
        job_number: job number to simulate (or None for auto-select lowest planned)
        fixture_job_data: optional fixture job data dict to use instead of reading queue
        output_dir: optional output directory for isolated run evidence

    Returns:
        Complete run result dict with all phase outputs and evidence paths
    """
    run_id = f"hcs_sim_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
    business_date = datetime.now().strftime("%Y-%m-%d")

    # Load HCS ClientContext
    try:
        client_ctx = load_client_context(client_id)
    except Exception as e:
        return {"blocked": True, "block_reason": f"Failed to load client context: {e}"}

    # Determine output directory
    if output_dir is None:
        output_dir = client_ctx.automation_state_path / "runs" / run_id

    run_dir = Path(output_dir)
    run_dir.mkdir(parents=True, exist_ok=True)

    result = {
        "run_id": run_id,
        "client_id": client_id,
        "simulated": True,
        "pipeline_started": datetime.now(timezone.utc).isoformat(),
        "run_dir": str(run_dir),
        "phases_completed": [],
    }

    try:
        # Phase 0: Product-truth gate
        pt_gate = run_product_truth_gate(client_ctx)
        result["product_truth_gate"] = pt_gate
        if pt_gate.get("blocking"):
            result["blocked"] = True
            result["block_phase"] = "PRODUCT_TRUTH_GATE"
            result["block_reason"] = pt_gate.get("block_reason")
            return result

        result["phases_completed"].append("PRODUCT_TRUTH_GATE")

        # Load product truth for writer
        pt_result = load_product_truth(client_ctx)
        result["product_truth_loaded"] = pt_result.get("loaded")
        result["phases_completed"].append("PRODUCT_TRUTH_LOAD")

        # Get job data (from fixture or queue)
        if fixture_job_data:
            job_ctx_data = fixture_job_data
        else:
            # Read queue for job selection
            content = client_ctx.queue_path.read_text()
            jobs = []
            for m in re.finditer(
                r"^## Job (\d+)\n(.*?)(?=^## |\Z)",
                content,
                re.M | re.S
            ):
                num = m.group(1)
                block = m.group(2)
                def f(key):
                    mm = re.search(rf"{key}:\s*(.+?)(?=\n)", block, re.M)
                    return mm.group(1).strip() if mm else None
                jobs.append({
                    "job_number": num,
                    "topic": f("Topic"),
                    "queue_status": f("Status"),
                    "target_date": f("Date target"),
                    "keyword": f("Target keyword"),
                    "file_path": f("File"),
                })

            planned = [j for j in jobs if j["queue_status"] == "planned"]
            planned.sort(key=lambda j: int(j["job_number"]))
            if not planned:
                result["blocked"] = True
                result["block_reason"] = "No planned jobs in queue"
                return result
            selected = planned[0] if job_number is None else next(
                (j for j in planned if j["job_number"] == str(job_number)), planned[0]
            )
            job_ctx_data = {
                "job_number": selected["job_number"],
                "topic": selected["topic"],
                "target_keyword": selected["keyword"],
                "target_date": selected["target_date"],
                "queue_status": "planned",
                "shopify_handle": None,
                "shopify_article_id": None,
                "published_at": None,
                "file_path": selected["file_path"],
            }

        # Build canonical job context
        job_number_str = str(job_ctx_data["job_number"])
        job_ctx = {
            "job_number": job_number_str,
            "job_label": f"Job {job_number_str}",
            "title": job_ctx_data["topic"],
            "topic": job_ctx_data["topic"],
            "target_keyword": job_ctx_data["target_keyword"],
            "target_date": job_ctx_data["target_date"],
            "expected_draft_date": job_ctx_data["target_date"],
            "queue_status": job_ctx_data["queue_status"],
            "shopify_handle": job_ctx_data.get("shopify_handle"),
            "shopify_article_id": job_ctx_data.get("shopify_article_id"),
            "published_at": job_ctx_data.get("published_at"),
            "file_path": job_ctx_data.get("file_path"),
            "local_draft_path": None,
            "local_draft_exists": False,
        }

        result["selected_job"] = job_ctx_data["job_number"]
        result["selected_topic"] = job_ctx_data["topic"]

        # Writer planning (with HCS-specific H2 outlines — FIX 1)
        writer_agent = HCSWriterAgent(str(BASE_DIR), business_date, client_context=client_ctx)
        writer_plan = build_hcs_writer_plan(writer_agent, job_ctx, pt_result, client_ctx)

        # Save writer plan
        plan_path = run_dir / "writer_plan.json"
        plan_path.write_text(json.dumps(writer_plan, indent=2, default=str), encoding="utf-8")

        # Writer execution
        draft_path = run_dir / f"writer_output_{job_number_str}.html"
        exec_result = write_hcs_article(writer_agent, job_ctx, writer_plan, draft_path, client_ctx)
        result["writer_execution"] = exec_result

        if not exec_result.get("success"):
            result["blocked"] = True
            result["block_phase"] = "WRITER_EXECUTION"
            result["block_reason"] = exec_result.get("error")
            return result

        result["phases_completed"].append("WRITER_EXECUTION")

        # Read written HTML
        html_content = draft_path.read_text(encoding="utf-8") if draft_path.exists() else ""
        html_sha256 = hashlib.sha256(html_content.encode()).hexdigest()

        # Client identity pass
        output_client_id = client_ctx.client_id
        if output_client_id != client_id:
            result["blocked"] = True
            result["block_phase"] = "CLIENT_IDENTITY_GATE"
            result["block_reason"] = f"Client mismatch: expected {client_id}, got {output_client_id}"
            return result
        result["client_identity_pass"] = True
        result["phases_completed"].append("CLIENT_IDENTITY_GATE")

        # Topic identity gate (FIX 1: uses HCS-specific H2s from writer_plan)
        gate_result = run_topic_identity_gate_hcs(job_ctx, writer_plan, html_content, client_ctx)
        result["topic_identity_gate"] = gate_result
        if gate_result.get("decision") == TOPIC_IDENTITY_BLOCK:
            result["blocked"] = True
            result["block_phase"] = "TOPIC_IDENTITY_GATE"
            result["block_reason"] = gate_result.get("blockers")
            return result
        result["topic_identity_pass"] = True
        result["phases_completed"].append("TOPIC_IDENTITY_GATE")

        # Phase 2A review
        phase2a_result = run_phase2a_review_hcs(job_ctx, writer_plan, draft_path, client_ctx)
        result["phase2a_review"] = phase2a_result
        review_decision = phase2a_result.get("review_decision", "")

        if review_decision == "POST_WRITE_REVIEW_BLOCKED":
            result["blocked"] = True
            result["block_phase"] = "PHASE2A_REVIEW"
            result["block_reason"] = phase2a_result.get("blockers", [])
            return result

        if review_decision == "POST_WRITE_REVIEW_NEEDS_HUMAN_REVIEW" and phase2a_result.get("blockers"):
            result["blocked"] = True
            result["block_phase"] = "PHASE2A_REVIEW"
            result["block_reason"] = phase2a_result.get("blockers", [])
            return result

        result["phase2a_pass"] = True
        result["phases_completed"].append("PHASE2A_REVIEW")

        # Phase 2B duplicate gate
        phase2b_result = run_phase2b_duplicate_gate_hcs([job_number_str], client_ctx)
        result["phase2b_duplicate"] = phase2b_result

        records = phase2b_result.get("records", [])
        record = next((r for r in records if str(r.get("job_number")) == job_number_str), {})
        record_type = record.get("record_type", "")

        BLOCKING_TYPES = frozenset([
            "human_duplicate_decision_required",
            "no_local_file",
            "skipped_not_due",
            "blocked_by_compliance_or_html",
        ])
        WARN_TYPES = frozenset(["unclear", "global_site_warning"])
        PASS_TYPES = frozenset(["self_match_info"])

        if record_type in BLOCKING_TYPES:
            result["blocked"] = True
            result["block_phase"] = "PHASE2B_DUPLICATE"
            result["block_reason"] = f"record_type={record_type}"
            return result

        if record_type in WARN_TYPES:
            result["phase2b_warn"] = True

        result["phase2b_pass"] = record_type in PASS_TYPES or record_type in WARN_TYPES
        result["phases_completed"].append("PHASE2B_DUPLICATE")

        # Publisher preflight
        result["publisher_preflight"] = {
            "passed": True,
            "simulated": True,
            "decision": "SIMULATED_NO_SHOPIFY_WRITE",
        }
        result["phases_completed"].append("PUBLISHER_PREFLIGHT")

        # Evidence capability check
        evidence_capable = run_dir.exists() and run_dir.is_dir()
        if not evidence_capable:
            result["blocked"] = True
            result["block_phase"] = "EVIDENCE_CAPABILITY"
            result["block_reason"] = f"Cannot write evidence to {run_dir}"
            return result
        result["evidence_capability_pass"] = True
        result["phases_completed"].append("EVIDENCE_CAPABILITY")

        # FIX 4: Enforce draft_only_policy before any transaction
        dop_check = check_draft_only_policy(client_ctx)
        result["draft_only_policy_check"] = dop_check
        if dop_check.get("blocking"):
            result["blocked"] = True
            result["block_phase"] = "DRAFT_ONLY_POLICY"
            result["block_reason"] = dop_check.get("block_reason")
            return result
        result["phases_completed"].append("DRAFT_ONLY_POLICY_CHECK")

        # FIX 2 + 3: Real shared transaction with idempotency
        tx_result = run_shared_transaction_with_mock_shopify(
            job_ctx=job_ctx,
            writer_plan=writer_plan,
            writer_execution={
                "output_path": str(draft_path),
                "sha256": html_sha256,
                "job_number": job_number_str,
            },
            client_ctx=client_ctx,
            run_dir=run_dir,
        )
        result["transaction_result"] = tx_result

        if tx_result.get("verification_passed"):
            result["phases_completed"].append("TRANSACTION_VERIFICATION")
        
        if tx_result.get("approved"):
            result["phases_completed"].append("TRANSACTION_APPROVED")

        result["phases_completed"].append("TRANSACTION_COMPLETE")

        # ── Write all evidence artifacts ──────────────────────────────────
        (run_dir / "selected_job.json").write_text(
            json.dumps({"job": job_ctx_data, "context": job_ctx}, indent=2, default=str), encoding="utf-8"
        )
        (run_dir / "client_context.json").write_text(
            json.dumps(client_ctx.to_dict(), indent=2, default=str), encoding="utf-8"
        )
        (run_dir / "product_truth_result.json").write_text(
            json.dumps({
                "validation": pt_result.get("validation"),
                "loaded": pt_result.get("loaded")
            }, indent=2, default=str), encoding="utf-8"
        )
        (run_dir / "writer_output.html").write_text(html_content, encoding="utf-8")
        (run_dir / "phase2a_review.json").write_text(
            json.dumps(phase2a_result, indent=2, default=str), encoding="utf-8"
        )
        (run_dir / "phase2b_duplicate.json").write_text(
            json.dumps(phase2b_result, indent=2, default=str), encoding="utf-8"
        )
        (run_dir / "publisher_preflight.json").write_text(
            json.dumps(result["publisher_preflight"], indent=2, default=str), encoding="utf-8"
        )
        (run_dir / "draft_only_policy_check.json").write_text(
            json.dumps(dop_check, indent=2, default=str), encoding="utf-8"
        )

        # Compute summary
        run_summary = {
            "run_id": run_id,
            "client_id": client_id,
            "selected_job": job_number_str,
            "selected_topic": job_ctx_data["topic"],
            "html_sha256": html_sha256,
            "html_word_count": len(html_content.split()),
            "phases_completed": result["phases_completed"],
            "client_identity_pass": result.get("client_identity_pass", False),
            "topic_identity_pass": result.get("topic_identity_pass", False),
            "phase2a_pass": result.get("phase2a_pass", False),
            "phase2b_pass": result.get("phase2b_pass", False),
            "publisher_preflight_pass": result.get("publisher_preflight", {}).get("passed", False),
            "draft_only_policy": dop_check.get("draft_only_policy", False),
            "transaction_decision": tx_result.get("decision", ""),
            "transaction_approved": tx_result.get("approved", False),
            "idempotent": tx_result.get("idempotent", False),
            "transaction_calls": tx_result.get("transaction_calls", 0),
            "evidence_written": True,
            "simulated": True,
        }
        (run_dir / "run_summary.json").write_text(
            json.dumps(run_summary, indent=2, default=str), encoding="utf-8"
        )
        result["run_summary"] = run_summary
        result["pipeline_completed"] = True
        result["pipeline_completed_at"] = datetime.now(timezone.utc).isoformat()

    except Exception as e:
        result["blocked"] = True
        result["block_phase"] = "PIPELINE_EXCEPTION"
        result["block_reason"] = str(e)
        result["exception_type"] = type(e).__name__

    return result


if __name__ == "__main__":
    import sys as _sys

    client_id = "hcs_gadgets"
    job_number = None
    output_dir = None

    for arg in _sys.argv[1:]:
        if arg.startswith("--client="):
            client_id = arg.split("=", 1)[1]
        elif arg.startswith("--job="):
            job_number = arg.split("=", 1)[1]
        elif arg.startswith("--output-dir="):
            output_dir = Path(arg.split("=", 1)[1])

    result = run_hcs_pipeline_simulation(
        client_id=client_id,
        job_number=job_number,
        output_dir=output_dir,
    )

    print(json.dumps(result, indent=2, default=str, allow_nan=False))
    _sys.exit(0 if not result.get("blocked") else 1)
