#!/usr/bin/env bash
set -euo pipefail

target="/docker/orin-prefect-shadow/secrets/tenant_owner_database_url"
if [[ -e "${target}" ]]; then
  echo "ERROR: target secret already exists; refusing to overwrite" >&2
  exit 1
fi

echo "Paste the complete orin_tenant_prefect_scheduler PostgreSQL session-pooler URL."
echo "Input is hidden and the URL will not be printed."
IFS= read -r -s -p "[tenant_owner_database_url]: " first
echo
IFS= read -r -s -p "[confirm tenant_owner_database_url]: " second
echo
if [[ "${first}" != "${second}" ]]; then
  echo "Tenant scheduler database URL entries did not match" >&2
  exit 1
fi
if [[ "${first}" != postgres://* && "${first}" != postgresql://* ]]; then
  echo "Tenant scheduler database URL must use postgres:// or postgresql://" >&2
  exit 1
fi

install -o 10010 -g 10010 -m 0400 /dev/null "${target}"
printf '%s' "${first}" > "${target}"
unset first second
echo "Tenant scheduler credential installed securely."
stat -c '%n owner=%u:%g mode=%a size=%s' "${target}"
