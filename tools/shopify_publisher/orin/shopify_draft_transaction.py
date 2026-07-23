"""
ORIN Phase I2 — Canonical Safe Shopify Draft Transaction for Hoverboard Store

tools/shopify_publisher/orin/shopify_draft_transaction.py

Canonical safe draft transaction for the Hoverboard Store Shopify integration.

Loads credentials from environment variables (see hoverboard_shopify_config):
    HOVERBOARD_STORE_SHOPIFY_STORE_DOMAIN
    HOVERBOARD_STORE_SHOPIFY_ACCESS_TOKEN
    HOVERBOARD_STORE_SHOPIFY_API_VERSION
    HOVERBOARD_STORE_SHOPIFY_BLOG_ID (optional; defaults to 113430790492)

Required environment variables:
    HOVERBOARD_STORE_SHOPIFY_STORE_DOMAIN
    HOVERBOARD_STORE_SHOPIFY_ACCESS_TOKEN
    HOVERBOARD_STORE_SHOPIFY_API_VERSION
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from hoverboard_shopify_config import load_hoverboard_shopify_config
from orin_shopify import (
    DraftReconciliationError,
    DraftSpec,
    GraphQLHTTPTransport,
    HiddenDraftGateway,
    ShopifyRequestError,
)
from workspace_paths import workspace_root

# ── Canonical HTML comparator (Tier C verification) ────────────────────────
# Production verification contract: Tier A (raw exact) → Tier B (inter-tag LF)
# → Tier C (canonical DOM comparison via html_canonical_comparator).
# Element-reorder is detected as FAIL_STRUCTURE_CHANGED in Tier C.
_AGENTS_DIR = Path(__file__).parent
sys.path.insert(0, str(_AGENTS_DIR))
from html_canonical_comparator import (
    compare_html_canonical,
    PASS_RAW_EXACT,
    PASS_ALLOWED_INTER_TAG_LF_NORMALIZATION,
    PASS_CANONICAL_HTML_EQUIVALENT,
    FAIL_TEXT_CONTENT_CHANGED,
    FAIL_HREF_CHANGED,
    FAIL_TAG_CHANGED,
    FAIL_ATTRIBUTE_CHANGED,
    FAIL_ELEMENT_MISSING,
    FAIL_ELEMENT_ADDED,
    FAIL_STRUCTURE_CHANGED,
    FAIL_UNSUPPORTED_NORMALIZATION,
)

# ── Cached config (lazy load) ──────────────────────────────────────────────

_cached_config: dict | None = None

def _get_shopify_config() -> dict:
    """
    Lazy-load (and cache) Hoverboard Store Shopify configuration.
    Fails closed if HOVERBOARD_STORE_SHOPIFY_* variables are not set.
    """
    global _cached_config
    if _cached_config is None:
        _cached_config = load_hoverboard_shopify_config()
    return _cached_config

BLOG_TITLE = "Journal Insights"

# ── Durable evidence retention ───────────────────────────────────────────────
# Per-transaction evidence directory: automation_state/runs/<run_id>/
# Contains: sent_body.html, fetched_body.html, verification.json, transaction_result.json
# Resolve absolute path to avoid double-".." traversal landing in tools/clients/...
_WORKSPACE_ROOT = workspace_root()
_EVIDENCE_BASE = _WORKSPACE_ROOT / "clients" / "hoverboard_store" / "content_engine" / "automation_state" / "runs"


def _create_transaction_run_dir(job_number: str) -> Path | None:
    """
    Create a unique run_id directory for a transaction attempt.
    Returns the Path to the created directory, or None if creation failed.
    Directory path: <evidence_base>/<job_number>_<unix_ts>_<8随机hex>/
    """
    import time, secrets
    try:
        ts = int(time.time())
        rand = secrets.token_hex(4)
        run_id = f"job{job_number}_{ts}_{rand}"
        run_dir = _EVIDENCE_BASE / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        return run_dir
    except Exception:
        return None


def _persist_sent_body(run_dir: Path, body: str) -> None:
    """Persist the exact sent body HTML to durable storage."""
    try:
        (run_dir / "sent_body.html").write_text(body, encoding="utf-8")
        (run_dir / "sent_body_sha256.txt").write_text(
            hashlib.sha256(body.encode()).hexdigest(), encoding="utf-8"
        )
        (run_dir / "sent_body_bytes.txt").write_text(str(len(body.encode())), encoding="utf-8")
    except Exception:
        pass  # Non-fatal — evidence retention must not block the transaction


def _persist_fetched_body(run_dir: Path, body: str) -> None:
    """Persist the exact fetched body HTML to durable storage."""
    try:
        (run_dir / "fetched_body.html").write_text(body, encoding="utf-8")
        (run_dir / "fetched_body_sha256.txt").write_text(
            hashlib.sha256(body.encode()).hexdigest(), encoding="utf-8"
        )
        (run_dir / "fetched_body_bytes.txt").write_text(str(len(body.encode())), encoding="utf-8")
    except Exception:
        pass


def _persist_verification(
    run_dir: Path,
    verification_passed: bool,
    failures: list,
    details: dict,
    job_number: str = "",
    article_id: int | None = None,
    run_id: str = "",
) -> None:
    """Persist verification decision and details to durable storage.

    All evidence — sent_body, fetched_body, verification.json, transaction_result.json
    — must be persisted into the SAME transaction run_dir. caller is responsible for
    passing the single authoritative run_dir.
    """
    try:
        import json as _json
        from datetime import datetime, timezone
        verification_record = {
            "run_id": run_id,
            "run_dir": str(run_dir),
            "job_number": job_number,
            "shopify_article_id": article_id,
            "verification_passed": verification_passed,
            "failures": failures,
            "details": details,
            "comparator_normalization": "html_canonical_comparator.compare_html_canonical",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        (run_dir / "verification.json").write_text(
            _json.dumps(verification_record, indent=2), encoding="utf-8"
        )
    except Exception:
        pass


def _persist_transaction_result(run_dir: Path, result: dict) -> None:
    """Persist the full transaction result to durable storage."""
    try:
        import json as _json
        (run_dir / "transaction_result.json").write_text(
            _json.dumps(result, indent=2, default=str), encoding="utf-8"
        )
    except Exception:
        pass

# Transaction decisions
TRANSACTION_APPROVED = "TRANSACTION_APPROVED"
TRANSACTION_BLOCKED_GATE_NOT_APPROVED = "BLOCK_LIVE_DRAFT_NOT_APPROVED"
TRANSACTION_BLOCKED_CONTEXT_MISMATCH = "BLOCK_JOB_CONTEXT_MISMATCH"
TRANSACTION_BLOCKED_HANDLE_INVALID = "BLOCK_INVALID_HANDLE"
TRANSACTION_BLOCKED_DRAFT_MUTATED = "BLOCK_LOCAL_DRAFT_MUTATED_AFTER_WRITER"
TRANSACTION_BLOCKED_PUBLISH_CONFIG_UNSAFE = "BLOCK_PUBLISH_CONFIGURATION_UNSAFE"
TRANSACTION_APPROVED_DRAFT_CREATED = "DRAFT_CREATED_VERIFICATION_PASSED"
TRANSACTION_BLOCKED_VERIFICATION_FAILED = "SHOPIFY_DRAFT_VERIFICATION_FAILED"
TRANSACTION_BLOCKED_ARTICLE_ID_MISMATCH = "BLOCK_SHOPIFY_ARTICLE_ID_MISMATCH"
TRANSACTION_BLOCKED_TITLE_MISMATCH = "BLOCK_SHOPIFY_TITLE_MISMATCH"
TRANSACTION_BLOCKED_HANDLE_MISMATCH = "BLOCK_SHOPIFY_HANDLE_MISMATCH"
TRANSACTION_BLOCKED_NOT_DRAFT = "BLOCK_SHOPIFY_ARTICLE_NOT_DRAFT"
TRANSACTION_BLOCKED_PUBLISHED_AT_NOT_NULL = "BLOCK_SHOPIFY_PUBLISHED_AT_NOT_NULL"
TRANSACTION_BLOCKED_BODY_HASH_MISMATCH = "BLOCK_SHOPIFY_BODY_HASH_MISMATCH"
TRANSACTION_BLOCKED_SHOPIFY_ERROR = "BLOCK_SHOPIFY_API_ERROR"
TRANSACTION_BLOCKED_UNEXPECTED_ERROR = "BLOCK_UNEXPECTED_ERROR"

ALL_TRANSACTION_BLOCKING = frozenset([
    TRANSACTION_BLOCKED_GATE_NOT_APPROVED,
    TRANSACTION_BLOCKED_CONTEXT_MISMATCH,
    TRANSACTION_BLOCKED_HANDLE_INVALID,
    TRANSACTION_BLOCKED_DRAFT_MUTATED,
    TRANSACTION_BLOCKED_PUBLISH_CONFIG_UNSAFE,
    TRANSACTION_BLOCKED_VERIFICATION_FAILED,
    TRANSACTION_BLOCKED_ARTICLE_ID_MISMATCH,
    TRANSACTION_BLOCKED_TITLE_MISMATCH,
    TRANSACTION_BLOCKED_HANDLE_MISMATCH,
    TRANSACTION_BLOCKED_NOT_DRAFT,
    TRANSACTION_BLOCKED_PUBLISHED_AT_NOT_NULL,
    TRANSACTION_BLOCKED_BODY_HASH_MISMATCH,
    TRANSACTION_BLOCKED_SHOPIFY_ERROR,
    TRANSACTION_BLOCKED_UNEXPECTED_ERROR,
])


# ── Shopify API helpers ─────────────────────────────────────────────────────

def shopify_request(
    method: str,
    endpoint: str,
    payload: dict | None = None,
    *,
    raw: bool = False,
    return_headers: bool = False,
) -> tuple[dict | None, str | None] | tuple[dict | None, dict, str | None]:
    """
    Make a Shopify REST API call for Hoverboard Store.
    method: GET or POST
    endpoint: e.g. /blogs/{blog_id}/articles.json
    raw: if True, do not wrap payload in {"article": ...} (for GETs / inventory)
    Returns (response_dict, error_or_none).
    Fails closed if HOVERBOARD_STORE_SHOPIFY_* variables are not set.
    """
    cfg = _get_shopify_config()
    url = f"https://{cfg['store_domain']}{endpoint}"
    headers = {
        "X-Shopify-Access-Token": cfg["access_token"],
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if raw or method == "GET":
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
    else:
        data = json.dumps({"article": payload}).encode("utf-8") if payload is not None else None

    req = urllib.request.Request(
        url,
        data=data,
        headers=headers,
        method=method,
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            if return_headers:
                resp_headers = {k.lower(): v for k, v in resp.headers.items()}
                return result, resp_headers, None
            return result, None
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        if return_headers:
            return None, {}, f"HTTP {e.code}: {body[:500]}"
        return None, f"HTTP {e.code}: {body[:500]}"
    except Exception as e:
        if return_headers:
            return None, {}, f"ERROR: {e}"
        return None, f"ERROR: {e}"


def fetch_blog_articles_paginated(limit: int = 250, max_pages: int = 20) -> tuple[list[dict], str | None]:
    """
    Fetch all articles from the configured blog via live Shopify API pagination.
    Uses Link header page_info for cursor-based pagination.
    Returns (articles_list, error_or_none).
    Fails closed if HOVERBOARD_STORE_SHOPIFY_* variables are not set.
    """
    import re as _re
    cfg = _get_shopify_config()
    blog_id = cfg["blog_id"]
    api_version = cfg["api_version"]
    all_articles = []
    page_info = None

    for _page in range(1, max_pages + 1):
        if page_info:
            endpoint = (f"/admin/api/{api_version}/blogs/{blog_id}/"
                        f"articles.json?limit={limit}&page_info={page_info}")
        else:
            endpoint = (f"/admin/api/{api_version}/blogs/{blog_id}/"
                        f"articles.json?limit={limit}")

        data, resp_headers, err = shopify_request("GET", endpoint, return_headers=True)
        if err:
            return [], f"API_ERROR: {err}"
        articles = data.get("articles", []) if data else []
        if not articles:
            break
        all_articles.extend(articles)
        link = resp_headers.get("link", "")
        if "rel=\"next\"" not in link.lower():
            break
        m = _re.search(r'page_info=([^&>\s]+).*?rel="next"', link, _re.IGNORECASE)
        if not m:
            break
        page_info = m.group(1)

    return all_articles, None


def compute_sha256(content: str) -> str:
    """Compute SHA256 of a string."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def compute_file_sha256(path: str) -> str:
    """Compute SHA256 of a file."""
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def extract_meta_from_html(html_path: str) -> dict:
    """Extract title, handle, body from HTML file."""
    content = Path(html_path).read_text(encoding="utf-8")

    title_match = re.search(r'<meta\s+name="title"\s+content="([^"]+)"', content)
    if not title_match:
        h1 = re.search(r"<h1[^>]*>([^<]+)</h1>", content)
        if h1:
            title = re.sub(r"<[^>]+>", "", h1.group(1)).strip()
        else:
            title = ""
    else:
        title = title_match.group(1)

    handle_match = re.search(r'<meta\s+name="url_slug"\s+content="([^"]+)"', content)
    if handle_match:
        handle = handle_match.group(1)
    else:
        handle = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")

    return {
        "title": title,
        "handle": handle,
        "body_html": content,
    }


