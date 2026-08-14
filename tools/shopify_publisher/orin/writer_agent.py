
import json
import re
import hashlib
from html import unescape
from pathlib import Path
from datetime import datetime, timedelta
import sys
_AGENTS_DIR = Path(__file__).parent
sys.path.insert(0, str(_AGENTS_DIR))
_SOURCE_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_SOURCE_ROOT))

from content_quality_gate import CONTRACT_VERSION, DEFAULT_CONTRACT, evaluate_article_quality
from model_writer import ModelWriterError, generate_article, model_writer_enabled
from topic_identity_gate import (
    TOPIC_IDENTITY_BLOCK,
    get_blocked_terms_for_cluster,
    run_topic_identity_gate,
)

# Sentinels
BLOCK_JOB_CONTEXT_MISMATCH = "BLOCK_JOB_CONTEXT_MISMATCH"
BLOCK_INVALID_PLANNED_HANDLE = "BLOCK_INVALID_PLANNED_HANDLE"


def _model_quality_retry_feedback(receipt):
    """Return a small, deterministic retry brief from a quality receipt.

    The prior article text is deliberately excluded: sending it back to the
    model would widen prompt-injection exposure and makes evidence needlessly
    large. Only machine-generated codes and numeric expectations are used.
    """
    return {
        "visible_word_count": receipt["metrics"].get("visible_word_count", 0),
        "target_keyword_occurrences": receipt["metrics"].get(
            "target_keyword_occurrences", 0
        ),
        "failed_requirements": [
            {
                "code": blocker["code"],
                "actual": blocker["actual"],
                "expected": blocker["expected"],
            }
            for blocker in receipt["blockers"]
        ],
    }


def _model_topic_identity_retry_feedback(receipt, writer_plan):
    """Return safe, deterministic corrections for topic-identity failures.

    The generated article and gate detail strings are deliberately excluded.
    Only approved plan inputs and fixed failure codes are returned to the
    model.
    """
    requirements = []
    blockers = set(receipt.get("blockers", []))

    if "H1_MISSING_OR_MISMATCH" in blockers:
        requirements.append(
            {
                "code": "TI_H1_MISSING_OR_MISMATCH",
                "actual": "failed",
                "expected": (
                    "include exactly one H1 whose text exactly matches "
                    f"{writer_plan.get('title', '')!r}"
                ),
            }
        )

    if "H2_PLAN_MISMATCH" in blockers:
        required_h2s = [
            item.get("h2", "").strip()
            for item in writer_plan.get("h2_outline", [])
            if item.get("h2", "").strip()
        ]
        requirements.append(
            {
                "code": "TI_H2_PLAN_MISMATCH",
                "actual": "one or more approved H2 headings are missing",
                "expected": {
                    "required_h2_headings": required_h2s,
                    "matching": "include each heading as an H2",
                },
            }
        )

    if "TOPIC_IDENTITY_CONTAMINATED" in blockers:
        requirements.append(
            {
                "code": "TI_TOPIC_IDENTITY_CONTAMINATED",
                "actual": "one or more blocked cross-topic terms are present",
                "expected": {
                    "blocked_terms_must_be_absent": sorted(
                        get_blocked_terms_for_cluster(
                            writer_plan.get("cluster", "")
                        )
                    )
                },
            }
        )

    for blocker in sorted(
        blockers
        - {
            "H1_MISSING_OR_MISMATCH",
            "H2_PLAN_MISMATCH",
            "TOPIC_IDENTITY_CONTAMINATED",
        }
    ):
        requirements.append(
            {
                "code": f"TI_{blocker}",
                "actual": "failed",
                "expected": "satisfy the approved topic-identity contract",
            }
        )

    return {"failed_requirements": requirements}


def _model_validation_retry_feedback(quality_receipt, topic_receipt, writer_plan):
    """Combine quality and topic failures into the single bounded retry."""
    failed_requirements = []
    if not quality_receipt["passed"]:
        failed_requirements.extend(
            _model_quality_retry_feedback(quality_receipt)["failed_requirements"]
        )
    if topic_receipt["decision"] == TOPIC_IDENTITY_BLOCK:
        failed_requirements.extend(
            _model_topic_identity_retry_feedback(
                topic_receipt, writer_plan
            )["failed_requirements"]
        )
    return {"failed_requirements": failed_requirements}


def _model_validation_receipts(
    body_html,
    *,
    job_number,
    title,
    target_keyword,
    cluster,
    h2_outline,
    site_url,
):
    """Evaluate both fail-closed writer contracts for one model response."""
    quality_receipt = evaluate_article_quality(
        body_html,
        target_keyword=target_keyword,
        site_url=site_url,
        approved_title=title,
    )
    topic_receipt = run_topic_identity_gate(
        job_id=job_number,
        expected_topic=title,
        target_keyword=target_keyword,
        cluster=cluster,
        approved_h2_plan=h2_outline,
        output_html=body_html,
    )
    return quality_receipt, topic_receipt


def _hcs_model_validation_receipts(
    body_html,
    *,
    job_number,
    title,
    target_keyword,
    cluster,
    h2_outline,
):
    """Evaluate HCS structure, UK compliance, and topic identity pre-write."""
    from hcs_html_contract_validator import run_checks as run_hcs_contract_checks
    from tools.shopify_publisher.compliance_check import analyze_html

    contract_failures, _, _ = run_hcs_contract_checks(body_html)
    compliance_failures, _ = analyze_html(body_html)
    blockers = []
    if contract_failures:
        blockers.append(
            {
                "code": "HCS_HTML_CONTRACT",
                "actual": "one or more mandatory HCS structural checks failed",
                "expected": (
                    "satisfy every HCS output-contract requirement, including "
                    "wrappers, planned H2s, FAQ items, CTA, and deterministic schema"
                ),
            }
        )
    if compliance_failures:
        blockers.append(
            {
                "code": "HCS_UK_COMPLIANCE",
                "actual": "unsafe or insufficiently restricted public-use wording detected",
                "expected": (
                    "describe electric-scooter riding only on suitable private land "
                    "with the landowner's permission; do not mention roads, streets, "
                    "pavements, cycle lanes, commuting, or other public-access surfaces"
                ),
            }
        )
    quality_receipt = {
        "passed": not blockers,
        "blockers": blockers,
        "metrics": {
            "hcs_contract_failure_count": len(contract_failures),
            "uk_compliance_failure_count": len(compliance_failures),
        },
    }
    topic_receipt = run_topic_identity_gate(
        job_id=job_number,
        expected_topic=title,
        target_keyword=target_keyword,
        cluster=cluster,
        approved_h2_plan=h2_outline,
        output_html=_html_without_schema_scripts(body_html),
    )
    return quality_receipt, topic_receipt


def _model_attempt_receipt(attempt, model_result, quality_receipt, topic_receipt):
    """Build durable evidence for one model response validation."""
    quality_codes = [
        blocker["code"] for blocker in quality_receipt["blockers"]
    ]
    topic_codes = [
        f"TI_{blocker}" for blocker in topic_receipt["blockers"]
    ]
    return {
        "attempt": attempt,
        "response_id": model_result.response_id,
        "quality_passed": quality_receipt["passed"],
        "topic_identity_passed": (
            topic_receipt["decision"] != TOPIC_IDENTITY_BLOCK
        ),
        "blocker_codes": quality_codes + topic_codes,
    }


_RETRYABLE_MODEL_OUTPUT_PREFIXES = (
    "model response ",
    "model article ",
)
_RETRYABLE_MODEL_OUTPUT_ERRORS = {
    "model returned an empty article",
    "model provider did not return a complete response",
}


def _model_output_retry_feedback(error):
    """Return a bounded correction brief for a deterministic output miss."""
    detail = str(error)
    if (
        detail not in _RETRYABLE_MODEL_OUTPUT_ERRORS
        and not detail.startswith(_RETRYABLE_MODEL_OUTPUT_PREFIXES)
    ):
        raise error
    expected = (
        "exactly one complete HTML article inside the required sentinel pair "
        "with no other text"
    )
    if detail.startswith("model article contains unsupported attribute:"):
        expected = (
            "use only class on allowed tags, href on a tags, and a lowercase "
            "anchor-safe id on h2 tags; remove id from every non-h2 element "
            "and remove every other attribute"
        )
    return {
        "failed_requirements": [
            {
                "code": "MW_OUTPUT_CONTRACT",
                "actual": detail,
                "expected": expected,
            }
        ],
    }


def _normalise_model_metadata(
    body_html,
    *,
    meta_title,
    meta_description,
    approved_handle,
    target_keyword,
    cluster,
    job_number,
):
    """Replace model-authored metadata with deterministic approved values.

    SEO metadata is structured pipeline data, not creative article copy. The
    model still authors the visible article, but it cannot introduce random
    length failures or alter the approved handle through leading comments.
    """
    article_start = re.search(
        r'<div\b[^>]*\bclass\s*=\s*["\'][^"\']*\bhs-article\b[^"\']*["\'][^>]*>',
        body_html,
        flags=re.IGNORECASE,
    )
    if article_start is None:
        return body_html

    def comment_value(value):
        return re.sub(r"\s+", " ", str(value)).strip().replace("--", "—")

    metadata = "\n".join(
        [
            "<!--",
            f"SEO Title: {comment_value(meta_title)}",
            f"Meta Title: {comment_value(meta_title)}",
            f"Meta Description: {comment_value(meta_description)}",
            f"URL Slug: {comment_value(approved_handle)}",
            f"Target Keyword: {comment_value(target_keyword)}",
            f"Cluster: {comment_value(cluster)}",
            f"Job: {comment_value(job_number)}",
            "-->",
        ]
    )
    return f"{metadata}\n{body_html[article_start.start():].lstrip()}"


