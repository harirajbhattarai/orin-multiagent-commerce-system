from __future__ import annotations

import sys
from pathlib import Path

import pytest


ORIN_TOOLS = Path(__file__).resolve().parents[1] / "tools" / "shopify_publisher" / "orin"
sys.path.insert(0, str(ORIN_TOOLS))

from hoverboard_shopify_config import (  # noqa: E402
    HoverboardShopifyConfigError,
    load_hoverboard_shopify_config,
)


def base_environment(monkeypatch):
    monkeypatch.setenv(
        "HOVERBOARD_STORE_SHOPIFY_STORE_DOMAIN",
        "hoverboardstore.myshopify.com",
    )
    monkeypatch.setenv("HOVERBOARD_STORE_SHOPIFY_API_VERSION", "2026-04")
    monkeypatch.delenv("HOVERBOARD_STORE_SHOPIFY_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("HOVERBOARD_STORE_SHOPIFY_ACCESS_TOKEN_FILE", raising=False)


def test_shopify_token_can_be_read_from_a_private_service_owned_file(tmp_path, monkeypatch):
    base_environment(monkeypatch)
    secret = tmp_path / "shopify_access_token"
    secret.write_text("private-test-token\n", encoding="utf-8")
    secret.chmod(0o400)
    monkeypatch.setenv("HOVERBOARD_STORE_SHOPIFY_ACCESS_TOKEN_FILE", str(secret))

    config = load_hoverboard_shopify_config()

    assert config["access_token"] == "private-test-token"
    assert config["api_version"] == "2026-04"


def test_shopify_config_rejects_ambiguous_token_sources(tmp_path, monkeypatch):
    base_environment(monkeypatch)
    secret = tmp_path / "shopify_access_token"
    secret.write_text("file-token\n", encoding="utf-8")
    secret.chmod(0o400)
    monkeypatch.setenv("HOVERBOARD_STORE_SHOPIFY_ACCESS_TOKEN", "direct-token")
    monkeypatch.setenv("HOVERBOARD_STORE_SHOPIFY_ACCESS_TOKEN_FILE", str(secret))

    with pytest.raises(HoverboardShopifyConfigError, match="exactly one"):
        load_hoverboard_shopify_config()
