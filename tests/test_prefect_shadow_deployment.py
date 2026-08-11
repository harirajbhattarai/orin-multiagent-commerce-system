from pathlib import Path


COMPOSE = Path("deploy/prefect-shadow/compose.yml").read_text(encoding="utf-8")
ENTRYPOINT = Path("deploy/prefect-shadow/entrypoint.sh").read_text(encoding="utf-8")
MIGRATION = Path(
    "supabase/migrations/20260804153033_phase7_prefect_shadow_role.sql"
).read_text(encoding="utf-8")
OWNER_MIGRATION = Path(
    "supabase/migrations/20260811002121_phase7_prefect_ownership_commissioning.sql"
).read_text(encoding="utf-8")
SCHEDULER_MIGRATION = Path(
    "supabase/migrations/20260811082754_phase7_prefect_recurring_dry_run.sql"
).read_text(encoding="utf-8")
BOOTSTRAP = Path("src/orin_prefect_shadow/bootstrap.py").read_text(
    encoding="utf-8"
)


def service(name: str, next_name: str | None) -> str:
    body = COMPOSE.split(f"  {name}:", 1)[1]
    if next_name:
        body = body.split(f"\n  {next_name}:", 1)[0]
    return body


def test_every_prefect_service_is_disabled_by_default_and_pinned():
    assert COMPOSE.count("profiles:") == 5
    assert ":latest" not in COMPOSE
    assert "prefecthq/prefect:3.8.1" not in COMPOSE
    assert "postgres:16.10-bookworm@sha256:" in COMPOSE
    assert "pull_policy: never" in COMPOSE


def test_server_is_loopback_only_and_has_no_traefik_or_docker_socket():
    assert '"127.0.0.1:${ORIN_PREFECT_UI_PORT:-54200}:4200"' in COMPOSE
    assert (
        "PREFECT_SERVER_UI_STATIC_DIRECTORY: "
        "/home/orin-prefect/.prefect/ui"
    ) in COMPOSE
    assert (
        "/home/orin-prefect/.prefect:rw,noexec,nosuid,size=96m,"
        "uid=10004,gid=10004"
    ) in COMPOSE
    assert "traefik." not in COMPOSE.lower()
    assert "/var/run/docker.sock" not in COMPOSE
    assert "network_mode: host" not in COMPOSE
    assert "privileged:" not in COMPOSE


def test_shadow_worker_has_only_its_read_only_database_secret():
    worker = service("prefect-shadow-worker", "prefect-owner-worker")
    assert "shadow_database_url" in worker
    assert "prefect_api_auth" in worker
    assert "shopify" not in worker.lower()
    assert "worker_database_url" not in worker
    assert "scheduler_database_url" not in worker
    assert "control_database_url" not in worker
    assert "writer_api_key" not in worker
    assert "--limit 1" not in worker  # fixed in the immutable entrypoint
    assert 'PREFECT_RUNNER_PROCESS_LIMIT: "1"' in worker
    assert "--limit 1" in ENTRYPOINT
    assert "--no-create-pool-if-not-found" in ENTRYPOINT
    assert "--install-policy never" in ENTRYPOINT


def test_owner_worker_has_only_its_fixed_commissioning_secret():
    worker = service("prefect-owner-worker", None).split("\nsecrets:", 1)[0]
    assert "owner_database_url" in worker
    assert "prefect_api_auth" in worker
    assert "shopify" not in worker.lower()
    assert "shadow_database_url" not in worker
    assert "worker_database_url" not in worker
    assert "scheduler_database_url" not in worker
    assert "control_database_url" not in worker
    assert "writer_api_key" not in worker
    assert 'restart: "no"' in worker
    assert 'PREFECT_RUNNER_PROCESS_LIMIT: "1"' in worker
    assert "--pool orin-owner-process" in ENTRYPOINT
    assert "--name orin-hbstore-prefect-scheduler-1" in ENTRYPOINT


def test_bootstrap_and_worker_do_not_receive_prefect_database_password():
    bootstrap = service("prefect-bootstrap", "prefect-shadow-worker")
    worker = service("prefect-shadow-worker", "prefect-owner-worker")
    owner = service("prefect-owner-worker", None).split("\nsecrets:", 1)[0]
    assert "prefect_server_database_password" not in bootstrap
    assert "prefect_postgres_password" not in bootstrap
    assert "prefect_server_database_password" not in worker
    assert "prefect_postgres_password" not in worker
    assert "prefect_server_database_password" not in owner
    assert "prefect_postgres_password" not in owner


def test_database_role_has_one_function_and_no_direct_table_grants():
    assert "grant execute on function orin_private.get_prefect_shadow_snapshot(text)" in MIGRATION
    assert "grant select" not in MIGRATION.lower()
    assert "enqueue_hoverboard_scheduled_job" not in MIGRATION
    assert "claim_next_job" not in MIGRATION
    assert "complete_job" not in MIGRATION
    assert "p_client_id is distinct from 'hoverboard_store'" in MIGRATION


def test_owner_role_is_separate_and_dry_run_only():
    assert "create role orin_prefect_scheduler" in OWNER_MIGRATION
    assert "grant select" not in OWNER_MIGRATION.lower()
    assert (
        "grant execute on function "
        "orin_private.enqueue_hoverboard_prefect_commissioning_job()"
    ) in OWNER_MIGRATION
    assert "v_access.allowed_mode <> 'dry-run'" in OWNER_MIGRATION
    assert "v_access.shopify_writes_enabled" in OWNER_MIGRATION
    assert "prefect:orin-hbstore-prod" in OWNER_MIGRATION
    assert "pg_advisory_xact_lock" in OWNER_MIGRATION


def test_daily_prefect_boundary_replaces_commissioning_access_safely():
    assert "enqueue_hoverboard_prefect_scheduled_job()" in SCHEDULER_MIGRATION
    assert "revoke all on all tables" in SCHEDULER_MIGRATION
    assert "grant select" not in SCHEDULER_MIGRATION.lower()
    assert "v_access.allowed_mode <> 'dry-run'" in SCHEDULER_MIGRATION
    assert "v_access.shopify_writes_enabled" in SCHEDULER_MIGRATION
    assert "prefect:orin-hbstore-prod" in SCHEDULER_MIGRATION
    assert "pg_advisory_xact_lock" in SCHEDULER_MIGRATION
    assert "orin-scheduler-v1:" in SCHEDULER_MIGRATION
    assert (
        "revoke all on function "
        "orin_private.enqueue_hoverboard_prefect_commissioning_job()"
        in SCHEDULER_MIGRATION
    )


def test_daily_prefect_schedule_is_exact_and_disabled_by_default():
    assert 'SCHEDULER_CRON = "0 11 * * *"' in BOOTSTRAP
    assert 'SCHEDULER_TIMEZONE = "Europe/London"' in BOOTSTRAP
    assert 'SCHEDULER_SLUG = "hbstore-daily-dry-run"' in BOOTSTRAP
    assert "hbstore_daily_scheduler_flow.to_deployment" in BOOTSTRAP
    assert "paused=True" in BOOTSTRAP
    assert "active=False" in BOOTSTRAP
    assert "CANCEL_NEW" in BOOTSTRAP
