from __future__ import annotations

import sys
from pathlib import Path


WRITER_DIR = (
    Path(__file__).resolve().parents[1] / "tools" / "shopify_publisher" / "orin"
)
sys.path.insert(0, str(WRITER_DIR))

from job_context import build_job_context  # noqa: E402


def test_build_job_context_preserves_revision_notes():
    notes = (
        "- Human revision request (must be applied): Correct the formula and "
        "rewrite the FAQ."
    )

    context = build_job_context(
        "42",
        {
            "topic": "Hoverboard Motor Power Claims",
            "keyword": "hoverboard motor power explained",
            "target_date": "2026-09-20",
            "queue_status": "planned",
            "notes": notes,
        },
    )

    assert context["notes"] == notes
