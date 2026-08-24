from pathlib import Path


COMPOSE = Path("deploy/vps/compose.yml").read_text(encoding="utf-8")


def test_deployment_is_manual_and_not_publicly_routed():
    assert 'profiles: ["commissioner"]' in COMPOSE
    assert 'profiles: ["manual-api"]' in COMPOSE
    assert 'profiles: ["manual-worker"]' in COMPOSE
    assert 'profiles: ["automatic-worker"]' in COMPOSE
    assert 'profiles: ["hcs-dry-run-worker"]' in COMPOSE
    assert 'profiles: ["hcs-approval-worker"]' in COMPOSE
    assert 'profiles: ["generic-pilot-worker"]' in COMPOSE
    assert 'profiles: ["scheduler-trigger"]' in COMPOSE
    assert 'profiles: ["watchdog"]' in COMPOSE
    assert 'profiles: ["hcs-watchdog"]' in COMPOSE
    assert 'profiles: ["evidence-sync"]' in COMPOSE
    assert '"127.0.0.1:${ORIN_API_PORT:-58080}:8000"' in COMPOSE
    assert "traefik." not in COMPOSE.lower()
    assert "50083" not in COMPOSE
    assert "network_mode: host" not in COMPOSE
    assert COMPOSE.count("pull_policy: never") == 11
    assert ":latest" not in COMPOSE


def test_deployment_does_not_share_privileged_runtime_surfaces():
    assert "/var/run/docker.sock" not in COMPOSE
    assert "/data/.openclaw" not in COMPOSE
    assert "privileged:" not in COMPOSE
    assert COMPOSE.count("read_only: true") >= 6
    assert COMPOSE.count('cap_drop: ["ALL"]') == 11
    assert COMPOSE.count("no-new-privileges:true") == 11
    assert COMPOSE.count('restart: "no"') == 6
    assert COMPOSE.count("restart: unless-stopped") == 5


def test_database_credentials_are_file_backed_and_role_separated():
    assert (
        "ORIN_COMMISSIONER_DATABASE_URL_FILE: "
        "/run/secrets/commissioner_database_url"
    ) in COMPOSE
    assert "ORIN_COMMISSIONER_DATABASE_ROLE: orin_commissioner" in COMPOSE
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
    assert "ORIN_WATCHDOG_DATABASE_URL_FILE: /run/secrets/hcs_watchdog_database_url" in COMPOSE
    assert "ORIN_DATABASE_URL:" not in COMPOSE
    assert "ORIN_WORKER_DATABASE_URL:" not in COMPOSE
    assert "ORIN_SCHEDULER_DATABASE_URL:" not in COMPOSE
    assert "ORIN_WATCHDOG_DATABASE_URL:" not in COMPOSE
    assert "ORIN_COMMISSIONER_DATABASE_URL:" not in COMPOSE
    assert "service_role" not in COMPOSE
    assert "postgresql://" not in COMPOSE


