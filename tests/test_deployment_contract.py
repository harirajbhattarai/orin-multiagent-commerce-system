from pathlib import Path


COMPOSE = Path("deploy/vps/compose.yml").read_text(encoding="utf-8")


def test_deployment_is_manual_and_not_publicly_routed():
    assert 'profiles: ["manual-api"]' in COMPOSE
    assert 'profiles: ["manual-worker"]' in COMPOSE
    assert 'profiles: ["automatic-worker"]' in COMPOSE
    assert 'profiles: ["scheduler-trigger"]' in COMPOSE
    assert 'profiles: ["watchdog"]' in COMPOSE
    assert 'profiles: ["evidence-sync"]' in COMPOSE
    assert '"127.0.0.1:${ORIN_API_PORT:-58080}:8000"' in COMPOSE
    assert "traefik." not in COMPOSE.lower()
    assert "50083" not in COMPOSE
    assert "network_mode: host" not in COMPOSE
    assert COMPOSE.count("pull_policy: never") == 6
    assert ":latest" not in COMPOSE


def test_deployment_does_not_share_privileged_runtime_surfaces():
    assert "/var/run/docker.sock" not in COMPOSE
    assert "/data/.openclaw" not in COMPOSE
    assert "privileged:" not in COMPOSE
    assert COMPOSE.count("read_only: true") >= 6
    assert COMPOSE.count('cap_drop: ["ALL"]') == 6
    assert COMPOSE.count("no-new-privileges:true") == 6
    assert COMPOSE.count('restart: "no"') == 4
    assert COMPOSE.count("restart: unless-stopped") == 2


def test_database_credentials_are_file_backed_and_role_separated():
    assert "ORIN_DATABASE_URL_FILE: /run/secrets/control_database_url" in COMPOSE
    assert "ORIN_WORKER_DATABASE_URL_FILE: /run/secrets/worker_database_url" in COMPOSE
    assert (
        "ORIN_SCHEDULER_DATABASE_URL_FILE: /run/secrets/scheduler_database_url"
        in COMPOSE
    )
    assert (
        "ORIN_WATCHDOG_DATABASE_URL_FILE: /run/secrets/watchdog_database_url"
        in COMPOSE
    )
    assert "ORIN_DATABASE_URL:" not in COMPOSE
    assert "ORIN_WORKER_DATABASE_URL:" not in COMPOSE
    assert "ORIN_SCHEDULER_DATABASE_URL:" not in COMPOSE
    assert "ORIN_WATCHDOG_DATABASE_URL:" not in COMPOSE
    assert "service_role" not in COMPOSE
    assert "postgresql://" not in COMPOSE


def test_shopify_credential_is_file_backed_and_namespaced():
    assert (
        "HOVERBOARD_STORE_SHOPIFY_ACCESS_TOKEN_FILE: "
        "/run/secrets/hoverboard_shopify_access_token"
    ) in COMPOSE
    assert "HOVERBOARD_STORE_SHOPIFY_ACCESS_TOKEN:" not in COMPOSE
    assert (
        "${ORIN_SECRETS_DIR:?set ORIN_SECRETS_DIR}/"
        "hoverboard_shopify_access_token"
    ) in COMPOSE
    assert (
        "HOVERBOARD_STORE_SHOPIFY_STORE_DOMAIN: 5a1679-88.myshopify.com"
    ) in COMPOSE
    assert "HOVERBOARD_STORE_SHOPIFY_API_VERSION: \"2026-07\"" in COMPOSE
    assert "HOVERBOARD_STORE_SHOPIFY_BLOG_ID: \"113430790492\"" in COMPOSE


def test_model_writer_is_pinned_opt_in_and_file_backed():
    assert 'ORIN_MODEL_WRITER_ENABLED: "${ORIN_MODEL_WRITER_ENABLED:-0}"' in COMPOSE
    assert "ORIN_WRITER_API_KEY_FILE: /run/secrets/writer_api_key" in COMPOSE
    assert "ORIN_WRITER_API_KEY:" not in COMPOSE
    assert "${ORIN_SECRETS_DIR:?set ORIN_SECRETS_DIR}/writer_api_key" in COMPOSE
    assert "ORIN_WRITER_TIMEOUT_SECONDS: \"240\"" in COMPOSE


def test_worker_has_scoped_content_write_access_and_private_evidence():
    worker = COMPOSE.split("  worker:", 1)[1].split(
        "\n  worker-daemon:", 1
    )[0]
    assert "ports:" not in worker
    assert "ORIN_REPO_ROOT: /app" in worker
    assert "target: /runtime\n        read_only: true" in worker
    assert (
        "source: ${ORIN_RUNTIME_ROOT:?set ORIN_RUNTIME_ROOT}/clients/"
        "hoverboard_store/content_engine"
    ) in worker
    assert "target: /runtime/clients/hoverboard_store/content_engine" in worker
    assert "target: /evidence" in worker
    assert "--artifact-root" in worker


