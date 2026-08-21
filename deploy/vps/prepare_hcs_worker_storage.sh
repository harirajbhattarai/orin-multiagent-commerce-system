#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "HCS worker storage preparation must run as root on the VPS" >&2
  exit 1
fi

evidence_root="${ORIN_EVIDENCE_ROOT:-/docker/orin/evidence}"
runtime_gid="${ORIN_RUNTIME_GID:-1000}"
target="${evidence_root}/hcs_gadgets"
approval_target="${target}/approval"

if [[ ! -d "${evidence_root}" || -L "${evidence_root}" ]]; then
  echo "evidence root must be a real directory: ${evidence_root}" >&2
  exit 1
fi
if [[ ! "${runtime_gid}" =~ ^[0-9]+$ ]]; then
  echo "ORIN_RUNTIME_GID must be numeric" >&2
  exit 1
fi
if [[ -e "${target}" && ( ! -d "${target}" || -L "${target}" ) ]]; then
  echo "HCS evidence target must be a real directory: ${target}" >&2
  exit 1
fi

install -d -m 0710 -o 10005 -g "${runtime_gid}" -- "${target}"
install -d -m 0700 -o 10006 -g "${runtime_gid}" -- "${approval_target}"

if [[ "$(stat -c %a "${target}")" != "710" \
      || "$(stat -c %u "${target}")" != "10005" \
      || "$(stat -c %g "${target}")" != "${runtime_gid}" ]]; then
  echo "HCS evidence directory ownership or mode is invalid" >&2
  exit 1
fi
if [[ "$(stat -c %a "${approval_target}")" != "700" \
      || "$(stat -c %u "${approval_target}")" != "10006" \
      || "$(stat -c %g "${approval_target}")" != "${runtime_gid}" ]]; then
  echo "HCS approval evidence directory ownership or mode is invalid" >&2
  exit 1
fi

echo "HCS private evidence directory prepared."
stat -c '%n owner=%u:%g mode=%a' "${target}"
stat -c '%n owner=%u:%g mode=%a' "${approval_target}"
