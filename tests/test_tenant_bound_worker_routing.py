from pathlib import Path


MIGRATION = Path(
    "supabase/migrations/20260814111851_tenant_bound_worker_routing.sql"
).read_text(encoding="utf-8")
REPOSITORY = Path("src/orin_worker/repository.py").read_text(encoding="utf-8")
CLI = Path("src/orin_worker/cli.py").read_text(encoding="utf-8")


def test_stale_unbound_worker_loses_legacy_claim_privileges():
    assert (
        "revoke execute on function orin_private.materialize_next_content_decision()"
        in MIGRATION
    )
    assert (
        "revoke execute on function orin_private.claim_next_job(text, integer)"
        in MIGRATION
    )
    assert "from orin_worker;" in MIGRATION


def test_hoverboard_worker_functions_are_tenant_bound_and_least_privilege():
    assert "p_client_id is distinct from 'hoverboard_store'" in MIGRATION
    assert "where decision.client_id = p_client_id" in MIGRATION
    assert "where candidate.client_id = p_client_id" in MIGRATION
    assert "and claimed.client_id = p_client_id" in MIGRATION
    assert "for update of candidate skip locked" in MIGRATION
    assert (
        "grant execute on function orin_private.claim_next_job_for_client"
        in MIGRATION
    )
    assert "orin_hcs_worker;" in MIGRATION


def test_application_routes_each_client_to_its_matching_database_boundary():
    assert 'if self.client_id == "hoverboard_store"' in REPOSITORY
    assert "claim_next_job_for_client(" in REPOSITORY
    assert "materialize_next_content_decision_for_client(" in REPOSITORY
    assert "claim_next_dry_run_job_for_client(" in REPOSITORY
    assert "materialize_next_dry_run_decision_for_client(" in REPOSITORY
    assert "claim_next_hcs_approved_draft_job_for_client(" in REPOSITORY
    assert "materialize_next_hcs_approved_draft_decision_for_client(" in REPOSITORY
    assert '"hoverboard_store": {"orin_worker"}' in REPOSITORY
    assert '"hcs_gadgets": {"orin_hcs_worker", "orin_hcs_shopify_worker"}' in REPOSITORY


def test_every_worker_command_requires_a_supported_client_binding():
    assert "required=True" in CLI
    assert 'choices=("hoverboard_store", "hcs_gadgets")' in CLI
