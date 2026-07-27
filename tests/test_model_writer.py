import json
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

from model_writer import (  # noqa: E402
    ARTICLE_END,
    ARTICLE_START,
    MINIMAX_ENDPOINT,
    MINIMAX_MODEL,
    ModelWriterError,
    build_request_payload,
    extract_article_html,
    generate_article,
)


JOB_CONTEXT = {
    "job_number": "99",
    "topic": "Hoverboard Charger Not Working: Safe Checks",
}
WRITER_PLAN = {
    "title": "Hoverboard Charger Not Working: Safe Checks",
    "approved_handle": "hoverboard-charger-not-working-safe-checks",
    "target_keyword": "hoverboard charger not working",
    "search_intent": "Troubleshooting",
    "reader_persona": "UK hoverboard owner",
    "article_angle": "Safe diagnostic checks",
    "cluster": "Troubleshooting",
    "compliance_notes": "Use only model-specific manufacturer guidance.",
    "h2_outline": [
        {"id": "safe-checks", "h2": "Safe Checks", "label": "Safe checks"},
    ],
    "blocked_topic_terms": ["hoverkart", "hoverkarts"],
    "faq_plan": [],
    "internal_link_plan": [],
    "cta_plan": {},
    "claims_to_avoid": ["guarantee"],
    "content_quality_contract": {"version": "phase3.5-blog-v1"},
}
ARTICLE = """<!--
Meta Title: Hoverboard Charger Not Working: Safe Checks
Meta Description: Read this practical UK guide to hoverboard charger not working. Check common causes, safety warnings and next steps before replacing parts or seeking support.
-->
<div class="hs-article"><div class="hs-container">
<h1>Hoverboard Charger Not Working: Safe Checks</h1>
</div></div>"""