def test_automatic_worker_is_fixed_scope_and_not_publicly_routed():
    worker = COMPOSE.split("  worker-daemon:", 1)[1].split(
        "\nsecrets:", 1
    )[0]
    assert "ports:" not in worker
    assert "serve" in worker
    assert "--worker-id" in worker
    assert "orin-hbstore-prod" in worker
    assert "--as-of-date" not in worker
    assert "--job-number" not in worker
    assert "restart: unless-stopped" in worker
    assert "stop_grace_period: 300s" in worker
    assert "target: /runtime\n        read_only: true" in worker
    assert (
        "source: ${ORIN_RUNTIME_ROOT:?set ORIN_RUNTIME_ROOT}/clients/"
        "hoverboard_store/content_engine"
    ) in worker
    assert "target: /runtime/clients/hoverboard_store/content_engine" in worker
    assert "/var/run/docker.sock" not in worker


def test_scheduler_trigger_is_fixed_input_socket_only_and_credential_isolated():
    trigger = COMPOSE.split("  scheduler-trigger:", 1)[1].split(
        "\n  control-api:", 1
    )[0]
    assert 'user: "10002:${ORIN_RUNTIME_GID:-1000}"' in trigger
    assert "ports:" not in trigger
    assert "target: /run/orin" in trigger
    assert "ORIN_SCHEDULER_SOCKET_PATH: /run/orin/orin-hbstore-trigger.sock" in trigger
    assert 'ORIN_SCHEDULER_ALLOWED_PEER_UID: "${ORIN_RUNTIME_UID:-1000}"' in trigger
    assert "scheduler_database_url" in trigger
    assert "worker_database_url" not in trigger
    assert "hoverboard_shopify_access_token" not in trigger
    assert "writer_api_key" not in trigger


def test_watchdog_is_socket_only_read_only_and_credential_isolated():
    watchdog = COMPOSE.split("  watchdog:", 1)[1].split(
        "\n  scheduler-trigger:", 1
    )[0]
    assert 'user: "10003:${ORIN_RUNTIME_GID:-1000}"' in watchdog
    assert "local/orin-watchdog:${ORIN_WATCHDOG_DEPLOY_SHA" in watchdog
    assert "local/orin-watchdog:${ORIN_DEPLOY_SHA" not in watchdog
    assert "ports:" not in watchdog
    assert "restart: unless-stopped" in watchdog
    assert "timeout: 15s" in watchdog
    assert "watchdog_database_url" in watchdog
    assert "orin-hbstore-watchdog.sock" in watchdog
    assert "ORIN_WATCHDOG_ALLOWED_PEER_UID" in watchdog
    assert "target: /run/orin" in watchdog
    assert (
        "source: ${ORIN_TRIGGER_SOCKET_DIR:?set ORIN_TRIGGER_SOCKET_DIR}/watchdog"
        in watchdog
    )
    assert (
        "/data/.openclaw/run/orin/watchdog/orin-hbstore-watchdog.sock"
        in Path(
            "deploy/openclaw/orin-watchdog/bin/orin_watchdog_check.py"
        ).read_text(encoding="utf-8")
    )
    assert "scheduler_database_url" not in watchdog
    assert "worker_database_url" not in watchdog
    assert "control_database_url" not in watchdog
    assert "hoverboard_shopify_access_token" not in watchdog
    assert "writer_api_key" not in watchdog
    assert "/var/run/docker.sock" not in watchdog


def test_non_watchdog_services_remain_pinned_to_runtime_revision():
    non_watchdog = COMPOSE.split("\n  scheduler-trigger:", 1)[1]
    assert "ORIN_WATCHDOG_DEPLOY_SHA" not in non_watchdog
    assert non_watchdog.count("${ORIN_DEPLOY_SHA") >= 4


def test_evidence_sync_is_one_shot_read_only_and_credential_isolated():
    service = COMPOSE.split("  evidence-sync:", 1)[1].split("\nsecrets:", 1)[0]
    assert 'profiles: ["evidence-sync"]' in service
    assert 'restart: "no"' in service
    assert "ports:" not in service
    assert "target: /evidence\n        read_only: true" in service
    assert "ORIN_EVIDENCE_SERVICE_KEY_FILE: /run/secrets/evidence_service_key" in service
    assert "worker_database_url" not in service
    assert "hoverboard_shopify_access_token" not in service
    assert "writer_api_key" not in service
    assert "/var/run/docker.sock" not in service
