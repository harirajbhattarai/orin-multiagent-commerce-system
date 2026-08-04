"""Create at most one verified, unpublished Shopify article per request."""

from __future__ import annotations

import hashlib
import json
import re
import socket
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Protocol


MARKER_NAMESPACE = "orin_control"
MARKER_KEY = "idempotency_key"
MARKER_TYPE = "single_line_text_field"
MARKER_PREFIX = "orin-v1:"
_GRAPHQL_ID = re.compile(r"^gid://shopify/Article/([0-9]+)$")


FIND_MARKED_DRAFTS = """
query FindOrinDrafts($blogId: ID!, $after: String) {
  blog(id: $blogId) {
    articles(first: 100, after: $after) {
      nodes {
        id
        handle
        title
        body
        publishedAt
        metafield(namespace: "orin_control", key: "idempotency_key") {
          value
        }
      }
      pageInfo {
        hasNextPage
        endCursor
      }
    }
  }
}
""".strip()


CREATE_HIDDEN_DRAFT = """
mutation CreateOrinHiddenDraft($article: ArticleCreateInput!) {
  articleCreate(article: $article) {
    article {
      id
      handle
      title
      body
      publishedAt
      metafield(namespace: "orin_control", key: "idempotency_key") {
        value
      }
    }
    userErrors {
      field
      message
      code
    }
  }
}
""".strip()


VERIFY_HIDDEN_DRAFT = """
query VerifyOrinHiddenDraft($id: ID!) {
  article(id: $id) {
    id
    handle
    title
    body
    publishedAt
    metafield(namespace: "orin_control", key: "idempotency_key") {
      value
    }
  }
}
""".strip()


class ShopifyRequestError(RuntimeError):
    """Shopify could not provide an authoritative GraphQL response."""


class DraftReconciliationError(RuntimeError):
    """A hidden draft cannot be created or reconciled safely."""

    def __init__(self, message: str, *, article_id: str | None = None) -> None:
        super().__init__(message)
        self.article_id = article_id


class GraphQLTransport(Protocol):
    def execute(self, document: str, variables: dict[str, Any]) -> dict[str, Any]: ...


@dataclass(frozen=True)
class DraftSpec:
    blog_id: str
    title: str
    body_html: str
    handle: str
    author_name: str
    idempotency_key: str


@dataclass(frozen=True)
class DraftResult:
    article_id: str
    numeric_article_id: int
    handle: str
    create_count: int
    reconciliation_status: str
    shopify_write_state: str
    idempotency_marker: str
    body_sha256: str


def idempotency_marker(value: str) -> str:
    """Return the exact marker shared by Shopify and the durable database."""
    if not value or len(value) > 220 or any(character.isspace() for character in value):
        raise ValueError("idempotency key must be 1-220 non-whitespace characters")
    return f"{MARKER_PREFIX}{value}"


