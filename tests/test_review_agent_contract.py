import sys
from pathlib import Path


ORIN_TOOLS = (
    Path(__file__).resolve().parents[1]
    / "tools"
    / "shopify_publisher"
    / "orin"
)
sys.path.insert(0, str(ORIN_TOOLS))

from review_agent import unapproved_internal_hrefs  # noqa: E402


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

