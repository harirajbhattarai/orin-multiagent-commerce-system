#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "watchdog database secret installation must run as root on the VPS" >&2
  exit 1
fi

secrets_dir="${ORIN_SECRETS_DIR:-/docker/orin/secrets}"
target="${secrets_dir}/watchdog_database_url"

if [[ ! -d "${secrets_dir}" ]]; then
  echo "secrets directory does not exist: ${secrets_dir}" >&2
  exit 1
fi
if [[ -e "${target}" ]]; then
  echo "watchdog database secret already exists; refusing to overwrite" >&2
  exit 1
fi

echo "Paste the complete orin_watchdog PostgreSQL session-pooler URL."
echo "Input is hidden and the URL will not be printed."
read -r -s -p "[watchdog_database_url]: " first
echo
read -r -s -p "[confirm watchdog_database_url]: " second
echo

if [[ "${first}" != "${second}" ]]; then
  echo "watchdog database URL entries did not match" >&2
  exit 1
fi
if [[ ${#first} -lt 40 || "${first}" == *$'\n'* || "${first}" == *$'\r'* ]]; then
  echo "watchdog database URL must be one line with at least 40 characters" >&2
  exit 1
fi
if [[ "${first}" != postgres://* && "${first}" != postgresql://* ]]; then
  echo "watchdog database URL must use postgres:// or postgresql://" >&2
  exit 1
fi
if [[ "${first}" != *"orin_watchdog"* ]]; then
  echo "watchdog database URL must identify the orin_watchdog role" >&2
  exit 1
fi

umask 077
temporary="$(mktemp "${secrets_dir}/.watchdog_database_url.XXXXXX")"
cleanup() {
  rm -f -- "${temporary}"
}
trap cleanup EXIT

printf '%s\n' "${first}" > "${temporary}"
chown 10003:10003 "${temporary}"
chmod 0400 "${temporary}"
mv -- "${temporary}" "${target}"
trap - EXIT

echo "Watchdog database credential installed securely."
stat -c '%n owner=%u:%g mode=%a size=%s' "${target}"
