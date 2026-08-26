#!/usr/bin/env bash
set -euo pipefail

secrets_dir="${ORIN_PREFECT_SECRETS_DIR:-/docker/orin-prefect-shadow/secrets}"
source_path="${secrets_dir}/prefect_api_auth"
target="${secrets_dir}/tenant_prefect_api_auth"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Tenant Prefect API credential preparation must run as root" >&2
  exit 1
fi
if [[ ! -f "${source_path}" || ! -s "${source_path}" || "$(wc -l < "${source_path}")" -gt 1 ]]; then
  echo "The canonical Prefect API credential is missing or invalid" >&2
  exit 1
fi

install -d -m 0700 -o root -g root "${secrets_dir}"
temporary="$(mktemp "${secrets_dir}/.tenant_prefect_api_auth.XXXXXX")"
trap 'rm -f "${temporary}"' EXIT
cp "${source_path}" "${temporary}"
chown 10010:10010 "${temporary}"
chmod 0400 "${temporary}"
mv -f "${temporary}" "${target}"
trap - EXIT
echo "Tenant Prefect API credential installed securely."
