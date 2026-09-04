from pathlib import Path

from orin_hcs_vault_draft_worker.cli import _runtime_config, build_parser


MIGRATION = Path(
    "supabase/migrations/20260904131500_hcs_vault_approved_draft_worker.sql"
).read_text(encoding="utf-8")
COMPOSE = Path("deploy/vps/compose.yml").read_text(encoding="utf-8")
PYPROJECT = Path("pyproject.toml").read_text(encoding="utf-8")


def test_hcs_vault_worker_is_exact_client_and_unpublished_draft_only():
    assert "v_job.client_id <> 'hcs_gadgets'" in MIGRATION
    assert "v_job.requested_mode <> 'hidden-draft'" in MIGRATION
    assert "settings.approved_draft_writes_enabled" in MIGRATION
    assert "not settings.shopify_writes_enabled" in MIGRATION
    assert "shopify_connection_method <> 'manual_token'" in MIGRATION
    assert "refresh_token" not in MIGRATION
    assert "articleCreate" not in MIGRATION
    assert "publishDate" not in MIGRATION


def test_hcs_vault_worker_receives_only_function_grants():
    assert (
        "grant execute on function "
        "orin_private.get_hcs_vault_approved_draft_context(uuid, text)\n"
        "  to orin_oauth_draft_worker;"
    ) in MIGRATION
    assert "grant select" not in MIGRATION
    assert "vault.decrypted_secrets" in MIGRATION


def test_hcs_vault_worker_is_persistent_and_has_no_duplicate_shopify_secret():
    service = COMPOSE.split("  hcs-vault-approval-worker:", 1)[1].split(
        "\n  evidence-sync:", 1
    )[0]
    assert 'profiles: ["hcs-vault-approval-worker"]' in service
    assert "orin_hcs_vault_draft_worker" in service
    assert "oauth_draft_worker_database_url" in service
    assert "hcs_shopify_access_token" not in service
    assert "SHOPIFY_CLIENT_SECRET" not in service
    assert 'ORIN_MODEL_WRITER_ENABLED: "0"' in service
    assert "restart: unless-stopped" in service
    assert "ports:" not in service


def test_hcs_vault_worker_cli_has_no_client_override():
    args = build_parser().parse_args(["once"])
    assert args.command == "once"
    assert not hasattr(args, "client_id")


def test_hcs_vault_worker_is_packaged_in_the_production_wheel():
    assert 'orin-hcs-vault-draft-worker = "orin_hcs_vault_draft_worker.cli:main"' in PYPROJECT
    assert '"src/orin_hcs_vault_draft_worker"' in PYPROJECT


def test_hcs_vault_runtime_config_is_server_context_only():
    runtime = _runtime_config(
        {
            "shopify": {
                "store_domain": "hcsgadgets-com.myshopify.com",
                "access_token": "server-side-vault-token",
                "api_version": "2026-07",
                "blog_id": "gid://shopify/Blog/89150259452",
                "author_name": "HCS GADGETS",
            }
        }
    )
    assert runtime.store_domain == "hcsgadgets-com.myshopify.com"
    assert runtime.access_token == "server-side-vault-token"
    assert runtime.blog_id == "gid://shopify/Blog/89150259452"
