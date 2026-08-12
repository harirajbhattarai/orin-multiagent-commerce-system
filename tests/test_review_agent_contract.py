import sys
from pathlib import Path


ORIN_TOOLS = (
    Path(__file__).resolve().parents[1]
    / "tools"
    / "shopify_publisher"
    / "orin"
)
sys.path.insert(0, str(ORIN_TOOLS))

from review_agent import (  # noqa: E402
    blocked_claims_in_text,
    faq_questions_match_plan,
    unapproved_internal_hrefs,
)


def test_unapproved_internal_hrefs_rejects_invented_model_url():
    plan = {
        "internal_link_plan": [
            {
                "url": "https://hoverboardstore.co.uk/collections/electric-scooters"
            },
            {"url": "https://hoverboardstore.co.uk/pages/contact"},
        ],
        "cta_plan": {
            "button_href": "https://hoverboardstore.co.uk/collections/electric-scooters"
        },
    }
    html = (
        '<a href="https://hoverboardstore.co.uk/collections/electric-scooters">'
        "Approved collection</a>"
        '<a href="https://hoverboardstore.co.uk/browse-electric-scooters">'
        "Invented route</a>"
    )

    assert unapproved_internal_hrefs(html, plan) == [
        "https://hoverboardstore.co.uk/browse-electric-scooters"
    ]


def test_blocked_claims_accepts_cautionary_range_language():
    html = (
        "<p>Treat the headline range as an upper estimate rather than an "
        "everyday guarantee.</p>"
    )

    assert blocked_claims_in_text(html, ["guarantee"]) == []


def test_blocked_claims_rejects_affirmative_guarantee():
    html = "<p>This range guarantee applies to every everyday journey.</p>"

    assert blocked_claims_in_text(html, ["guarantee"]) == ["guarantee"]


def test_blocked_claims_checks_each_occurrence_independently():
    html = (
        "<p>This is not a guarantee.</p>"
        "<p>Our range guarantee applies to every journey.</p>"
    )

    assert blocked_claims_in_text(html, ["guarantee"]) == ["guarantee"]


def test_faq_questions_must_match_the_approved_plan_in_order():
    plan = [
        {"question": "What affects electric scooter range?"},
        {"question": "Where should I check battery guidance?"},
    ]
    matching_html = (
        '<div class="hs-faq-q">What affects electric scooter range?</div>'
        '<div class="hs-faq-q">Where should I check battery guidance?</div>'
    )
    stale_html = (
        '<div class="hs-faq-q">What should I check before riding?</div>'
        '<div class="hs-faq-q">Where should I check battery guidance?</div>'
    )

    assert faq_questions_match_plan(matching_html, plan)
    assert not faq_questions_match_plan(stale_html, plan)
