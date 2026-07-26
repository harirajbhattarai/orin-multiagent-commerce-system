#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "writer secret installation must run as root on the VPS" >&2
  exit 1
fi

secrets_dir="${ORIN_SECRETS_DIR:-/docker/orin/secrets}"
runtime_uid="${ORIN_RUNTIME_UID:-1000}"
runtime_gid="${ORIN_RUNTIME_GID:-1000}"
target="${secrets_dir}/writer_api_key"

if [[ ! "${runtime_uid}" =~ ^[0-9]+$ || ! "${runtime_gid}" =~ ^[0-9]+$ ]]; then
  echo "runtime UID and GID must be numeric" >&2
  exit 1
fi
if [[ ! -d "${secrets_dir}" ]]; then
  echo "secrets directory does not exist: ${secrets_dir}" >&2
  exit 1
fi
if [[ -e "${target}" ]]; then
  echo "writer secret already exists; refusing to overwrite" >&2
  exit 1
fi

echo "Paste the dedicated MiniMax API key. Input is hidden."
read -r -s -p "[writer_api_key]: " first
echo
read -r -s -p "[confirm writer_api_key]: " second
echo

if [[ "${first}" != "${second}" ]]; then
  echo "writer API key entries did not match" >&2
  exit 1
fi
if [[ ${#first} -lt 20 || "${first}" == *$'\n'* || "${first}" == *$'\r'* ]]; then
  echo "writer API key must be one line with at least 20 characters" >&2
  exit 1
fi

umask 077
temporary="$(mktemp "${secrets_dir}/.writer_api_key.XXXXXX")"
cleanup() {
  rm -f -- "${temporary}"
}
trap cleanup EXIT

printf '%s\n' "${first}" > "${temporary}"
chown "${runtime_uid}:${runtime_gid}" "${temporary}"
chmod 0400 "${temporary}"
mv -- "${temporary}" "${target}"
trap - EXIT

echo "Writer credential installed securely."
stat -c '%n owner=%u:%g mode=%a size=%s' "${target}"
