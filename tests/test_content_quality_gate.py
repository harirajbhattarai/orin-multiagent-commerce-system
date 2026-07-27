import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ORIN_TOOLS = (
    Path(__file__).resolve().parents[1]
    / "tools"
    / "shopify_publisher"
    / "orin"
)
sys.path.insert(0, str(ORIN_TOOLS))

from content_quality_gate import evaluate_article_quality  # noqa: E402
from model_writer import ModelWriterError, ModelWriterResult  # noqa: E402
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

    def test_highlights_h2_is_not_a_substantive_section(self):
        html = _valid_article().replace(
            '<div class="hs-quick-answer">',
            (
                '<div class="hs-highlights"><h2>Highlights</h2>'
                "<p>Short summary points for the reader.</p></div>"
                '<div class="hs-quick-answer">'
            ),
            1,
        )

        receipt = evaluate_article_quality(
            html,
            target_keyword=TARGET_KEYWORD,
            site_url=SITE_URL,
        )

        self.assertTrue(receipt["passed"], receipt["blockers"])
        headings = {
            section["heading"]
            for section in receipt["metrics"]["substantive_sections"]
        }
        self.assertNotIn("Highlights", headings)

    def test_writer_plans_have_four_substantive_sections(self):
        repository_root = Path(__file__).resolve().parents[1]
        cases = [
            (
                "Birthday Hoverboard Gift Guide for Kids UK",
                "birthday hoverboard gift guide",
            ),
            ("Hoverboard Battery Care", "hoverboard battery care"),
            ("Christmas Hoverboard Ideas", "christmas hoverboard ideas"),
            ("Understanding Hoverboards", "understanding hoverboards"),
        ]
        non_substantive_ids = {"introduction", "quick-answer", "faq", "cta"}

        for index, (topic, keyword) in enumerate(cases, start=1):
            with self.subTest(topic=topic):
                writer = WriterAgent(str(repository_root), "2026-07-26")
                job_context = {
                    "job_number": str(200 + index),
                    "job_label": f"Job {200 + index}",
                    "topic": topic,
                    "target_keyword": keyword,
                    "target_date": "2026-08-01",
                    "expected_draft_date": "2026-07-18",
                    "queue_status": "planned",
                    "file_path": "",
                    "shopify_handle": None,
                }
                plan = writer.plan_writing(job_ctx=job_context)["writer_plan"]
                substantive = [
                    item
                    for item in plan["h2_outline"]
                    if item["id"] not in non_substantive_ids
                ]
                self.assertGreaterEqual(len(substantive), 4)

    def test_writer_supporting_copy_does_not_force_keyword_repetition(self):
        repository_root = Path(__file__).resolve().parents[1]
        writer = WriterAgent(str(repository_root), "2026-07-26")
        keyword = "birthday hoverboard gift guide"
        job_context = {
            "job_number": "299",
            "job_label": "Job 299",
            "topic": "Birthday Hoverboard Gift Guide for Kids UK",
            "target_keyword": keyword,
            "target_date": "2026-08-11",
            "expected_draft_date": "2026-07-28",
            "queue_status": "planned",
            "file_path": "",
            "shopify_handle": None,
        }

        plan = writer.plan_writing(job_ctx=job_context)["writer_plan"]
        supporting_copy = (
            repr(plan["faq_plan"]) + repr(plan["cta_plan"])
        ).lower()

        self.assertNotIn(keyword, supporting_copy)

    def test_buyer_plan_aligns_cta_heading_and_excludes_hoverkart_links(self):
        repository_root = Path(__file__).resolve().parents[1]
        writer = WriterAgent(str(repository_root), "2026-07-26")
        job_context = {
            "job_number": "299",
            "job_label": "Job 299",
            "topic": "Birthday Hoverboard Gift Guide for Kids UK",
            "target_keyword": "birthday hoverboard gift guide",
            "target_date": "2026-08-11",
            "expected_draft_date": "2026-07-28",
            "queue_status": "planned",
            "cluster": "Buyer Guide",
            "file_path": "",
            "shopify_handle": None,
        }

        plan = writer.plan_writing(job_ctx=job_context)["writer_plan"]
        cta_heading = next(
            item["h2"] for item in plan["h2_outline"] if item["id"] == "cta"
        )
        links_text = repr(plan["internal_link_plan"]).lower()

        self.assertEqual(cta_heading, plan["cta_plan"]["heading"])
        self.assertNotIn("hoverkart", links_text)
        self.assertIn("hoverkart", plan["blocked_topic_terms"])
        self.assertGreaterEqual(len(plan["internal_link_plan"]), 5)

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

    def test_hidden_content_is_not_counted_as_visible(self):
        for marker in (' hidden', ' style="display:none"'):
            with self.subTest(marker=marker):
                html = _valid_article().replace(
                    '<div class="hs-article">',
                    f'<div class="hs-article"{marker}>',
                    1,
                )
                receipt = evaluate_article_quality(
                    html, target_keyword=TARGET_KEYWORD, site_url=SITE_URL
                )
                self.assertEqual(receipt["metrics"]["visible_word_count"], 0)
                self.assertFalse(receipt["passed"])

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

    def test_model_writer_gets_one_quality_retry_before_draft_is_written(self):
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
        too_short = (
            "<div class=\"hs-article\"><div class=\"hs-container\">"
            "<h1>Hoverboard Charger Not Working: Safe Checks</h1>"
            "<p>Too short to pass the quality contract.</p>"
            "</div></div>"
        )
        first = ModelWriterResult(
            body_html=too_short,
            provider="minimax",
            model="MiniMax-M3",
            response_id="initial-response",
            finish_reason="stop",
            usage={},
        )
        second = ModelWriterResult(
            body_html=_valid_article(),
            provider="minimax",
            model="MiniMax-M3",
            response_id="retry-response",
            finish_reason="stop",
            usage={},
        )

        with tempfile.TemporaryDirectory() as directory:
            output_path = Path(directory) / "article.html"
            with patch.dict(os.environ, {"ORIN_MODEL_WRITER_ENABLED": "1"}):
                with patch("writer_agent.generate_article", side_effect=[first, second]) as generate:
                    stats = writer.write_selected_job_draft(
                        job_ctx=job_context,
                        writer_plan=plan,
                        output_path_override=str(output_path),
                    )

        self.assertEqual(generate.call_count, 2)
        self.assertEqual(generate.call_args_list[0].kwargs["attempt"], 1)
        self.assertEqual(generate.call_args_list[1].kwargs["attempt"], 2)
        self.assertIn(
            "CQ_VISIBLE_WORD_COUNT_LOW",
            {
                item["code"]
                for item in generate.call_args_list[1].kwargs["quality_retry"][
                    "failed_requirements"
                ]
            },
        )
        self.assertTrue(stats["model_attempts"][1]["quality_passed"])
        self.assertEqual(stats["model_response_id"], "retry-response")

    def test_model_writer_uses_bounded_retry_for_missing_approved_h2(self):
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
        plan["h2_outline"] = [
            {"id": f"check-{index}", "h2": f"Detailed Check {index}"}
            for index in range(1, 7)
        ]
        missing_h2 = _valid_article().replace(
            "<h2>Detailed Check 1</h2>",
            "<h2>Unapproved Replacement</h2>",
            1,
        )
        first = ModelWriterResult(
            body_html=missing_h2,
            provider="minimax",
            model="MiniMax-M3",
            response_id="missing-h2-response",
            finish_reason="stop",
            usage={},
        )
        second = ModelWriterResult(
            body_html=_valid_article(),
            provider="minimax",
            model="MiniMax-M3",
            response_id="corrected-h2-response",
            finish_reason="stop",
            usage={},
        )

        with tempfile.TemporaryDirectory() as directory:
            output_path = Path(directory) / "article.html"
            with patch.dict(os.environ, {"ORIN_MODEL_WRITER_ENABLED": "1"}):
                with patch(
                    "writer_agent.generate_article",
                    side_effect=[first, second],
                ) as generate:
                    stats = writer.write_selected_job_draft(
                        job_ctx=job_context,
                        writer_plan=plan,
                        output_path_override=str(output_path),
                    )

        self.assertEqual(generate.call_count, 2)
        retry_requirements = generate.call_args_list[1].kwargs[
            "quality_retry"
        ]["failed_requirements"]
        topic_requirement = next(
            item
            for item in retry_requirements
            if item["code"] == "TI_H2_PLAN_MISMATCH"
        )
        self.assertIn(
            "Detailed Check 1",
            topic_requirement["expected"]["required_h2_headings"],
        )
        self.assertFalse(stats["model_attempts"][0]["topic_identity_passed"])
        self.assertTrue(stats["model_attempts"][1]["topic_identity_passed"])
        self.assertEqual(stats["model_response_id"], "corrected-h2-response")

    def test_topic_retry_never_exceeds_two_model_calls(self):
        repository_root = Path(__file__).resolve().parents[1]
        writer = WriterAgent(str(repository_root), "2026-07-26")
        job_context = {
            "job_number": "99",
            "topic": "Hoverboard Charger Not Working: Safe Checks",
            "target_keyword": TARGET_KEYWORD,
        }
        plan = writer.plan_writing(job_ctx=job_context)["writer_plan"]
        plan["h2_outline"] = [
            {"id": f"check-{index}", "h2": f"Detailed Check {index}"}
            for index in range(1, 7)
        ]
        missing_h2 = _valid_article().replace(
            "<h2>Detailed Check 1</h2>",
            "<h2>Unapproved Replacement</h2>",
            1,
        )
        failed = ModelWriterResult(
            body_html=missing_h2,
            provider="minimax",
            model="MiniMax-M3",
            response_id="still-missing-h2",
            finish_reason="stop",
            usage={},
        )

        with tempfile.TemporaryDirectory() as directory:
            output_path = Path(directory) / "article.html"
            with patch.dict(os.environ, {"ORIN_MODEL_WRITER_ENABLED": "1"}):
                with patch(
                    "writer_agent.generate_article",
                    side_effect=[failed, failed],
                ) as generate:
                    stats = writer.write_selected_job_draft(
                        job_ctx=job_context,
                        writer_plan=plan,
                        output_path_override=str(output_path),
                    )

        self.assertEqual(generate.call_count, 2)
        self.assertFalse(stats["model_attempts"][1]["topic_identity_passed"])
        self.assertIn(
            "TI_H2_PLAN_MISMATCH",
            stats["model_attempts"][1]["blocker_codes"],
        )

    def test_model_writer_spends_same_single_retry_budget_on_output_contract(self):
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
        corrected = ModelWriterResult(
            body_html=_valid_article(),
            provider="minimax",
            model="MiniMax-M3",
            response_id="contract-retry-response",
            finish_reason="stop",
            usage={},
        )

        with tempfile.TemporaryDirectory() as directory:
            output_path = Path(directory) / "article.html"
            with patch.dict(os.environ, {"ORIN_MODEL_WRITER_ENABLED": "1"}):
                with patch(
                    "writer_agent.generate_article",
                    side_effect=[
                        ModelWriterError(
                            "model response contains text outside the article sentinels"
                        ),
                        corrected,
                    ],
                ) as generate:
                    stats = writer.write_selected_job_draft(
                        job_ctx=job_context,
                        writer_plan=plan,
                        output_path_override=str(output_path),
                    )

        self.assertEqual(generate.call_count, 2)
        self.assertEqual(generate.call_args_list[0].kwargs["attempt"], 1)
        self.assertEqual(generate.call_args_list[1].kwargs["attempt"], 2)
        self.assertEqual(
            generate.call_args_list[1].kwargs["quality_retry"][
                "failed_requirements"
            ][0]["code"],
            "MW_OUTPUT_CONTRACT",
        )
        self.assertEqual(
            [attempt["attempt"] for attempt in stats["model_attempts"]],
            [1, 2],
        )
        self.assertTrue(stats["model_attempts"][1]["quality_passed"])

    def test_html_policy_error_uses_the_bounded_output_retry(self):
        repository_root = Path(__file__).resolve().parents[1]
        writer = WriterAgent(str(repository_root), "2026-07-26")
        job_context = {
            "job_number": "99",
            "topic": "Hoverboard Charger Not Working: Safe Checks",
            "target_keyword": TARGET_KEYWORD,
        }
        plan = writer.plan_writing(job_ctx=job_context)["writer_plan"]
        corrected = ModelWriterResult(
            body_html=_valid_article(),
            provider="minimax",
            model="MiniMax-M3",
            response_id="policy-retry-response",
            finish_reason="stop",
            usage={},
        )

        with tempfile.TemporaryDirectory() as directory:
            output_path = Path(directory) / "article.html"
            with patch.dict(os.environ, {"ORIN_MODEL_WRITER_ENABLED": "1"}):
                with patch(
                    "writer_agent.generate_article",
                    side_effect=[
                        ModelWriterError(
                            "model article contains unsupported attribute: id"
                        ),
                        corrected,
                    ],
                ) as generate:
                    stats = writer.write_selected_job_draft(
                        job_ctx=job_context,
                        writer_plan=plan,
                        output_path_override=str(output_path),
                    )

        self.assertEqual(generate.call_count, 2)
        self.assertEqual(
            generate.call_args_list[1].kwargs["quality_retry"][
                "failed_requirements"
            ][0]["code"],
            "MW_OUTPUT_CONTRACT",
        )
        self.assertEqual(stats["model_response_id"], "policy-retry-response")

    def test_non_output_model_error_does_not_retry(self):
        repository_root = Path(__file__).resolve().parents[1]
        writer = WriterAgent(str(repository_root), "2026-07-26")
        job_context = {
            "job_number": "99",
            "topic": "Hoverboard Charger Not Working: Safe Checks",
            "target_keyword": TARGET_KEYWORD,
        }
        plan = writer.plan_writing(job_ctx=job_context)["writer_plan"]

        with tempfile.TemporaryDirectory() as directory:
            output_path = Path(directory) / "article.html"
            with patch.dict(os.environ, {"ORIN_MODEL_WRITER_ENABLED": "1"}):
                with patch(
                    "writer_agent.generate_article",
                    side_effect=ModelWriterError(
                        "model provider returned HTTP 429"
                    ),
                ) as generate:
                    with self.assertRaisesRegex(ModelWriterError, "HTTP 429"):
                        writer.write_selected_job_draft(
                            job_ctx=job_context,
                            writer_plan=plan,
                            output_path_override=str(output_path),
                        )

        self.assertEqual(generate.call_count, 1)


if __name__ == "__main__":
    unittest.main()
