#!/usr/bin/env bash
set -euo pipefail

require_shadow_secret=false
require_owner_secret=false
require_hcs_owner_secret=false
require_tenant_owner_secret=false
allow_running_server=false
for argument in "$@"; do
  case "${argument}" in
    --require-shadow-secret) require_shadow_secret=true ;;
    --require-owner-secret) require_owner_secret=true ;;
    --require-hcs-owner-secret) require_hcs_owner_secret=true ;;
    --require-tenant-owner-secret) require_tenant_owner_secret=true ;;
    --allow-running-server) allow_running_server=true ;;
    *)
      echo "usage: $0 [--require-shadow-secret] [--require-owner-secret] [--require-hcs-owner-secret] [--require-tenant-owner-secret] [--allow-running-server]" >&2
      exit 2
      ;;
  esac
done

: "${ORIN_PREFECT_DEPLOY_SHA:?set ORIN_PREFECT_DEPLOY_SHA}"
: "${ORIN_PREFECT_PROJECT_ROOT:?set ORIN_PREFECT_PROJECT_ROOT}"
: "${ORIN_PREFECT_SECRETS_DIR:?set ORIN_PREFECT_SECRETS_DIR}"
: "${ORIN_PREFECT_UI_PORT:=54200}"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Prefect preflight must run as root on the VPS" >&2
  exit 1
fi
if [[ ! "${ORIN_PREFECT_DEPLOY_SHA}" =~ ^[0-9a-f]{40}$ ]]; then
  echo "ORIN_PREFECT_DEPLOY_SHA must be an exact 40-character commit" >&2
  exit 1
fi
if [[ -n "$(git -c safe.directory="${ORIN_PREFECT_PROJECT_ROOT}" -C "${ORIN_PREFECT_PROJECT_ROOT}" status --porcelain)" ]]; then
  echo "canonical Git checkout is not clean" >&2
  exit 1
fi
actual_sha="$(git -c safe.directory="${ORIN_PREFECT_PROJECT_ROOT}" -C "${ORIN_PREFECT_PROJECT_ROOT}" rev-parse HEAD)"
if [[ "${actual_sha}" != "${ORIN_PREFECT_DEPLOY_SHA}" ]]; then
  echo "checkout mismatch: expected ${ORIN_PREFECT_DEPLOY_SHA}, received ${actual_sha}" >&2
  exit 1
fi
if ss -H -ltn "sport = :${ORIN_PREFECT_UI_PORT}" | grep -q .; then
  if [[ "${allow_running_server}" != true ]]; then
    echo "loopback Prefect port ${ORIN_PREFECT_UI_PORT} is already in use" >&2
    exit 1
  fi
  running_health="$(docker inspect orin-prefect-shadow-prefect-server-1 \
    --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' \
    2>/dev/null || true)"
  if [[ "${running_health}" != "healthy" ]]; then
    echo "existing Prefect server is not healthy" >&2
    exit 1
  fi
fi

compose_file="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/compose.yml"
if [[ -n "$(docker compose --env-file /dev/null -f "${compose_file}" config --services)" ]]; then
  echo "Prefect deployment has an unprofiled default service" >&2
  exit 1
fi
docker compose --env-file /dev/null -f "${compose_file}" --profile "*" config --quiet

declare -A expected_uid=(
  [prefect_postgres_password]=999
  [prefect_server_database_password]=10004
  [prefect_api_auth]=10004
  [hcs_prefect_api_auth]=10007
  [shadow_database_url]=10004
  [owner_database_url]=10004
  [hcs_owner_database_url]=10007
  [tenant_prefect_api_auth]=10010
  [tenant_owner_database_url]=10010
)
secret_names=(
  prefect_postgres_password
  prefect_server_database_password
  prefect_api_auth
)
if [[ "${require_shadow_secret}" == true ]]; then
  secret_names+=(shadow_database_url)
fi
if [[ "${require_owner_secret}" == true ]]; then
  secret_names+=(owner_database_url)
fi
if [[ "${require_hcs_owner_secret}" == true ]]; then
  secret_names+=(hcs_owner_database_url hcs_prefect_api_auth)
fi
if [[ "${require_tenant_owner_secret}" == true ]]; then
  secret_names+=(tenant_owner_database_url tenant_prefect_api_auth)
fi
for name in "${secret_names[@]}"; do
  path="${ORIN_PREFECT_SECRETS_DIR}/${name}"
  if [[ ! -f "${path}" || ! -s "${path}" ]]; then
    echo "missing or empty secret: ${path}" >&2
    exit 1
  fi
  if [[ "$(stat -c %a "${path}")" != "400" ]]; then
    echo "secret must have mode 0400: ${path}" >&2
    exit 1
  fi
  if [[ "$(stat -c %u "${path}")" != "${expected_uid[${name}]}" ]]; then
    echo "secret has the wrong owner: ${path}" >&2
    exit 1
  fi
  if [[ "$(wc -l < "${path}")" -gt 1 ]]; then
    echo "secret must contain exactly one line: ${path}" >&2
    exit 1
  fi
done
if [[ "${require_hcs_owner_secret}" == true ]] && ! cmp -s \
  "${ORIN_PREFECT_SECRETS_DIR}/prefect_api_auth" \
  "${ORIN_PREFECT_SECRETS_DIR}/hcs_prefect_api_auth"; then
  echo "HCS Prefect API auth copy does not match the server credential" >&2
  exit 1
fi
if [[ "${require_tenant_owner_secret}" == true ]] && ! cmp -s \
  "${ORIN_PREFECT_SECRETS_DIR}/prefect_api_auth" \
  "${ORIN_PREFECT_SECRETS_DIR}/tenant_prefect_api_auth"; then
  echo "Tenant Prefect API auth copy does not match the server credential" >&2
  exit 1
fi
if ! cmp -s \
  "${ORIN_PREFECT_SECRETS_DIR}/prefect_postgres_password" \
  "${ORIN_PREFECT_SECRETS_DIR}/prefect_server_database_password"; then
  echo "Prefect database password copies do not match" >&2
  exit 1
fi

echo "ORIN Prefect shadow preflight passed; no service was started"
