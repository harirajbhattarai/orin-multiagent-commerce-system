from __future__ import annotations

import sys
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
