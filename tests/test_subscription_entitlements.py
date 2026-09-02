from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "supabase/migrations/20260902142655_subscription_entitlements.sql"


def test_subscription_contract_is_tenant_scoped_and_read_only():
    sql = MIGRATION.read_text()

    assert "alter table public.client_subscriptions enable row level security" in sql
    assert "membership.user_id = (select auth.uid())" in sql
    assert "grant select (" in sql
    assert "grant insert" not in sql
    assert "grant update" not in sql
    assert "grant delete" not in sql
    assert "with (security_invoker = true)" in sql


def test_subscription_entitlement_fails_closed_without_touching_shopify_gates():
    sql = MIGRATION.read_text()

    assert "content_plan_items_enforce_subscription" in sql
    assert "monthly article allowance reached" in sql
    assert "pg_advisory_xact_lock" in sql
    assert "insert into public.content_jobs" not in sql
    assert "update public.client_runtime_settings" not in sql
    assert "update public.scheduler_health" not in sql
    assert "can_publish_live boolean not null default false" in sql
    assert "check (not can_publish_live)" in sql


def test_follow_up_usage_view_preserves_the_redacted_content_plan_grant():
    sql = (
        ROOT
        / "supabase/migrations/20260902145402_fix_subscription_usage_view.sql"
    ).read_text()

    assert "item.source_document" not in sql
    assert "grant select" not in sql
    assert "create or replace view public.client_subscription_summary" in sql
