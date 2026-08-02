#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "evidence service key installation must run as root on the VPS" >&2
  exit 1
fi

secrets_dir="${ORIN_SECRETS_DIR:-/docker/orin/secrets}"
runtime_uid="${ORIN_RUNTIME_UID:-1000}"
runtime_gid="${ORIN_RUNTIME_GID:-1000}"
target="${secrets_dir}/evidence_service_key"

if [[ ! "${runtime_uid}" =~ ^[0-9]+$ || ! "${runtime_gid}" =~ ^[0-9]+$ ]]; then
  echo "runtime UID and GID must be numeric" >&2
  exit 1
fi
if [[ ! -d "${secrets_dir}" ]]; then
  echo "secrets directory does not exist: ${secrets_dir}" >&2
  exit 1
fi
if [[ -e "${target}" ]]; then
  echo "evidence service key already exists; refusing to overwrite" >&2
  exit 1
fi

echo "Paste the Supabase server-side secret key for one-shot evidence sync."
echo "Input is hidden. Never use a publishable key or place this value in Git."
read -r -s -p "[evidence_service_key]: " first
echo
read -r -s -p "[confirm evidence_service_key]: " second
echo

if [[ "${first}" != "${second}" ]]; then
  echo "evidence service key entries did not match" >&2
  exit 1
fi
if [[ ${#first} -lt 32 || "${first}" == *$'\n'* || "${first}" == *$'\r'* ]]; then
  echo "evidence service key must be one line with at least 32 characters" >&2
  exit 1
fi

umask 077
temporary="$(mktemp "${secrets_dir}/.evidence_service_key.XXXXXX")"
cleanup() {
  rm -f -- "${temporary}"
}
trap cleanup EXIT

printf '%s\n' "${first}" > "${temporary}"
chown "${runtime_uid}:${runtime_gid}" "${temporary}"
chmod 0400 "${temporary}"
mv -- "${temporary}" "${target}"
trap - EXIT

echo "Evidence service key installed securely."
stat -c '%n owner=%u:%g mode=%a size=%s' "${target}"