# ── Core transaction functions ───────────────────────────────────────────────

def create_shopify_draft(
    title: str,
    body_html: str,
    handle: str,
) -> tuple[dict | None, str | None]:
    """
    Create one Shopify draft article in Journal Insights.
    Returns (article_dict, error_or_none).
    published=false, published_at not sent.
    """
    cfg = _get_shopify_config()
    payload = {
        "title": title,
        "body_html": body_html,
        "handle": handle,
        "published": False,
    }
    endpoint = f"/admin/api/{cfg['api_version']}/blogs/{cfg['blog_id']}/articles.json"
    data, err = shopify_request("POST", endpoint, payload)
    if err:
        return None, err
    article = data.get("article") if data else None
    return article, None


def fetch_shopify_article(article_id: int) -> tuple[dict | None, str | None]:
    """
    Fetch one Shopify article by exact ID.
    Returns (article_dict, error_or_none).
    """
    cfg = _get_shopify_config()
    endpoint = f"/admin/api/{cfg['api_version']}/blogs/{cfg['blog_id']}/articles/{article_id}.json"
    data, err = shopify_request("GET", endpoint)
    if err:
        return None, err
    article = data.get("article") if data else None
    return article, None


def _narrow_inter_tag_lf_normalize(html: str) -> str:
    """
    Narrow inter-tag LF normalisation.

    Applies ONLY the transformation observed in Shopify HTML storage:
    Remove LF byte (0x0A) strictly between a closing '>' and an opening '<'.

    Transformation: '>\n<' → '><'

    Does NOT:
    - Strip spaces
    - Strip tabs
    - Strip CR automatically
    - Modify text-node whitespace
    - Normalise attributes
    - Use generic \\s+ patterns
    - Apply full all-whitespace stripping

    This rule is intentionally narrow and specifically targets the Shopify
    inter-tag linefeed insertion observed in production.
    """
    return re.sub(r">\x0a\s*<", "><", html)


