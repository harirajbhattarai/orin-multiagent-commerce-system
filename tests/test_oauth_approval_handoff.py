from pathlib import Path


MIGRATION = Path(
    "supabase/migrations/20260829091501_oauth_approval_handoff.sql"
).read_text(encoding="utf-8")
EDGE_FUNCTION = Path(
    "supabase/functions/orin-client-onboarding/index.ts"
).read_text(encoding="utf-8")


def _function(name: str, next_name: str) -> str:
    return MIGRATION.split(name, 1)[1].split(next_name, 1)[0]


def test_handoff_pauses_only_the_generic_recurring_scheduler():
    begin = _function(
        "create or replace function public.service_begin_oauth_approval_handoff",
        "create or replace function public.service_bind_oauth_approval_handoff",
    )
    assert "p_client_id in ('hoverboard_store', 'hcs_gadgets')" in begin
    assert "for update" in begin
    assert "job.status in ('queued', 'leased', 'running')" in begin
    assert "incident.status <> 'resolved'" in begin
    assert "settings.approved_draft_writes_enabled" in begin
    assert "not settings.shopify_writes_enabled" in begin
    assert "settings.allowed_mode = 'dry-run'" in begin
    assert "set enabled = false" in begin
    assert "state = 'disabled', scheduler_owner = null" in begin


def test_handoff_materializes_only_the_exact_version_bound_decision():
    bind = _function(
        "create or replace function public.service_bind_oauth_approval_handoff",
        "create or replace function public.service_cancel_oauth_approval_handoff",
    )
    assert "v_decision.request_id <> v_handoff.request_id" in bind
    assert "v_decision.content_item_id <> v_handoff.content_item_id" in bind
    assert "v_decision.content_item_version <> v_handoff.content_item_version" in bind
    assert "v_decision.decision <> 'approve_hidden_draft'" in bind
    assert "materialize_next_oauth_approved_draft_decision" in bind


def test_success_restores_the_schedule_without_opening_broad_writes():
    restore = _function(
        "create or replace function orin_private.restore_oauth_approval_handoff",
        "create or replace function public.service_begin_oauth_approval_handoff",
    )
    complete = _function(
        "create or replace function orin_private.complete_oauth_approved_draft_job",
        "create or replace function orin_private.defer_oauth_approved_draft_job",
    )
    assert "set enabled = true" in restore
    assert "scheduler_owner = 'prefect:orin-tenant-pilot'" in restore
    assert "shopify_writes_enabled" not in restore
    assert "shopify_create_count" in complete
    assert "= 1" in complete
    assert "shopify_published" in complete
    assert "'completed'" in complete


def test_failure_is_fail_closed_and_edge_cancels_only_before_decision():
    cancel = _function(
        "create or replace function public.service_cancel_oauth_approval_handoff",
        "create or replace function orin_private.complete_oauth_approved_draft_job",
    )
    deferred = _function(
        "create or replace function orin_private.defer_oauth_approved_draft_job",
        "revoke all on function orin_private.restore_oauth_approval_handoff",
    )
    assert "content_decisions" in cancel
    assert "return query select v_handoff.handoff_id, v_handoff.status, false" in cancel
    assert "v_result.status = 'failed'" in deferred
    assert "'blocked'" in deferred
    assert 'p_error: "Approval preparation did not complete."' in EDGE_FUNCTION


def test_browser_roles_cannot_execute_service_handoff_functions():
    for signature in (
        "service_begin_oauth_approval_handoff",
        "service_bind_oauth_approval_handoff",
        "service_cancel_oauth_approval_handoff",
    ):
        block = MIGRATION.split(f"revoke all on function public.{signature}", 1)[1]
        assert "from public, anon, authenticated" in block.split(";", 1)[0]
    assert "grant execute on function public.service_begin_oauth_approval_handoff" in MIGRATION
    assert "to service_role" in MIGRATION
