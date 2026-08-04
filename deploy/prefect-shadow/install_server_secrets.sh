#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "Prefect secret installation must run as root on the VPS" >&2
  exit 1
fi

secrets_dir="${ORIN_PREFECT_SECRETS_DIR:-/docker/orin-prefect-shadow/secrets}"
postgres_target="${secrets_dir}/prefect_postgres_password"
server_target="${secrets_dir}/prefect_server_database_password"
auth_target="${secrets_dir}/prefect_api_auth"

install -d -m 0700 -o root -g root "${secrets_dir}"
for target in "${postgres_target}" "${server_target}" "${auth_target}"; do
  if [[ -e "${target}" ]]; then
    echo "secret already exists; refusing to overwrite: ${target}" >&2
    exit 1
  fi
done

database_password="$(openssl rand -hex 32)"
api_password="$(openssl rand -hex 32)"

umask 077
postgres_tmp="$(mktemp "${secrets_dir}/.prefect_postgres_password.XXXXXX")"
server_tmp="$(mktemp "${secrets_dir}/.prefect_server_database_password.XXXXXX")"
auth_tmp="$(mktemp "${secrets_dir}/.prefect_api_auth.XXXXXX")"
cleanup() {
  rm -f -- "${postgres_tmp}" "${server_tmp}" "${auth_tmp}"
}
trap cleanup EXIT

printf '%s\n' "${database_password}" > "${postgres_tmp}"
printf '%s\n' "${database_password}" > "${server_tmp}"
printf 'orin-shadow:%s\n' "${api_password}" > "${auth_tmp}"
chown 999:999 "${postgres_tmp}"
chown 10004:10004 "${server_tmp}" "${auth_tmp}"
chmod 0400 "${postgres_tmp}" "${server_tmp}" "${auth_tmp}"
mv -- "${postgres_tmp}" "${postgres_target}"
mv -- "${server_tmp}" "${server_target}"
mv -- "${auth_tmp}" "${auth_target}"
trap - EXIT

echo "Prefect database and API credentials installed securely."
stat -c '%n owner=%u:%g mode=%a size=%s' \
  "${postgres_target}" "${server_target}" "${auth_target}"
echo "The Prefect UI username is orin-shadow. The password was not printed."