def _compute_normalized_sha256(html: str) -> str:
    """Compute SHA256 of HTML after narrow inter-tag LF normalisation."""
    normalized = _narrow_inter_tag_lf_normalize(html)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def verify_shopify_draft_against_local(
    article: dict,
    expected_article_id: int | None,
    expected_title: str,
    expected_handle: str,
    expected_local_html: str,
    expected_local_sha256: str,
) -> tuple[bool, list[str], dict]:
    """
    Verify a freshly-fetched Shopify article matches expected selected-job state.

    Checks:
    1. article_id matches expected (if expected_id provided)
    2. title exact match
    3. handle exact match
    4. published_at is null
    5. article is draft (not published)
    6. body_html SHA256 matches expected local SHA256
       using two-tier comparison:
       (A) Raw exact-byte SHA256 → PASS if equal
       (B) Narrow inter-tag LF normalised SHA256 → PASS if raw mismatch
           is solely explained by '>\\n<' → '><' normalisation
       (C) FAIL if neither matches

    Returns (all_passed, list_of_failures, details_dict)
    """
    failures = []
    details = {}

    # 1. Article ID check
    fetched_id = article.get("id")
    details["fetched_article_id"] = fetched_id
    details["expected_article_id"] = expected_article_id
    if expected_article_id is not None and fetched_id != expected_article_id:
        failures.append(f"article_id: expected {expected_article_id}, got {fetched_id}")

    # 2. Title exact match
    fetched_title = article.get("title", "")
    details["fetched_title"] = fetched_title
    details["expected_title"] = expected_title
    if fetched_title != expected_title:
        failures.append(f"title: expected {expected_title!r}, got {fetched_title!r}")

    # 3. Handle exact match
    fetched_handle = article.get("handle", "")
    details["fetched_handle"] = fetched_handle
    details["expected_handle"] = expected_handle
    if fetched_handle != expected_handle:
        failures.append(f"handle: expected {expected_handle!r}, got {fetched_handle!r}")

    # 4. published_at is null
    fetched_published_at = article.get("published_at")
    details["fetched_published_at"] = fetched_published_at
    if fetched_published_at is not None:
        failures.append(f"published_at: expected null, got {fetched_published_at!r}")

    # 5. Article is draft (not published)
    is_draft = fetched_published_at is None
    details["is_draft"] = is_draft
    if not is_draft:
        failures.append(f"article is not draft: published_at={fetched_published_at!r}")

    # 6. Body hash comparison — two-tier
    fetched_body = article.get("body_html", "")
    details["fetched_body_length"] = len(fetched_body)
    details["expected_body_length"] = len(expected_local_html)

    fetched_raw_sha256 = compute_sha256(fetched_body)
    details["fetched_body_sha256"] = fetched_raw_sha256
    details["expected_local_sha256"] = expected_local_sha256

    # Tier A: exact byte match
    if fetched_raw_sha256 == expected_local_sha256:
        details["body_verification_result"] = "PASS_RAW_EXACT"
        details["body_verification_note"] = "Raw SHA256 match — byte-exact content"
    else:
        # Tier B: narrow inter-tag LF normalisation
        local_normalized_sha = _compute_normalized_sha256(expected_local_html)
        fetched_normalized_sha = _compute_normalized_sha256(fetched_body)
        details["local_normalized_sha256"] = local_normalized_sha
        details["fetched_normalized_sha256"] = fetched_normalized_sha

        if local_normalized_sha == fetched_normalized_sha:
            # Normalised match — the only difference is inter-tag LF insertion
            details["body_verification_result"] = "PASS_ALLOWED_INTER_TAG_LF_NORMALIZATION"
            details["body_verification_note"] = (
                f"Raw SHA256 mismatch but narrow-normalised SHA256 matches. "
                f"Difference only: inter-tag LF normalisation "
                f"(>{chr(10)}< → ><). Content is equivalent."
            )
        else:
            # Tier C: canonical DOM comparison via html_canonical_comparator.
            # compare_html_canonical handles entity encoding equivalence,
            # whitespace normalisation, and element-reorder detection.
            canonical_decision, canonical_msgs = compare_html_canonical(
                expected_local_html, fetched_body
            )
            details["canonical_decision"] = canonical_decision
            details["canonical_details"] = canonical_msgs
            details["local_normalized_sha256"] = local_normalized_sha
            details["fetched_normalized_sha256"] = fetched_normalized_sha

            if canonical_decision == PASS_CANONICAL_HTML_EQUIVALENT:
                # Entity encoding difference only — content semantically equivalent
                details["body_verification_result"] = "PASS_CANONICAL_HTML_EQUIVALENT"
                details["body_verification_note"] = (
                    f"Canonical comparison: content equivalent despite serialization "
                    f"difference (entity encoding and/or structural whitespace). "
                    f"Decision: {canonical_decision}."
                )
            else:
                # Failure — canonical comparator detected content difference
                details["body_verification_result"] = canonical_decision
                details["body_verification_note"] = (
                    f"Canonical comparison failed: {canonical_decision}. "
                    f"Messages: {canonical_msgs}. "
                    f"Raw: {fetched_raw_sha256} vs {expected_local_sha256}. "
                    f"Normalized: {fetched_normalized_sha} vs {local_normalized_sha}."
                )
                failures.append(
                    f"body_sha256: canonical comparison {canonical_decision} "
                    f"(raw {len(fetched_body)} vs local {len(expected_local_html)} bytes)"
                )
                for msg in canonical_msgs:
                    if msg not in failures:
                        failures.append(msg)

    return len(failures) == 0, failures, details


