from pathlib import Path


MIGRATION = Path(
    "supabase/migrations/20260905143000_queue_requested_content_revisions.sql"
).read_text(encoding="utf-8")


def test_consumed_change_requests_queue_one_dry_run_job():
    assert "content_decisions_queue_consumed_revision" in MIGRATION
    assert "old.processing_status <> 'recorded'" in MIGRATION
    assert "new.processing_status <> 'consumed'" in MIGRATION
    assert "new.decision <> 'request_changes'" in MIGRATION
    assert "new.content_job_id is not null" in MIGRATION
    assert "'decision:' || new.decision_id::text" in MIGRATION
    assert "'dry-run'" in MIGRATION
    assert "'{}'::jsonb" in MIGRATION


def test_revision_handoff_is_limited_to_the_two_dedicated_workers():
    assert "new.client_id not in ('hoverboard_store', 'hcs_gadgets')" in MIGRATION
    assert "set status = 'in_progress'" in MIGRATION
    assert "Revision draft-generation job queued." in MIGRATION


def test_worker_snapshot_binds_the_exact_revision_note_to_its_job():
    assert "decision.content_job_id = v_job.job_id" in MIGRATION
    assert "decision.decision = 'request_changes'" in MIGRATION
    assert "'revision_request', v_revision_note" in MIGRATION
    assert "Human revision request (must be applied):" in MIGRATION


def test_revision_generation_does_not_open_a_shopify_write_path():
    trigger_body = MIGRATION.split(
        "create or replace function orin_private.queue_consumed_content_revision()",
        1,
    )[1].split("$$;", 1)[0]
    assert "requested_mode" in trigger_body
    assert "'dry-run'" in trigger_body
    assert "hidden-draft" not in trigger_body
    assert "shopify_writes_enabled" not in trigger_body
