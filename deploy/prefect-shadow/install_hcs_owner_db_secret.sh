#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "HCS owner database secret installation must run as root on the VPS" >&2
  exit 1
fi

secrets_dir="${ORIN_PREFECT_SECRETS_DIR:-/docker/orin-prefect-shadow/secrets}"
target="${secrets_dir}/hcs_owner_database_url"

if [[ ! -d "${secrets_dir}" ]]; then
  echo "secrets directory does not exist: ${secrets_dir}" >&2
  exit 1
fi
if [[ -e "${target}" ]]; then
  echo "HCS owner database secret already exists; refusing to overwrite" >&2
  exit 1
fi

echo "Paste the complete orin_hcs_prefect_scheduler PostgreSQL session-pooler URL."
echo "Input is hidden and the URL will not be printed."
read -r -s -p "[hcs_owner_database_url]: " first
echo
read -r -s -p "[confirm hcs_owner_database_url]: " second
echo

if [[ "${first}" != "${second}" ]]; then
  echo "HCS owner database URL entries did not match" >&2
  exit 1
fi
if [[ ${#first} -lt 40 || "${first}" == *$'\n'* || "${first}" == *$'\r'* ]]; then
  echo "HCS owner database URL must be one line with at least 40 characters" >&2
  exit 1
fi
if [[ "${first}" != postgres://* && "${first}" != postgresql://* ]]; then
  echo "HCS owner database URL must use postgres:// or postgresql://" >&2
  exit 1
fi
if [[ "${first}" != *"orin_hcs_prefect_scheduler"* ]]; then
  echo "HCS owner database URL must identify orin_hcs_prefect_scheduler" >&2
  exit 1
fi

umask 077
temporary="$(mktemp "${secrets_dir}/.hcs_owner_database_url.XXXXXX")"
cleanup() { rm -f -- "${temporary}"; }
trap cleanup EXIT
printf '%s\n' "${first}" > "${temporary}"
chown 10007:10007 "${temporary}"
chmod 0400 "${temporary}"
mv -- "${temporary}" "${target}"
trap - EXIT

echo "HCS Prefect owner credential installed securely."
stat -c '%n owner=%u:%g mode=%a size=%s' "${target}"
