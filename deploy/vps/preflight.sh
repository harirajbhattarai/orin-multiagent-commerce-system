#!/usr/bin/env bash
set -euo pipefail

require_secrets=false
require_shopify_secret=false
require_writer_secret=false
require_scheduler_secret=false
require_watchdog_secret=false
require_evidence_secret=false
for argument in "$@"; do
  case "${argument}" in
    --require-secrets)
      require_secrets=true
      ;;
    --require-shopify-secret)
      require_secrets=true
      require_shopify_secret=true
      ;;
    --require-writer-secret)
      require_secrets=true
      require_writer_secret=true
      ;;
    --require-scheduler-secret)
      require_secrets=true
      require_scheduler_secret=true
      ;;
    --require-watchdog-secret)
      require_secrets=true
      require_watchdog_secret=true
      ;;
    --require-evidence-secret)
      require_secrets=true
      require_evidence_secret=true
      ;;
    *)
      echo "usage: $0 [--require-secrets] [--require-shopify-secret] [--require-writer-secret] [--require-scheduler-secret] [--require-watchdog-secret] [--require-evidence-secret]" >&2
      exit 2
      ;;
  esac
done

required=(
  ORIN_DEPLOY_SHA
  ORIN_WATCHDOG_DEPLOY_SHA
  ORIN_PROJECT_ROOT
  ORIN_RUNTIME_ROOT
  ORIN_EVIDENCE_ROOT
  ORIN_SECRETS_DIR
  ORIN_TRIGGER_SOCKET_DIR
  ORIN_RUNTIME_UID
  ORIN_RUNTIME_GID
  ORIN_API_PORT
)
for name in "${required[@]}"; do
  if [[ -z "${!name:-}" ]]; then
    echo "missing required deployment variable: ${name}" >&2
    exit 1
  fi
done

if [[ "${EUID}" -ne 0 ]]; then
  echo "preflight must run as root on the VPS" >&2
  exit 1
fi
if [[ ! "${ORIN_DEPLOY_SHA}" =~ ^[0-9a-f]{40}$ ]]; then
  echo "ORIN_DEPLOY_SHA must be a full Git commit" >&2
  exit 1
fi
if [[ ! "${ORIN_WATCHDOG_DEPLOY_SHA}" =~ ^[0-9a-f]{40}$ ]]; then
  echo "ORIN_WATCHDOG_DEPLOY_SHA must be a full Git commit" >&2
  exit 1
fi
if [[ ! "${ORIN_API_PORT}" =~ ^[0-9]+$ ]]; then
  echo "ORIN_API_PORT must be numeric" >&2
  exit 1
fi

for command in docker git python3 stat; do
  command -v "${command}" >/dev/null
done
docker compose version >/dev/null

if [[ ! -d "${ORIN_PROJECT_ROOT}/.git" ]]; then
  echo "canonical Git checkout not found: ${ORIN_PROJECT_ROOT}" >&2
  exit 1
fi
if [[ ! -d "${ORIN_RUNTIME_ROOT}" ]]; then
  echo "runtime workspace not found: ${ORIN_RUNTIME_ROOT}" >&2
  exit 1
fi
if [[ ! -d "${ORIN_TRIGGER_SOCKET_DIR}" ]]; then
  echo "scheduler trigger socket directory not found: ${ORIN_TRIGGER_SOCKET_DIR}" >&2
  exit 1
fi
if [[ -n "$(git -c safe.directory="${ORIN_PROJECT_ROOT}" -C "${ORIN_PROJECT_ROOT}" status --porcelain)" ]]; then
  echo "canonical Git checkout is not clean" >&2
  exit 1
fi
actual_sha="$(git -c safe.directory="${ORIN_PROJECT_ROOT}" -C "${ORIN_PROJECT_ROOT}" rev-parse HEAD)"
if [[ "${actual_sha}" != "${ORIN_DEPLOY_SHA}" ]]; then
  echo "checkout mismatch: expected ${ORIN_DEPLOY_SHA}, received ${actual_sha}" >&2
  exit 1
