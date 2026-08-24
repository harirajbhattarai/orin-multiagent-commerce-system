#!/usr/bin/env bash
set -euo pipefail

if [[ "$(id -u)" -ne 0 ]]; then
  echo "commissioner database secret installation must run as root on the VPS" >&2
  exit 1
fi

secrets_dir="${ORIN_SECRETS_DIR:-/docker/orin/secrets}"
target="${secrets_dir}/commissioner_database_url"
if [[ ! -d "${secrets_dir}" || -L "${secrets_dir}" ]]; then
  echo "ORIN secrets directory is missing or unsafe" >&2
  exit 1
fi
if [[ -e "${target}" || -L "${target}" ]]; then
  echo "commissioner database secret already exists; refusing to overwrite" >&2
  exit 1
fi

echo "Paste the complete orin_commissioner PostgreSQL session-pooler URL."
echo "Input is hidden and the URL will not be printed."
read -r -s -p "[commissioner_database_url]: " first
echo
read -r -s -p "[confirm commissioner_database_url]: " second
echo
if [[ "${first}" != "${second}" ]]; then
  echo "commissioner database URL entries did not match" >&2
  exit 1
fi
if [[ "${first}" == *$'\n'* || ${#first} -lt 40 ]]; then
  echo "commissioner database URL must be one line with at least 40 characters" >&2
  exit 1
fi
if [[ "${first}" != postgres://* && "${first}" != postgresql://* ]]; then
  echo "commissioner database URL must use postgres:// or postgresql://" >&2
  exit 1
fi
if [[ "${first}" != *"orin_commissioner"* ]]; then
  echo "commissioner database URL must identify orin_commissioner" >&2
  exit 1
fi

umask 077
temporary="$(mktemp "${secrets_dir}/.commissioner_database_url.XXXXXX")"
trap 'rm -f -- "${temporary}"' EXIT
printf '%s\n' "${first}" > "${temporary}"
chown 10009:10009 "${temporary}"
chmod 0400 "${temporary}"
mv -T "${temporary}" "${target}"
trap - EXIT
echo "Commissioner database credential installed securely."
stat -c '%n owner=%u:%g mode=%a size=%s' "${target}"
