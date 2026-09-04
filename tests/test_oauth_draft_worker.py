from pathlib import Path

import pytest

from orin_oauth_draft_worker.cli import _client_id, _runtime_config


MIGRATION = Path(
    "supabase/migrations/20260825094846_generic_oauth_approved_draft_worker.sql"
).read_text(encoding="utf-8")
COMPOSE = Path("deploy/vps/compose.yml").read_text(encoding="utf-8")
IDLE_POLL_FIX = Path(
    "supabase/migrations/20260904154325_defer_oauth_boundary_until_work_exists.sql"
).read_text(encoding="utf-8")


def test_oauth_approval_role_is_function_only_and_live_publish_blind():
    assert "create role orin_oauth_draft_worker nologin" in MIGRATION
    assert "revoke all on all tables in schema public from orin_oauth_draft_worker" in MIGRATION
    assert "grant execute on function orin_private.claim_next_oauth_approved_draft_job" in MIGRATION
    assert "grant execute on function orin_private.get_oauth_approved_draft_context" in MIGRATION
    assert "grant select" not in "\n".join(
        line for line in MIGRATION.splitlines() if "orin_oauth_draft_worker" in line
    )
    assert "articleCreate" not in MIGRATION
    assert "publishDate" not in MIGRATION
    assert "settings.shopify_writes_enabled" in MIGRATION
    assert "not v_settings.approved_draft_writes_enabled" in MIGRATION


def test_oauth_approval_claim_requires_exact_human_approved_frozen_draft():
    claim = MIGRATION.split(
        "create or replace function orin_private.claim_next_oauth_approved_draft_job", 1
    )[1].split(
        "create or replace function orin_private.get_oauth_approved_draft_context", 1
    )[0]
    assert "candidate.requested_mode = 'hidden-draft'" in claim
    assert "candidate.payload = '{}'::jsonb" in claim
    assert "candidate.approved_draft_id is not null" in claim
    assert "candidate.approved_body_sha256 is not null" in claim
    assert "decision.decision = 'approve_hidden_draft'" in claim
    assert "decision.processing_status = 'consumed'" in claim
    assert "candidate.source_job_key = 'decision:' || decision.decision_id::text" in claim


def test_idle_oauth_poll_checks_for_work_before_asserting_fresh_credentials():
    materialize = IDLE_POLL_FIX.split(
        "create or replace function orin_private.materialize_next_oauth_approved_draft_decision",
        1,
    )[1].split(
        "create or replace function orin_private.claim_next_oauth_approved_draft_job", 1
    )[0]
    claim = IDLE_POLL_FIX.split(
        "create or replace function orin_private.claim_next_oauth_approved_draft_job", 1
    )[1]

    materialize_no_work = "if not found then return; end if;"
    claim_no_work = "if v_job_id is null then return; end if;"
    boundary = "perform orin_private.assert_oauth_approved_draft_boundary(p_client_id);"

    assert materialize.index(materialize_no_work) < materialize.index(boundary)
    assert claim.index(claim_no_work) < claim.index(boundary)
    assert claim.index(boundary) < claim.index("set status = 'leased'")


def test_oauth_worker_never_receives_refresh_material_or_an_app_secret():
    context = MIGRATION.split(
        "create or replace function orin_private.get_oauth_approved_draft_context", 1
    )[1].split(
        "create or replace function orin_private.complete_oauth_approved_draft_job", 1
    )[0]
    service = COMPOSE.split("  oauth-draft-worker:", 1)[1].split(
        "\n  evidence-sync:", 1
    )[0]
    assert "shopify_refresh_secret_id" not in context
    assert "refresh_token" not in context
    assert "SHOPIFY_CLIENT_SECRET" not in service
    assert "writer_api_key" not in service
    assert "oauth_draft_worker_database_url" in service
    assert 'ORIN_MODEL_WRITER_ENABLED: "0"' in service
    assert "ports:" not in service


def test_oauth_worker_is_bound_to_generic_client_ids():
    assert _client_id("orin_oauth_test") == "orin_oauth_test"
    for value in ("hoverboard_store", "hcs_gadgets", "Bad Client", "x"):
        with pytest.raises(Exception):
            _client_id(value)


def test_oauth_runtime_config_is_assembled_from_server_context_only():
    runtime = _runtime_config(
        {
            "shopify": {
                "store_domain": "orin-oauth-test.myshopify.com",
                "access_token": "server-side-token",
                "api_version": "2026-07",
                "blog_id": "gid://shopify/Blog/124952412448",
                "author_name": "ORIN OAuth Test",
            }
        }
    )
    assert runtime.store_domain == "orin-oauth-test.myshopify.com"
    assert runtime.blog_id == "gid://shopify/Blog/124952412448"
    assert runtime.access_token == "server-side-token"


def test_approval_refresh_stays_service_role_only():
    assert "service_get_client_shopify_approval_connection" in MIGRATION
    assert "service_rotate_client_shopify_approval_tokens" in MIGRATION
    assert "from public, anon, authenticated" in MIGRATION
    assert "to service_role" in MIGRATION
    assert "perform orin_private.assume_verified_operator(p_operator_id)" in MIGRATION
    assert "not settings.shopify_writes_enabled" in MIGRATION
    assert "settings.approved_draft_writes_enabled" in MIGRATION


def test_oauth_worker_secret_installer_and_preflight_are_private():
    installer = Path("deploy/vps/install_oauth_draft_worker_db_secret.sh").read_text(
        encoding="utf-8"
    )
    preflight = Path("deploy/vps/preflight.sh").read_text(encoding="utf-8")
    assert 'target="${secrets_dir}/oauth_draft_worker_database_url"' in installer
    assert '"${first}" != *"orin_oauth_draft_worker"*' in installer
    assert 'chown "10009:${runtime_gid}" "${temporary}"' in installer
    assert 'chmod 0400 "${temporary}"' in installer
    assert "--require-oauth-draft-worker-secret" in preflight
    assert "[oauth_draft_worker_database_url]=10009" in preflight
    assert "generic-oauth-drafts" in preflight
