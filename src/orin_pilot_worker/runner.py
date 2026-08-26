"""Generate one version-bound generic review draft without Shopify access."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import uuid
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from typing import Any

from orin_runner.contract import FinalResult, SCHEMA_VERSION
from orin_worker.models import ClaimedJob
from tools.shopify_publisher.orin.model_writer import ModelWriterError, generate_article


PILOT_CONFIG_VERSION = "generic-oauth-pilot/v1"
MIN_WORD_COUNT = 1200
MIN_H2_COUNT = 5
MIN_PARAGRAPH_COUNT = 10
MAX_ARTICLE_BYTES = 500_000
MAX_PILOT_JOB_ATTEMPTS = 2


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _code_version() -> str:
    configured = os.environ.get("ORIN_CODE_VERSION")
    if configured:
        return configured
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    return result.stdout.strip() if result.returncode == 0 else "unknown"


def _private_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    path.chmod(0o600)


def _plain_text(body_html: str) -> str:
    no_comments = re.sub(r"<!--.*?-->", " ", body_html, flags=re.DOTALL)
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", no_comments))).strip()


def _metadata(body_html: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for comment in re.findall(r"<!--(.*?)-->", body_html, flags=re.DOTALL):
        for line in comment.splitlines():
            if ":" not in line:
                continue
            label, value = line.split(":", 1)
            key = {
                "Meta Title": "meta_title",
                "Meta Description": "meta_description",
                "URL Slug": "url_slug",
            }.get(label.strip())
            if key and key not in values:
                values[key] = value.strip()
    return values


def validate_generic_article(body_html: str, *, title: str, target_keyword: str) -> dict[str, Any]:
    plain = _plain_text(body_html)
    words = re.findall(r"\b[\w'-]+\b", plain)
    h1_values = [
        _plain_text(value)
        for value in re.findall(r"<h1\b[^>]*>(.*?)</h1>", body_html, flags=re.I | re.S)
    ]
    h2_count = len(re.findall(r"<h2\b", body_html, flags=re.I))
    paragraph_count = len(re.findall(r"<p\b", body_html, flags=re.I))
    keyword_count = plain.casefold().count(target_keyword.casefold()) if target_keyword else 0
    meta = _metadata(body_html)
    failures: list[str] = []
    if len(body_html.encode("utf-8")) > MAX_ARTICLE_BYTES:
        failures.append("ARTICLE_TOO_LARGE")
    if len(h1_values) != 1 or h1_values[0] != title:
        failures.append("H1_MISMATCH")
    if len(words) < MIN_WORD_COUNT:
        failures.append("WORD_COUNT_LOW")
    if h2_count < MIN_H2_COUNT:
        failures.append("H2_COUNT_LOW")
    if paragraph_count < MIN_PARAGRAPH_COUNT:
        failures.append("PARAGRAPH_COUNT_LOW")
    if keyword_count < 3 or keyword_count > 8:
        failures.append("KEYWORD_COUNT_INVALID")
    if not re.search(r'<article\b[^>]*class=["\'][^"\']*\borin-article\b', body_html, re.I):
        failures.append("WRAPPER_MISSING")
    if not 30 <= len(meta.get("meta_title", "")) <= 60:
        failures.append("META_TITLE_LENGTH")
    if not 120 <= len(meta.get("meta_description", "")) <= 160:
        failures.append("META_DESCRIPTION_LENGTH")
    return {
        "passed": not failures,
        "failures": failures,
        "word_count": len(words),
        "h2_count": h2_count,
        "paragraph_count": paragraph_count,
        "target_keyword_count": keyword_count,
        **meta,
    }


def generic_quality_retry_payload(receipt: dict[str, Any]) -> dict[str, Any]:
    """Return only deterministic, non-secret measurements for a model retry."""
    return {
        "failed_requirements": list(receipt.get("failures", [])),
        "observed": {
            "word_count": receipt.get("word_count"),
            "h2_count": receipt.get("h2_count"),
            "paragraph_count": receipt.get("paragraph_count"),
            "target_keyword_count": receipt.get("target_keyword_count"),
            "meta_title_length": len(str(receipt.get("meta_title", ""))),
            "meta_description_length": len(
                str(receipt.get("meta_description", ""))
            ),
        },
        "required": {
            "word_count_min": MIN_WORD_COUNT,
            "h2_count_min": MIN_H2_COUNT,
            "paragraph_count_min": MIN_PARAGRAPH_COUNT,
            "target_keyword_count_min": 3,
            "target_keyword_count_max": 8,
            "meta_title_length_min": 30,
            "meta_title_length_max": 60,
            "meta_description_length_min": 120,
            "meta_description_length_max": 160,
        },
    }


def _writer_plan(context: dict[str, Any]) -> dict[str, Any]:
    item = context["content_item"]
    title = str(item["topic"])
    keyword = str(item["target_keyword"])
    cluster = str(item.get("cluster") or "Product education")
    return {
        "client_id": context["client_id"],
        "title": title,
        "approved_handle": re.sub(r"[^a-z0-9]+", "-", title.casefold()).strip("-")[:120],
        "target_keyword": keyword,
        "search_intent": cluster,
        "reader_persona": f"Reader in {context.get('market_country') or 'the client market'}",
        "article_angle": "Practical, non-speculative buyer education",
        "cluster": cluster,
        "compliance_notes": str(item.get("notes") or "Check model-specific facts at source."),
        "h2_outline": [],
        "blocked_topic_terms": [],
        "faq_plan": [],
        "internal_link_plan": [],
        "cta_plan": {},
        "claims_to_avoid": [
            "guarantee", "guaranteed", "in stock", "best price", "certified safe"
        ],
        "content_quality_contract": {"version": PILOT_CONFIG_VERSION},
        "client_profile": {
            "display_name": context.get("display_name", ""),
            "market_country": context.get("market_country", ""),
            "timezone": context.get("timezone", ""),
            "brand_voice": context.get("brand_voice", ""),
            "content_categories": context.get("content_categories", []),
            "product_scope": context.get("product_scope", []),
        },
    }


def execute_generic_pilot(
    job: ClaimedJob,
    *,
    context: dict[str, Any],
    artifact_root: Path,
) -> dict[str, Any]:
    if job.requested_mode != "dry-run" or job.payload != {}:
        raise RuntimeError("generic pilot accepts only an empty dry-run job")
    if context.get("client_id") != job.client_id:
        raise RuntimeError("pilot context crossed the claimed client boundary")
    started_at = _now()
    run_id = f"pilot_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:8]}"
    run_dir = (artifact_root / job.client_id / run_id).resolve()
    run_dir.mkdir(parents=True, mode=0o700)
    run_dir.chmod(0o700)
    os.environ["ORIN_RUN_ARTIFACT_DIR"] = str(run_dir)
    item = context.get("content_item")
    if item is None and context.get("source_kind") == "recurring":
        finished_at = _now()
        final = FinalResult(
            schema=SCHEMA_VERSION,
            run_id=run_id,
            request_id=str(job.request_id),
            client_id=job.client_id,
            job_id=None,
            attempt=job.attempt_count,
            requested_mode="dry-run",
            effective_mode="dry-run",
            status="completed",
            decision="no_job_due",
            code_version=_code_version(),
            config_version=PILOT_CONFIG_VERSION,
            idempotency_key=f"{job.client_id}:{job.request_id}",
            replay_disposition="terminal",
            shopify_write_state="not_attempted",
            shopify_idempotency_marker=None,
            shopify_article_id=None,
            shopify_create_count=0,
            shopify_published=False,
            queue_changed=False,
            reconciliation_status="not_required",
            started_at=started_at,
            finished_at=finished_at,
            artifact_uri=str(run_dir),
            error_code=None,
            pipeline_exit_code=0,
        ).to_dict()
        _private_json(
            run_dir / "scheduler_receipt.json",
            {
                "schema": "orin.generic-recurring-dry-run/v1",
                "client_id": job.client_id,
                "decision": "no_job_due",
                "shopify_create_count": 0,
                "shopify_published": False,
            },
        )
        _private_json(run_dir / "final_result.json", final)
        return final
    if not isinstance(item, dict) or str(item.get("status")) != "in_progress":
        raise RuntimeError("pilot content item is not version-bound and in progress")

    plan = _writer_plan(context)
    safe_context = {
        "client_id": job.client_id,
        "job_number": str(item["item_number"]),
        "topic": item["topic"],
    }
    _private_json(run_dir / "pilot_context.json", context)
    _private_json(run_dir / "writer_plan.json", plan)

    receipt: dict[str, Any] = {}
    body_html = ""
    try:
        for attempt in (1, 2):
            result = generate_article(
                job_context=safe_context,
                writer_plan=plan,
                attempt=attempt,
                quality_retry=(
                    None
                    if attempt == 1
                    else generic_quality_retry_payload(receipt)
                ),
            )
            body_html = result.body_html
            receipt = validate_generic_article(
                body_html,
                title=str(item["topic"]),
                target_keyword=str(item["target_keyword"]),
            )
            _private_json(run_dir / f"quality_receipt_attempt_{attempt}.json", receipt)
            if receipt["passed"]:
                break
        if not receipt.get("passed"):
            raise ModelWriterError("generic article failed deterministic quality checks")
    except Exception as exc:
        finished_at = _now()
        retryable = job.attempt_count < MAX_PILOT_JOB_ATTEMPTS
        final = FinalResult(
            schema=SCHEMA_VERSION,
            run_id=run_id,
            request_id=str(job.request_id),
            client_id=job.client_id,
            job_id=str(item["item_number"]),
            attempt=job.attempt_count,
            requested_mode="dry-run",
            effective_mode="dry-run",
            status="failed",
            decision=(
                "GENERIC_PILOT_DRAFT_RETRY"
                if retryable
                else "GENERIC_PILOT_DRAFT_FAILED"
            ),
            code_version=_code_version(),
            config_version=PILOT_CONFIG_VERSION,
            idempotency_key=f"{job.client_id}:{job.request_id}",
            replay_disposition="retry" if retryable else "terminal",
            shopify_write_state="not_attempted",
            shopify_idempotency_marker=None,
            shopify_article_id=None,
            shopify_create_count=0,
            shopify_published=False,
            queue_changed=False,
            reconciliation_status="not_required",
            started_at=started_at,
            finished_at=finished_at,
            artifact_uri=str(run_dir),
            error_code="ORIN_GENERIC_PILOT_DRAFT_FAILED",
            pipeline_exit_code=1,
        ).to_dict()
        _private_json(run_dir / "failure.json", {"error_type": type(exc).__name__})
        _private_json(run_dir / "final_result.json", final)
        return final

    raw = body_html.encode("utf-8")
    (run_dir / "review_draft.html").write_bytes(raw)
    (run_dir / "review_draft.html").chmod(0o600)
    finished_at = _now()
    final = FinalResult(
        schema=SCHEMA_VERSION,
        run_id=run_id,
        request_id=str(job.request_id),
        client_id=job.client_id,
        job_id=str(item["item_number"]),
        attempt=job.attempt_count,
        requested_mode="dry-run",
        effective_mode="dry-run",
        status="completed",
        decision="GENERIC_PILOT_REVIEW_DRAFT_CREATED",
        code_version=_code_version(),
        config_version=PILOT_CONFIG_VERSION,
        idempotency_key=f"{job.client_id}:{job.request_id}",
        replay_disposition="terminal",
        shopify_write_state="not_attempted",
        shopify_idempotency_marker=None,
        shopify_article_id=None,
        shopify_create_count=0,
        shopify_published=False,
        queue_changed=False,
        reconciliation_status="not_required",
        started_at=started_at,
        finished_at=finished_at,
        artifact_uri=str(run_dir),
        error_code=None,
        pipeline_exit_code=0,
    ).to_dict()
    final["_review_draft"] = {
        "content_item_id": item["content_item_id"],
        "content_item_version": item["version"],
        "title": item["topic"],
        "body_html": body_html,
        "body_sha256": hashlib.sha256(raw).hexdigest(),
        "word_count": receipt["word_count"],
        "meta_title": receipt.get("meta_title", ""),
        "meta_description": receipt.get("meta_description", ""),
        "quality_score": 100,
        "checks": [
            "Version-bound generic pilot context verified",
            "Deterministic HTML and content quality checks passed",
            "Shopify credential was unavailable and no Shopify write was attempted",
        ],
    }
    _private_json(run_dir / "final_result.json", {k: v for k, v in final.items() if k != "_review_draft"})
    return final
