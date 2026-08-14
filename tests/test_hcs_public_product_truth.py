import importlib
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
ORIN_TOOLS = REPO_ROOT / "tools" / "shopify_publisher" / "orin"


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


def _load_adapter(monkeypatch):
    monkeypatch.syspath_prepend(str(ORIN_TOOLS))
    sys.modules.pop("hcs_product_truth_adapter", None)
    return importlib.import_module("hcs_product_truth_adapter")


def test_public_product_truth_never_loads_admin_token(monkeypatch):
    module = _load_adapter(monkeypatch)
    monkeypatch.setenv("ORIN_HCS_PRODUCT_TRUTH_SOURCE", "public-storefront")
    monkeypatch.setattr(
        module,
        "_load_token",
        lambda: (_ for _ in ()).throw(AssertionError("admin token was loaded")),
    )
    monkeypatch.setattr(
        module.urllib.request,
        "urlopen",
        lambda request, timeout: _Response(
            {
                "products": [
                    {
                        "id": 10,
                        "title": "Adult Electric Scooter",
                        "handle": "adult-electric-scooter",
                        "vendor": "HCS",
                        "product_type": "Electric Scooter",
                        "tags": ["adult"],
                        "variants": [
                            {
                                "id": 11,
                                "title": "Default",
                                "price": "299.99",
                                "position": 1,
                            }
                        ],
                    }
                ]
            }
        ),
    )

    adapter = module.HCSProductTruth()
    catalogue = adapter.fetch_and_normalise()
    validation = adapter.validate()

    assert len(catalogue) == 1
    assert catalogue[0]["status"] == "active"
    assert catalogue[0]["product_url"] == (
        "https://hcsgadgets.com/products/adult-electric-scooter"
    )
    assert validation["validation_status"] == "PRODUCT_TRUTH_VALID"
    assert validation["freshness_status"] == "PRODUCT_TRUTH_FRESH"
    assert validation["writer_ready"] is True
    assert adapter.shopify_write_count == 0


def test_hcs_worker_explicitly_uses_public_product_truth():
    compose = (REPO_ROOT / "deploy" / "vps" / "compose.yml").read_text(
        encoding="utf-8"
    )
    worker = compose.split("  hcs-worker-daemon:", 1)[1].split(
        "\n  evidence-sync:", 1
    )[0]

    assert "ORIN_HCS_PRODUCT_TRUTH_SOURCE: public-storefront" in worker
    assert "hoverboard_shopify_access_token" not in worker