def test_hcs_watchdog_is_fixed_read_only_and_has_no_shopify_surface():
    watchdog = COMPOSE.split("  hcs-watchdog:", 1)[1].split(
        "\n  scheduler-trigger:", 1
    )[0]
    assert 'user: "10008:${ORIN_RUNTIME_GID:-1000}"' in watchdog
    assert "ORIN_WATCHDOG_DATABASE_ROLE: orin_hcs_watchdog" in watchdog
    assert "ORIN_WATCHDOG_CLIENT_ID: hcs_gadgets" in watchdog
    assert "ORIN_WATCHDOG_SCHEDULER_OWNER: prefect:orin-hcs-prod" in watchdog
    assert "ORIN_WATCHDOG_SCHEDULE_NAME: orin-hcs-prod" in watchdog
    assert 'ORIN_WATCHDOG_EXPECTED_LOCAL_MINUTE: "30"' in watchdog
    assert "ORIN_WATCHDOG_REQUIRE_APPROVED_DRAFT_WRITES_DISABLED" in watchdog
    assert 'ORIN_WATCHDOG_DRY_RUN_ONLY: "true"' in watchdog
    assert "CHECK ORIN-HCS WATCHDOG V1" in watchdog
    assert "shopify_access_token" not in watchdog
    assert "writer_api_key" not in watchdog
    installer = Path("deploy/vps/install_hcs_watchdog_db_secret.sh").read_text(
        encoding="utf-8"
    )
    preflight = Path("deploy/vps/preflight.sh").read_text(encoding="utf-8")
    focused_preflight = Path("deploy/vps/hcs_watchdog_preflight.sh").read_text(
        encoding="utf-8"
    )
    client = Path(
        "deploy/openclaw/orin-hcs-watchdog/bin/orin_hcs_watchdog_check.py"
    ).read_text(encoding="utf-8")
    assert 'target="${secrets_dir}/hcs_watchdog_database_url"' in installer
    assert '"${first}" != *"orin_hcs_watchdog"*' in installer
    assert 'chown 10008:10008 "${temporary}"' in installer
    assert "--require-hcs-watchdog-secret" in preflight
    assert "[hcs_watchdog_database_url]=10008" in preflight
    assert "hcs_watchdog_database_url" in focused_preflight
    assert "10008:10008 mode 0400" in focused_preflight
    assert "hcs-watchdog" in focused_preflight
    assert "orin-hcs-watchdog.sock" in client
    assert 'REQUEST_LINE = b"CHECK ORIN-HCS WATCHDOG V1\\n"' in client


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
    assert "--client-id\n      - hoverboard_store" in worker
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


def test_hcs_workers_have_non_overlapping_credentials_and_modes():
    worker = COMPOSE.split("  hcs-dry-run-worker-daemon:", 1)[1].split(
        "\n  hcs-approval-worker:", 1
    )[0]
    approval = COMPOSE.split("  hcs-approval-worker:", 1)[1].split(
        "\n  evidence-sync:", 1
    )[0]
    assert 'profiles: ["hcs-dry-run-worker"]' in worker
    assert "--client-id\n      - hcs_gadgets" in worker
    assert "orin-hcs-prod" in worker
    assert "ORIN_WORKER_DATABASE_ROLE: orin_hcs_worker" in worker
    assert "hcs_worker_database_url" in worker
    assert 'ORIN_MODEL_WRITER_ENABLED: "${ORIN_HCS_MODEL_WRITER_ENABLED:-0}"' in worker
    assert "ORIN_WRITER_API_KEY_FILE: /run/secrets/hcs_writer_api_key" in worker
    assert "hcs_writer_api_key" in worker
    assert "hcs_shopify_access_token" not in worker
    assert "HCS_GADGETS_SHOPIFY_ACCESS_TOKEN_FILE" not in worker
    assert 'profiles: ["hcs-approval-worker"]' in approval
    assert 'user: "10006:${ORIN_RUNTIME_GID:-1000}"' in approval
    assert "ORIN_WORKER_DATABASE_ROLE: orin_hcs_shopify_worker" in approval
    assert "hcs_shopify_worker_database_url" in approval
    assert 'ORIN_MODEL_WRITER_ENABLED: "0"' in approval
    assert "hcs_writer_api_key" not in approval
    assert "HCS_GADGETS_SHOPIFY_ACCESS_TOKEN_FILE: /run/secrets/hcs_shopify_access_token" in approval
    assert "hcs_shopify_access_token" in approval
    assert "- once" in approval
    assert "restart: \"no\"" in approval
    assert "- serve" not in approval
    assert "HOVERBOARD_STORE_SHOPIFY" not in worker + approval
    assert (
        "source: ${ORIN_RUNTIME_ROOT:?set ORIN_RUNTIME_ROOT}/clients/hcs_gadgets"
        in worker and "source: ${ORIN_RUNTIME_ROOT:?set ORIN_RUNTIME_ROOT}/clients/hcs_gadgets" in approval
    )
    assert "target: /runtime/clients/hcs_gadgets" in worker + approval
    assert "source: ${ORIN_RUNTIME_ROOT:?set ORIN_RUNTIME_ROOT}\n" not in worker
    assert (
        "source: ${ORIN_EVIDENCE_ROOT:?set ORIN_EVIDENCE_ROOT}/hcs_gadgets"
        in worker
    )
    assert "target: /evidence" in worker
    assert "source: ${ORIN_EVIDENCE_ROOT:?set ORIN_EVIDENCE_ROOT}/hcs_gadgets/approval" in approval
    assert "--as-of-date" not in worker
    assert "--job-number" not in worker
    assert "ports:" not in worker
    assert "ports:" not in approval