class GraphQLHTTPTransport:
    """Small authenticated Shopify Admin GraphQL transport."""

    def __init__(
        self,
        *,
        store_domain: str,
        access_token: str,
        api_version: str,
        timeout_seconds: float = 30,
    ) -> None:
        if not store_domain or "/" in store_domain:
            raise ValueError("store_domain must be a Shopify hostname")
        if not access_token:
            raise ValueError("Shopify access token is required")
        if not re.fullmatch(r"[0-9]{4}-[0-9]{2}", api_version):
            raise ValueError("Shopify API version must use YYYY-MM")
        self.url = f"https://{store_domain}/admin/api/{api_version}/graphql.json"
        self.access_token = access_token
        self.timeout_seconds = timeout_seconds

    def execute(self, document: str, variables: dict[str, Any]) -> dict[str, Any]:
        request = urllib.request.Request(
            self.url,
            data=json.dumps({"query": document, "variables": variables}).encode("utf-8"),
            headers={
                "X-Shopify-Access-Token": self.access_token,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            body = error.read().decode("utf-8", errors="replace")
            raise ShopifyRequestError(f"Shopify HTTP {error.code}: {body[:500]}") from error
        except (urllib.error.URLError, TimeoutError, socket.timeout, OSError) as error:
            raise ShopifyRequestError(f"Shopify request did not complete authoritatively: {error}") from error
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise ShopifyRequestError("Shopify returned an invalid JSON response") from error

        if not isinstance(payload, dict):
            raise ShopifyRequestError("Shopify returned a non-object response")
        if payload.get("errors"):
            raise ShopifyRequestError(f"Shopify GraphQL errors: {payload['errors']}")
        data = payload.get("data")
        if not isinstance(data, dict):
            raise ShopifyRequestError("Shopify response is missing GraphQL data")
        return data


class HiddenDraftGateway:
    """Find-before-create boundary with post-write draft verification."""

    def __init__(self, transport: GraphQLTransport, *, maximum_pages: int = 100) -> None:
        if maximum_pages < 1:
            raise ValueError("maximum_pages must be positive")
        self.transport = transport
        self.maximum_pages = maximum_pages

    @staticmethod
    def _marker(article: dict[str, Any]) -> str | None:
        metafield = article.get("metafield")
        return metafield.get("value") if isinstance(metafield, dict) else None

    @staticmethod
    def _numeric_id(article_id: str) -> int:
        match = _GRAPHQL_ID.fullmatch(article_id)
        if match is None:
            raise DraftReconciliationError("Shopify returned an invalid article ID")
        return int(match.group(1))

    @staticmethod
    def _verified_result(
        article: dict[str, Any],
        *,
        spec: DraftSpec,
        marker: str,
        create_count: int,
        reconciliation_status: str,
        shopify_write_state: str,
    ) -> DraftResult:
        article_id = article.get("id")
        if not isinstance(article_id, str):
            raise DraftReconciliationError("Shopify article is missing its ID")
        if article.get("publishedAt") is not None:
            raise DraftReconciliationError(
                "Shopify article is published or scheduled; manual review required",
                article_id=article_id,
            )
        if article.get("handle") != spec.handle:
            raise DraftReconciliationError(
                "Shopify marker belongs to a different article handle",
                article_id=article_id,
            )
        if HiddenDraftGateway._marker(article) != marker:
            raise DraftReconciliationError(
                "Shopify article is missing the expected idempotency marker",
                article_id=article_id,
            )
        if article.get("title") != spec.title:
            raise DraftReconciliationError(
                "Shopify article title differs from the approved review draft",
                article_id=article_id,
            )
        body = article.get("body")
        if not isinstance(body, str):
            raise DraftReconciliationError(
                "Shopify article is missing its body for exact verification",
                article_id=article_id,
            )
        body_sha256 = hashlib.sha256(body.encode("utf-8")).hexdigest()
        approved_sha256 = hashlib.sha256(spec.body_html.encode("utf-8")).hexdigest()
        if body_sha256 != approved_sha256:
            raise DraftReconciliationError(
                "Shopify article body differs from the approved review draft",
                article_id=article_id,
            )
        return DraftResult(
            article_id=article_id,
            numeric_article_id=HiddenDraftGateway._numeric_id(article_id),
            handle=spec.handle,
            create_count=create_count,
            reconciliation_status=reconciliation_status,
            shopify_write_state=shopify_write_state,
            idempotency_marker=marker,
            body_sha256=body_sha256,
        )

    def _find(self, *, blog_id: str, marker: str) -> list[dict[str, Any]]:
        matches: list[dict[str, Any]] = []
        after: str | None = None
        seen_cursors: set[str] = set()
        for _ in range(self.maximum_pages):
            data = self.transport.execute(
                FIND_MARKED_DRAFTS,
                {"blogId": blog_id, "after": after},
            )
            blog = data.get("blog")
            if not isinstance(blog, dict):
                raise DraftReconciliationError("configured Shopify blog was not found")
            connection = blog.get("articles")
            if not isinstance(connection, dict):
                raise DraftReconciliationError("Shopify article connection is missing")
            nodes = connection.get("nodes")
            if not isinstance(nodes, list) or not all(isinstance(node, dict) for node in nodes):
                raise DraftReconciliationError("Shopify article list is invalid")
            matches.extend(node for node in nodes if self._marker(node) == marker)

            page_info = connection.get("pageInfo")
            if not isinstance(page_info, dict):
                raise DraftReconciliationError("Shopify pagination metadata is missing")
            if not page_info.get("hasNextPage"):
                return matches
            cursor = page_info.get("endCursor")
            if not isinstance(cursor, str) or not cursor or cursor in seen_cursors:
                raise DraftReconciliationError("Shopify pagination did not advance safely")
            seen_cursors.add(cursor)
            after = cursor
        raise DraftReconciliationError("Shopify reconciliation scan exceeded its safe page limit")

    def _reconcile(self, spec: DraftSpec, marker: str) -> DraftResult | None:
        matches = self._find(blog_id=spec.blog_id, marker=marker)
        if len(matches) > 1:
            raise DraftReconciliationError("multiple Shopify articles share the idempotency marker")
        if not matches:
            return None
        return self._verified_result(
            matches[0],
            spec=spec,
            marker=marker,
            # This is a request-level observed article count, not the number of
            # mutation calls made by this process. A marker-owned article means
            # exactly one durable Shopify article exists for this request.
            create_count=1,
            reconciliation_status="reconciled",
            shopify_write_state="article_observed",
        )

    def ensure(self, spec: DraftSpec) -> DraftResult:
        marker = idempotency_marker(spec.idempotency_key)
        existing = self._reconcile(spec, marker)
        if existing is not None:
            return existing

        variables = {
            "article": {
                "author": {"name": spec.author_name},
                "blogId": spec.blog_id,
                "title": spec.title,
                "body": spec.body_html,
                "handle": spec.handle,
                "isPublished": False,
                "metafields": [
                    {
                        "namespace": MARKER_NAMESPACE,
                        "key": MARKER_KEY,
                        "type": MARKER_TYPE,
                        "value": marker,
                    }
                ],
            }
        }
        try:
            data = self.transport.execute(CREATE_HIDDEN_DRAFT, variables)
        except ShopifyRequestError:
            recovered = self._reconcile(spec, marker)
            if recovered is not None:
                return recovered
            raise

        payload = data.get("articleCreate")
        if not isinstance(payload, dict):
            raise DraftReconciliationError("Shopify create response is missing articleCreate")
        user_errors = payload.get("userErrors")
        if user_errors:
            raise DraftReconciliationError(f"Shopify rejected hidden draft creation: {user_errors}")
        article = payload.get("article")
        if not isinstance(article, dict) or not isinstance(article.get("id"), str):
            raise DraftReconciliationError("Shopify create response is missing the article")

        verified_data = self.transport.execute(VERIFY_HIDDEN_DRAFT, {"id": article["id"]})
        verified = verified_data.get("article")
        if not isinstance(verified, dict):
            raise DraftReconciliationError("created Shopify article could not be fetched for verification")
        return self._verified_result(
            verified,
            spec=spec,
            marker=marker,
            create_count=1,
            reconciliation_status="reconciled",
            shopify_write_state="article_observed",
        )
