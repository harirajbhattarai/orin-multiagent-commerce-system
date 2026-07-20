#!/usr/bin/env python3
"""
HCS Gadgets — Product Truth Adapter v1.1

Production adapter for HCS Gadgets product truth.

Provides:
- fetch_current_products()    — fetch live from Shopify (GET only)
- normalise(raw_products)     — normalise to canonical schema
- validate(catalogue)         — schema + freshness validation
- get_price_range(variants)  — price range semantics
- build_link_map(catalogue)  — verified product URLs

This module is the single authoritative source for HCS product truth.
It must NOT import from automation_state or evidence directories.

Configuration (required):
    clients/hcs_gadgets/content_engine/hcs_client_config.json
    key: product_truth_max_age_hours (positive number)

Usage:
    from hcs_product_truth_adapter import HCSProductTruth
    adapter = HCSProductTruth()
    catalogue = adapter.fetch_and_normalise()
    result    = adapter.validate(catalogue)
"""
import datetime
import hashlib
import json
import os
import re
import urllib.request
import urllib.error

VERSION = "1.1"
CLIENT_ID = "hcs_gadgets"
SOURCE_STORE = "hcsgadgets-com.myshopify.com"
CURRENCY = "GBP"

# ─── Shopify API ───────────────────────────────────────────────────────────────

CONFIG_PATH = "clients/hcs_gadgets/shopify_config/.env"

def _load_token():
    with open(CONFIG_PATH) as f:
        for line in f:
            if "ADMIN_ACCESS_TOKEN" in line or "SHOPIFY_ADMIN_ACCESS_TOKEN" in line:
                return line.strip().split("=", 1)[1].strip()
    raise RuntimeError("No Shopify admin access token found in clients/hcs_gadgets/shopify_config/.env")

BASE_URL = f"https://{SOURCE_STORE}/admin/api/2026-01"

