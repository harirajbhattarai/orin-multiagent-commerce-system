#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "HCS Shopify secret installation must run as root on the VPS" >&2
  exit 1
fi

secrets_dir="${ORIN_SECRETS_DIR:-/docker/orin/secrets}"
runtime_gid="${ORIN_RUNTIME_GID:-1000}"
target="${secrets_dir}/hcs_shopify_access_token"

if [[ ! "${runtime_gid}" =~ ^[0-9]+$ ]]; then
  echo "runtime GID must be numeric" >&2
  exit 1
fi
if [[ ! -d "${secrets_dir}" ]]; then
  echo "secrets directory does not exist: ${secrets_dir}" >&2
  exit 1
fi
if [[ -e "${target}" ]]; then
  echo "HCS Shopify secret already exists; refusing to overwrite" >&2
  exit 1
fi

echo "Paste the HCS Shopify Admin API access token. Input is hidden."
read -r -s -p "[hcs_shopify_access_token]: " first
echo
read -r -s -p "[confirm hcs_shopify_access_token]: " second
echo

if [[ -z "${first}" || "${first}" != "${second}" ]]; then
  echo "HCS Shopify access tokens are empty or do not match" >&2
  exit 1
fi

umask 077
temporary="$(mktemp "${secrets_dir}/.hcs_shopify_access_token.XXXXXX")"
cleanup() { rm -f -- "${temporary}"; }
trap cleanup EXIT
printf '%s\n' "${first}" > "${temporary}"
chown 10006:"${runtime_gid}" "${temporary}"
chmod 0400 "${temporary}"
mv -n -- "${temporary}" "${target}"
trap - EXIT

echo "HCS Shopify credential installed securely."
stat -c '%n owner=%u:%g mode=%a size=%s' "${target}"