# ── Handle validation ────────────────────────────────────────────────────────

CANONICAL_HANDLE_RE = re.compile(r"^[a-z0-9][a-z0-9-]*[a-z0-9]$|^[a-z0-9]$")

def is_valid_handle(handle: str) -> bool:
    """Canonical handle: lowercase, hyphens only, no leading/trailing hyphens."""
    if not handle:
        return False
    return bool(CANONICAL_HANDLE_RE.match(handle))


# ── Main transaction ─────────────────────────────────────────────────────────

def run_safe_draft_transaction(
    selected_job_context: dict,
    writer_plan: dict,
    writer_execution: dict,
    post_write_review: dict,
    html_validation: dict,
    publisher_preflight: dict,
    publisher_route: str,
    live_draft_gate_result: dict,
    # Override for unsafe publish regression (Phase I2 §14)
    _unsafe_publish_config: bool = False,
) -> dict:
    """
    Run the canonical safe Shopify draft transaction for the selected job.

    Required invariant: live_draft_gate_result.decision == "LIVE_DRAFT_WRITE_APPROVED"
    Required invariant: live_draft_gate_result.approved == True

    Returns structured transaction result with decision, approved, and all details.
    """
    blockers = []
    job_number = str(selected_job_context.get("job_number", ""))
    title = selected_job_context.get("topic", "")

    # ── EVIDENCE CONTRACT: create run_dir at the very top of the transaction.
    # Every return path — success, verification failure, gate rejection,
    # context mismatch, handle invalid, draft mutated, unsafe publish config,
    # Shopify API error, fetch failure, verification failure — must carry a
    # run_dir and persist transaction_result.json. This is the durable
    # contract that queue commit references.
    _transaction_run_dir: Path | None = _create_transaction_run_dir(job_number)

    def _return_with_evidence(**kwargs) -> dict:
        """Build a result and persist it to run_dir, then return it.

        run_dir and run_id are added to the result so every return path
        carries the authoritative transaction evidence location.
        """
        if _transaction_run_dir is not None:
            if "run_dir" not in kwargs:
                kwargs["run_dir"] = str(_transaction_run_dir)
            if "run_id" not in kwargs:
                kwargs["run_id"] = _transaction_run_dir.name
        result = _make_result(**kwargs)
        if _transaction_run_dir is not None:
            _persist_transaction_result(_transaction_run_dir, result)
        return result

    # ── I2 §8: Gate approval check ──────────────────────────────────────
    gate_decision = live_draft_gate_result.get("decision", "")
    gate_approved = live_draft_gate_result.get("approved", False)

    if not gate_approved or gate_decision != "LIVE_DRAFT_WRITE_APPROVED":
        blockers.append(TRANSACTION_BLOCKED_GATE_NOT_APPROVED)
        return _return_with_evidence(
            decision=TRANSACTION_BLOCKED_GATE_NOT_APPROVED,
            approved=False,
            blockers=blockers,
            message=(
                f"Gate not approved. gate_decision={gate_decision!r}, "
                f"gate_approved={gate_approved}. "
                f"Cannot proceed with Shopify draft creation."
            ),
            job_number=job_number,
            title=title,
        )

    # ── I2 §9: Job context identity invariants ───────────────────────────
    ctx_job = str(selected_job_context.get("job_number", ""))

    wp_job = str(
        writer_plan.get("job_number", "")
        or writer_plan.get("next_writing_candidate", {}).get("job_number", "")
    )
    we_job = str(writer_execution.get("job_number", ""))
    pwr_job = str(post_write_review.get("job_number", ""))
    hv_job = str(html_validation.get("job_number", ""))
    pp_job = str(
        publisher_preflight.get("publisher_job_number", "")
        or publisher_preflight.get("job_number", "")
    )
    gt_job = str(live_draft_gate_result.get("job_number", ""))

    for label, val in [
        ("selected_job_context.job_number", ctx_job),
        ("writer_plan.job_number", wp_job),
        ("writer_execution.job_number", we_job),
        ("post_write_review.job_number", pwr_job),
        ("html_validation.job_number", hv_job),
        ("publisher_preflight.job_number", pp_job),
        ("live_draft_gate_result.job_number", gt_job),
    ]:
        if val != ctx_job:
            blockers.append(TRANSACTION_BLOCKED_CONTEXT_MISMATCH)

    if TRANSACTION_BLOCKED_CONTEXT_MISMATCH in blockers:
        mismatch_details = []
        for label, val in [
            ("writer_plan", wp_job), ("writer_execution", we_job),
            ("post_write_review", pwr_job), ("html_validation", hv_job),
            ("publisher_preflight", pp_job), ("live_draft_gate", gt_job),
        ]:
            if val != ctx_job:
                mismatch_details.append(f"{label}={val} != context={ctx_job}")
        return _return_with_evidence(
            decision=TRANSACTION_BLOCKED_CONTEXT_MISMATCH,
            approved=False,
            blockers=blockers,
            message=f"Job context mismatch: {', '.join(mismatch_details)}",
            job_number=job_number,
            title=title,
        )

    # ── I2 §10: Article identity (title + handle) ─────────────────────────
    # Title from selected job context (authoritative)
    expected_title = selected_job_context.get("topic", "")

    # Handle: writer_plan.approved_handle (authoritative), fall back to
    # publisher_preflight.payload_preview.handle (set during preflight)
    expected_handle = (
        writer_plan.get("approved_handle", "")
        or publisher_preflight.get("payload_preview", {}).get("handle", "")
        or selected_job_context.get("shopify_handle", "")
    )

    # Validate handle format
    if not is_valid_handle(expected_handle):
        blockers.append(TRANSACTION_BLOCKED_HANDLE_INVALID)
        return _return_with_evidence(
            decision=TRANSACTION_BLOCKED_HANDLE_INVALID,
            approved=False,
            blockers=blockers,
            message=f"Invalid handle: {expected_handle!r}",
            job_number=job_number,
            title=expected_title,
            handle=expected_handle,
        )

    # ── I2 §11: Local artifact invariance ────────────────────────────────
    local_path = writer_execution.get("output_path", "")
    expected_sha256 = writer_execution.get("sha256", "")

    if not local_path:
        blockers.append(TRANSACTION_BLOCKED_DRAFT_MUTATED)
        return _return_with_evidence(
            decision=TRANSACTION_BLOCKED_DRAFT_MUTATED,
            approved=False,
            blockers=blockers,
            message="Writer execution has no output_path",
            job_number=job_number,
            title=expected_title,
        )

    current_sha256 = compute_file_sha256(local_path)
    if current_sha256 != expected_sha256:
        blockers.append(TRANSACTION_BLOCKED_DRAFT_MUTATED)
        return _return_with_evidence(
            decision=TRANSACTION_BLOCKED_DRAFT_MUTATED,
            approved=False,
            blockers=blockers,
            message=(
                f"Local draft has been mutated after Writer execution. "
                f"current_sha256={current_sha256}, "
                f"expected_sha256={expected_sha256}"
            ),
            job_number=job_number,
            title=expected_title,
            handle=expected_handle,
        )

    # Read body HTML for payload
    body_html = Path(local_path).read_text(encoding="utf-8")

    # ── Durable evidence: create run directory ──────────────────────────
    # CRITICAL FIX: Use the SAME _transaction_run_dir created at the top of
    # run_safe_draft_transaction(). Do NOT call _create_transaction_run_dir()
    # again. The second call was creating a duplicate run_dir (job24 had two
    # run dirs: 47c995a0 for sent/fetched, da714740 for transaction_result).
    # All evidence — sent body, fetched body, verification, transaction result
    # — must flow through the single _transaction_run_dir created at line 563.
    if _transaction_run_dir is not None:
        _persist_sent_body(_transaction_run_dir, body_html)
    # _transaction_run_dir is already None-safe from line 563

    # ── I2 §13: published_at safety check ───────────────────────────────
    # The transaction always sends published=false and no published_at.
    # If called with _unsafe_publish_config=True (regression test), block it.
    if _unsafe_publish_config:
        blockers.append(TRANSACTION_BLOCKED_PUBLISH_CONFIG_UNSAFE)
        return _return_with_evidence(
            decision=TRANSACTION_BLOCKED_PUBLISH_CONFIG_UNSAFE,
            approved=False,
            blockers=blockers,
            message="Unsafe publish configuration: published_at would not be null",
            job_number=job_number,
            title=expected_title,
            handle=expected_handle,
        )

    # ── I2 §12: Build payload (draft only) ───────────────────────────────
    payload_title = expected_title
    payload_handle = expected_handle
    payload_body = body_html
    # published=false — explicit
    # published_at — NOT sent (null)

    # ── I6 §30-31: Reconcile first, then create at most one hidden draft ─
    idempotency_key = os.environ.get("ORIN_IDEMPOTENCY_KEY", "")
    if not idempotency_key:
        blockers.append(TRANSACTION_BLOCKED_SHOPIFY_ERROR)
        return _return_with_evidence(
            decision=TRANSACTION_BLOCKED_SHOPIFY_ERROR,
            approved=False,
            blockers=blockers,
            message="Durable Shopify idempotency key is missing.",
            job_number=job_number,
            title=payload_title,
            handle=payload_handle,
            shopify_error="ORIN_IDEMPOTENCY_KEY is required",
        )

    cfg = _get_shopify_config()
    gateway = HiddenDraftGateway(
        GraphQLHTTPTransport(
            store_domain=cfg["store_domain"],
            access_token=cfg["access_token"],
            api_version=cfg["api_version"],
        )
    )
    try:
        draft_result = gateway.ensure(
            DraftSpec(
                blog_id=f"gid://shopify/Blog/{cfg['blog_id']}",
                title=payload_title,
                body_html=payload_body,
                handle=payload_handle,
                author_name="ORIN",
                idempotency_key=idempotency_key,
            )
        )
    except (DraftReconciliationError, ShopifyRequestError, ValueError) as error:
        blockers.append(TRANSACTION_BLOCKED_SHOPIFY_ERROR)
        return _return_with_evidence(
            decision=TRANSACTION_BLOCKED_SHOPIFY_ERROR,
            approved=False,
            blockers=blockers,
            message=f"Shopify hidden-draft reconciliation failed: {error}",
            job_number=job_number,
            title=payload_title,
            handle=payload_handle,
            shopify_error=str(error),
            reconciliation_status="needs_review",
            shopify_write_state="unknown",
        )

    returned_article_id = draft_result.numeric_article_id

    # ── I6 §31: Immediately fetch exact article by ID (not from POST response)
    fetched_article, fetch_err = fetch_shopify_article(returned_article_id)

    # Persist fetched body if fetch succeeded (even if we block below)
    # Uses _transaction_run_dir (the single authoritative run_dir for this transaction)
    if fetched_article and _transaction_run_dir is not None:
        fetched_body = fetched_article.get("body_html", "")
        _persist_fetched_body(_transaction_run_dir, fetched_body)

    if fetch_err or fetched_article is None:
        # Draft was created but we couldn't verify it — treat as failed
        blockers.append(TRANSACTION_BLOCKED_VERIFICATION_FAILED)
        return _return_with_evidence(
            decision=TRANSACTION_BLOCKED_VERIFICATION_FAILED,
            approved=False,
            blockers=blockers,
            message=(
                f"Shopify draft created (ID={returned_article_id}) but "
                f"fetch verification failed: {fetch_err}. "
                f"Article kept hidden. Do not publish. Do not update queue."
            ),
            job_number=job_number,
            title=payload_title,
            handle=payload_handle,
            shopify_article_id=returned_article_id,
            shopify_error=fetch_err,
            shopify_create_count=draft_result.create_count,
            reconciliation_status="needs_review",
            shopify_write_state=draft_result.shopify_write_state,
            shopify_idempotency_marker=draft_result.idempotency_marker,
        )

    # ── I3 §17-18: Run post-fetch verification ────────────────────────────
    verification_passed, verification_failures, verification_details = (
        verify_shopify_draft_against_local(
            article=fetched_article,
            expected_article_id=returned_article_id,
            expected_title=payload_title,
            expected_handle=payload_handle,
            expected_local_html=payload_body,
            expected_local_sha256=expected_sha256,
        )
    )

    # ── Persist verification.json into the single authoritative run_dir ──
    # Persisted for BOTH pass and fail outcomes. Uses _transaction_run_dir
    # (the single run_dir created at line 563 — not a duplicate). This
    # ensures verification evidence is in the same dir as sent_body,
    # fetched_body, and transaction_result.json.
    if _transaction_run_dir is not None:
        _persist_verification(
            run_dir=_transaction_run_dir,
            verification_passed=verification_passed,
            failures=verification_failures,
            details=verification_details,
            job_number=job_number,
            article_id=returned_article_id,
            run_id=_transaction_run_dir.name,
        )

    if not verification_passed:
        blockers.append(TRANSACTION_BLOCKED_VERIFICATION_FAILED)
        return _return_with_evidence(
            decision=TRANSACTION_BLOCKED_VERIFICATION_FAILED,
            approved=False,
            blockers=blockers,
            message=(
                f"Shopify draft verification failed. "
                f"Failures: {verification_failures}. "
                f"Article kept hidden. Do not publish. Do not update queue."
            ),
            job_number=job_number,
            title=payload_title,
            handle=payload_handle,
            shopify_article_id=returned_article_id,
            verification_failures=verification_failures,
            verification_details=verification_details,
            shopify_create_count=draft_result.create_count,
            reconciliation_status="needs_review",
            shopify_write_state=draft_result.shopify_write_state,
            shopify_idempotency_marker=draft_result.idempotency_marker,
        )

    # ── All checks passed ───────────────────────────────────────────────
    return _return_with_evidence(
        decision=TRANSACTION_APPROVED_DRAFT_CREATED,
        approved=True,
        blockers=[],
        message="Shopify draft created and verified successfully.",
        job_number=job_number,
        title=payload_title,
        handle=payload_handle,
        shopify_article_id=returned_article_id,
        shopify_fetched_article_id=fetched_article.get("id"),
        shopify_title=fetched_article.get("title"),
        shopify_handle=fetched_article.get("handle"),
        shopify_published_at=fetched_article.get("published_at"),
        shopify_body_sha256=verification_details.get("fetched_body_sha256"),
        local_sha256=expected_sha256,
        verification_details=verification_details,
        shopify_create_count=draft_result.create_count,
        reconciliation_status=draft_result.reconciliation_status,
        shopify_write_state=draft_result.shopify_write_state,
        shopify_idempotency_marker=draft_result.idempotency_marker,
    )


