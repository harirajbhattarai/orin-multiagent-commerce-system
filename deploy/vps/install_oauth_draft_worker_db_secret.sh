#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "OAuth draft worker database secret installation must run as root on the VPS" >&2
  exit 1
fi

secrets_dir="${ORIN_SECRETS_DIR:-/docker/orin/secrets}"
target="${secrets_dir}/oauth_draft_worker_database_url"
runtime_gid="${ORIN_RUNTIME_GID:-1000}"
evidence_root="${ORIN_EVIDENCE_ROOT:-/docker/orin/evidence}"

if [[ ! -d "${secrets_dir}" ]]; then
  echo "secrets directory does not exist: ${secrets_dir}" >&2
  exit 1
fi
if [[ -e "${target}" ]]; then
  echo "OAuth draft worker database secret already exists; refusing to overwrite" >&2
  exit 1
fi

echo "Paste the complete orin_oauth_draft_worker PostgreSQL session-pooler URL."
echo "Input is hidden and the URL will not be printed."
read -r -s -p "[oauth_draft_worker_database_url]: " first
echo
read -r -s -p "[confirm oauth_draft_worker_database_url]: " second
echo

if [[ "${first}" != "${second}" ]]; then
  echo "OAuth draft worker database URL entries did not match" >&2
  exit 1
fi
if [[ ${#first} -lt 40 || "${first}" == *$'\n'* || "${first}" == *$'\r'* ]]; then
  echo "OAuth draft worker database URL must be one line with at least 40 characters" >&2
  exit 1
fi
if [[ "${first}" != postgres://* && "${first}" != postgresql://* ]]; then
  echo "OAuth draft worker database URL must use postgres:// or postgresql://" >&2
  exit 1
fi
if [[ "${first}" != *"orin_oauth_draft_worker"* ]]; then
  echo "OAuth draft worker database URL must identify orin_oauth_draft_worker" >&2
  exit 1
fi

umask 077
temporary="$(mktemp "${secrets_dir}/.oauth_draft_worker_database_url.XXXXXX")"
trap 'rm -f -- "${temporary}"' EXIT
printf '%s\n' "${first}" > "${temporary}"
chown "10009:${runtime_gid}" "${temporary}"
chmod 0400 "${temporary}"
mv -- "${temporary}" "${target}"
trap - EXIT

install -d -m 0700 -o 10009 -g "${runtime_gid}" \
  "${evidence_root}/generic-oauth-drafts"
echo "OAuth draft worker database credential installed securely."
stat -c '%n owner=%u:%g mode=%a size=%s' "${target}"
