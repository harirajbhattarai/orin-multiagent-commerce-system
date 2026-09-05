from __future__ import annotations

import sys
import tempfile
from pathlib import Path


WRITER_DIR = Path(__file__).parents[1] / "tools" / "shopify_publisher" / "orin"
sys.path.insert(0, str(WRITER_DIR))

from content_quality_gate import DEFAULT_CONTRACT  # noqa: E402
from writer_agent import WriterAgent, _model_validation_receipts  # noqa: E402


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


def test_motor_power_revision_is_bound_to_topic_specific_plan():
    revision = (
        "Correct the voltage/current explanation: at the same wattage, higher "
        "voltage means lower current (P = V x I), not higher current. Rewrite "
        "the FAQ so every question directly addresses motor wattage, rated vs "
        "peak power, and single vs dual motor claims."
    )
    with tempfile.TemporaryDirectory() as directory:
        agent = WriterAgent(directory, "2026-09-05")
        plan = agent._build_dynamic_writer_plan(
            {
                "job_number": 42,
                "topic": "Hoverboard Motor Power Claims: How Buyers Should Read Product Specs",
                "target_keyword": "hoverboard motor power explained",
                "queue_status": "planned",
                "notes": f"- Human revision request (must be applied): {revision}",
            }
        )

    assert plan["cluster"] == "Buyer Guide"
    assert plan["revision_requirements"] == revision
    assert plan["revision_contract"]["required_phrase_groups"] == [
        ["higher voltage"],
        ["lower current"],
        ["P = V × I", "P = V x I", "power is voltage multiplied by current"],
    ]
    assert [item["question"] for item in plan["faq_plan"]] == [
        "What does a hoverboard's rated motor wattage tell me?",
        "How is peak motor power different from rated power?",
        "How should I compare single-motor and dual-motor claims?",
        "Does higher voltage mean higher current at the same wattage?",
    ]
    assert "Rated Power Versus Peak Power" in [
        section["h2"] for section in plan["h2_outline"]
    ]


def test_revision_contract_blocks_draft_that_omits_the_correction():
    receipt, _ = _model_validation_receipts(
        "<div><h1>Hoverboard Motor Power Claims</h1><p>Generic copy.</p></div>",
        job_number="42",
        title="Hoverboard Motor Power Claims",
        target_keyword="hoverboard motor power explained",
        cluster="Buyer Guide",
        h2_outline=[],
        site_url="https://hoverboardstore.co.uk",
        revision_contract={
            "required_phrase_groups": [
                ["higher voltage"],
                ["lower current"],
                ["P = V x I", "power is voltage multiplied by current"],
            ]
        },
    )

    assert "CQ_REVISION_REQUIREMENTS_MISSING" in {
        blocker["code"] for blocker in receipt["blockers"]
    }
    assert receipt["passed"] is False


def test_revision_contract_accepts_the_required_correction_phrases():
    receipt, _ = _model_validation_receipts(
        (
            "<div><h1>Hoverboard Motor Power Claims</h1><p>At the same wattage, "
            "higher voltage means lower current because power is voltage "
            "multiplied by current.</p></div>"
        ),
        job_number="42",
        title="Hoverboard Motor Power Claims",
        target_keyword="hoverboard motor power explained",
        cluster="Buyer Guide",
        h2_outline=[],
        site_url="https://hoverboardstore.co.uk",
        revision_contract={
            "required_phrase_groups": [
                ["higher voltage"],
                ["lower current"],
                ["P = V x I", "power is voltage multiplied by current"],
            ]
        },
    )

    assert "CQ_REVISION_REQUIREMENTS_MISSING" not in {
        blocker["code"] for blocker in receipt["blockers"]
    }
