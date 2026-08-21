#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "HCS Prefect API auth preparation must run as root on the VPS" >&2
  exit 1
fi

secrets_dir="${ORIN_PREFECT_SECRETS_DIR:-/docker/orin-prefect-shadow/secrets}"
source_path="${secrets_dir}/prefect_api_auth"
target="${secrets_dir}/hcs_prefect_api_auth"

if [[ ! -f "${source_path}" || -L "${source_path}" || ! -s "${source_path}" ]]; then
  echo "Prefect API auth source is missing or unsafe" >&2
  exit 1
fi
if [[ "$(stat -c %a "${source_path}")" != "400" \
      || "$(stat -c %u "${source_path}")" != "10004" \
      || "$(stat -c %g "${source_path}")" != "10004" ]]; then
  echo "Prefect API auth source must be 10004:10004 mode 0400" >&2
  exit 1
fi
if [[ "$(wc -l < "${source_path}")" -gt 1 ]]; then
  echo "Prefect API auth source must contain one non-empty line" >&2
  exit 1
fi
if [[ -e "${target}" ]]; then
  echo "HCS Prefect API auth copy already exists; refusing to overwrite" >&2
  exit 1
fi

umask 077
temporary="$(mktemp "${secrets_dir}/.hcs_prefect_api_auth.XXXXXX")"
cleanup() { rm -f -- "${temporary}"; }
trap cleanup EXIT
cp -- "${source_path}" "${temporary}"
chown 10007:10007 "${temporary}"
chmod 0400 "${temporary}"
mv -- "${temporary}" "${target}"
trap - EXIT

echo "HCS Prefect API auth copy prepared securely."
stat -c '%n owner=%u:%g mode=%a size=%s' "${target}"