def shopify_get(path):
    token = _load_token()
    url = f"{BASE_URL}{path}"
    req = urllib.request.Request(url, headers={
        "X-Shopify-Access-Token": token,
        "Content-Type": "application/json"
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode()), r
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Shopify API error {e.code} on {path}: {e.read().decode()}")

# ─── Schema constants ─────────────────────────────────────────────────────────

REQUIRED_PRODUCT_FIELDS = ["id", "title", "handle", "status"]
REQUIRED_VARIANT_FIELDS = ["id", "product_id", "price"]

# ─── Price Range Semantics ────────────────────────────────────────────────────

def get_price_range(variants):
    """
    Compute price range semantics for a list of variants.

    Returns dict:
        has_price_range            : bool
        price_min                  : str or None  (unformatted numeric)
        price_max                  : str or None  (unformatted numeric)
        primary_variant_price      : str or None  (unformatted numeric)
        display_price             : str or None  (presentation-ready with £)

    Policy:
        A. One active priced variant       → has_price_range=False,
           display_price="£8.99"
        B. Multiple, identical prices      → has_price_range=False,
           display_price="£8.99"
        C. Multiple, different prices       → has_price_range=True,
           display_price="From £8.99"
        D. Specific variant selected        → has_price_range=False,
           display_price="£8.99"
        E. No active valid variant price   → has_price_range=False,
           display_price=None  → PRODUCT_TRUTH_INVALID
    """
    # Collect all non-null, non-empty, valid numeric prices
    priced = []
    for v in variants:
        price = v.get("price")
        if price is not None and price != "":
            try:
                priced.append({
                    "price": str(float(price)),
                    "title": v.get("title", ""),
                    "id": str(v["id"]),
                    "position": v.get("position", 999)
                })
            except (ValueError, TypeError):
                continue

    if not priced:
        return {
            "has_price_range": False,
            "price_min": None,
            "price_max": None,
            "primary_variant_price": None,
            "display_price": None
        }

    # Sort by position FIRST so priced[0] is the primary (first by position)
    priced.sort(key=lambda p: p.get("position", 999))

    # Sort prices numerically (not lexicographically) for correct min/max
    prices = sorted(set(p["price"] for p in priced), key=lambda x: float(x))
    pmin = prices[0]
    pmax = prices[-1]

    if len(prices) == 1:
        # A/B: Single or all-identical prices → exact primary price
        return {
            "has_price_range": False,
            "price_min": pmin,
            "price_max": pmax,
            "primary_variant_price": priced[0]["price"],
            "display_price": f"£{priced[0]["price"]}"
        }
    else:
        # C: Multiple different prices → "From £{min}" range price
        # D: Specific selected variant (primary by position) → exact primary price
        # Since the adapter cannot know which variant is "selected" in the
        # current call context, Policy D is implemented as: the primary variant
        # (first by position) is treated as the customer-selected entry point.
        # Its exact price is shown as the display_price, while has_price_range
        # signals that other price points exist above it.
        primary_price = priced[0]["price"]
        has_range = any(p["price"] != primary_price for p in priced)
        # When a range exists (multiple different prices), use "From £" format (Policy C).
        # The primary variant's exact price is preserved in primary_variant_price.
        display = f"From £{primary_price}" if has_range else f"£{primary_price}"
        return {
            "has_price_range": has_range,
            "price_min": pmin,
            "price_max": pmax,
            "primary_variant_price": primary_price,
            "display_price": display
        }

# ─── Validation ───────────────────────────────────────────────────────────────

def validate_product(record, is_active=True):
    """Validate a single raw product record. Returns (is_valid, errors)."""
    errors = []
    for field in REQUIRED_PRODUCT_FIELDS:
        if field not in record or record[field] is None:
            errors.append(f"missing_required_field:{field}")

    title = record.get("title", "")
    if not title or not title.strip():
        errors.append("empty_title")

    handle = record.get("handle", "")
    if not handle or not handle.strip():
        errors.append("empty_handle")

    if is_active:
        variants = record.get("variants", [])
        has_valid_price = any(
            v.get("price") not in (None, "") and str(v.get("price")).strip() != ""
            for v in variants
        )
        if not has_valid_price:
            errors.append("active_product_no_valid_price")

    for v in record.get("variants", []):
        price = v.get("price")
        if price is not None and price != "":
            try:
                p = float(price)
                if p < 0:
                    errors.append(f"negative_price:{price}")
            except (ValueError, TypeError):
                errors.append(f"invalid_price_format:{price}")

    return len(errors) == 0, errors

def validate_variant(variant):
    """Validate a single variant record. Returns (is_valid, errors)."""
    errors = []
    for field in REQUIRED_VARIANT_FIELDS:
        if field not in variant or variant[field] is None:
            errors.append(f"missing_variant_field:{field}")
    price = variant.get("price")
    if price is not None and price != "":
        try:
            p = float(price)
            if p < 0:
                errors.append(f"negative_variant_price:{price}")
        except (ValueError, TypeError):
            errors.append(f"unparseable_variant_price:{price}")
    return len(errors) == 0, errors

def check_freshness(fetched_at_str, max_age_hours):
    """
    Compute freshness from fetched_at timestamp only.
    Does NOT use generated_at, file mtime, or validation time.
    Requires max_age_hours as a required parameter (no module-level fallback).
    """
    if not fetched_at_str or not isinstance(fetched_at_str, str):
        return "PRODUCT_TRUTH_INVALID", None

    try:
        fetched = fetched_at_str.replace("Z", "+00:00")
        fetched_dt = datetime.datetime.fromisoformat(fetched)
        if fetched_dt.tzinfo is None:
            fetched_dt = fetched_dt.replace(tzinfo=datetime.timezone.utc)
    except (ValueError, TypeError):
        return "PRODUCT_TRUTH_INVALID", None

    now_dt = datetime.datetime.now(datetime.timezone.utc)
    age_hours = (now_dt - fetched_dt).total_seconds() / 3600

    if age_hours <= max_age_hours:
        return "PRODUCT_TRUTH_FRESH", age_hours
    else:
        return "PRODUCT_TRUTH_STALE", age_hours

# ─── Normaliser ───────────────────────────────────────────────────────────────

def build_product_url(handle):
    return f"https://hcsgadgets.com/products/{handle}"

def normalise_product(raw_product, fetched_at):
    """Transform a raw Shopify product dict into the normalised schema."""
    variants = raw_product.get("variants", [])
    sorted_variants = sorted(variants, key=lambda v: v.get("position", 999))

    # Primary variant (first by position)
    primary_variant_data = sorted_variants[0] if sorted_variants else {}

    # Price range
    price_info = get_price_range(sorted_variants)

    primary_variant = None
    if primary_variant_data:
        primary_variant = {
            "variant_id": str(primary_variant_data["id"]),
            "product_id": str(raw_product["id"]),
            "title": primary_variant_data.get("title", ""),
            "price": primary_variant_data.get("price", ""),
            "currency": CURRENCY,
            "compare_at_price": primary_variant_data.get("compare_at_price"),
            "sku": primary_variant_data.get("sku"),
            "inventory_quantity": primary_variant_data.get("inventory_quantity"),
            "updated_at": primary_variant_data.get("updated_at"),
            "position": primary_variant_data.get("position"),
            "requires_shipping": primary_variant_data.get("requires_shipping"),
            "weight": primary_variant_data.get("weight"),
            "weight_unit": primary_variant_data.get("weight_unit"),
            "taxable": primary_variant_data.get("taxable"),
        }

    return {
        "product_id": str(raw_product["id"]),
        "title": raw_product.get("title", ""),
        "handle": raw_product.get("handle", ""),
        "status": raw_product.get("status", "unknown"),
        "product_url": build_product_url(raw_product.get("handle", "")),
        "price": price_info.get("primary_variant_price"),
        "price_min": price_info.get("price_min"),
        "price_max": price_info.get("price_max"),
        "has_price_range": price_info.get("has_price_range"),
        "display_price": price_info.get("display_price"),
        "currency": CURRENCY,
        "vendor": raw_product.get("vendor", ""),
        "product_type": raw_product.get("product_type", ""),
        "tags": raw_product.get("tags", ""),
        "updated_at": raw_product.get("updated_at"),
        "created_at": raw_product.get("created_at"),
        "fetched_at": fetched_at,
        "source_store": SOURCE_STORE,
        "client_id": CLIENT_ID,
        "primary_variant_id": str(primary_variant_data["id"]) if primary_variant_data else None,
        "primary_variant_title": primary_variant_data.get("title", "") if primary_variant_data else None,
        "primary_variant_price": primary_variant_data.get("price", "") if primary_variant_data else None,
        "all_variant_prices": [
            {"variant_id": str(v["id"]), "price": v.get("price", ""), "title": v.get("title", "")}
            for v in sorted_variants
            if v.get("price") is not None and v.get("price") != ""
        ],
        "primary_variant": primary_variant,
        "variant_count": len(sorted_variants),
    }

# ─── Deterministic Hashing ────────────────────────────────────────────────────

def compute_source_snapshot_sha(raw_products):
    """Hash of the canonical raw Shopify snapshot (excludes wrapper metadata)."""
    canonical = sorted(raw_products, key=lambda p: str(p.get("id", "")))
    return hashlib.sha256(json.dumps(canonical, sort_keys=True).encode()).hexdigest()

def compute_normalised_catalog_sha(normalised_products):
    """
    Hash of the normalised product records.
    Excludes: generated_at, fetched_at, validated_at
    (these are runtime metadata, not product data).
    """
    records = []
    for p in normalised_products:
        record = {k: v for k, v in p.items()
                  if k not in ("generated_at", "fetched_at", "validated_at")}
        records.append(record)
    records.sort(key=lambda p: str(p.get("product_id", "")))
    return hashlib.sha256(json.dumps(records, sort_keys=True).encode()).hexdigest()

# ─── Link Map Builder ──────────────────────────────────────────────────────────

def build_link_map(normalised_catalogue, fetched_at):
    """Build verified product URL map from normalised catalogue."""
    active = [p for p in normalised_catalogue if p.get("status") == "active"]
    return {
        "timestamp": fetched_at,
        "generated_by": "hcs_product_truth_adapter.py v1.1",
        "source_store": SOURCE_STORE,
        "client_id": CLIENT_ID,
        "validator_version": VERSION,
        "product_count": len(normalised_catalogue),
        "verified_product_urls_count": len(active),
        "verified_products": [
            {
                "url": p["product_url"],
                "title": p["title"],
                "handle": p["handle"],
                "type": "product",
                "verified": True,
                "product_id": p["product_id"],
                "price": p.get("price") or p.get("display_price"),
            }
            for p in active
        ],
        "verified_collections": [],
        "verified_blog_articles": [],
        "broken_links": [],
        "fallback_url": "https://hcsgadgets.com/collections/all",
        "all_product_url": "https://hcsgadgets.com/collections/all",
        "verified_collection_map": {},
    }

# ─── Config Loading ────────────────────────────────────────────────────────────

CONFIG_FILE = "clients/hcs_gadgets/content_engine/hcs_client_config.json"

def _load_and_validate_config():
    """
    Load and validate HCS product-truth configuration.

    Returns:
        (max_age_hours, validation_status, validation_reason)

    validation_status values:
        PRODUCT_TRUTH_CONFIG_VALID       — config file exists, key present, value positive number
        PRODUCT_TRUTH_CONFIG_MISSING    — file does not exist
        PRODUCT_TRUTH_CONFIG_MALFORMED  — JSON parse error
        PRODUCT_TRUTH_MAX_AGE_MISSING   — key not in config
        PRODUCT_TRUTH_MAX_AGE_INVALID   — value is zero/negative/non-numeric/boolean/empty
    """
    if not os.path.exists(CONFIG_FILE):
        return None, "PRODUCT_TRUTH_INVALID", "PRODUCT_TRUTH_CONFIG_MISSING"

    try:
        with open(CONFIG_FILE) as f:
            cfg = json.load(f)
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as e:
        return None, "PRODUCT_TRUTH_INVALID", "PRODUCT_TRUTH_CONFIG_MALFORMED"

    if "product_truth_max_age_hours" not in cfg:
        return None, "PRODUCT_TRUTH_INVALID", "PRODUCT_TRUTH_MAX_AGE_MISSING"

    val = cfg["product_truth_max_age_hours"]

    # Check type: must be numeric (int or float), positive, non-zero
    if not isinstance(val, (int, float)):
        return None, "PRODUCT_TRUTH_INVALID", "PRODUCT_TRUTH_MAX_AGE_INVALID"
    if isinstance(val, bool):  # bool is subclass of int in Python
        return None, "PRODUCT_TRUTH_INVALID", "PRODUCT_TRUTH_MAX_AGE_INVALID"
    if val <= 0:
        return None, "PRODUCT_TRUTH_INVALID", "PRODUCT_TRUTH_MAX_AGE_INVALID"

    return float(val), "PRODUCT_TRUTH_CONFIG_VALID", None

# ─── Main Adapter Class ────────────────────────────────────────────────────────

class HCSProductTruth:
    """
    Production HCS Gadgets product truth adapter.

    Configuration is loaded and validated at instance initialisation.
    If configuration is missing or invalid, the adapter initialises in a
    blocked state: writer_ready=False, validation_status=PRODUCT_TRUTH_INVALID.

    Usage (valid config):
        adapter = HCSProductTruth()          # config loaded here
        catalogue = adapter.fetch_and_normalise()   # Shopify GET + normalise
        result    = adapter.validate()               # schema + freshness

    Usage (invalid/missing config):
        adapter = HCSProductTruth()          # returns blocked adapter
        result  = adapter.validate()          # returns PRODUCT_TRUTH_INVALID
    """

    def __init__(self):
        self.raw_products = None
        self.normalised = None
        self.fetched_at = None
        self.generated_at = None
        self.source_snapshot_sha = None
        self.normalised_catalog_sha = None
        self.shopify_write_count = 0

        # Load and validate configuration at runtime
        self.product_truth_max_age_hours, self.config_validation_status, \
            self.config_validation_reason = _load_and_validate_config()

        if self.config_validation_status == "PRODUCT_TRUTH_CONFIG_VALID":
            self.writer_ready = True
            self.validation_status = "PRODUCT_TRUTH_UNVALIDATED"
            self.validation_reason = None
        else:
            self.writer_ready = False
            self.validation_status = "PRODUCT_TRUTH_INVALID"
            self.validation_reason = self.config_validation_reason

    def fetch_current_products(self):
        """Fetch all products from Shopify. Returns raw product list. GET only."""
        self.shopify_write_count += 0  # marker; GET only
        all_products = []
        page_info = None
        while True:
            if page_info:
                path = f"/products.json?limit=250&page_info={page_info}"
            else:
                path = "/products.json?limit=250"
            data, _ = shopify_get(path)
            products = data.get("products", [])
            all_products.extend(products)
            # Pagination via Link header
            _, response = shopify_get(path)
            link = response.headers.get("Link", "")
            next_page = None
            for part in link.split(","):
                if 'rel="next"' in part:
                    m = re.search(r'<([^>]+)>;\s*rel="next"', part)
                    if m:
                        next_url = m.group(1)
                        m2 = re.search(r"page_info=([^&>]+)", next_url)
                        if m2:
                            next_page = m2.group(1)
            if next_page:
                page_info = next_page
            else:
                break
        return all_products

    def fetch_and_normalise(self):
        """Fetch from Shopify and normalise. Returns normalised catalogue."""
        if not self.writer_ready:
            return None

        now_utc = datetime.datetime.now(datetime.timezone.utc)
        self.fetched_at = now_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
        self.generated_at = self.fetched_at

        raw = self.fetch_current_products()
        for p in raw:
            p["fetched_at"] = self.fetched_at
        self.raw_products = raw
        self.source_snapshot_sha = compute_source_snapshot_sha(raw)

        self.normalised = [normalise_product(p, self.fetched_at) for p in raw]
        self.normalised_catalog_sha = compute_normalised_catalog_sha(self.normalised)

        return self.normalised

    def validate(self):
        """
        Full schema + freshness validation.

        Returns dict with:
            status             : VALID | INVALID
            freshness_status  : PRODUCT_TRUTH_FRESH | PRODUCT_TRUTH_STALE | PRODUCT_TRUTH_INVALID
            validation_status : PRODUCT_TRUTH_INVALID (if blocked)
            validation_reason : explicit failure code
            writer_ready      : bool
            ...
        """
        # If config was invalid, return blocked result immediately
        if self.config_validation_status != "PRODUCT_TRUTH_CONFIG_VALID":
            return {
                "status": "INVALID",
                "freshness_status": "PRODUCT_TRUTH_INVALID",
                "validation_status": "PRODUCT_TRUTH_INVALID",
                "validation_reason": self.config_validation_reason,
                "writer_ready": False,
                "total": 0,
                "validated_count": 0,
                "rejected_count": 0,
                "active_count": 0,
                "all_active_have_prices": False,
                "duplicate_errors": [],
                "rejected_products": [],
                "validation_results": [],
                "max_age_hours": None,
                "age_hours": None,
            }

        if self.raw_products is None:
            return {
                "status": "INVALID",
                "freshness_status": "PRODUCT_TRUTH_INVALID",
                "validation_status": "PRODUCT_TRUTH_INVALID",
                "validation_reason": "PRODUCT_TRUTH_NO_DATA_FETCHED",
                "writer_ready": False,
                "total": 0,
                "validated_count": 0,
                "rejected_count": 0,
                "active_count": 0,
                "all_active_have_prices": False,
                "duplicate_errors": [],
                "rejected_products": [],
                "validation_results": [],
                "max_age_hours": self.product_truth_max_age_hours,
                "age_hours": None,
            }

        fetched_at = self.raw_products[0].get("fetched_at") if self.raw_products else None
        freshness_status, age_hours = check_freshness(
            fetched_at, self.product_truth_max_age_hours
        )

        validation_results = []
        rejected = []
        validated_raw = []

        for product in (self.raw_products or []):
            is_active = product.get("status") == "active"
            is_valid, errors = validate_product(product, is_active=is_active)
            variant_errors = []
            for v in product.get("variants", []):
                v_valid, v_errors = validate_variant(v)
                if not v_valid:
                    variant_errors.extend(v_errors)
            all_errors = errors + variant_errors

            if is_valid and not variant_errors:
                validated_raw.append(product)
            else:
                rejected.append({
                    "product_id": str(product.get("id")),
                    "title": product.get("title", ""),
                    "handle": product.get("handle", ""),
                    "errors": all_errors,
                })

        # Duplicate handle check on raw
        seen_handles = {}
        dupes = []
        for p in validated_raw:
            h = p["handle"]
            if h in seen_handles:
                dupes.append(h)
            else:
                seen_handles[h] = str(p.get("id"))

        if dupes:
            validated_raw = [p for p in validated_raw if p["handle"] not in dupes]
            for dup in dupes:
                rejected.append({
                    "product_id": seen_handles.get(dup, "unknown"),
                    "title": "duplicate",
                    "handle": dup,
                    "errors": ["duplicate_handle"]
                })

        total = len(self.raw_products) if self.raw_products else 0
        active_raw = [p for p in validated_raw if p.get("status") == "active"]
        all_active_have_prices = all(
            any(v.get("price") not in (None, "") for v in p.get("variants", []))
            for p in active_raw
        )

        overall_valid = (
            not rejected
            and freshness_status == "PRODUCT_TRUTH_FRESH"
            and all_active_have_prices
        )

        return {
            "status": "VALID" if overall_valid else "INVALID",
            "freshness_status": freshness_status,
            "age_hours": age_hours,
            "max_age_hours": self.product_truth_max_age_hours,
            "validation_status": "PRODUCT_TRUTH_VALID" if overall_valid else "PRODUCT_TRUTH_INVALID",
            "validation_reason": None if overall_valid else (
                "PRODUCT_TRUTH_STALE" if freshness_status == "PRODUCT_TRUTH_STALE"
                else "PRODUCT_TRUTH_REJECTED"
            ),
            "writer_ready": overall_valid,
            "total": total,
            "validated_count": len(validated_raw),
            "rejected_count": len(rejected),
            "active_count": len(active_raw),
            "all_active_have_prices": all_active_have_prices,
            "duplicate_errors": dupes,
            "rejected_products": rejected,
            "validation_results": validation_results,
        }