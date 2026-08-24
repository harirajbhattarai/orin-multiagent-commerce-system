from pathlib import Path

from orin_pilot_worker.runner import validate_generic_article
from tools.shopify_publisher.orin.model_writer import build_request_payload


MIGRATION = Path(
    "supabase/migrations/20260824160000_generic_oauth_pilot_worker.sql"
).read_text(encoding="utf-8")
COMPOSE = Path("deploy/vps/compose.yml").read_text(encoding="utf-8")


def test_generic_pilot_role_is_function_only_and_credential_blind():
    assert "create role orin_pilot_worker nologin" in MIGRATION
    assert "revoke all on all tables in schema public from orin_pilot_worker" in MIGRATION
    assert "grant execute on function orin_private.claim_next_generic_pilot_job" in MIGRATION
    assert "grant execute on function orin_private.get_generic_pilot_context" in MIGRATION
    assert "grant execute on function orin_private.complete_generic_pilot_job" in MIGRATION
    assert "grant select" not in "\n".join(
        line for line in MIGRATION.splitlines() if "orin_pilot_worker" in line
    )
    context_function = MIGRATION.split(
        "create or replace function orin_private.get_generic_pilot_context", 1
    )[1].split(
        "create or replace function orin_private.complete_generic_pilot_job", 1
    )[0]
    assert "vault." not in context_function
    assert "shopify_credential_secret_id" not in context_function
    assert "shopify_refresh_secret_id" not in context_function


def test_generic_pilot_never_routes_dedicated_tenants_or_opens_shopify():
    assert "not in ('hoverboard_store', 'hcs_gadgets')" in MIGRATION
    assert "profile.shopify_connection_method = 'oauth'" in MIGRATION
    assert "onboarding.status = 'database_provisioned'" in MIGRATION
    assert "not settings.shopify_writes_enabled" in MIGRATION
    assert "not settings.approved_draft_writes_enabled" in MIGRATION
    preparation = MIGRATION.split(
        "create or replace function orin_private.prepare_generic_pilot_dry_run", 1
    )[1].split(
        "create or replace function orin_private.claim_next_generic_pilot_job", 1
    )[0]
    assert "shopify_writes_enabled = false" in preparation
    assert "approved_draft_writes_enabled = false" in preparation
    assert "commissioning_status = 'dry_run_pending'" in preparation


def test_generic_pilot_compose_is_one_shot_and_has_no_shopify_secret():
    service = COMPOSE.split("  generic-pilot-worker:", 1)[1].split(
        "\n  evidence-sync:", 1
    )[0]
    assert 'profiles: ["generic-pilot-worker"]' in service
    assert 'restart: "no"' in service
    assert "orin_pilot_worker" in service
    assert "ORIN_CODE_VERSION: ${ORIN_DEPLOY_SHA:?set ORIN_DEPLOY_SHA}" in service
    assert "ORIN_MODEL_WRITER_ENABLED: \"1\"" in service
    assert "pilot_worker_database_url" in service
    assert "writer_api_key" in service
    assert "shopify_access_token" not in service
    assert "refresh_token" not in service
    assert "ports:" not in service
    assert "- once" in service
    assert "- serve" not in service


def test_generic_pilot_secret_install_and_preflight_are_private():
    installer = Path("deploy/vps/install_pilot_worker_db_secret.sh").read_text(
        encoding="utf-8"
    )
    preflight = Path("deploy/vps/preflight.sh").read_text(encoding="utf-8")
    assert 'target="${secrets_dir}/pilot_worker_database_url"' in installer
    assert '"${first}" != *"orin_pilot_worker"*' in installer
    assert 'chmod 0400 "${temporary}"' in installer
    assert 'install -d -m 0700' in installer
    assert "--require-pilot-worker-secret" in preflight
    assert '[pilot_worker_database_url]="${ORIN_RUNTIME_UID}"' in preflight
    assert 'pilot_evidence_root="${ORIN_EVIDENCE_ROOT}/generic-pilot"' in preflight


def test_generic_writer_prompt_uses_safe_client_profile():
    payload = build_request_payload(
        {"client_id": "orin_oauth_test", "job_number": "1"},
        {
            "client_id": "orin_oauth_test",
            "title": "How to Choose Snowboard Accessories",
            "target_keyword": "snowboard accessories guide",
            "cluster": "Buying guides",
            "client_profile": {
                "display_name": "ORIN OAuth Test",
                "market_country": "GB",
                "brand_voice": "Helpful and clear.",
                "product_scope": ["snowboard", "accessories"],
            },
        },
    )
    prompt = payload["messages"][1]["content"]
    assert "article.orin-article" in prompt
    assert "ORIN OAuth Test" in prompt
    assert "snowboard" in prompt
    assert "HCS Gadgets article" not in prompt
    assert "Hoverboard Store" not in prompt


def test_generic_article_quality_contract_accepts_safe_complete_html():
    title = "How to Choose Snowboard Accessories"
    keyword = "snowboard accessories guide"
    filler = " ".join(["practical"] * 125)
    sections = "".join(
        f"<h2>Section {number}</h2><p>{filler}</p><p>{filler}</p>"
        for number in range(1, 6)
    )
    html = f"""<!--
Meta Title: Snowboard Accessories: A Practical Buying Guide
Meta Description: Use this practical snowboard checklist to compare accessories, verify product details, and choose suitable items with confidence before buying.
URL Slug: snowboard-accessories-practical-guide
-->
<article class="orin-article"><h1>{title}</h1>
<p>{keyword}. {keyword}. {keyword}.</p>{sections}</article>"""
    receipt = validate_generic_article(html, title=title, target_keyword=keyword)
    assert receipt["passed"], receipt
    assert receipt["word_count"] >= 1200
    assert receipt["h2_count"] == 5
    assert receipt["paragraph_count"] >= 10
