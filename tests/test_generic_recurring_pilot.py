from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from orin_pilot_worker.runner import execute_generic_pilot
from orin_worker.models import ClaimedJob


MIGRATION = Path(
    "supabase/migrations/20260826113000_generic_recurring_pilot.sql"
).read_text(encoding="utf-8")


def test_shared_scheduler_role_is_function_only_and_shopify_blind():
    assert "create role orin_tenant_prefect_scheduler nologin" in MIGRATION
    assert "revoke all on all tables in schema public" in MIGRATION
    assert "grant execute on function orin_private.enqueue_due_tenant_prefect_jobs()" in MIGRATION
    scheduler_role_lines = "\n".join(
        line for line in MIGRATION.splitlines()
        if "orin_tenant_prefect_scheduler" in line
    )
    assert "grant select" not in scheduler_role_lines.lower()
    assert "to orin_tenant_prefect_scheduler" not in MIGRATION.split(
        "grant select (", 1
    )[1].split(";", 1)[0].lower()
    enqueue = MIGRATION.split(
        "create or replace function orin_private.enqueue_due_tenant_prefect_jobs()", 1
    )[1].split("create or replace function orin_private.claim_next_generic_pilot_job", 1)[0]
    assert "requested_mode" in enqueue and "'dry-run'" in enqueue
    assert "shopify_writes_enabled" in enqueue
    assert "shopify_create" not in enqueue.lower()
    assert "shopify_token" not in enqueue.lower()
    assert "pg_advisory_xact_lock" in enqueue


def test_activation_preserves_approval_only_drafts_but_never_opens_broad_writes():
    activation = MIGRATION.split(
        "create or replace function public.service_activate_client_recurring_pilot", 1
    )[1].split("create or replace function orin_private.enqueue_due_tenant_prefect_jobs", 1)[0]
    assert "shopify_writes_enabled = false" in activation
    assert "approved_draft_writes_enabled = true" not in activation
    assert "scheduler_owner = 'prefect:orin-tenant-pilot'" in activation
    assert "statement_timestamp() + interval '2 minutes'" in activation


def test_empty_recurring_run_completes_without_model_or_shopify(tmp_path, monkeypatch):
    monkeypatch.setenv("ORIN_CODE_VERSION", "test-revision")
    job = ClaimedJob(
        job_id=uuid4(),
        client_id="orin_oauth_test",
        request_id=uuid4(),
        requested_mode="dry-run",
        attempt_count=1,
        payload={},
        lease_expires_at=datetime.now(timezone.utc),
    )
    result = execute_generic_pilot(
        job,
        context={"client_id": "orin_oauth_test", "source_kind": "recurring", "content_item": None},
        artifact_root=tmp_path,
    )
    assert result["status"] == "completed"
    assert result["decision"] == "no_job_due"
    assert result["shopify_create_count"] == 0
    assert result["shopify_published"] is False
    assert result["queue_changed"] is False
    assert Path(result["artifact_uri"], "scheduler_receipt.json").is_file()
