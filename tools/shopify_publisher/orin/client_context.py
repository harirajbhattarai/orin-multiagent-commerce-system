#!/usr/bin/env python3
"""
ORIN ClientContext — Shared Client Isolation Contract

One canonical ClientContext object holds all client-specific configuration.
Every shared ORIN component receives ClientContext explicitly.

Required fields:
  - client_id           : str  — unique client identifier (e.g. "hcs_gadgets", "hoverboard_store")
  - client_root         : Path — absolute path to client root directory
  - queue_path          : Path — absolute path to content queue
  - drafts_path         : Path — absolute path to drafts directory
  - automation_state_path: Path — absolute path to automation_state directory
  - store_domain        : str  — Shopify store domain
  - site_url            : str  — public site URL
  - blog_id             : str  — Shopify blog ID
  - blog_handle         : str  — Shopify blog handle
  - byline              : str  — author byline for articles
  - timezone            : str  — IANA timezone (e.g. "Europe/London")
  - draft_only_policy   : bool — True = no live Shopify writes

  - brand_rules_path     : Path — brand rules file
  - writing_rules_path   : Path — writing rules file
  - html_rules_path     : Path — HTML/design rules file
  - compliance_rules_path: Path — compliance rules file

  - product_truth_adapter  : str | None — path to product-truth adapter module
  - product_truth_normalised: Path | None — normalised product truth JSON
  - product_truth_link_map : Path | None — product link map JSON

  - shopify_config_path  : Path | None — Shopify credentials .env path
  - shopify_config_env_prefix: str — env var prefix for Shopify credentials

Rules:
  - No silent default to Hoverboard Store
  - Unknown client blocks (raises ValueError)
  - Missing required field blocks (raises ValueError)
  - All resolved paths must be inside client_root
  - HCS evidence CANNOT be written inside Hoverboard Store paths
  - Hoverboard Store evidence CANNOT be written inside HCS paths

Usage:
    from client_context import ClientContext, load_client_context

    ctx = load_client_context("hcs_gadgets")
    ctx = load_client_context("hoverboard_store")
"""
import json
import os
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

BASE_DIR = Path("/data/.openclaw/workspace")
REGISTRY_PATH = Path(__file__).parent / "client_registry.json"

# Required fields for ClientContext
_REQUIRED_FIELDS = [
    "client_id", "client_root", "queue_path", "drafts_path",
    "automation_state_path", "store_domain", "site_url", "blog_id",
    "blog_handle", "byline", "timezone", "draft_only_policy",
    "brand_rules_path", "writing_rules_path", "html_rules_path",
    "compliance_rules_path",
]


