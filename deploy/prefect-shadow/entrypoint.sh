#!/usr/bin/env bash
set -euo pipefail

read_secret() {
  local path="$1"
  if [[ ! -f "${path}" || ! -s "${path}" || "$(wc -l < "${path}")" -gt 1 ]]; then
    echo "invalid secret file: ${path}" >&2
    exit 1
  fi
  tr -d '\r\n' < "${path}"
}

mode="${1:-}"
api_auth="$(read_secret /run/secrets/prefect_api_auth)"

case "${mode}" in
  server)
    database_password="$(read_secret /run/secrets/prefect_server_database_password)"
    encoded_password="$(python -c 'import sys; from urllib.parse import quote; print(quote(sys.argv[1], safe=""))' "${database_password}")"
    export PREFECT_SERVER_API_AUTH_STRING="${api_auth}"
    export PREFECT_SERVER_DATABASE_CONNECTION_URL="postgresql+asyncpg://prefect:${encoded_password}@prefect-postgres:5432/prefect"
    exec prefect server start --host 0.0.0.0
    ;;
  bootstrap)
    export PREFECT_API_AUTH_STRING="${api_auth}"
    exec python -m orin_prefect_shadow.bootstrap
    ;;
  hcs-bootstrap)
    export PREFECT_API_AUTH_STRING="${api_auth}"
    exec python -c 'from orin_prefect_shadow.bootstrap import bootstrap_hcs; bootstrap_hcs()'
    ;;
  tenant-bootstrap)
    export PREFECT_API_AUTH_STRING="${api_auth}"
    exec python -c 'from orin_prefect_shadow.bootstrap import bootstrap_tenant; bootstrap_tenant()'
    ;;
  worker)
    export PREFECT_API_AUTH_STRING="${api_auth}"
    exec prefect worker start \
      --pool orin-shadow-process \
      --name orin-hbstore-shadow-1 \
      --limit 1 \
      --no-create-pool-if-not-found \
      --install-policy never
    ;;
  owner-worker)
    export PREFECT_API_AUTH_STRING="${api_auth}"
    exec prefect worker start \
      --pool orin-owner-process \
      --name orin-hbstore-prefect-scheduler-1 \
      --limit 1 \
      --with-healthcheck \
      --no-create-pool-if-not-found \
      --install-policy never
    ;;
  hcs-owner-worker)
    export PREFECT_API_AUTH_STRING="${api_auth}"
    exec prefect worker start \
      --pool orin-hcs-owner-process \
      --name orin-hcs-prefect-scheduler-1 \
      --limit 1 \
      --with-healthcheck \
      --no-create-pool-if-not-found \
      --install-policy never
    ;;
  tenant-owner-worker)
    export PREFECT_API_AUTH_STRING="${api_auth}"
    exec prefect worker start \
      --pool orin-tenant-owner-process \
      --name orin-tenant-prefect-scheduler-1 \
      --limit 1 \
      --with-healthcheck \
      --no-create-pool-if-not-found \
      --install-policy never
    ;;
  *)
    echo "usage: entrypoint.sh {server|bootstrap|hcs-bootstrap|tenant-bootstrap|worker|owner-worker|hcs-owner-worker|tenant-owner-worker}" >&2
    exit 2
    ;;
esac
