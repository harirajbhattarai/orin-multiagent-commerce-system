import sys
import tempfile
import unittest
from pathlib import Path


ORIN_TOOLS = (
    Path(__file__).resolve().parents[1]
    / "tools"
    / "shopify_publisher"
    / "orin"
)
sys.path.insert(0, str(ORIN_TOOLS))

from content_quality_gate import evaluate_article_quality  # noqa: E402
from writer_agent import WriterAgent  # noqa: E402


TARGET_KEYWORD = "hoverboard charger not working"
SITE_URL = "https://hoverboardstore.co.uk"


def _paragraph(section: int, paragraph: int, words: int = 130) -> str:
    tokens = [
        f"section{section}detail{paragraph}point{index}"
        for index in range(words)
    ]
    return " ".join(tokens)


def _valid_article() -> str:
    meta_description = (
        "Read this practical UK guide to hoverboard charger not working. "
        "Check common causes, safety warnings and next steps before replacing "
        "parts or seeking support."
    )
    sections = []
    for section in range(1, 7):
        opening = ""
        if section == 1:
            opening = (
                "Hoverboard charger not working is the problem this guide "
                "helps readers investigate safely. "
            )
        sections.append(
            f"<h2>Detailed Check {section}</h2>"
            f"<p>{opening}{_paragraph(section, 1)}</p>"
            f"<p>{_paragraph(section, 2)}</p>"
        )
    links = "".join(
        (
            f'<li><a href="{SITE_URL}/guides/internal-guide-{index}">'
            f"Internal guide {index}</a></li>"
        )
        for index in range(1, 6)
    )
    faqs = "".join(
        (
            '<div class="hs-faq-item">'
            f'<div class="hs-faq-q">Question {index}?</div>'
            f'<div class="hs-faq-a">{_paragraph(20 + index, 1, 45)}</div>'
            "</div>"
        )
        for index in range(1, 4)
    )
    return f"""<!--
SEO Title: Hoverboard Charger Not Working: Safe Checks
Meta Title: Hoverboard Charger Not Working: Safe Checks
Meta Description: {meta_description}
URL Slug: hoverboard-charger-not-working
Target Keyword: {TARGET_KEYWORD}
-->
<div class="hs-article">
  <div class="hs-container">
    <h1>Hoverboard Charger Not Working: Safe Checks</h1>
    <div class="hs-quick-answer"><p><strong>Quick Answer:</strong>
      Start with the socket, charger indicator and manufacturer guidance.
    </p></div>
    {''.join(sections)}
    <section class="hs-faq">
      <h2>Frequently Asked Questions</h2>
      {faqs}
    </section>
    <div class="hs-related"><h2>Related Guides</h2><ul>{links}</ul></div>
    <div class="hs-cta"><p>Choose the safest next step.</p></div>
  </div>
</div>"""


