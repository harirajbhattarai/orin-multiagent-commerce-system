from pathlib import Path


COMPOSE = Path("deploy/vps/compose.yml").read_text(encoding="utf-8")


def test_deployment_is_manual_and_not_publicly_routed():
    assert 'profiles: ["manual-api"]' in COMPOSE
    assert 'profiles: ["manual-worker"]' in COMPOSE
    assert '"127.0.0.1:${ORIN_API_PORT:-58080}:8000"' in COMPOSE
    assert "traefik." not in COMPOSE.lower()
    assert "50083" not in COMPOSE
    assert "network_mode: host" not in COMPOSE
    assert COMPOSE.count("pull_policy: never") == 2
    assert ":latest" not in COMPOSE


def test_deployment_does_not_share_privileged_runtime_surfaces():
    assert "/var/run/docker.sock" not in COMPOSE
    assert "/data/.openclaw" not in COMPOSE
    assert "privileged:" not in COMPOSE
    assert COMPOSE.count("read_only: true") >= 3
    assert COMPOSE.count('cap_drop: ["ALL"]') == 2
    assert COMPOSE.count("no-new-privileges:true") == 2
    assert COMPOSE.count('restart: "no"') == 2


def test_database_credentials_are_file_backed_and_role_separated():
    assert "ORIN_DATABASE_URL_FILE: /run/secrets/control_database_url" in COMPOSE
    assert "ORIN_WORKER_DATABASE_URL_FILE: /run/secrets/worker_database_url" in COMPOSE
    assert "ORIN_DATABASE_URL:" not in COMPOSE
    assert "ORIN_WORKER_DATABASE_URL:" not in COMPOSE
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


def test_worker_has_no_port_and_uses_read_only_runtime_plus_private_evidence():
    worker = COMPOSE.split("  worker:", 1)[1].split("\nsecrets:", 1)[0]
    assert "ports:" not in worker
    assert "target: /runtime\n        read_only: true" in worker
    assert "target: /evidence" in worker
    assert "--artifact-root" in worker