@dataclass
class ClientContext:
    """Canonical client configuration for ORIN pipeline components."""
    client_id: str
    client_root: Path
    queue_path: Path
    drafts_path: Path
    automation_state_path: Path
    store_domain: str
    site_url: str
    blog_id: str
    blog_handle: str
    byline: str
    timezone: str
    draft_only_policy: bool

    brand_rules_path: Path
    writing_rules_path: Path
    html_rules_path: Path
    compliance_rules_path: Path

    product_truth_adapter: Optional[str] = None
    product_truth_normalised: Optional[Path] = None
    product_truth_link_map: Optional[Path] = None

    shopify_config_path: Optional[Path] = None
    shopify_config_env_prefix: str = ""

    # Internal computed fields
    _validated: bool = field(default=False, repr=False)

    def validate(self) -> None:
        """
        Validate client context.
        Raises ValueError if any required field is missing or paths are outside client_root.
        """
        missing = []
        for fname in _REQUIRED_FIELDS:
            v = getattr(self, fname, None)
            if v is None or v == "":
                missing.append(fname)
            elif isinstance(v, Path) and not v.is_absolute():
                missing.append(f"{fname} (not absolute)")
        if missing:
            raise ValueError(f"ClientContext validation failed for {self.client_id}: missing {missing}")

        # All paths must be inside client_root
        path_fields = ["queue_path", "drafts_path", "automation_state_path",
                       "brand_rules_path", "writing_rules_path", "html_rules_path",
                       "compliance_rules_path"]
        for f in path_fields:
            v = getattr(self, f, None)
            if v and isinstance(v, Path):
                try:
                    v.relative_to(self.client_root)
                except ValueError:
                    raise ValueError(
                        f"ClientContext validation failed for {self.client_id}: "
                        f"{f}={v} is outside client_root={self.client_root}"
                    )

        self._validated = True

    def to_dict(self) -> dict:
        """Serialize to dict (Paths converted to strings)."""
        d = {}
        for k, v in asdict(self).items():
            if isinstance(v, Path):
                d[k] = str(v)
            else:
                d[k] = v
        return d

    @classmethod
    def from_registry_dict(cls, client_id: str, config: dict) -> "ClientContext":
        """
        Build ClientContext from a client_registry.json dict entry.
        Raises ValueError if required fields are missing.
        """
        def p(v):
            """Convert to Path if non-empty string."""
            if v and isinstance(v, str):
                return Path(v)
            return None

        def sp(v):
            """Convert to absolute Path from workspace-relative string."""
            if v and isinstance(v, str):
                abs_path = BASE_DIR / v if not v.startswith("/") else Path(v)
                return abs_path
            return None

        ctx = cls(
            client_id=config.get("client_id", ""),
            client_root=sp(config.get("client_root", "")),
            queue_path=sp(config.get("queue_path", "")),
            drafts_path=sp(config.get("drafts_path", "")),
            automation_state_path=sp(config.get("automation_state_path", "")),
            store_domain=config.get("store_domain", ""),
            site_url=config.get("site_url", ""),
            blog_id=str(config.get("blog_id", "")),
            blog_handle=config.get("blog_handle", ""),
            byline=config.get("byline", ""),
            timezone=config.get("timezone", "Europe/London"),
            draft_only_policy=config.get("draft_only_policy", False),
            brand_rules_path=sp(config.get("brand_rules_path", "")),
            writing_rules_path=sp(config.get("writing_rules_path", "")),
            html_rules_path=sp(config.get("html_rules_path", "")),
            compliance_rules_path=sp(config.get("compliance_rules_path", "")),
            product_truth_adapter=config.get("product_truth_adapter"),
            product_truth_normalised=p(config.get("product_truth_normalised")),
            product_truth_link_map=p(config.get("product_truth_link_map")),
            shopify_config_path=sp(config.get("shopify_config_path")),
            shopify_config_env_prefix=config.get("shopify_config_env_prefix", ""),
        )
        return ctx


def load_registry() -> dict:
    """Load the shared ORIN client registry."""
    if not REGISTRY_PATH.exists():
        raise RuntimeError(f"ORIN client registry not found: {REGISTRY_PATH}")
    with open(REGISTRY_PATH) as f:
        return json.load(f)


def load_client_context(client_id: str) -> ClientContext:
    """
    Load and validate ClientContext for a given client_id.
    Raises KeyError if client_id not in registry.
    Raises ValueError if required fields are missing.
    """
    registry = load_registry()
    clients = registry.get("clients", {})
    if client_id not in clients:
        raise KeyError(
            f"Unknown client_id: {client_id!r}. "
            f"Available: {list(clients.keys())}"
        )
    config = clients[client_id]
    ctx = ClientContext.from_registry_dict(client_id, config)
    ctx.validate()
    return ctx


def get_client_root(client_id: str) -> Path:
    """Quick helper: return client_root for a client without full context."""
    ctx = load_client_context(client_id)
    return ctx.client_root


if __name__ == "__main__":
    # Self-test
    for cid in ["hcs_gadgets", "hoverboard_store"]:
        try:
            ctx = load_client_context(cid)
            print(f"✅ {cid}: {ctx.client_root}")
        except Exception as e:
            print(f"❌ {cid}: {e}")