class ContentQualityGateTests(unittest.TestCase):
    def test_complete_article_passes(self):
        receipt = evaluate_article_quality(
            _valid_article(),
            target_keyword=TARGET_KEYWORD,
            site_url=SITE_URL,
        )

        self.assertTrue(receipt["passed"], receipt["blockers"])
        self.assertGreaterEqual(receipt["metrics"]["visible_word_count"], 1500)
        self.assertEqual(receipt["metrics"]["internal_link_count"], 5)
        self.assertEqual(receipt["metrics"]["faq_item_count"], 3)

    def test_thin_template_is_blocked_with_machine_readable_codes(self):
        html = f"""<!--
Meta Title: Hoverboard Charger Not Working: Safe Checks
Meta Description: Read this practical UK guide to hoverboard charger not working. Check common causes, safety warnings and next steps before replacing parts or seeking support.
-->
<div class="hs-article"><div class="hs-container">
<h1>Hoverboard Charger Not Working: Safe Checks</h1>
<div class="hs-quick-answer"><p>{TARGET_KEYWORD} quick answer.</p></div>
<h2>Checks</h2><p>{TARGET_KEYWORD} basic checks.</p>
<div class="hs-cta"><p>Next step.</p></div>
</div></div>"""

        receipt = evaluate_article_quality(
            html,
            target_keyword=TARGET_KEYWORD,
            site_url=SITE_URL,
        )
        codes = {blocker["code"] for blocker in receipt["blockers"]}

        self.assertFalse(receipt["passed"])
        self.assertIn("CQ_VISIBLE_WORD_COUNT_LOW", codes)
        self.assertIn("CQ_H2_COUNT_LOW", codes)
        self.assertIn("CQ_INTERNAL_LINK_COUNT_LOW", codes)
        self.assertIn("CQ_SUBSTANTIVE_SECTION_COUNT_LOW", codes)

    def test_markup_and_comments_do_not_inflate_visible_word_count(self):
        html = (
            "<!-- " + ("commentword " * 2000) + " -->"
            '<div class="' + ("markup-token-" * 300) + '">'
            "<h1>Hoverboard Charger Not Working</h1>"
            "<p>Only visible words count.</p></div>"
        )

        receipt = evaluate_article_quality(
            html,
            target_keyword=TARGET_KEYWORD,
            site_url=SITE_URL,
        )

        self.assertLess(receipt["metrics"]["visible_word_count"], 20)
        self.assertFalse(receipt["passed"])

    def test_repeated_substantive_paragraph_is_blocked(self):
        html = _valid_article()
        repeated = _paragraph(99, 1, 50)
        html = html.replace(
            "<h2>Detailed Check 2</h2>",
            f"<p>{repeated}</p><p>{repeated}</p><h2>Detailed Check 2</h2>",
        )

        receipt = evaluate_article_quality(
            html,
            target_keyword=TARGET_KEYWORD,
            site_url=SITE_URL,
        )
        codes = {blocker["code"] for blocker in receipt["blockers"]}

        self.assertFalse(receipt["passed"])
        self.assertIn("CQ_REPEATED_PARAGRAPHS", codes)

    def test_external_links_do_not_count_as_internal(self):
        html = _valid_article().replace(
            SITE_URL,
            "https://example.com",
        )

        receipt = evaluate_article_quality(
            html,
            target_keyword=TARGET_KEYWORD,
            site_url=SITE_URL,
        )
        codes = {blocker["code"] for blocker in receipt["blockers"]}

        self.assertEqual(receipt["metrics"]["internal_link_count"], 0)
        self.assertIn("CQ_INTERNAL_LINK_COUNT_LOW", codes)

    def test_current_template_is_safely_blocked_until_long_form_writer_exists(self):
        repository_root = Path(__file__).resolve().parents[1]
        writer = WriterAgent(str(repository_root), "2026-07-26")
        job_context = {
            "job_number": "99",
            "job_label": "Job 99",
            "topic": "Hoverboard Charger Not Working: Safe Checks",
            "target_keyword": TARGET_KEYWORD,
            "target_date": "2026-07-26",
            "expected_draft_date": "2026-07-26",
            "queue_status": "planned",
            "file_path": "",
            "shopify_handle": None,
        }
        plan = writer.plan_writing(job_ctx=job_context)["writer_plan"]

        with tempfile.TemporaryDirectory() as directory:
            output_path = Path(directory) / "article.html"
            writer.write_selected_job_draft(
                job_ctx=job_context,
                writer_plan=plan,
                output_path_override=str(output_path),
            )
            receipt = evaluate_article_quality(
                output_path.read_text(encoding="utf-8"),
                target_keyword=TARGET_KEYWORD,
                site_url=SITE_URL,
            )

        codes = {blocker["code"] for blocker in receipt["blockers"]}
        self.assertFalse(receipt["passed"])
        self.assertIn("CQ_VISIBLE_WORD_COUNT_LOW", codes)
        self.assertGreaterEqual(receipt["metrics"]["internal_link_count"], 5)
        self.assertGreaterEqual(receipt["metrics"]["seo_title_chars"], 30)
        self.assertLessEqual(receipt["metrics"]["seo_title_chars"], 60)
        self.assertGreaterEqual(receipt["metrics"]["meta_description_chars"], 120)
        self.assertLessEqual(receipt["metrics"]["meta_description_chars"], 160)


if __name__ == "__main__":
    unittest.main()
