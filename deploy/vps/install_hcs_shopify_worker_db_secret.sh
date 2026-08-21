#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "HCS Shopify worker database secret installation must run as root on the VPS" >&2
  exit 1
fi

secrets_dir="${ORIN_SECRETS_DIR:-/docker/orin/secrets}"
target="${secrets_dir}/hcs_shopify_worker_database_url"

if [[ ! -d "${secrets_dir}" ]]; then
  echo "secrets directory does not exist: ${secrets_dir}" >&2
  exit 1
fi
if [[ -e "${target}" ]]; then
  echo "HCS Shopify worker database secret already exists; refusing to overwrite" >&2
  exit 1
fi

echo "Paste the complete orin_hcs_shopify_worker PostgreSQL session-pooler URL."
echo "Input is hidden and the URL will not be printed."
read -r -s -p "[hcs_shopify_worker_database_url]: " first
echo
read -r -s -p "[confirm hcs_shopify_worker_database_url]: " second
echo

if [[ "${first}" != "${second}" ]]; then
  echo "HCS Shopify worker database URL entries did not match" >&2
  exit 1
fi
if [[ ${#first} -lt 40 || "${first}" == *$'\n'* || "${first}" == *$'\r'* ]]; then
  echo "HCS Shopify worker database URL must be one line with at least 40 characters" >&2
  exit 1
fi
if [[ "${first}" != postgres://* && "${first}" != postgresql://* ]]; then
  echo "HCS Shopify worker database URL must use postgres:// or postgresql://" >&2
  exit 1
fi
if [[ "${first}" != *"orin_hcs_shopify_worker"* ]]; then
  echo "HCS Shopify worker URL must identify orin_hcs_shopify_worker" >&2
  exit 1
fi

umask 077
temporary="$(mktemp "${secrets_dir}/.hcs_shopify_worker_database_url.XXXXXX")"
cleanup() { rm -f -- "${temporary}"; }
trap cleanup EXIT
printf '%s\n' "${first}" > "${temporary}"
chown 10006:10006 "${temporary}"
chmod 0400 "${temporary}"
mv -n -- "${temporary}" "${target}"
trap - EXIT

echo "HCS Shopify worker database credential installed securely."
stat -c '%n owner=%u:%g mode=%a size=%s' "${target}"
