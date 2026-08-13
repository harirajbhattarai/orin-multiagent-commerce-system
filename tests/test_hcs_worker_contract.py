from pathlib import Path


MIGRATION = Path(
    "supabase/migrations/20260814003000_hcs_dedicated_dry_run_worker.sql"
).read_text(encoding="utf-8")


def test_hcs_role_is_nologin_and_can_only_use_scoped_claim_functions():
    assert "create role orin_hcs_worker nologin" in MIGRATION
    assert "p_client_id is distinct from 'hcs_gadgets'" in MIGRATION
    assert "candidate.client_id = p_client_id" in MIGRATION
    assert "candidate.requested_mode = 'dry-run'" in MIGRATION
    assert "not settings.shopify_writes_enabled" in MIGRATION
    assert "not settings.approved_draft_writes_enabled" in MIGRATION
    assert "grant execute on function orin_private.claim_next_job(" not in MIGRATION
    assert "grant execute on function orin_private.materialize_next_content_decision(" not in MIGRATION


def test_cross_client_exact_topic_and_body_reuse_is_blocked():
    assert "content_plan_items_global_topic_identity_idx" in MIGRATION
    assert "content_drafts_global_body_identity_idx" in MIGRATION
    assert "create unique index" in MIGRATION
