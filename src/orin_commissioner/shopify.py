"""Read-only Shopify commissioning probe."""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from orin_commissioner.models import CommissioningContext


STORE_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]*\.myshopify\.com$")
BLOG_PATTERN = re.compile(r"^gid://shopify/Blog/[0-9]+$")


class ShopifyProbeError(RuntimeError):
    """Transient Shopify/network failure that may be retried."""


class PermanentCommissioningError(RuntimeError):
    """Configuration or identity mismatch that must fail closed."""


@dataclass(frozen=True)
class ShopifyIdentityReceipt:
    store_domain: str
    shop_name: str
    primary_domain: str
    blog_gid: str
    blog_title: str
    product_count: int

    def evidence(self) -> dict[str, Any]:
        return {
            "store_domain": self.store_domain,
            "shop_name": self.shop_name,
            "primary_domain": self.primary_domain,
            "blog_gid": self.blog_gid,
            "blog_title": self.blog_title,
            "product_count": self.product_count,
            "shopify_mutation_attempted": False,
        }


QUERY = """
query OrinReadOnlyCommissioning {
  shop { name myshopifyDomain primaryDomain { host } }
  blogs(first: 50) { nodes { id title } }
  productsCount { count }
}
"""


def probe_shopify_identity(
    context: CommissioningContext,
    *,
    api_version: str = "2026-07",
    timeout_seconds: float = 30,
    opener: Any = urllib.request.urlopen,
) -> ShopifyIdentityReceipt:
    if not STORE_PATTERN.fullmatch(context.store_domain):
        raise PermanentCommissioningError("invalid Shopify store domain")
    if not BLOG_PATTERN.fullmatch(context.blog_gid):
        raise PermanentCommissioningError("invalid Shopify blog identity")
    if not context.access_token or len(context.access_token) > 512:
        raise PermanentCommissioningError("invalid Shopify credential")
    if timeout_seconds <= 0 or timeout_seconds > 120:
        raise ValueError("Shopify probe timeout must be between 0 and 120 seconds")

    request = urllib.request.Request(
        f"https://{context.store_domain}/admin/api/{api_version}/graphql.json",
        data=json.dumps({"query": QUERY}).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "X-Shopify-Access-Token": context.access_token,
            "User-Agent": "ORIN-Commissioner/1",
        },
        method="POST",
    )
    try:
        with opener(request, timeout=timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise ShopifyProbeError("Shopify read-only probe failed") from exc

    if not isinstance(payload, dict) or payload.get("errors"):
        raise ShopifyProbeError("Shopify returned a GraphQL error")
    data = payload.get("data")
    if not isinstance(data, dict):
        raise ShopifyProbeError("Shopify response is missing data")
    shop = data.get("shop")
    blogs = data.get("blogs")
    products_count = data.get("productsCount")
    if not isinstance(shop, dict) or not isinstance(blogs, dict) or not isinstance(products_count, dict):
        raise ShopifyProbeError("Shopify response shape is invalid")

    returned_domain = str(shop.get("myshopifyDomain") or "").lower()
    if returned_domain != context.store_domain:
        raise PermanentCommissioningError("Shopify credential belongs to another store")
    nodes = blogs.get("nodes")
    if not isinstance(nodes, list):
        raise ShopifyProbeError("Shopify blog response is invalid")
    matching_blog = next(
        (blog for blog in nodes if isinstance(blog, dict) and blog.get("id") == context.blog_gid),
        None,
    )
    if matching_blog is None:
        raise PermanentCommissioningError("configured Shopify blog is unavailable")
    count = products_count.get("count")
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        raise ShopifyProbeError("Shopify product count is invalid")

    primary = shop.get("primaryDomain")
    primary_domain = str(primary.get("host") or "") if isinstance(primary, dict) else ""
    return ShopifyIdentityReceipt(
        store_domain=returned_domain,
        shop_name=str(shop.get("name") or ""),
        primary_domain=primary_domain,
        blog_gid=context.blog_gid,
        blog_title=str(matching_blog.get("title") or context.blog_title),
        product_count=count,
    )