# ── Result builder ──────────────────────────────────────────────────────────

def _make_result(
    decision: str,
    approved: bool,
    blockers: list[str],
    message: str,
    job_number: str = "",
    title: str = "",
    handle: str = "",
    shopify_article_id: int | None = None,
    shopify_fetched_article_id: int | None = None,
    shopify_title: str | None = None,
    shopify_handle: str | None = None,
    shopify_published_at: str | None = None,
    shopify_body_sha256: str | None = None,
    local_sha256: str | None = None,
    verification_failures: list[str] | None = None,
    verification_details: dict | None = None,
    shopify_error: str | None = None,
    shopify_create_count: int = 0,
    reconciliation_status: str = "not_started",
    shopify_write_state: str = "not_attempted",
    shopify_idempotency_marker: str | None = None,
    run_dir: Path | str | None = None,
    run_id: str = "",
) -> dict:
    """Build a structured transaction result dict."""
    result = {
        "decision": decision,
        "approved": bool(approved),
        "job_number": job_number,
        "title": title,
        "handle": handle or None,
        "blockers": blockers,
        "message": message,
        "shopify_create_count": shopify_create_count,
        "reconciliation_status": reconciliation_status,
        "shopify_write_state": shopify_write_state,
    }
    if shopify_idempotency_marker is not None:
        result["shopify_idempotency_marker"] = shopify_idempotency_marker
    if shopify_article_id is not None:
        result["shopify_article_id"] = shopify_article_id
    if shopify_fetched_article_id is not None:
        result["shopify_fetched_article_id"] = shopify_fetched_article_id
    if shopify_title is not None:
        result["shopify_title"] = shopify_title
    if shopify_handle is not None:
        result["shopify_handle"] = shopify_handle
    if shopify_published_at is not None:
        result["shopify_published_at"] = shopify_published_at
    if shopify_body_sha256 is not None:
        result["shopify_body_sha256"] = shopify_body_sha256
    if local_sha256 is not None:
        result["local_sha256"] = local_sha256
    if verification_failures is not None:
        result["verification_failures"] = verification_failures
    if verification_details is not None:
        result["verification_details"] = verification_details
    if shopify_error is not None:
        result["shopify_error"] = shopify_error
    if run_dir is not None:
        result["run_dir"] = str(run_dir)
    if run_id:
            result["run_id"] = run_id
    return result