fi

if docker ps --quiet --filter label=com.docker.compose.project=orin-control | grep -q .; then
  echo "an ORIN deployment container is already running" >&2
  exit 1
fi
if ss -H -ltn "sport = :${ORIN_API_PORT}" | grep -q .; then
  echo "loopback API port ${ORIN_API_PORT} is already in use" >&2
  exit 1
fi

scheduler_status="$(docker exec openclaw-utgd-openclaw-1 openclaw cron status --json)"
scheduler_jobs="$(docker exec openclaw-utgd-openclaw-1 openclaw cron list --all --json)"
python3 -c '
import json, sys
status = json.loads(sys.argv[1])
jobs = json.loads(sys.argv[2])["jobs"]
if status.get("nextWakeAtMs") is not None:
    raise SystemExit("OpenClaw scheduler has a next wake")
if any(job.get("enabled") or job.get("status") != "disabled" for job in jobs):
    raise SystemExit("an OpenClaw job is not disabled")
' "${scheduler_status}" "${scheduler_jobs}"

compose_file="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/compose.yml"
if [[ -n "$(docker compose --env-file /dev/null -f "${compose_file}" config --services)" ]]; then
  echo "deployment has an unprofiled default service" >&2
  exit 1
fi
docker compose --env-file /dev/null -f "${compose_file}" --profile "*" config --quiet

if [[ "${require_secrets}" == true ]]; then
  declare -A expected_uid=(
    [watchdog_database_url]=10003
    [scheduler_database_url]=10002
    [control_database_url]=10001
    [worker_database_url]="${ORIN_RUNTIME_UID}"
    [hoverboard_shopify_access_token]="${ORIN_RUNTIME_UID}"
    [writer_api_key]="${ORIN_RUNTIME_UID}"
    [evidence_service_key]="${ORIN_RUNTIME_UID}"
  )
  secret_names=(control_database_url worker_database_url)
  if [[ "${require_scheduler_secret}" == true ]]; then
    secret_names+=(scheduler_database_url)
  fi
  if [[ "${require_watchdog_secret}" == true ]]; then
    secret_names+=(watchdog_database_url)
  fi
  if [[ "${require_shopify_secret}" == true ]]; then
    secret_names+=(hoverboard_shopify_access_token)
  fi
  if [[ "${require_writer_secret}" == true ]]; then
    secret_names+=(writer_api_key)
  fi
  if [[ "${require_evidence_secret}" == true ]]; then
    secret_names+=(evidence_service_key)
  fi
  for secret_name in "${secret_names[@]}"; do
    secret_path="${ORIN_SECRETS_DIR}/${secret_name}"
    if [[ ! -f "${secret_path}" ]]; then
      echo "missing secret file: ${secret_path}" >&2
      exit 1
    fi
    if [[ "$(stat -c %a "${secret_path}")" != "400" ]]; then
      echo "secret must have mode 0400: ${secret_path}" >&2
      exit 1
    fi
    if [[ "$(stat -c %u "${secret_path}")" != "${expected_uid[${secret_name}]}" ]]; then
      echo "secret has the wrong owner: ${secret_path}" >&2
      exit 1
    fi
    if [[ "$(wc -l < "${secret_path}")" -gt 1 || ! -s "${secret_path}" ]]; then
      echo "secret must contain exactly one non-empty line: ${secret_path}" >&2
      exit 1
    fi
  done
  if [[ ! -d "${ORIN_EVIDENCE_ROOT}" ]]; then
    echo "evidence directory is missing: ${ORIN_EVIDENCE_ROOT}" >&2
    exit 1
  fi
  if [[ "$(stat -c %a "${ORIN_EVIDENCE_ROOT}")" != "700" \
        || "$(stat -c %u "${ORIN_EVIDENCE_ROOT}")" != "${ORIN_RUNTIME_UID}" ]]; then
    echo "evidence directory must be mode 0700 and owned by the runtime UID" >&2
    exit 1
  fi
fi

echo "ORIN deployment preflight passed; no service was started"
