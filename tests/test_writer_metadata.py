from __future__ import annotations

import sys
import tempfile
from pathlib import Path


WRITER_DIR = Path(__file__).parents[1] / "tools" / "shopify_publisher" / "orin"
sys.path.insert(0, str(WRITER_DIR))

from content_quality_gate import DEFAULT_CONTRACT  # noqa: E402
from writer_agent import WriterAgent  # noqa: E402


def build_meta_description(keyword: str) -> str:
    return WriterAgent._build_meta_description(None, keyword.title(), keyword)


def test_meta_description_is_complete_for_current_hbstore_keywords():
    descriptions = (
        build_meta_description("hoverboard footpad grip"),
        build_meta_description("hoverboard motor power explained"),
    )

    for description in descriptions:
        assert DEFAULT_CONTRACT["min_meta_description_chars"] <= len(description)
        assert len(description) <= DEFAULT_CONTRACT["max_meta_description_chars"]
        assert description.endswith(".")
        assert not description.endswith(" seeking.")
        assert not description.endswith(" qualified.")


def test_meta_description_uses_a_shorter_complete_template_when_needed():
    keyword = "a deliberately longer hoverboard comparison phrase"
    description = build_meta_description(keyword)

    assert keyword in description
    assert description.endswith(".")
    assert len(description) <= DEFAULT_CONTRACT["max_meta_description_chars"]


def test_accessory_outline_uses_grammatical_matters_heading():
    with tempfile.TemporaryDirectory() as directory:
        agent = WriterAgent(directory, "2026-08-13")
        outline = agent._generate_h2_outline(
            "Hoverboard Footpads and Grip: What to Check Before Buying",
            "hoverboard footpad grip",
            "Accessories",
        )

    headings = [section["h2"] for section in outline]
    assert "Why Hoverboard Footpad Grip Matters" in headings
    assert "Why Hoverboard Footpad Grip Matter" not in headings


def test_footpad_faq_and_compliance_plan_are_topic_specific():
    with tempfile.TemporaryDirectory() as directory:
        agent = WriterAgent(directory, "2026-08-13")
        context = {
            "job_number": 43,
            "topic": "Hoverboard Footpads and Grip: What to Check Before Buying",
            "target_keyword": "hoverboard footpad grip",
            "queue_status": "planned",
            "cluster": "Accessories",
        }
        plan = agent._build_dynamic_writer_plan(context)

    questions = [item["question"] for item in plan["faq_plan"]]
    assert questions == [
        "What signs show that hoverboard footpad grip is worn?",
        "How should hoverboard footpads be cleaned?",
        "Can I fit any replacement grip pad to my hoverboard?",
        "What footwear should a rider use on hoverboard footpads?",
    ]
    compliance = plan["compliance_notes"]
    assert "do not advise lifting, removing, cutting" in compliance
    assert "Require suitable closed footwear" in compliance
    assert "qualified service provider" in compliance
