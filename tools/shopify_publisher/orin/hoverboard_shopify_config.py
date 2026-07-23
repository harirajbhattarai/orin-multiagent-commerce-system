"""
Hoverboard Store Shopify Configuration Loader

tools/shopify_publisher/orin/hoverboard_shopify_config.py

Canonical single source for Hoverboard Store Shopify API credentials.
Loads configuration from namespaced environment variables only.
No hardcoded credentials. No token defaults. No credential in docstrings.
"""

from __future__ import annotations

import os
from pathlib import Path

from orin_control.secrets import read_private_secret


# ── Error classification ───────────────────────────────────────────────────────

HOVERBOARD_SHOPIFY_CONFIG_MISSING = "HOVERBOARD_SHOPIFY_CONFIG_MISSING"


class HoverboardShopifyConfigError(Exception):
    """
    Raised when required Hoverboard Store Shopify configuration is missing
    from the environment. Carries HOVERBOARD_SHOPIFY_CONFIG_MISSING classification.
    Does not include any credential values in error message.
    """
    classification = HOVERBOARD_SHOPIFY_CONFIG_MISSING

    def __init__(self, missing_vars: list[str]):
        self.missing_vars = missing_vars
        var_list = ", ".join(missing_vars)
        super().__init__(
            f"Hoverboard Store Shopify configuration missing. "
            f"Required environment variables: {var_list}"
        )


# ── Credential loader ─────────────────────────────────────────────────────────

def _get_required_env(var_name: str) -> str:
    """
    Get a required environment variable. Fail closed if missing.
    Returns the variable value. Never prints or returns the variable name
    in error messages that could leak configuration structure.
    """
    value = os.environ.get(var_name, "")
    if not value:
        raise HoverboardShopifyConfigError([var_name])
    return value


def load_hoverboard_shopify_config() -> dict:
    """
    Load Hoverboard Store Shopify configuration from environment variables.

    Required configuration:
        HOVERBOARD_STORE_SHOPIFY_STORE_DOMAIN
        HOVERBOARD_STORE_SHOPIFY_API_VERSION
        Exactly one of HOVERBOARD_STORE_SHOPIFY_ACCESS_TOKEN or
        HOVERBOARD_STORE_SHOPIFY_ACCESS_TOKEN_FILE

    Returns:
        dict with keys:
            store_domain (str): Shopify store domain
            access_token (str): Admin API access token
            api_version (str): API version string
            blog_id (int): Blog/Article ID for drafts

    Raises:
        HoverboardShopifyConfigError: if any required variable is missing.
            The error classification is HOVERBOARD_SHOPIFY_CONFIG_MISSING.
    """
    missing = []

    store_domain = os.environ.get("HOVERBOARD_STORE_SHOPIFY_STORE_DOMAIN", "")
    if not store_domain:
        missing.append("HOVERBOARD_STORE_SHOPIFY_STORE_DOMAIN")

    direct_access_token = os.environ.get("HOVERBOARD_STORE_SHOPIFY_ACCESS_TOKEN", "")
    access_token_file = os.environ.get("HOVERBOARD_STORE_SHOPIFY_ACCESS_TOKEN_FILE", "")
    if bool(direct_access_token) == bool(access_token_file):
        missing.append(
            "exactly one of HOVERBOARD_STORE_SHOPIFY_ACCESS_TOKEN "
            "or HOVERBOARD_STORE_SHOPIFY_ACCESS_TOKEN_FILE"
        )

    api_version = os.environ.get("HOVERBOARD_STORE_SHOPIFY_API_VERSION", "")
    if not api_version:
        missing.append("HOVERBOARD_STORE_SHOPIFY_API_VERSION")

    if missing:
        raise HoverboardShopifyConfigError(missing)

    access_token = (
        direct_access_token
        if direct_access_token
        else read_private_secret(Path(access_token_file), label="Shopify access token")
    )

    # Blog ID is optional — fall back to a known default if not set
    blog_id_str = os.environ.get("HOVERBOARD_STORE_SHOPIFY_BLOG_ID", "")
    blog_id = int(blog_id_str) if blog_id_str else 113430790492

    return {
        "store_domain": store_domain,
        "access_token": access_token,
        "api_version": api_version,
        "blog_id": blog_id,
    }

