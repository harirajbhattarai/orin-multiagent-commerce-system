"""
Hoverboard Store Shopify Configuration Loader

tools/shopify_publisher/orin/hoverboard_shopify_config.py

Canonical single source for Hoverboard Store Shopify API credentials.
Loads configuration from namespaced environment variables only.
No hardcoded credentials. No token defaults. No credential in docstrings.
"""

from __future__ import annotations

import os


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

    Required variables:
        HOVERBOARD_STORE_SHOPIFY_STORE_DOMAIN
        HOVERBOARD_STORE_SHOPIFY_ACCESS_TOKEN
        HOVERBOARD_STORE_SHOPIFY_API_VERSION

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

    access_token = os.environ.get("HOVERBOARD_STORE_SHOPIFY_ACCESS_TOKEN", "")
    if not access_token:
        missing.append("HOVERBOARD_STORE_SHOPIFY_ACCESS_TOKEN")

    api_version = os.environ.get("HOVERBOARD_STORE_SHOPIFY_API_VERSION", "")
    if not api_version:
        missing.append("HOVERBOARD_STORE_SHOPIFY_API_VERSION")

    if missing:
        raise HoverboardShopifyConfigError(missing)

    # Blog ID is optional — fall back to a known default if not set
    blog_id_str = os.environ.get("HOVERBOARD_STORE_SHOPIFY_BLOG_ID", "")
    blog_id = int(blog_id_str) if blog_id_str else 113430790492

    return {
        "store_domain": store_domain,
        "access_token": access_token,
        "api_version": api_version,
        "blog_id": blog_id,
    }