class ModelWriterTests(unittest.TestCase):
    def test_request_is_pinned_and_disables_thinking(self):
        payload = build_request_payload(JOB_CONTEXT, WRITER_PLAN)

        self.assertEqual(payload["model"], MINIMAX_MODEL)
        self.assertEqual(payload["thinking"], {"type": "disabled"})
        self.assertFalse(payload["stream"])
        self.assertGreaterEqual(payload["max_completion_tokens"], 6000)
        self.assertIn("1,500 visible words", payload["messages"][1]["content"])
        self.assertIn(
            "Attribute allowlist: class on allowed tags",
            payload["messages"][1]["content"],
        )
        self.assertIn(
            "Do not add aria-*",
            payload["messages"][1]["content"],
        )
        self.assertIn(
            '"compliance_notes": "Use only model-specific manufacturer guidance."',
            payload["messages"][1]["content"],
        )
        self.assertIn(
            "Do not infer performance, stability, terrain suitability",
            payload["messages"][1]["content"],
        )
        self.assertIn(
            "Do not provide medical advice",
            payload["messages"][1]["content"],
        )
        self.assertIn(
            "Use every h2_outline[].h2 value verbatim",
            payload["messages"][1]["content"],
        )
        self.assertIn(
            '"blocked_topic_terms": [',
            payload["messages"][1]["content"],
        )
        self.assertIn(
            "Do not use any word or phrase listed in blocked_topic_terms",
            payload["messages"][1]["content"],
        )
        self.assertIn(
            "Do not repeat any word or phrase from claims_to_avoid",
            payload["messages"][1]["content"],
        )
        self.assertIn(
            '"safer than"',
            payload["messages"][1]["content"],
        )
        self.assertNotIn(
            "safety guarantees",
            payload["messages"][0]["content"].lower(),
        )
        self.assertEqual(MINIMAX_ENDPOINT, "https://api.minimax.io/v1/chat/completions")

    def test_extracts_exact_sentinel_artifact(self):
        content = f"{ARTICLE_START}\n{ARTICLE}\n{ARTICLE_END}"

        self.assertEqual(extract_article_html(content), ARTICLE)

    def test_allows_safe_h2_anchor_ids(self):
        article = (
            '<div class="hs-article"><h2 id="before-you-buy_2">'
            "Before You Buy</h2></div>"
        )

        self.assertEqual(
            extract_article_html(f"{ARTICLE_START}{article}{ARTICLE_END}"),
            article,
        )

    def test_rejects_unsafe_or_misplaced_ids(self):
        unsafe_articles = [
            '<h2 id="bad anchor">Heading</h2>',
            '<h2 id="x&quot; onclick=&quot;alert(1)">Heading</h2>',
            '<div id="allowed-looking">Content</div>',
        ]
        for article in unsafe_articles:
            with self.subTest(article=article):
                with self.assertRaises(ModelWriterError):
                    extract_article_html(f"{ARTICLE_START}{article}{ARTICLE_END}")

    def test_rejects_markdown_or_text_outside_sentinels(self):
        with self.assertRaises(ModelWriterError):
            extract_article_html(f"```html\n{ARTICLE}\n```")
        with self.assertRaises(ModelWriterError):
            extract_article_html(f"note\n{ARTICLE_START}{ARTICLE}{ARTICLE_END}")
        with self.assertRaises(ModelWriterError):
            extract_article_html(
                f"{ARTICLE_START}<script>alert(1)</script>{ARTICLE_END}"
            )
        with self.assertRaises(ModelWriterError):
            extract_article_html(
                f'{ARTICLE_START}<a href="javascript:alert(1)">x</a>{ARTICLE_END}'
            )
        with self.assertRaises(ModelWriterError):
            extract_article_html(
                f'{ARTICLE_START}<div onclick="alert(1)">x</div>{ARTICLE_END}'
            )

    def test_rejects_parsed_active_urls_and_concealment(self):
        unsafe_articles = [
            '<a href=javascript:alert(1)>x</a>',
            '<a href="java&#x73;cript:alert(1)">x</a>',
            '<div hidden><p>x</p></div>',
            '<div style="display:none"><p>x</p></div>',
        ]
        for article in unsafe_articles:
            with self.subTest(article=article):
                with self.assertRaises(ModelWriterError):
                    extract_article_html(f"{ARTICLE_START}{article}{ARTICLE_END}")

    def test_fake_provider_writes_private_non_secret_evidence(self):
        captured = {}

        def fake_transport(payload, api_key, timeout):
            captured["payload"] = payload
            captured["api_key"] = api_key
            captured["timeout"] = timeout
            return {
                "id": "response-test",
                "model": MINIMAX_MODEL,
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "content": f"{ARTICLE_START}{ARTICLE}{ARTICLE_END}"
                        },
                    }
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 20},
                "input_sensitive": False,
                "output_sensitive": False,
            }

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            key_path = root / "writer_api_key"
            key_path.write_text("secret-test-key\n", encoding="utf-8")
            key_path.chmod(0o400)
            evidence_dir = root / "evidence"
            evidence_dir.mkdir(mode=0o700)
            environment = {
                "ORIN_WRITER_API_KEY_FILE": str(key_path),
                "ORIN_RUN_ARTIFACT_DIR": str(evidence_dir),
                "ORIN_WRITER_TIMEOUT_SECONDS": "60",
            }
            with patch.dict(os.environ, environment, clear=False):
                result = generate_article(
                    job_context=JOB_CONTEXT,
                    writer_plan=WRITER_PLAN,
                    transport=fake_transport,
                )

            request_path = evidence_dir / "model_writer_request.json"
            response_path = evidence_dir / "model_writer_response.json"
            request_text = request_path.read_text(encoding="utf-8")
            response = json.loads(response_path.read_text(encoding="utf-8"))

            self.assertEqual(result.body_html, ARTICLE)
            self.assertEqual(result.model, MINIMAX_MODEL)
            self.assertEqual(captured["api_key"], "secret-test-key")
            self.assertNotIn("secret-test-key", request_text)
            self.assertEqual(response["body_html"], ARTICLE)
            self.assertEqual(request_path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(response_path.stat().st_mode & 0o777, 0o600)

    def test_second_attempt_requires_quality_feedback_and_preserves_evidence(self):
        captured = {}

        def fake_transport(payload, api_key, timeout):
            captured["payload"] = payload
            return {
                "id": "response-retry",
                "model": MINIMAX_MODEL,
                "choices": [{"finish_reason": "stop", "message": {"content": f"{ARTICLE_START}{ARTICLE}{ARTICLE_END}"}}],
                "usage": {},
            }

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            key_path = root / "writer_api_key"
            key_path.write_text("secret-test-key\n", encoding="utf-8")
            key_path.chmod(0o400)
            evidence_dir = root / "evidence"
            evidence_dir.mkdir(mode=0o700)
            with patch.dict(
                os.environ,
                {
                    "ORIN_WRITER_API_KEY_FILE": str(key_path),
                    "ORIN_RUN_ARTIFACT_DIR": str(evidence_dir),
                },
                clear=False,
            ):
                with self.assertRaises(ModelWriterError):
                    generate_article(
                        job_context=JOB_CONTEXT,
                        writer_plan=WRITER_PLAN,
                        transport=fake_transport,
                        attempt=2,
                    )
                generate_article(
                    job_context=JOB_CONTEXT,
                    writer_plan=WRITER_PLAN,
                    transport=fake_transport,
                    attempt=2,
                    quality_retry={"failed_requirements": [{"code": "CQ_VISIBLE_WORD_COUNT_LOW"}]},
                )

            retry_request = evidence_dir / "model_writer_attempt_2_request.json"
            retry_response = evidence_dir / "model_writer_attempt_2_response.json"
            self.assertTrue(retry_request.is_file())
            self.assertTrue(retry_response.is_file())
            self.assertFalse((evidence_dir / "model_writer_request.json").exists())
            self.assertIn("final quality-correction attempt", captured["payload"]["messages"][1]["content"])
            self.assertEqual(retry_request.stat().st_mode & 0o777, 0o600)

    def test_rejects_incomplete_or_wrong_model_response(self):
        def incomplete_transport(payload, api_key, timeout):
            return {
                "model": MINIMAX_MODEL,
                "choices": [
                    {
                        "finish_reason": "length",
                        "message": {
                            "content": f"{ARTICLE_START}{ARTICLE}{ARTICLE_END}"
                        },
                    }
                ],
            }

        def wrong_model_transport(payload, api_key, timeout):
            return {
                "model": "MiniMax-M2.7",
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "content": f"{ARTICLE_START}{ARTICLE}{ARTICLE_END}"
                        },
                    }
                ],
            }

        with tempfile.TemporaryDirectory() as directory:
            key_path = Path(directory) / "writer_api_key"
            key_path.write_text("secret-test-key\n", encoding="utf-8")
            key_path.chmod(0o400)
            with patch.dict(
                os.environ,
                {"ORIN_WRITER_API_KEY_FILE": str(key_path)},
                clear=False,
            ):
                with self.assertRaises(ModelWriterError):
                    generate_article(
                        job_context=JOB_CONTEXT,
                        writer_plan=WRITER_PLAN,
                        transport=incomplete_transport,
                    )
                with self.assertRaises(ModelWriterError):
                    generate_article(
                        job_context=JOB_CONTEXT,
                        writer_plan=WRITER_PLAN,
                        transport=wrong_model_transport,
                    )


if __name__ == "__main__":
    unittest.main()
