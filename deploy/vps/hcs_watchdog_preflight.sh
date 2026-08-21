#!/usr/bin/env bash
set -euo pipefail

require_image=false
if [[ "${1:-}" == "--require-image" && "$#" -eq 1 ]]; then
  require_image=true
elif [[ "$#" -ne 0 ]]; then
  echo "usage: $0 [--require-image]" >&2
  exit 2
fi

if [[ "${EUID}" -ne 0 ]]; then
  echo "HCS watchdog preflight must run as root on the VPS" >&2
  exit 1
fi

required=(
  ORIN_WATCHDOG_DEPLOY_SHA ORIN_PROJECT_ROOT ORIN_SECRETS_DIR
  ORIN_TRIGGER_SOCKET_DIR ORIN_RUNTIME_UID ORIN_RUNTIME_GID
)
for name in "${required[@]}"; do
  if [[ -z "${!name:-}" ]]; then
    echo "missing required deployment variable: ${name}" >&2
    exit 1
  fi
done
if [[ ! "${ORIN_WATCHDOG_DEPLOY_SHA}" =~ ^[0-9a-f]{40}$ ]]; then
  echo "ORIN_WATCHDOG_DEPLOY_SHA must be a full Git commit" >&2
  exit 1
fi
for command in docker git python3 stat; do command -v "${command}" >/dev/null; done

if [[ -n "$(git -c safe.directory="${ORIN_PROJECT_ROOT}" -C "${ORIN_PROJECT_ROOT}" status --porcelain)" ]]; then
  echo "canonical Git checkout is not clean" >&2
  exit 1
fi
actual_sha="$(git -c safe.directory="${ORIN_PROJECT_ROOT}" -C "${ORIN_PROJECT_ROOT}" rev-parse HEAD)"
if [[ "${actual_sha}" != "${ORIN_WATCHDOG_DEPLOY_SHA}" ]]; then
  echo "checkout mismatch: expected ${ORIN_WATCHDOG_DEPLOY_SHA}, received ${actual_sha}" >&2
  exit 1
fi

secret_path="${ORIN_SECRETS_DIR}/hcs_watchdog_database_url"
if [[ ! -f "${secret_path}" || -L "${secret_path}" ]]; then
  echo "HCS watchdog database secret is missing or unsafe" >&2
  exit 1
fi
if [[ "$(stat -c %a "${secret_path}")" != "400" \
      || "$(stat -c %u "${secret_path}")" != "10008" \
      || "$(stat -c %g "${secret_path}")" != "10008" ]]; then
  echo "HCS watchdog database secret must be 10008:10008 mode 0400" >&2
  exit 1
fi
if [[ "$(wc -l < "${secret_path}")" -gt 1 || ! -s "${secret_path}" ]]; then
  echo "HCS watchdog database secret must contain one non-empty line" >&2
  exit 1
fi
if ! grep -q "orin_hcs_watchdog" "${secret_path}"; then
  echo "HCS watchdog URL does not identify the dedicated role" >&2
  exit 1
fi

socket_dir="${ORIN_TRIGGER_SOCKET_DIR}/hcs-watchdog"
if [[ ! -d "${socket_dir}" || -L "${socket_dir}" ]]; then
  echo "HCS watchdog socket directory does not exist or is unsafe" >&2
  exit 1
fi
if [[ "$(stat -c %a "${socket_dir}")" != "710" \
      || "$(stat -c %u "${socket_dir}")" != "10008" \
      || "$(stat -c %g "${socket_dir}")" != "${ORIN_RUNTIME_GID}" ]]; then
  echo "HCS watchdog socket directory must be 10008:${ORIN_RUNTIME_GID} mode 0710" >&2
  exit 1
fi
if docker ps --quiet \
    --filter label=com.docker.compose.project=orin-control \
    --filter label=com.docker.compose.service=hcs-watchdog | grep -q .; then
  echo "HCS watchdog service is already running" >&2
  exit 1
fi

jobs="$(docker exec openclaw-utgd-openclaw-1 openclaw cron list --all --json)"
python3 - "${jobs}" <<'PY'
import json
import sys

jobs = json.loads(sys.argv[1]).get("jobs", [])
enabled = [
    job for job in jobs
    if "hcs" in str(job.get("name", "")).lower()
    and "watchdog" in str(job.get("name", "")).lower()
    and job.get("enabled")
]
if enabled:
    raise SystemExit("an HCS watchdog schedule is already enabled")
PY

if [[ "${require_image}" == true ]]; then
  image="local/orin-watchdog:${ORIN_WATCHDOG_DEPLOY_SHA}"
  if ! docker image inspect "${image}" >/dev/null 2>&1; then
    echo "immutable watchdog image is missing" >&2
    exit 1
  fi
  revision="$(docker image inspect "${image}" --format '{{ index .Config.Labels "org.opencontainers.image.revision" }}')"
  if [[ "${revision}" != "${ORIN_WATCHDOG_DEPLOY_SHA}" ]]; then
    echo "watchdog image revision does not match deployment revision" >&2
    exit 1
  fi
fi

echo "HCS watchdog preflight passed; no service or schedule was changed"