def _normalise_hcs_model_output(
    body_html,
    *,
    meta_title,
    meta_description,
    approved_handle,
    target_keyword,
    cluster,
    job_number,
    title,
    site_url,
    blog_handle,
    byline,
):
    """Bind HCS metadata and deterministic schema to validated model HTML."""
    article_start = re.search(
        r'<article\b[^>]*\bclass\s*=\s*["\'][^"\']*\bhcs-article\b[^"\']*["\'][^>]*>',
        body_html,
        flags=re.IGNORECASE,
    )
    if article_start is None:
        return body_html
    article = body_html[article_start.start():].lstrip()
    closing = re.search(r"</article>\s*$", article, flags=re.IGNORECASE)
    if closing is None:
        return body_html

    def text_content(fragment):
        return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()

    faq_entities = []
    for faq in re.findall(
        r'<div\b[^>]*\bclass\s*=\s*["\'][^"\']*\bhcs-faq-item\b[^"\']*["\'][^>]*>(.*?)</div>',
        article,
        flags=re.IGNORECASE | re.DOTALL,
    ):
        question = re.search(r"<h3\b[^>]*>(.*?)</h3>", faq, flags=re.IGNORECASE | re.DOTALL)
        answer = re.search(r"<p\b[^>]*>(.*?)</p>", faq, flags=re.IGNORECASE | re.DOTALL)
        if question is not None and answer is not None:
            faq_entities.append(
                {
                    "@type": "Question",
                    "name": text_content(question.group(1)),
                    "acceptedAnswer": {
                        "@type": "Answer",
                        "text": text_content(answer.group(1)),
                    },
                }
            )

    today = datetime.now().date().isoformat()
    canonical_url = f"{site_url.rstrip('/')}/blogs/{blog_handle}/{approved_handle}"
    schemas = [
        {
            "@context": "https://schema.org",
            "@type": "BlogPosting",
            "headline": title,
            "datePublished": today,
            "dateModified": today,
            "author": {"@type": "Organization", "name": byline},
            "publisher": {
                "@type": "Organization",
                "name": byline,
                "url": site_url,
            },
            "url": canonical_url,
            "description": meta_description,
        }
    ]
    if faq_entities:
        schemas.append(
            {
                "@context": "https://schema.org",
                "@type": "FAQPage",
                "mainEntity": faq_entities,
            }
        )
    schema_html = "\n".join(
        '<script type="application/ld+json">\n'
        + json.dumps(schema, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
        + "\n</script>"
        for schema in schemas
    )
    article = article[:closing.start()].rstrip() + "\n\n" + schema_html + "\n</article>"

    def comment_value(value):
        return re.sub(r"\s+", " ", str(value)).strip().replace("--", "—")

    metadata = "\n".join(
        [
            "<!--",
            f"SEO Title: {comment_value(meta_title)}",
            f"Meta Title: {comment_value(meta_title)}",
            f"Meta Description: {comment_value(meta_description)}",
            f"URL Slug: {comment_value(approved_handle)}",
            f"Target Keyword: {comment_value(target_keyword)}",
            f"Cluster: {comment_value(cluster)}",
            f"Job: {comment_value(job_number)}",
            "-->",
        ]
    )
    return f"{metadata}\n{article}"


def _html_without_schema_scripts(html):
    """Return visible article HTML without deterministic JSON-LD payloads."""
    return re.sub(
        r"<script\b[^>]*>.*?</script>",
        "",
        html,
        flags=re.IGNORECASE | re.DOTALL,
    )


class WriterAgent:
    def __init__(self, base_dir, current_date_str, client_context=None):
        """
        Initialise WriterAgent.

        Args:
            base_dir: workspace root (e.g. /data/.openclaw/workspace)
            current_date_str: YYYY-MM-DD string
            client_context: optional ClientContext object or client_id string.
                           When provided, writer uses client-specific paths,
                           byline, URLs and brand rules instead of hardcoded
                           Hoverboard Store values.
                           When None, falls back to hardcoded Hoverboard Store
                           paths for backward compatibility.
        """
        self.base_dir = Path(base_dir)

        # Client context: support both ClientContext objects and client_id strings
        self._client_context = None
        if client_context is not None:
            if isinstance(client_context, str):
                from client_context import load_client_context
                self._client_context = load_client_context(client_context)
            else:
                self._client_context = client_context

        self._init_paths()
        self.queue_path = self.content_dir / "content_queue_3_months.md"
        self.current_date = datetime.strptime(current_date_str, "%Y-%m-%d").date()

    def _init_paths(self):
        """Initialise paths based on client context or Hoverboard Store defaults."""
        if self._client_context is not None:
            ctx = self._client_context
            self.content_dir = ctx.client_root / "content_engine"
            self.rules_path = ctx.brand_rules_path
            self.writing_rules_path = ctx.writing_rules_path
            self.compliance_rules_path = ctx.compliance_rules_path
            self.draft_inventory_path = ctx.client_root / "obsidian_vault" / "Draft Inventory.md"
            self.shopify_inventory_path = ctx.client_root / "content_engine" / "shopify_inventory.json"
        else:
            # Backward-compatible defaults: Hoverboard Store
            self.content_dir = self.base_dir / "clients" / "hoverboard_store" / "content_engine"
            self.rules_path = self.base_dir / "clients" / "hoverboard_store" / "rules.md"
            self.writing_rules_path = self.content_dir / "writing_rules.md"
            self.compliance_rules_path = self.content_dir / "compliance_rules.md"
            self.draft_inventory_path = (
                self.base_dir / "clients" / "hoverboard_store"
                / "obsidian_vault" / "Hoverboard Store Content System" / "Draft Inventory.md"
            )
            self.shopify_inventory_path = self.content_dir / "shopify_inventory.json"

    @property
    def byline(self) -> str:
        """Author byline for articles."""
        if self._client_context is not None:
            return self._client_context.byline
        return "Hoverboard Store"

    @property
    def site_url(self) -> str:
        """Public site URL."""
        if self._client_context is not None:
            return self._client_context.site_url
        return "https://hoverboardstore.co.uk"

    @property
    def blog_handle(self) -> str:
        """Shopify blog handle."""
        if self._client_context is not None:
            return self._client_context.blog_handle
        return "journal-insights"

    @property
    def is_hcs(self) -> bool:
        """True if client is HCS Gadgets."""
        return self._client_context is not None and self._client_context.client_id == "hcs_gadgets"

    def _read_file(self, path):
        if path.exists():
            return path.read_text()
        return ""

    def _parse_queue(self, queue_content):
        jobs = []
        job_pattern = re.compile(r"## Job (\d+)\nDate target: (\d{4}-\d{2}-\d{2})\nCluster: (.+)\nDecision: (.+)\nStatus: (.+)\nTopic: (.+)\nTarget keyword: (.+)\nFile: (.+)\nNotes:\n((?:- .+\n)+)", re.MULTILINE)
        for match in job_pattern.finditer(queue_content):
            job_data = match.groups()
            jobs.append({
                "job_number": int(job_data[0]),
                "date_target": datetime.strptime(job_data[1], "%Y-%m-%d").date(),
                "cluster": job_data[2],
                "decision": job_data[3],
                "status": job_data[4],
                "topic": job_data[5],
                "target_keyword": job_data[6],
                "file": job_data[7],
                "notes": [note.strip() for note in job_data[8].strip().split('\\n- ') if note.strip()]
            })
        return jobs

    def _generate_slug(self, topic):
        # Use canonical handle utility — single source of truth
        from handle_utils import normalise_shopify_handle
        return normalise_shopify_handle(topic)

    def _read_compliance_rules(self):
        """Read Hoverboard Store compliance rules."""
        path = self.compliance_rules_path
        if path.exists():
            return path.read_text()
        return ""

    def _read_writing_rules(self):
        """Read Hoverboard Store writing rules."""
        path = self.writing_rules_path
        if path.exists():
            return path.read_text()
        return ""

    def _generate_article_angle(self, topic, target_keyword, cluster):
        """
        Derive article angle from topic, keyword, and cluster.
        Hoverboard Store uses practical buyer-guide angles with safety-first framing.
        """
        cluster_angles = {
            "Hoverkart": (
                f"A practical compatibility and safety guide for buyers "
                f"considering a {target_keyword}. Focus on what to check before "
                f"purchasing, what questions to ask, and how to verify fit. "
                f"No road-use claims. No performance guarantees."
            ),
            "Accessories": (
                f"A practical safety and usability guide covering {target_keyword}. "
                f"Focus on what genuinely helps, what to avoid, and how to use "
                f"accessories correctly. No safety guarantees. No performance claims."
            ),
            "Safety": (
                f"A safety-first practical guide on {target_keyword}. "
                f"Focus on actionable checks and precautions. "
                f"No guaranteed safety claims. No legal permissions."
            ),
            "Troubleshooting": (
                f"A practical troubleshooting guide for {target_keyword}. "
                f"Help readers diagnose the issue safely and know when to seek "
                f"professional support. No repair guarantees."
            ),
            "Buyer Guide": (
                f"A practical buyer guide for {target_keyword}. "
                f"Help readers make an informed decision without exaggerated claims. "
                f"No best-in-class claims. No performance warranties."
            ),
            "Maintenance": (
                f"A practical maintenance guide for {target_keyword}. "
                f"Help readers look after their equipment correctly. "
                f"No guarantees about equipment longevity."
            ),
            "Seasonal": (
                f"A seasonal gift or occasion guide for {target_keyword}. "
                f"Focus on practical suitability and safety considerations. "
                f"No road-use claims. No performance promises."
            ),
        }
        return cluster_angles.get(cluster, f"A practical guide on {target_keyword}. No safety guarantees.")

    @staticmethod
    def _is_electric_scooter_topic(topic, target_keyword):
        """Return whether the approved subject is specifically about scooters."""
        return "scooter" in f"{topic} {target_keyword}".lower()

    def _generate_h2_outline(self, topic, target_keyword, cluster):
        """
        Generate H2 outline from topic and cluster.
        Hoverboard Store uses: Intro → dedicated Quick Answer block →
        Content H2s → Checklist → FAQ → CTA.
        """
        base_outline = [
            {"id": "introduction", "h2": "Introduction", "label": "Introduction"},
        ]

        cluster_outlines = {
            "Hoverkart": [
                {"id": "why-compatibility-matters", "h2": "Why Hoverkart Compatibility Matters", "label": "Why compatibility matters"},
                {"id": "what-to-check-before-buying", "h2": "What to Check Before You Buy", "label": "What to check before buying"},
                {"id": "wheel-size-match", "h2": "Wheel Size and Board Compatibility", "label": "Wheel size match"},
                {"id": "weight-limits", "h2": "Weight Limits and Rider Suitability", "label": "Weight limits"},
                {"id": "frame-and-straps", "h2": "Frame, Straps, and Connection Points", "label": "Frame and straps"},
                {"id": "safety-considerations", "h2": "Safety Considerations", "label": "Safety considerations"},
                {"id": "checklist", "h2": "Compatibility Checklist", "label": "Compatibility checklist"},
                {"id": "faq", "h2": "Frequently Asked Questions", "label": "FAQs"},
            ],
            "Accessories": [
                {"id": "why-it-matters", "h2": f"Why {target_keyword.title()} Matters", "label": "Why it matters"},
                {"id": "what-to-look-for", "h2": "What to Look For", "label": "What to look for"},
                {"id": "things-to-avoid", "h2": "Things to Avoid", "label": "Things to avoid"},
                {"id": "checklist", "h2": "Quick Checklist", "label": "Quick checklist"},
                {"id": "faq", "h2": "Frequently Asked Questions", "label": "FAQs"},
            ],
            "Safety": [
                {"id": "why-it-matters", "h2": f"Why {target_keyword.title()} Matters", "label": "Why it matters"},
                {"id": "key-checks", "h2": "Key Safety Checks", "label": "Key safety checks"},
                {"id": "warning-signs", "h2": "Warning Signs to Watch For", "label": "Warning signs"},
                {"id": "checklist", "h2": "Safety Checklist", "label": "Safety checklist"},
                {"id": "faq", "h2": "Frequently Asked Questions", "label": "FAQs"},
            ],
            "Troubleshooting": [
                {"id": "quick-diagnosis", "h2": "Quick Diagnosis", "label": "Quick diagnosis"},
                {"id": "common-causes", "h2": "Common Causes", "label": "Common causes"},
                {"id": "safe-checks", "h2": "Safe Checks You Can Do", "label": "Safe checks"},
                {"id": "when-to-get-help", "h2": "When to Get Professional Help", "label": "When to get help"},
                {"id": "faq", "h2": "Frequently Asked Questions", "label": "FAQs"},
            ],
            "Buyer Guide": [
                {"id": "what-to-look-for", "h2": "What to Look For", "label": "What to look for"},
                {"id": "key-factors", "h2": "Key Factors for Your Decision", "label": "Key factors"},
                {"id": "suitability-and-support", "h2": "Suitability, Safety, and Support Checks", "label": "Suitability and support"},
                {"id": "checklist", "h2": "Buyer's Checklist", "label": "Buyer's checklist"},
                {"id": "faq", "h2": "Frequently Asked Questions", "label": "FAQs"},
            ],
            "Maintenance": [
                {"id": "why-maintenance-matters", "h2": "Why Maintenance Matters", "label": "Why maintenance matters"},
                {"id": "how-to-do-it-safely", "h2": "How to Do It Safely", "label": "How to do it safely"},
                {"id": "warning-signs", "h2": "Warning Signs That Need Expert Help", "label": "Warning signs"},
                {"id": "checklist", "h2": "Maintenance Checklist", "label": "Maintenance checklist"},
                {"id": "faq", "h2": "Frequently Asked Questions", "label": "FAQs"},
            ],
            "Seasonal": [
                {"id": "what-to-consider", "h2": "What to Consider", "label": "What to consider"},
                {"id": "top-picks", "h2": "Practical Picks for This Occasion", "label": "Practical picks"},
                {"id": "safety-reminder", "h2": "A Quick Safety Reminder", "label": "Safety reminder"},
                {"id": "before-you-order", "h2": "Checks to Make Before You Order", "label": "Before you order"},
                {"id": "faq", "h2": "Frequently Asked Questions", "label": "FAQs"},
            ],
        }

        content_outline = cluster_outlines.get(cluster, [
            {"id": "overview", "h2": "Overview", "label": "Overview"},
            {"id": "key-points", "h2": "Key Points", "label": "Key points"},
            {"id": "practical-considerations", "h2": "Practical Considerations", "label": "Practical considerations"},
            {"id": "checklist", "h2": "Checklist", "label": "Checklist"},
            {"id": "faq", "h2": "Frequently Asked Questions", "label": "FAQs"},
        ])

        closing_heading = (
            "Explore Electric Scooters at Hoverboard Store"
            if self._is_electric_scooter_topic(topic, target_keyword)
            else "Find the Right Hoverboard Setup at Hoverboard Store"
        )
        closing = [
            {
                "id": "cta",
                "h2": closing_heading,
                "label": "Shop now",
            },
        ]

        return base_outline + content_outline + closing

    def _generate_internal_links(self, topic, target_keyword, cluster):
        """
        Generate internal link candidates from cluster and topic.
        Returns list of dicts with anchor_text, reason, and collection/blog URL.
        """
        links = []

        if self._is_electric_scooter_topic(topic, target_keyword) and not self.is_hcs:
            return [
                {
                    "anchor_text": "browse electric scooters",
                    "url": f"{self.site_url}/collections/electric-scooters",
                    "reason": "Primary electric scooter collection",
                    "type": "collection",
                },
                {
                    "anchor_text": "responsible use and safety guidance",
                    "url": f"{self.site_url}/pages/safety-responsible-use",
                    "reason": "Store safety and responsible-use guidance",
                    "type": "page",
                },
                {
                    "anchor_text": "electric scooter support FAQs",
                    "url": f"{self.site_url}/pages/faqs",
                    "reason": "Store support and frequently asked questions",
                    "type": "page",
                },
                {
                    "anchor_text": "contact the Hoverboard Store team",
                    "url": f"{self.site_url}/pages/contact",
                    "reason": "Model-specific support contact",
                    "type": "page",
                },
                {
                    "anchor_text": "read more practical riding guides",
                    "url": f"{self.site_url}/blogs/{self.blog_handle}",
                    "reason": "Primary advice and support blog",
                    "type": "blog",
                },
            ]

        # Collection links (always relevant)
        collection_links = {
            "Hoverkart": {
                "url": "https://hoverboardstore.co.uk/collections/hoverkarts",
                "anchor": "hoverkarts",
                "reason": "Primary hoverkart collection page",
            },
            "Accessories": {
                "url": "https://hoverboardstore.co.uk/collections/accessories",
                "anchor": "hoverboard accessories",
                "reason": "Primary accessories collection",
            },
            "Safety": {
                "url": "https://hoverboardstore.co.uk/collections/hoverboards",
                "anchor": "hoverboards",
                "reason": "Hoverboard collection — safety starts with the right board",
            },
            "default": {
                "url": "https://hoverboardstore.co.uk/collections/hoverboards",
                "anchor": "hoverboards",
                "reason": "Primary hoverboard collection",
            },
        }

        cl = collection_links.get(cluster, collection_links["default"])
        links.append({
            "anchor_text": cl["anchor"],
            "url": cl["url"],
            "reason": cl["reason"],
            "type": "collection",
        })

        # Blog cross-links by cluster
        blog_links = {
            "Hoverkart": [
                {
                    "anchor_text": "how to choose a hoverkart for a child",
                    "url": "https://hoverboardstore.co.uk/blogs/journal-insights/how-to-choose-hoverkart-for-child",
                    "reason": "Related hoverkart guide — covers seat and frame selection",
                },
                {
                    "anchor_text": "hoverkart setup guide for beginners",
                    "url": "https://hoverboardstore.co.uk/blogs/journal-insights/hoverkart-setup-guide-beginners",
                    "reason": "Related hoverkart setup guide — covers straps and connection",
                },
            ],
            "Accessories": [
                {
                    "anchor_text": "hoverboard safety checklist before every ride",
                    "url": "https://hoverboardstore.co.uk/blogs/journal-insights/hoverboard-safety-checklist-before-every-ride",
                    "reason": "Related safety checklist — relevant companion piece",
                },
            ],
            "Safety": [
                {
                    "anchor_text": "hoverboard laws UK 2026",
                    "url": "https://hoverboardstore.co.uk/blogs/journal-insights/hoverboard-laws-uk-where-you-can-and-cannot-ride",
                    "reason": "Related legal/safety guide — private land use reminder",
                },
            ],
            "Troubleshooting": [
                {
                    "anchor_text": "hoverboard accessories checklist for new riders",
                    "url": "https://hoverboardstore.co.uk/blogs/journal-insights/hoverboard-accessories-checklist-new-riders",
                    "reason": "Related accessories guide — new rider support",
                },
            ],
            "default": [
                {
                    "anchor_text": "hoverboard safety checklist before every ride",
                    "url": "https://hoverboardstore.co.uk/blogs/journal-insights/hoverboard-safety-checklist-before-every-ride",
                    "reason": "Safety checklist — always relevant companion",
                },
            ],
        }

        bl = blog_links.get(cluster, blog_links["default"])
        for b in bl:
            links.append({**b, "type": "blog"})

        if self.is_hcs:
            return links

        # Phase 3.5 requires five useful internal paths for a long-form blog
        # post. Add stable collection and guide candidates, then de-duplicate by
        # URL so the writer can place at least five distinct links.
        standard_links = [
            {
                "anchor_text": "browse hoverboards",
                "url": f"{self.site_url}/collections/hoverboards",
                "reason": "Primary hoverboard collection",
                "type": "collection",
            },
            {
                "anchor_text": "shop hoverboard accessories",
                "url": f"{self.site_url}/collections/accessories",
                "reason": "Accessories collection for relevant support products",
                "type": "collection",
            },
            {
                "anchor_text": "hoverboard safety checklist",
                "url": (
                    f"{self.site_url}/blogs/{self.blog_handle}/"
                    "hoverboard-safety-checklist-before-every-ride"
                ),
                "reason": "Safety checklist for supporting guidance",
                "type": "blog",
            },
            {
                "anchor_text": "UK hoverboard laws guide",
                "url": (
                    f"{self.site_url}/blogs/{self.blog_handle}/"
                    "hoverboard-laws-uk-where-you-can-and-cannot-ride"
                ),
                "reason": "UK use and legal-context guide",
                "type": "blog",
            },
            {
                "anchor_text": "new rider accessories guide",
                "url": (
                    f"{self.site_url}/blogs/{self.blog_handle}/"
                    "hoverboard-accessories-checklist-new-riders"
                ),
                "reason": "Practical supporting guide for new riders and buyers",
                "type": "blog",
            },
        ]
        if cluster == "Hoverkart":
            standard_links.insert(
                1,
                {
                    "anchor_text": "explore hoverkarts",
                    "url": f"{self.site_url}/collections/hoverkarts",
                    "reason": "Hoverkart collection for compatible seated setups",
                    "type": "collection",
                },
            )
        existing_urls = {link.get("url") for link in links}
        for link in standard_links:
            if link["url"] not in existing_urls:
                links.append(link)
                existing_urls.add(link["url"])

        return links

    def _generate_faq_plan(self, topic, target_keyword, cluster):
        """
        Generate FAQ plan from topic and cluster.
        Returns list of {question, answer_template} dicts.
        """
        if self._is_electric_scooter_topic(topic, target_keyword):
            topic_text = f"{topic} {target_keyword}".lower()
            if "range" in topic_text:
                return [
                    {
                        "question": "What conditions sit behind an electric scooter range figure?",
                        "answer_template": (
                            "Check the exact product listing, manual, and manufacturer notes for "
                            "the rider weight, speed or mode, surface, temperature, and other test "
                            "conditions used for that model."
                        ),
                    },
                    {
                        "question": "Why can real-world electric scooter range differ from the listing?",
                        "answer_template": (
                            "Real use varies with the rider, terrain, speed or mode, temperature, "
                            "tyre condition, charging, and storage. Avoid a generic prediction and "
                            "use the model-specific manufacturer guidance."
                        ),
                    },
                    {
                        "question": "How should I compare range claims between scooter models?",
                        "answer_template": (
                            "Compare the stated test conditions as well as the headline distance. "
                            "Ask the seller or manufacturer when a listing does not explain how "
                            "the figure was measured."
                        ),
                    },
                    {
                        "question": "Where should I check battery charging and storage guidance?",
                        "answer_template": (
                            "Use the manual and manufacturer guidance for the exact scooter and "
                            "battery. Follow their charging, storage, inspection, and replacement "
                            "instructions rather than general advice."
                        ),
                    },
                ]

            if "brake" in topic_text:
                return [
                    {
                        "question": "What should I check before a child rides an electric scooter?",
                        "answer_template": (
                            "Check the brake lever or control, visible cable or hose, foot brake, "
                            "wheels, and tyres against the manual for that exact scooter. Stop use "
                            "if anything is loose, damaged, worn, or behaves differently from the "
                            "previous ride."
                        ),
                    },
                    {
                        "question": "What should I do if the brake lever feels different?",
                        "answer_template": (
                            "Do not ride the scooter until the cause is understood. Check the manual "
                            "for the model and ask the manufacturer, seller, or a qualified technician "
                            "to inspect or adjust the brake when needed."
                        ),
                    },
                    {
                        "question": "Should I test the brake after the visual checks?",
                        "answer_template": (
                            "Follow the model's manual. If it permits a functional check, an adult can "
                            "supervise a gentle walking-pace test in a suitable private space after the "
                            "visual checks pass. Stop immediately if braking feels inconsistent."
                        ),
                    },
                    {
                        "question": "How often should electric scooter brakes be checked?",
                        "answer_template": (
                            "Use a short visual and feel-based check before each ride, then follow the "
                            "manufacturer's maintenance and service intervals for deeper inspection. "
                            "Check again after a knock, wet ride, unusual noise, or change in feel."
                        ),
                    },
                ]

            return [
                {
                    "question": "Which product details should I verify before choosing an electric scooter?",
                    "answer_template": (
                        "Check the exact listing, label, manual, and manufacturer guidance for "
                        "the intended rider and use. Do not infer suitability from appearance or "
                        "from a different scooter model."
                    ),
                },
                {
                    "question": "Where can I find model-specific electric scooter guidance?",
                    "answer_template": (
                        "Start with the manual and manufacturer documentation for the exact model. "
                        "Ask the seller or manufacturer when a specification or instruction is unclear."
                    ),
                },
                {
                    "question": "What should I ask the seller before I buy?",
                    "answer_template": (
                        "Ask for the exact model specification, manual, manufacturer guidance, and "
                        "any product-specific limits that matter to the intended rider and use."
                    ),
                },
                {
                    "question": "What UK use rules should I check for an electric scooter?",
                    "answer_template": (
                        "Check current official UK guidance for the rider and location before use. "
                        "Use suitable private land with the landowner's permission and follow the "
                        "manual and manufacturer guidance."
                    ),
                },
            ]

        topic_text = f"{topic} {target_keyword}".lower()
        if "footpad" in topic_text or "foot pad" in topic_text:
            return [
                {
                    "question": "What signs show that hoverboard footpad grip is worn?",
                    "answer_template": (
                        "Stop using the board if the pad is loose, split, peeling, uneven, "
                        "or no longer provides a consistent surface. Check the exact model "
                        "manual and ask the manufacturer, seller, or a qualified service "
                        "provider when replacement or sensor work may be needed."
                    ),
                },
                {
                    "question": "How should hoverboard footpads be cleaned?",
                    "answer_template": (
                        "Follow the cleaning instructions in the manual for the exact board. "
                        "Do not remove the pads, soak the board, use harsh chemicals, or allow "
                        "liquid into seams or sensor areas unless the manufacturer explicitly "
                        "instructs you to do so."
                    ),
                },
                {
                    "question": "Can I fit any replacement grip pad to my hoverboard?",
                    "answer_template": (
                        "No. Confirm exact-model compatibility, dimensions, sensor clearance, "
                        "and fitting instructions with the manufacturer or seller. Do not cut, "
                        "layer, or reposition material over a sensor area."
                    ),
                },
                {
                    "question": "What footwear should a rider use on hoverboard footpads?",
                    "answer_template": (
                        "Use suitable closed footwear that is secure, dry, and in good "
                        "condition. Follow the board and protective-equipment manufacturers' "
                        "instructions, and do not ride in socks or with bare feet."
                    ),
                },
            ]

        faq_templates = {
            "Hoverkart": [
                {
                    "question": f"How do I know if a hoverkart is compatible with my hoverboard?",
                    "answer_template": (
                        "Check three things before buying: wheel size (6.5, 8, or 8.5 inch), "
                        "the hoverkart frame connector type, and the weight limit. "
                        "Not all hoverkarts fit all boards — confirm the specifications match "
                        "your board before purchasing."
                    ),
                },
                {
                    "question": "What wheel sizes are compatible with most hoverkarts?",
                    "answer_template": (
                        "Most hoverkarts are designed for 6.5-inch, 8-inch, or 8.5-inch wheels. "
                        "Check your hoverboard wheel diameter and match it to the hoverkart specification. "
                        "Using the wrong wheel size can affect stability and safety."
                    ),
                },
                {
                    "question": "What is the weight limit for a hoverkart?",
                    "answer_template": (
                        "Weight limits vary by hoverkart model. Check the manufacturer's "
                        "specification for your specific hoverkart. Do not exceed the rated limit — "
                        "it affects stability and safety. Also check your hoverboard's weight limit."
                    ),
                },
                {
                    "question": "Can I use a hoverkart on any hoverboard?",
                    "answer_template": (
                        "No — hoverkart compatibility depends on wheel size, frame connector, "
                        "and weight limit. Not all hoverkarts fit all boards. "
                        "Use the compatibility checklist in this guide to verify fit before buying."
                    ),
                },
            ],
        }
        return faq_templates.get(cluster, [
            {
                "question": "What does this guide help me decide?",
                "answer_template": (
                    "This guide explains the practical checks a UK buyer or rider "
                    "can make before choosing or using a hoverboard setup. Always "
                    "follow manufacturer guidance and use equipment in an "
                    "appropriate private space."
                ),
            },
            {
                "question": "How should I approach safety?",
                "answer_template": (
                    "Safety depends on correct use, suitable protective equipment, "
                    "the condition of the board and accessories, and following "
                    "manufacturer guidance. No product or accessory removes all "
                    "risk, so assess the rider and conditions each time."
                ),
            },
            {
                "question": "What should I check before first use?",
                "answer_template": (
                    "Check the equipment is in good condition, fits correctly, and is suitable "
                    "for your hoverboard model. Always follow the manufacturer's fitting instructions. "
                    "If anything is damaged or worn, do not use it until repaired or replaced."
                ),
            },
        ])

    def _build_dynamic_writer_plan(self, job_ctx):
        """
        Build a writer plan from canonical selected-job context.

        INPUT: job_ctx from /tmp/orin_selected_job_context.json

        INVARIANT: writer_plan.job_number == selected_job_context.job_number
        If invariant fails → raises BLOCK_JOB_CONTEXT_MISMATCH

        OUTPUT: writer plan dict with full article planning metadata.
        """
        # ── INVARIANT CHECK ────────────────────────────────────────────────
        # writer_plan.job_number must == selected_job_context.job_number
        # job_number_check is the authoritative source, captured before plan build
        job_number_check = str(job_ctx.get("job_number", ""))
        if not job_number_check:
            raise ValueError(
                f"{BLOCK_JOB_CONTEXT_MISMATCH}: "
                f"selected_job_context.job_number is empty or missing. "
                f"Cannot build writer plan without a valid job number."
            )
        # All plan fields are derived from job_ctx. Plan integrity is by construction.
        # The post-build check below is a safeguard against future code changes
        # that might accidentally corrupt the job number during plan assembly.

        job_number = str(job_ctx["job_number"])
        job_label = job_ctx.get("job_label", f"Job {job_number}")
        topic = job_ctx.get("topic", "")
        target_keyword = job_ctx.get("target_keyword", "")
        target_date = job_ctx.get("target_date", "")
        expected_draft_date = job_ctx.get("expected_draft_date", "")
        queue_status = job_ctx.get("queue_status", "planned")
        file_path = job_ctx.get("file_path", "")
        shopify_handle = job_ctx.get("shopify_handle")

        # ── Cluster from queue notes or topic keywords ──────────────────────
        cluster = "default"
        topic_lower = topic.lower()
        if any(k in topic_lower for k in ["hoverkart", "kart"]):
            cluster = "Hoverkart"
        elif any(k in topic_lower for k in ["accessori", "helmet", "pad", "bag"]):
            cluster = "Accessories"
        elif any(k in topic_lower for k in ["safe", "checklist", "law"]):
            cluster = "Safety"
        elif any(k in topic_lower for k in ["wont turn", "not charging", "beeping", "flashing", "troubleshoot"]):
            cluster = "Troubleshooting"
        elif any(k in topic_lower for k in ["best", "guide", "choose", "vs"]):
            cluster = "Buyer Guide"
        elif any(k in topic_lower for k in ["clean", "store", "maintenance", "battery care"]):
            cluster = "Maintenance"
        elif any(k in topic_lower for k in ["gift", "christmas", "birthday"]):
            cluster = "Seasonal"

        # ── Approved handle (canonical) ─────────────────────────────────────
        # Precedence: A. existing shopify_handle if present, B. derive from topic
        if shopify_handle:
            approved_handle = shopify_handle
        else:
            approved_handle = self._generate_slug(topic)
        # ── CANONICAL HANDLE INVARIANT ───────────────────────────────────────
        # Every approved_handle in every writer plan MUST be canonical.
        # This prevents downstream phases from receiving broken handles.
        from handle_utils import (
            is_canonical_shopify_handle,
            validate_or_raise_canonical_handle,
            BLOCK_INVALID_PLANNED_HANDLE,
        )
        validate_or_raise_canonical_handle(approved_handle, job_label=f"Job {job_number}")

        # ── Search intent ─────────────────────────────────────────────────
        search_intent = (
            f"Informational — reader wants practical guidance on {target_keyword}. "
            "They are evaluating whether and how to proceed, and need honest, actionable advice. "
            "No purchase obligation. No performance guarantees."
        )

        # ── Reader persona ────────────────────────────────────────────────
        is_electric_scooter_topic = self._is_electric_scooter_topic(
            topic, target_keyword
        )
        reader_persona = (
            (
                "UK parent or guardian choosing, maintaining, or supervising a child-sized "
                "electric scooter. They want practical, model-specific checks, honest advice, "
                "and clear stop-use guidance without performance or safety promises."
            )
            if is_electric_scooter_topic
            else (
                "UK parent or guardian buying a hoverboard setup for a child, "
                "or an adult evaluating hoverboard accessories for themselves. "
                "They want practical safety guidance, honest advice, "
                "and clarity on what to check before spending money. "
                "They value safety over performance claims."
            )
        )

        # ── Article angle ────────────────────────────────────────────────
        article_angle = self._generate_article_angle(topic, target_keyword, cluster)

        # ── Compliance notes ──────────────────────────────────────────────
        compliance_notes = (
            f"Hoverboard Store article on {topic}. "
            "UK-focused. No road-use claims. No safety guarantees. "
            "No medical claims. No legal permission claims. "
            + (
                "Do not generalise hoverboard-specific guidance to electric scooters. "
                "Use model-specific electric scooter wording and advise checking current UK rules. "
                "Do not predict how wet, cold, or damp conditions change brake feel or stopping "
                "distance across models; effects vary by brake system. Do not recommend adjustment, "
                "powered testing, or electronic diagnostics unless the exact model manual permits it. "
                if is_electric_scooter_topic
                else "Hoverboards are for private land use only in England. "
            )
            + "All product feature claims must be plausible and widely accepted. "
            "Consult manufacturer guidance for all technical specifications."
        )
        topic_text = f"{topic} {target_keyword}".lower()
        if "footpad" in topic_text or "foot pad" in topic_text:
            compliance_notes += (
                " For footpad or grip guidance, do not advise lifting, removing, cutting, "
                "layering, or repositioning pads, and do not suggest inspecting beneath them "
                "or altering sensor areas. Do not claim pads protect the deck, keep sensors "
                "cleaner, or make learning safer or easier. Require suitable closed footwear. "
                "Tell readers to stop using damaged or loose pads, follow the exact model "
                "manual, and contact the manufacturer, seller, or a qualified service provider "
                "for replacement, fitment, or sensor work."
            )

        # ── Claims to avoid ──────────────────────────────────────────────
        claims_to_avoid = [
            "prevents all injuries",
            "eliminates risk",
            "no risk",
            "100% safe",
            "guarantee",
            "will prevent",
            "clinically proven",
            "award-winning",
            "UK's #1",
            "single most effective",
            "single most important",
            "prevents falls",
            "road legal",
            "pavement legal",
            "legal on UK roads",
            "safe for public use",
            "certified safe",
        ]
        if is_electric_scooter_topic:
            claims_to_avoid.extend(
                [
                    "expect the lever to feel firmer",
                    "stopping distances to be longer",
                    "normal responses to conditions",
                ]
            )

        # ── Recommended word count ───────────────────────────────────────
        if self.is_hcs:
            word_count = 1400 if cluster in ("Hoverkart", "Buyer Guide") else 1200
        else:
            word_count = DEFAULT_CONTRACT["min_visible_words"]
            if cluster in ("Hoverkart", "Buyer Guide"):
                word_count = 1800

        # ── H2 outline ───────────────────────────────────────────────────
        h2_outline = self._generate_h2_outline(topic, target_keyword, cluster)
        blocked_topic_terms = (
            []
            if self.is_hcs
            else sorted(get_blocked_terms_for_cluster(cluster))
        )

        # ── TOC plan ──────────────────────────────────────────────────────
        toc_plan = [
            {"label": item["label"], "href": f"#{item['id']}"}
            for item in h2_outline
            if item["id"] not in ("cta",)
        ]

        # ── FAQ plan ─────────────────────────────────────────────────────
        faq_plan = self._generate_faq_plan(topic, target_keyword, cluster)

        # ── CTA plan — cluster-gated ───────────────────────────────────────
        if is_electric_scooter_topic:
            cta_plan = {
                "heading": "Explore Electric Scooters at Hoverboard Store",
                "body": (
                    "Browse the electric scooter collection and compare the exact product "
                    "listing, manual, and manufacturer guidance for the rider and intended use. "
                    "Contact the Hoverboard Store team when model-specific support is needed."
                ),
                "button_text": "Shop Electric Scooters",
                "button_href": "https://hoverboardstore.co.uk/collections/electric-scooters",
                "cta_class": "hs-button",
                "placement": "End of article, inside hs-cta section",
            }
        elif cluster == "Hoverkart":
            cta_plan = {
                "heading": "Find the Right Hoverboard Setup at Hoverboard Store",
                "body": (
                    "Browse the full range of hoverboards, hoverkarts, and accessories. "
                    "Every product ships with manufacturer guidance. "
                    "Always ride in appropriate private spaces with appropriate safety gear."
                ),
                "button_text": "Shop Hoverboards and Accessories",
                "button_href": "https://hoverboardstore.co.uk/collections/hoverboards",
                "cta_class": "hs-button",
                "placement": "End of article, inside hs-cta section",
            }
        else:
            cta_plan = {
                "heading": "Find the Right Hoverboard Setup at Hoverboard Store",
                "body": (
                    "Browse our range of hoverboards and relevant accessories. "
                    "Every product ships with manufacturer guidance. Always "
                    "follow safety guidance and ride in appropriate private spaces."
                ),
                "button_text": "Shop Hoverboards and Accessories",
                "button_href": "https://hoverboardstore.co.uk/collections/hoverboards",
                "cta_class": "hs-button",
                "placement": "End of article, inside hs-cta section",
            }

        # ── Internal link plan ──────────────────────────────────────────
        internal_link_plan = self._generate_internal_links(topic, target_keyword, cluster)

        # ── HTML structure requirements ──────────────────────────────────
        html_structure = [
            "article.hs-article wrapper",
            "div.hs-container inside article",
            "h1 as main title (inside container)",
            "div.hs-meta with byline: 'By Hoverboard Store.'",
            "div.hs-quick-answer with summary paragraph",
            "div.hs-highlights with 3-4 bullet points",
            "section.hs-content with all H2 sections",
            "All H2s inside .hs-content have id attributes",
            "div.hs-split with hs-do and hs-dont sub-divs (if applicable)",
            "section.hs-faq with div.hs-faq-item children (h3 question + div.hs-faq-a answer)",
            "section.hs-cta with a.hs-button CTA",
            "No inline styles, no <style> tags",
            "No document wrappers (DOCTYPE, html, head, body)",
        ]

        # ── Proposed local file path ─────────────────────────────────────
        proposed_slug = approved_handle or self._generate_slug(topic)
        proposed_local_file_path = str(self.content_dir / "drafts" / f"{proposed_slug}.html")

        return {
            # Identity
            "job_number": job_number,
            "job_label": job_label,
            "topic": topic,
            "title": topic,  # title = topic as canonical heading
            # SEO
            "approved_handle": approved_handle,
            "target_keyword": target_keyword,
            "search_intent": search_intent,
            "site_url": self.site_url,
            # Angle
            "article_angle": article_angle,
            "reader_persona": reader_persona,
            # Compliance
            "compliance_notes": compliance_notes,
            "claims_to_avoid": claims_to_avoid,
            # Content plan
            "recommended_word_count": word_count,
            "content_quality_contract": (
                {
                    "version": CONTRACT_VERSION,
                    **DEFAULT_CONTRACT,
                }
                if not self.is_hcs
                else None
            ),
            "h2_outline": h2_outline,
            "blocked_topic_terms": blocked_topic_terms,
            "toc_plan": toc_plan,
            "faq_plan": faq_plan,
            "cta_plan": cta_plan,
            "internal_link_plan": internal_link_plan,
            "html_structure_requirements": html_structure,
            # Metadata
            "target_date": target_date,
            "expected_draft_date": expected_draft_date,
            "queue_status": queue_status,
            "cluster": cluster,
            # Draft path
            "proposed_local_file_path": proposed_local_file_path,
            "proposed_url_slug": proposed_slug,
            # Handoff
            "handoff_target": "Review Agent",
            "post_write_checks_to_run": [
                "HTML quality check (H1, H2s, paragraphs, lists, byline)",
                "Compliance check (legal, safety, product claims)",
                "Duplicate check (against published and draft inventory)",
                "SEO check (meta title, meta description, target keyword usage)",
                "Internal link check (all links functional and relevant)",
            ],
            # Plan source tracking
            "_plan_source": "_build_dynamic_writer_plan",
            "_job_context_hash": hashlib.md5(
                str(job_ctx.get("job_number", "")).encode()
            ).hexdigest()[:8],
        }

    def plan_writing(self, job_ctx=None):
        """
        Plan writing for a selected job.

        PRODUCTION PATH (job_ctx provided):
            Reads canonical selected-job context from job_ctx dict.
            Builds a dynamic writer plan for that specific job.
            Returns plan with full article planning metadata.

        BACKWARD-COMPATIBLE PATH (job_ctx not provided):
            Scans queue for next planned job.
            Returns next_writing_candidate info (no full plan).
            Used by standalone test runners only.
        """
        # ── PRODUCTION PATH: selected-job writer plan ───────────────────────────
        if job_ctx is not None:
            # Capture the expected job number BEFORE calling the builder
            expected_job_number = str(job_ctx.get("job_number", ""))
            if not expected_job_number:
                raise ValueError(
                    f"{BLOCK_JOB_CONTEXT_MISMATCH}: "
                    f"selected_job_context.job_number is empty or missing. "
                    f"Cannot build writer plan without a valid job number."
                )
            writer_plan = self._build_dynamic_writer_plan(job_ctx)
            # ── POST-BUILD INVARIANT CHECK ──────────────────────────────────────
            # writer_plan.job_number must == selected_job_context.job_number
            plan_job_number = str(writer_plan.get("job_number", ""))
            if plan_job_number != expected_job_number:
                raise ValueError(
                    f"{BLOCK_JOB_CONTEXT_MISMATCH}: "
                    f"writer_plan.job_number={plan_job_number} "
                    f"!= selected_job_context.job_number={expected_job_number}. "
                    f"Wrong job plan was built."
                )
            return {
                "writer_decision": "writer_plan_ready",
                "selected_job": str(job_ctx.get("job_number", "")),
                "selected_job_topic": job_ctx.get("topic", ""),
                "selected_job_keyword": job_ctx.get("target_keyword", ""),
                "selected_job_target_date": job_ctx.get("target_date", ""),
                "selected_job_expected_draft_date": job_ctx.get("expected_draft_date", ""),
                "writer_plan_source": "_build_dynamic_writer_plan",
                "writer_plan": writer_plan,
            }

        # ── BACKWARD-COMPATIBLE PATH: queue scan for next candidate ───────────
        queue_content = self._read_file(self.queue_path)
        jobs = self._parse_queue(queue_content)

        next_writing_candidate = None
        for job in jobs:
            if job["status"] == "planned" and (
                next_writing_candidate is None
                or job["date_target"] < next_writing_candidate["date_target"]
            ):
                next_writing_candidate = job

        return {
            "writer_decision": "no_writer_action",
            "selected_job": None,
            "next_writing_candidate": {
                "job_number": next_writing_candidate["job_number"],
                "topic": next_writing_candidate["topic"],
                "target_date": next_writing_candidate["date_target"].strftime("%Y-%m-%d"),
                "expected_draft_date": (next_writing_candidate["date_target"] - timedelta(days=14)).strftime("%Y-%m-%d"),
            } if next_writing_candidate else None,
            "writer_plan_source": "queue_scan_no_job_context",
            "writer_plan": None,
        }

    def write_selected_job_draft(self, job_ctx, writer_plan, output_path_override=None):
        """
        Generate a real HTML article draft for the selected job.

        INVARIANTS (all must pass before any article is written):
          1. job_ctx is not None
          2. writer_plan is not None
          3. writer_plan["job_number"] == job_ctx["job_number"]
             → BLOCK_JOB_CONTEXT_MISMATCH if violated
          4. writer_plan["approved_handle"] is canonical
             → BLOCK_INVALID_PLANNED_HANDLE if violated
          5. Writer active job number == job_ctx job number
             → BLOCK_JOB_CONTEXT_MISMATCH if violated

        ARTICLE STRUCTURE (Hoverboard Store standard):
          <!-- SEO metadata block -->
          <div class="hs-article">
            <div class="hs-container">
              <h1>Title</h1>
              <div class="hs-meta"><p>Published ... | By Hoverboard Store</p></div>
              <div class="hs-quick-answer"><p><strong>Quick Answer:</strong> ...</p></div>
              <div class="hs-highlights">
                <div class="hs-highlight">...</div>
                ...
              </div>
              [sections]
              <section class="hs-faq">[FAQs]</section>
              <div class="hs-cta">...</div>
            </div>
          </div>

        CLAIMS RULE:
          Do not invent specific product specs (wheel sizes, weight limits, model numbers).
          Use careful general checklist language. Flag unavailable facts as TBC.
          Queue notes say: wheel size compatibility, straps, frame, seat,
          manufacturer guidance. Avoid road-use claims.
        """
        import html as html_module

        # ── INVARIANT 1: job_ctx required ───────────────────────────────────
        if job_ctx is None:
            raise ValueError(
                f"{BLOCK_JOB_CONTEXT_MISMATCH}: "
                f"write_selected_job_draft requires job_ctx. Got None."
            )

        # ── INVARIANT 2: writer_plan required ──────────────────────────────
        if writer_plan is None:
            raise ValueError(
                f"{BLOCK_JOB_CONTEXT_MISMATCH}: "
                f"write_selected_job_draft requires writer_plan. Got None."
            )

        # ── INVARIANT 3: job number match ─────────────────────────────────
        ctx_job = str(job_ctx.get("job_number", ""))
        plan_job = str(writer_plan.get("job_number", ""))
        if ctx_job != plan_job:
            raise ValueError(
                f"{BLOCK_JOB_CONTEXT_MISMATCH}: "
                f"writer active job ({plan_job}) != job_ctx ({ctx_job}). "
                f"Cannot write draft for wrong job."
            )

        # ── INVARIANT 4: canonical handle ─────────────────────────────────
        from handle_utils import (
            is_canonical_shopify_handle,
            validate_or_raise_canonical_handle,
            BLOCK_INVALID_PLANNED_HANDLE,
        )
        approved_handle = writer_plan.get("approved_handle", "")
        validate_or_raise_canonical_handle(
            approved_handle, job_label=f"Job {ctx_job}"
        )

        # ── Extract identity fields ──────────────────────────────────────
        job_number = ctx_job
        title = writer_plan.get("title", job_ctx.get("topic", ""))
        target_keyword = writer_plan.get("target_keyword", "")
        article_angle = writer_plan.get("article_angle", "")
        cluster = writer_plan.get("cluster", "")
        h2_outline = writer_plan.get("h2_outline", [])
        faq_plan = writer_plan.get("faq_plan", [])
        cta_plan = writer_plan.get("cta_plan", {})
        internal_links = writer_plan.get("internal_link_plan", [])
        compliance_notes = writer_plan.get("compliance_notes", "")
        word_count_target = writer_plan.get("recommended_word_count", 1400)
        toc_plan = writer_plan.get("toc_plan", [])
        claims_to_avoid = writer_plan.get("claims_to_avoid", [])

        # ── Determine output path ─────────────────────────────────────────
        if output_path_override:
            output_path = Path(output_path_override)
        else:
            proposed = writer_plan.get("proposed_local_file_path", "")
            if proposed:
                output_path = Path(proposed)
            else:
                slug = approved_handle or self._generate_slug(title)
                output_path = self.content_dir / "drafts" / f"{slug}.html"

        # ── Build SEO metadata block ──────────────────────────────────────
        slug = approved_handle
        published_month = datetime.now().strftime("%B %Y")
        meta_title = self._build_meta_title(title, target_keyword)
        meta_description = self._build_meta_description(title, target_keyword)

        seo_block = f"""<!--
SEO Title: {meta_title}
Meta Title: {meta_title}
Meta Description: {meta_description}
URL Slug: {slug}
Target Keyword: {target_keyword}
Cluster: {cluster}
Job: {job_number}
-->"""

        # ── Build article sections ────────────────────────────────────────
        article_sections = []

        # H1 — title
        article_sections.append(f"<h1>{self._escape_html(title)}</h1>")

        # hs-meta byline
        article_sections.append(
            f'<div class="hs-meta">'
            f'<p>Published: {published_month} | Updated: {published_month} | By {self.byline}</p>'
            f'</div>'
        )

        # hs-quick-answer — derived from article angle + target keyword
        quick_answer_text = self._build_quick_answer(title, target_keyword, article_angle, cluster)
        article_sections.append(
            f'<div class="hs-quick-answer">'
            f'<p><strong>Quick Answer:</strong> {self._escape_html(quick_answer_text)}</p>'
            f'</div>'
        )

        # hs-highlights — 4 key takeaways derived from H2 outline
        highlights = self._build_highlights(h2_outline, title, target_keyword, cluster)
        hl_items = "\n".join(
            f'<div class="hs-highlight">{self._escape_html(h)}</div>'
            for h in highlights
        )
        article_sections.append(f'<div class="hs-highlights">\n{hl_items}\n</div>')

        # H2 sections — substantive content
        for section in h2_outline:
            section_id = section.get("id", "")
            section_h2 = section.get("h2", "")
            section_content = self._build_section_content(
                section_id, section_h2, title, target_keyword,
                cluster, article_angle, claims_to_avoid
            )
            article_sections.append(f"<h2>{self._escape_html(section_h2)}</h2>")
            article_sections.append(f"<p>{self._escape_html(section_content)}</p>")

        # FAQs
        if faq_plan:
            faq_sections = self._build_faqs(faq_plan, target_keyword, cluster, claims_to_avoid)
            article_sections.append('<section class="hs-faq">')
            article_sections.append("<h2>Frequently Asked Questions</h2>")
            for q, a in faq_sections:
                article_sections.append(
                    f'<div class="hs-faq-item">'
                    f'<div class="hs-faq-q">{self._escape_html(q)}</div>'
                    f'<div class="hs-faq-a">{self._escape_html(a)}</div>'
                    f'</div>'
                )
            article_sections.append('</section>')

        # CTA
        cta_section = self._build_cta(cta_plan, target_keyword)
        article_sections.append(f'<div class="hs-cta">\n{cta_section}\n</div>')

        # Related links (internal links)
        if internal_links:
            rel_section = self._build_related_links(internal_links)
            article_sections.append(f'<div class="hs-related">\n{rel_section}\n</div>')

        # ── Assemble full HTML ────────────────────────────────────────────
        sections_html = "\n\n".join(article_sections)

        full_html = f"""{seo_block}
<div class="hs-article">
  <div class="hs-container">

{sections_html}

  </div>
</div>"""

        # Phase 3.5 model path. This is opt-in and fail-closed: when enabled,
        # any provider, extraction, or validation error propagates and stops
        # the pipeline. The deterministic template is never used as a silent
        # fallback for a failed model request.
        writer_source = "deterministic_template"
        writer_model = None
        writer_provider = None
        model_response_id = None
        model_attempts = []
        if model_writer_enabled():
            retry_budget_used = False
            try:
                model_result = generate_article(
                    job_context=job_ctx,
                    writer_plan=writer_plan,
                    attempt=1,
                )
            except ModelWriterError as error:
                retry_feedback = _model_output_retry_feedback(error)
                retry_budget_used = True
                model_attempts.append(
                    {
                        "attempt": 1,
                        "response_id": None,
                        "quality_passed": False,
                        "blocker_codes": ["MW_OUTPUT_CONTRACT"],
                    }
                )
                model_result = generate_article(
                    job_context=job_ctx,
                    writer_plan=writer_plan,
                    quality_retry=retry_feedback,
                    attempt=2,
                )
            if self.is_hcs:
                full_html = _normalise_hcs_model_output(
                    model_result.body_html,
                    meta_title=meta_title,
                    meta_description=meta_description,
                    approved_handle=approved_handle,
                    target_keyword=target_keyword,
                    cluster=cluster,
                    job_number=job_number,
                    title=title,
                    site_url=self.site_url,
                    blog_handle=self.blog_handle,
                    byline=self.byline,
                )
            else:
                full_html = _normalise_model_metadata(
                    model_result.body_html,
                    meta_title=meta_title,
                    meta_description=meta_description,
                    approved_handle=approved_handle,
                    target_keyword=target_keyword,
                    cluster=cluster,
                    job_number=job_number,
                )
            writer_source = "model"
            writer_model = model_result.model
            writer_provider = model_result.provider
            model_response_id = model_result.response_id
            if self.is_hcs:
                initial_quality, initial_topic = _hcs_model_validation_receipts(
                    full_html,
                    job_number=job_number,
                    title=title,
                    target_keyword=target_keyword,
                    cluster=cluster,
                    h2_outline=h2_outline,
                )
            else:
                initial_quality, initial_topic = _model_validation_receipts(
                    full_html,
                    job_number=job_number,
                    title=title,
                    target_keyword=target_keyword,
                    cluster=cluster,
                    h2_outline=h2_outline,
                    site_url=writer_plan.get("site_url", self.site_url),
                )
            model_attempts.append(
                _model_attempt_receipt(
                    2 if retry_budget_used else 1,
                    model_result,
                    initial_quality,
                    initial_topic,
                )
            )
            validation_failed = (
                not initial_quality["passed"]
                or initial_topic["decision"] == TOPIC_IDENTITY_BLOCK
            )
            if self.is_hcs and validation_failed and retry_budget_used:
                raise ModelWriterError(
                    "HCS model article failed final contract validation"
                )
            if validation_failed and not retry_budget_used:
                retry_result = generate_article(
                    job_context=job_ctx,
                    writer_plan=writer_plan,
                    quality_retry=_model_validation_retry_feedback(
                        initial_quality,
                        initial_topic,
                        writer_plan,
                    ),
                    attempt=2,
                )
                if self.is_hcs:
                    full_html = _normalise_hcs_model_output(
                        retry_result.body_html,
                        meta_title=meta_title,
                        meta_description=meta_description,
                        approved_handle=approved_handle,
                        target_keyword=target_keyword,
                        cluster=cluster,
                        job_number=job_number,
                        title=title,
                        site_url=self.site_url,
                        blog_handle=self.blog_handle,
                        byline=self.byline,
                    )
                else:
                    full_html = _normalise_model_metadata(
                        retry_result.body_html,
                        meta_title=meta_title,
                        meta_description=meta_description,
                        approved_handle=approved_handle,
                        target_keyword=target_keyword,
                        cluster=cluster,
                        job_number=job_number,
                    )
                writer_model = retry_result.model
                writer_provider = retry_result.provider
                model_response_id = retry_result.response_id
                if self.is_hcs:
                    retry_quality, retry_topic = _hcs_model_validation_receipts(
                        full_html,
                        job_number=job_number,
                        title=title,
                        target_keyword=target_keyword,
                        cluster=cluster,
                        h2_outline=h2_outline,
                    )
                else:
                    retry_quality, retry_topic = _model_validation_receipts(
                        full_html,
                        job_number=job_number,
                        title=title,
                        target_keyword=target_keyword,
                        cluster=cluster,
                        h2_outline=h2_outline,
                        site_url=writer_plan.get("site_url", self.site_url),
                    )
                model_attempts.append(
                    _model_attempt_receipt(
                        2,
                        retry_result,
                        retry_quality,
                        retry_topic,
                    )
                )
                if self.is_hcs and (
                    not retry_quality["passed"]
                    or retry_topic["decision"] == TOPIC_IDENTITY_BLOCK
                ):
                    raise ModelWriterError(
                        "HCS model article failed final contract validation"
                    )

        # ── Write to output path ──────────────────────────────────────────
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(full_html, encoding="utf-8")

        # ── Compute stats ─────────────────────────────────────────────────
        actual_words = len(full_html.split())
        sha256 = hashlib.sha256(full_html.encode("utf-8")).hexdigest()
        h1_count = full_html.count("<h1>")
        h2_count = full_html.count("<h2>")

        return {
            "job_number": job_number,
            "title": title,
            "approved_handle": approved_handle,
            "output_path": str(output_path),
            "file_size_bytes": len(full_html),
            "word_count_approx": actual_words,
            "word_count_target": word_count_target,
            "sha256": sha256,
            "h1_count": h1_count,
            "h2_count": h2_count,
            "faq_count": len(faq_plan),
            "internal_link_count": len(internal_links),
            "writer_source": writer_source,
            "writer_provider": writer_provider,
            "writer_model": writer_model,
            "model_response_id": model_response_id,
            "model_attempts": model_attempts,
        }

    def _escape_html(self, text):
        """Escape HTML special characters."""
        import html
        return html.escape(text, quote=False)

    def _build_meta_description(self, title, keyword):
        """Build a complete meta description from title and keyword.

        Never trim prose at an arbitrary character boundary.  A shorter,
        complete template is preferable to a grammatically broken snippet in
        Shopify and search results.
        """
        subject = keyword.strip() or title.strip()
        candidates = (
            (
                f"Understand {subject} with this practical UK guide. Check "
                "product details, manufacturer guidance and safety information "
                "before making a decision."
            ),
            (
                f"UK guide to {subject}. Check specifications, manufacturer "
                "guidance and safety information before making an informed "
                "decision."
            ),
            (
                f"UK guide to {subject}. Check specs, safety information and "
                "manufacturer guidance before deciding."
            ),
        )
        minimum = DEFAULT_CONTRACT["min_meta_description_chars"]
        maximum = DEFAULT_CONTRACT["max_meta_description_chars"]
        for description in candidates:
            if minimum <= len(description) <= maximum:
                return description
        raise ValueError(
            "unable to build a complete meta description within the approved "
            f"{minimum}-{maximum} character range"
        )

    def _build_meta_title(self, title, keyword):
        """Build a complete SEO title within the approved 30-60 character range."""
        candidate = title.strip()
        if len(candidate) > DEFAULT_CONTRACT["max_seo_title_chars"]:
            candidate = (keyword or title).strip().title()
        if len(candidate) < DEFAULT_CONTRACT["min_seo_title_chars"]:
            candidate = f"{candidate}: Practical UK Guide"
        if len(candidate) > DEFAULT_CONTRACT["max_seo_title_chars"]:
            candidate = candidate[
                : DEFAULT_CONTRACT["max_seo_title_chars"]
            ].rsplit(" ", 1)[0].rstrip(" ,;:-")
        return candidate

    def _build_quick_answer(self, title, keyword, angle, cluster):
        """
        Build the quick answer paragraph.
        Cluster-gated: Hoverkart-specific content only for Hoverkart cluster.
        """
        is_hoverkart = (cluster == "Hoverkart")
        # Derive from article angle — use the core message
        if angle:
            angle_snippet = angle.split(".")[0][:200]
            return angle_snippet
        # Default fallback — cluster-gated
        if is_hoverkart:
            return (
                f"This guide covers what to check before buying a hoverkart. "
                f"It walks through wheel size, weight limits, frame compatibility, "
                f"strap fit, and how to check manufacturer guidance — "
                f"so you can buy with confidence."
            )
        # Generic fallback for non-Hoverkart clusters
        return (
            f"This guide covers the key points for {keyword}. "
            f"It walks through the most common causes, what to check, "
            f"and when to seek professional support. "
            f"Follow manufacturer guidance throughout."
        )

    def _build_highlights(self, h2_outline, title, keyword, cluster):
        """
        Build 4 highlight bullets from H2 outline.
        Cluster-gated: Hoverkart-specific highlights only for Hoverkart cluster.
        """
        highlights = []
        h2_ids = [s["id"] for s in h2_outline if s.get("id")]
        is_hoverkart = (cluster == "Hoverkart")

        if is_hoverkart:
            # Hoverkart-specific highlights
            if "wheel-size-match" in h2_ids:
                highlights.append(
                    "Check your hoverboard's wheel size before buying a hoverkart — "
                    "most hoverkarts are designed for 6.5 inch, 8 inch, or 8.5 inch boards."
                )
            if "weight-limits" in h2_ids:
                highlights.append(
                    "Hoverkarts have their own weight limits — "
                    "check both the hoverkart spec and your hoverboard's rider weight limit."
                )
            if "frame-and-straps" in h2_ids:
                highlights.append(
                    "Frame and strap compatibility varies by hoverkart model — "
                    "verify the connection points match your board before purchasing."
                )
            if "safety-considerations" in h2_ids:
                highlights.append(
                    "Hoverkarts are for private use on flat, smooth surfaces — "
                    "always supervise children and follow manufacturer guidance."
                )
            if len(highlights) < 4:
                highlights.append(
                    f"This checklist helps you verify hoverkart compatibility "
                    f"before you buy — covering the key checks for {keyword}."
                )
            if len(highlights) < 4:
                highlights.append(
                    "Read all product specifications carefully before purchase "
                    "and confirm compatibility with your specific hoverboard model."
                )
        else:
            # Generic highlights for non-Hoverkart clusters
            # Derive from H2 outline ids
            if "why-lights-flash" in h2_ids or "why-beeping" in h2_ids:
                highlights.append(
                    f"Most {keyword} issues have simple causes — check the obvious first."
                )
            if "common-causes" in h2_ids or "causes" in h2_ids:
                highlights.append(
                    f"Check the most common causes before trying more complex fixes."
                )
            if "safety" in h2_ids or "precautions" in h2_ids:
                highlights.append(
                    "Always follow manufacturer guidance and wear appropriate safety equipment."
                )
            if "when-to-replace" in h2_ids or "replace" in h2_ids:
                highlights.append(
                    "If damage is suspected, stop use and contact the manufacturer."
                )
            if len(highlights) < 4:
                highlights.append(
                    f"This guide covers the key points for {keyword}. "
                    f"Follow manufacturer guidance throughout."
                )
            if len(highlights) < 4:
                highlights.append(
                    "Read all product specifications carefully before any adjustment. "
                    "When in doubt, contact the manufacturer."
                )

        return highlights[:4]

    def _build_section_content(
        self, section_id, section_h2, title, keyword, cluster,
        article_angle, claims_to_avoid
    ):
        """
        Generate substantive paragraph content for an H2 section.
        Content is cluster-gated: Hoverkart-specific sections ONLY execute
        when cluster == "Hoverkart". All other clusters receive generic content
        derived from the current article's title, keyword, section_h2, and angle.

        This function must NEVER return hardcoded content for a different topic
        cluster. Unknown/non-specialised topics must use generic construction,
        not fall back to Hoverkart content.
        """
        # Track which claims to avoid in this section
        avoid = set(claims_to_avoid)
        s = section_id.lower()
        is_hoverkart = (cluster == "Hoverkart")

        # ── Cluster-gated introduction ──────────────────────────────────
        if s == "introduction":
            if is_hoverkart:
                return (
                    f"Buying a hoverkart for your hoverboard can open up a new way to ride — "
                    f"but not every hoverkart works with every hoverboard. "
                    f"This compatibility checklist walks you through the checks that matter most "
                    f"before you buy, so you can avoid a purchase that does not fit properly. "
                    f"It covers wheel size, weight limits, frame connection points, strap compatibility, "
                    f"and what to ask the manufacturer. "
                    f"No hoverkart guarantees safe operation — follow all guidance and supervise children at all times."
                )
            # Generic introduction derived from current article context
            return (
                f"{keyword.title()} can be confusing if you run into a problem — "
                f"but most issues have straightforward causes and simple fixes. "
                f"This guide walks through the most common reasons for {keyword}, "
                f"what to check, and when to seek professional support. "
                f"No diagnosis guarantees a specific outcome — follow manufacturer guidance throughout."
            )

        # ── Cluster-gated quick-answer ───────────────────────────────────
        if s == "quick-answer":
            if is_hoverkart:
                return (
                    f"The key checks before buying a hoverkart are: "
                    f"(1) confirm your hoverboard wheel size, "
                    f"(2) check the hoverkart weight limit against your board's limit and rider weight, "
                    f"(3) verify frame and strap compatibility with your specific board model, "
                    f"and (4) read the manufacturer guidance before first use."
                )
            # Generic quick-answer derived from current article context
            return (
                f"The key facts about {keyword}: "
                f"check the most common causes first, "
                f"follow manufacturer guidance for your specific model, "
                f"and do not force a fix if the cause is unclear."
            )


        if s == "why-compatibility-matters":
            return (
                "A hoverkart that does not fit your hoverboard properly can be unsafe. "
                "Connection points that do not align, weight limits that exceed your board's capacity, "
                "or straps that do not secure properly can cause the hoverkart to detach or the board to behave unpredictably. "
                "Taking a few minutes to verify compatibility before you buy "
                "is the simplest way to avoid a disappointing or unsafe setup."
            )

        if s == "what-to-check-before-buying":
            return (
                "Before purchasing a hoverkart, check four things: "
                "(1) your hoverboard wheel size, "
                "(2) your hoverboard's maximum rider weight and the hoverkart's own weight limit, "
                "(3) the hoverkart frame type and whether its connection system matches your board, "
                "(4) whether the straps and footrests are compatible with your board's footpad size. "
                "If any of these are unclear, contact the hoverkart manufacturer before buying."
            )

        if s == "wheel-size-match":
            return (
                "Wheel size is one of the most important compatibility factors. "
                "Most hoverkarts are designed for one or more of the three most common hoverboard wheel sizes: "
                "6.5 inch, 8 inch, and 8.5 inch. "
                "Using a hoverkart with the wrong wheel size can damage the board, "
                "cause the hoverkart to sit unevenly, or create a tripping hazard. "
                "Check your board's wheel size — usually labelled on the board or in the original packaging — "
                "and confirm it matches the hoverkart's compatible wheel size before purchasing. "
                "If you are unsure, measure the wheel diameter directly."
            )

        if s == "weight-limits":
            return (
                "Every hoverboard has a maximum rider weight limit — "
                "and every hoverkart has its own additional weight limit. "
                "Both limits must be respected for safe use. "
                "Check your hoverboard's label or user manual for its rider weight capacity, "
                "and check the hoverkart specification for its own limit (which may be lower). "
                "Riding with a combined weight that exceeds either limit can cause motor strain, "
                "loss of balance control, or unexpected board shutdown. "
                "If you cannot confirm the weight limits, contact the manufacturer before buying."
            )

        if s == "frame-and-straps":
            return (
                "Hoverkart frames connect to hoverboards in different ways. "
                "Some use a central clamp, others use adjustable arms, and some are model-specific. "
                "Before buying, verify that the hoverkart's connection system is designed to fit your board. "
                "Straps and footrests should be adjustable or correctly sized for your board's footpad dimensions. "
                "Incompatible frames can shift during use, creating a safety risk. "
                "If the product listing does not confirm compatibility with your board model, ask the seller directly."
            )

        if s == "safety-considerations":
            return (
                "Hoverkarts are designed for private use on flat, smooth, dry surfaces — "
                "flat indoor carpet or a smooth private pavement are typical environments. "
                "Do not use a hoverkart on public roads, pavements, uneven terrain, or wet surfaces. "
                "Children should always be supervised by an adult when using a hoverkart. "
                "No hoverkart makes a hoverboard safe for road use or removes the need for proper supervision. "
                "Always read and follow the manufacturer safety instructions before first use. "
                "Riders should wear appropriate protective equipment including a properly fitted helmet."
            )

        if s == "checklist":
            if is_hoverkart:
                return (
                    "Use this checklist before buying and before first use: "
                    "[ ] Confirm your hoverboard wheel size matches the hoverkart specification, "
                    "[ ] Check combined rider weight is within both the board's and hoverkart's limits, "
                    "[ ] Verify the frame connection type is compatible with your board, "
                    "[ ] Confirm strap and footrest adjustability for your board's footpad size, "
                    "[ ] Read all manufacturer safety guidance before first use, "
                    "[ ] Check the area is flat, smooth, and private before riding, "
                    "[ ] Ensure children are supervised at all times, "
                    "[ ] Confirm protective equipment — especially a properly fitted helmet — is available."
                )
            # Generic non-Hoverkart fallback
            return (
                f"Use this checklist when checking {keyword}: "
                "[ ] Check the most common causes first before more complex troubleshooting, "
                "[ ] Follow manufacturer guidance for your specific hoverboard model, "
                "[ ] Check all connections and settings before assuming a fault, "
                "[ ] Wear appropriate safety equipment during any inspection, "
                "[ ] Do not force any component if the cause is unclear, "
                "[ ] Contact the manufacturer or a qualified technician when in doubt."
            )

        if s == "faq":
            if is_hoverkart:
                return (
                    "See the Frequently Asked Questions section below for answers to common "
                    "compatibility questions, or contact the hoverkart manufacturer directly "
                    "with your board's specific model and wheel size."
                )
            # Generic non-Hoverkart fallback
            return (
                "See the Frequently Asked Questions section below for common "
                f"questions about {keyword}. Contact the manufacturer for your "
                "specific model if you need further support."
            )

        if s == "cta":
            if is_hoverkart:
                return (
                    "If you have confirmed your board is compatible, "
                    "browse our range of hoverboards and accessories to find the right setup for your needs. "
                    "All hoverboards sold by Hoverboard Store include manufacturer guidance — "
                    "keep it accessible for reference."
                )
            # Generic non-Hoverkart fallback
            return (
                "If you have checked the guidance above and need further support, "
                f"browse our range of hoverboards and accessories for {keyword}. "
                "Follow manufacturer guidance throughout."
            )

        # Default section — use article angle or generic
        if article_angle:
            return (
                f"{article_angle[:300]} "
                f"See below for the key points and FAQ section for more detail."
            )
        return (
            f"This section covers key points for {keyword}. "
            f"Check product compatibility before purchasing. "
            f"Follow all manufacturer guidance for safe use."
        )

    def _build_faqs(self, faq_plan, keyword, cluster, claims_to_avoid):
        """
        Build (question, answer) pairs from FAQ plan.
        Answers are cluster-gated: Hoverkart FAQ rules only execute
        when cluster == "Hoverkart". All other clusters receive answers
        derived from the current article's question, answer_direction, and keyword.
        """
        results = []
        for faq in faq_plan[:6]:
            q = faq.get("question", "")
            answer_dir = (
                faq.get("answer_direction")
                or faq.get("answer_template")
                or ""
            )
            # Generate answer from answer_direction + keyword + cluster
            a = self._build_faq_answer(q, keyword, answer_dir, claims_to_avoid, cluster)
            results.append((q, a))
        return results

    def _build_faq_answer(self, question, keyword, answer_direction, claims_to_avoid, cluster):
        """
        Build a FAQ answer from question, direction, keyword, and cluster.
        Cluster-gated: Hoverkart-specific answer rules ONLY execute for
        cluster == "Hoverkart". Non-Hoverkart clusters generate generic answers
        from the current article context without referencing Hoverkart.
        """
        q_lower = question.lower()
        is_hoverkart = (cluster == "Hoverkart")

        # ── Hoverkart-gated answers ──────────────────────────────────────
        if is_hoverkart:
            if "compatible" in q_lower and "how" in q_lower:
                return (
                    f"Hoverkart compatibility depends primarily on your hoverboard's wheel size "
                    f"(typically 6.5 inch, 8 inch, or 8.5 inch) and the hoverkart's own specification. "
                    f"Check the hoverkart product listing for compatible wheel sizes and confirm "
                    f"your board's wheel size before purchasing. "
                    f"Contact the manufacturer if the compatibility information is unclear."
                )

            if "wheel size" in q_lower:
                return (
                    "Most hoverkarts list compatible wheel sizes in their product specification. "
                    "Common sizes are 6.5 inch, 8 inch, and 8.5 inch wheels. "
                    "Measure your board's wheels directly if the size is not labelled, "
                    "or check the original hoverboard product listing or user manual."
                )

            if "weight limit" in q_lower:
                return (
                    "Check both the hoverboard's maximum rider weight limit "
                    "and the hoverkart's own weight specification. "
                    "Both must accommodate the combined load safely. "
                    "If either limit is unclear, contact the manufacturer before use. "
                    "Do not exceed either limit."
                )

            if "any hoverboard" in q_lower or "any board" in q_lower:
                return (
                    f"Not every hoverkart works with every hoverboard. "
                    f"Compatibility depends on wheel size, frame connection type, "
                    f"weight limits, and footpad dimensions. "
                    f"Check the hoverkart's compatibility list before buying, "
                    f"and contact the seller if your specific board model is not mentioned."
                )

            if "safe" in q_lower or "safety" in q_lower:
                return (
                    "Hoverkarts can be used safely when all compatibility checks are completed, "
                    "the area is flat and private, and children are supervised at all times. "
                    "No hoverkart eliminates all risk. Always follow manufacturer guidance, "
                    "wear protective equipment, and do not use on public roads or uneven terrain."
                )

            # Hoverkart default answer
            return (
                f"{answer_direction[:300]} "
                f"Check the hoverkart product specification for your board's wheel size, "
                f"weight limits, and connection type before purchasing. "
                f"Contact the manufacturer if you need confirmation of compatibility."
            )

        # ── Non-Hoverkart generic answers ─────────────────────────────────
        # All answers derive from the current article's question, direction, and keyword.
        # No product-specific defaults. No Hoverkart references.
        if "compatible" in q_lower and "how" in q_lower:
            return (
                f"{keyword.title()} compatibility depends on your specific model and setup. "
                f"Check the manufacturer guidance for your board to confirm "
                f"what applies to your situation. "
                f"Contact the manufacturer if the information is unclear."
            )

        if "wheel size" in q_lower:
            return (
                f"Wheel size is listed in your hoverboard's product specification "
                f"and on the board label itself. Common sizes are 6.5 inch, 8 inch, and 8.5 inch. "
                f"Check your board's label or original packaging, "
                f"or consult the manufacturer website for your specific model."
            )

        if "weight limit" in q_lower:
            return (
                "Check your hoverboard's maximum rider weight limit — "
                "listed on the product label, in the user manual, or on the manufacturer website. "
                "Do not exceed this limit. "
                "If the limit is unclear, contact the manufacturer before use."
            )

        if "safe" in q_lower or "safety" in q_lower:
            return (
                f"Most {keyword} issues can be handled safely when you follow manufacturer guidance, "
                f"check your board's specifications, and take sensible precautions. "
                f"Always follow manufacturer instructions for your specific model. "
                f"When in doubt, contact the manufacturer or a qualified technician."
            )

        # Generic fallback: use answer_direction + keyword context
        base = answer_direction[:300].strip() if answer_direction else (
            f"This question relates to {keyword}. "
            f"Consult your hoverboard's user manual or contact the manufacturer for guidance."
        )
        return (
            f"{base} "
            f"Always follow manufacturer guidance for your specific model. "
            f"When in doubt, contact the manufacturer or a qualified technician."
        )


    def _build_cta(self, cta_plan, keyword):
        """Build the CTA section HTML."""
        heading = cta_plan.get("heading", "Ready to find the right setup?")
        body = cta_plan.get(
            "body",
            f"Browse our full range of hoverboards and accessories to "
            f"find the right fit for your needs."
        )
        button_text = cta_plan.get("button_text", "Shop Now")
        button_url = cta_plan.get(
            "button_href",
            cta_plan.get("url", "/collections/hoverboards"),
        )

        return (
            f'<p>{self._escape_html(body)}</p>\n'
            f'<a href="{button_url}" class="hs-btn">{self._escape_html(button_text)}</a>'
        )

    def _build_related_links(self, internal_links):
        """Build the related links section HTML."""
        lines = ['<h2>Related Guides</h2>', '<ul>']
        for link in internal_links[:8]:
            anchor = link.get("anchor_text", "")
            url = link.get("url", "#")
            lines.append(f'<li><a href="{url}">{self._escape_html(anchor)}</a></li>')
        lines.append('</ul>')
        return '\n'.join(lines)


if __name__ == "__main__":
    # Direct test: python3 writer_agent.py
    import sys
    from workspace_paths import workspace_root

    BASE_DIR = workspace_root()
    CURRENT_DATE_STR = sys.argv[2] if len(sys.argv) > 2 else datetime.now().strftime("%Y-%m-%d")
    writer = WriterAgent(str(BASE_DIR), CURRENT_DATE_STR)

    # Try to read selected job context
    CONTEXT_PATH = Path("/tmp/orin_selected_job_context.json")
    job_ctx = None
    if CONTEXT_PATH.exists():
        import json
        job_ctx = json.loads(CONTEXT_PATH.read_text())

    result = writer.plan_writing(job_ctx=job_ctx)
    print(json.dumps(result, indent=2, default=str))