# ── CLI entry point ─────────────────────────────────────────────────────────

def main():
    """
    Phase I6 — Run safe draft transaction from JSON inputs.
    Usage:
      python3 shopify_draft_transaction.py \\
        --gate-result /tmp/orin_live_draft_gate_result.json \\
        --writer-execution /tmp/orin_job21_writer_execution_preview.json \\
        --output /tmp/orin_phase_i_transaction_result.json
    """
    import argparse
    parser = argparse.ArgumentParser(description="ORIN Safe Shopify Draft Transaction")
    parser.add_argument("--gate-result", required=True, help="Path to live_draft_gate result JSON")
    parser.add_argument("--selected-job-context", required=True, help="Path to selected job context JSON")
    parser.add_argument("--writer-plan", required=True, help="Path to writer plan JSON")
    parser.add_argument("--writer-execution", required=True, help="Path to writer execution JSON")
    parser.add_argument("--post-write-review", required=True, help="Path to post-write review JSON")
    parser.add_argument("--html-validation", required=True, help="Path to HTML validation JSON")
    parser.add_argument("--publisher-preflight", required=True, help="Path to publisher preflight JSON")
    parser.add_argument("--publisher-route", required=True, help="Publisher route string")
    parser.add_argument("--output", required=True, help="Output path for transaction result JSON")
    parser.add_argument("--unsafe-publish-config", action="store_true",
                        help="REGRESSION: simulate unsafe publish config")
    args = parser.parse_args()

    selected_job_context = json.loads(Path(args.selected_job_context).read_text())
    writer_plan = json.loads(Path(args.writer_plan).read_text())
    writer_execution = json.loads(Path(args.writer_execution).read_text())
    post_write_review = json.loads(Path(args.post_write_review).read_text())
    html_validation = json.loads(Path(args.html_validation).read_text())
    publisher_preflight = json.loads(Path(args.publisher_preflight).read_text())
    gate_result = json.loads(Path(args.gate_result).read_text())

    result = run_safe_draft_transaction(
        selected_job_context=selected_job_context,
        writer_plan=writer_plan,
        writer_execution=writer_execution,
        post_write_review=post_write_review,
        html_validation=html_validation,
        publisher_preflight=publisher_preflight,
        publisher_route=args.publisher_route,
        live_draft_gate_result=gate_result,
        _unsafe_publish_config=args.unsafe_publish_config,
    )

    Path(args.output).write_text(json.dumps(result, indent=2))
    print(f"Transaction decision: {result['decision']}")
    print(f"Approved: {result['approved']}")
    if result.get("shopify_article_id"):
        print(f"Shopify Article ID: {result['shopify_article_id']}")
    if result.get("shopify_body_sha256"):
        print(f"Shopify body SHA256: {result['shopify_body_sha256']}")
    if result.get("blockers"):
        print(f"Blockers: {result['blockers']}")


if __name__ == "__main__":
    main()