def test_hcs_worker_secret_installer_and_preflight_are_uid_scoped():
    installer = Path("deploy/vps/install_hcs_worker_db_secret.sh").read_text(
        encoding="utf-8"
    )
    preflight = Path("deploy/vps/preflight.sh").read_text(encoding="utf-8")
    storage = Path("deploy/vps/prepare_hcs_worker_storage.sh").read_text(
        encoding="utf-8"
    )
    writer_installer = Path("deploy/vps/install_hcs_writer_secret.sh").read_text(
        encoding="utf-8"
    )
    shopify_installer = Path("deploy/vps/install_hcs_shopify_secret.sh").read_text(
        encoding="utf-8"
    )
    approval_installer = Path(
        "deploy/vps/install_hcs_shopify_worker_db_secret.sh"
    ).read_text(encoding="utf-8")
    assert 'target="${secrets_dir}/hcs_worker_database_url"' in installer
    assert '"${first}" != *"orin_hcs_worker"*' in installer
    assert 'chown 10005:10005 "${temporary}"' in installer
    assert 'chmod 0400 "${temporary}"' in installer
    assert "--require-hcs-worker-secret" in preflight
    assert "[hcs_worker_database_url]=10005" in preflight
    assert 'target="${secrets_dir}/hcs_writer_api_key"' in writer_installer
    assert 'chown 10005:"${runtime_gid}" "${temporary}"' in writer_installer
    assert 'chmod 0400 "${temporary}"' in writer_installer
    assert "--require-hcs-writer-secret" in preflight
    assert "[hcs_writer_api_key]=10005" in preflight
    assert 'target="${secrets_dir}/hcs_shopify_access_token"' in shopify_installer
    assert 'chown 10006:"${runtime_gid}" "${temporary}"' in shopify_installer
    assert 'chmod 0400 "${temporary}"' in shopify_installer
    assert "--require-hcs-shopify-secret" in preflight
    assert "[hcs_shopify_access_token]=10006" in preflight
    assert 'target="${secrets_dir}/hcs_shopify_worker_database_url"' in approval_installer
    assert 'chown 10006:10006 "${temporary}"' in approval_installer
    assert "--require-hcs-approval-worker-secret" in preflight
    assert "[hcs_shopify_worker_database_url]=10006" in preflight
    assert 'hcs_evidence_root="${ORIN_EVIDENCE_ROOT}/hcs_gadgets"' in preflight
    assert 'hcs_runtime_root="${ORIN_RUNTIME_ROOT}/clients/hcs_gadgets"' in preflight
    assert "product_truth_normalised.json" in preflight
    assert "product_truth_link_map.json" in preflight
    assert 'target="${evidence_root}/hcs_gadgets"' in storage
    assert 'install -d -m 0710 -o 10005 -g "${runtime_gid}"' in storage
    assert 'install -d -m 0700 -o 10006 -g "${runtime_gid}"' in storage
    readme = Path("deploy/vps/README.md").read_text(encoding="utf-8")
    assert "install_hcs_writer_secret.sh" in readme
    assert "--require-hcs-writer-secret" in readme


def test_hcs_worker_build_fails_if_source_commit_and_image_tag_diverge():
    build = Path("deploy/vps/build_hcs_worker.sh").read_text(encoding="utf-8")
    assert 'actual_sha="$(git -c safe.directory=' in build
    assert 'if [[ "${actual_sha}" != "${deploy_sha}" ]]' in build
    assert 'image="local/orin-worker:${deploy_sha}"' in build
    assert 'if [[ "${image_revision}" != "${deploy_sha}" ]]' in build
    assert '"serve", "--client-id", "hcs_gadgets"' in build
    assert '"once", "--client-id", "hcs_gadgets"' in build


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
    assert 'test: ["CMD", "python", "-m", "orin_scheduler_trigger.healthcheck"]' in trigger
    assert "interval: 60s" in trigger
    assert "timeout: 15s" in trigger


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
