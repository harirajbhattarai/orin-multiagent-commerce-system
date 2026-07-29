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
  echo "watchdog preflight must run as root on the VPS" >&2
  exit 1
fi

required=(
  ORIN_DEPLOY_SHA
  ORIN_PROJECT_ROOT
  ORIN_SECRETS_DIR
  ORIN_TRIGGER_SOCKET_DIR
  ORIN_RUNTIME_UID
  ORIN_RUNTIME_GID
)
for name in "${required[@]}"; do
  if [[ -z "${!name:-}" ]]; then
    echo "missing required deployment variable: ${name}" >&2
    exit 1
  fi
done

if [[ ! "${ORIN_DEPLOY_SHA}" =~ ^[0-9a-f]{40}$ ]]; then
  echo "ORIN_DEPLOY_SHA must be a full Git commit" >&2
  exit 1
fi
if [[ ! "${ORIN_RUNTIME_UID}" =~ ^[0-9]+$ \
      || ! "${ORIN_RUNTIME_GID}" =~ ^[0-9]+$ ]]; then
  echo "runtime UID and GID must be numeric" >&2
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
if [[ -n "$(git -c safe.directory="${ORIN_PROJECT_ROOT}" -C "${ORIN_PROJECT_ROOT}" status --porcelain)" ]]; then
  echo "canonical Git checkout is not clean" >&2
  exit 1
fi
actual_sha="$(git -c safe.directory="${ORIN_PROJECT_ROOT}" -C "${ORIN_PROJECT_ROOT}" rev-parse HEAD)"
if [[ "${actual_sha}" != "${ORIN_DEPLOY_SHA}" ]]; then
  echo "checkout mismatch: expected ${ORIN_DEPLOY_SHA}, received ${actual_sha}" >&2
  exit 1
fi

proof_file="${ORIN_PHASE4_PROOF_FILE:-/docker/orin/evidence/phase4/latest_automatic_proof.json}"
if [[ ! -f "${proof_file}" || -L "${proof_file}" ]]; then
  echo "sealed Phase 4 automatic proof is missing" >&2
  exit 1
fi
if [[ "$(stat -c %a "${proof_file}")" != "400" \
      || "$(stat -c %u "${proof_file}")" != "0" ]]; then
  echo "Phase 4 proof must be root-owned with mode 0400" >&2
  exit 1
fi
python3 - "${proof_file}" <<'PY'
import json
import pathlib
import re
import sys

path = pathlib.Path(sys.argv[1])
try:
    proof = json.loads(path.read_text(encoding="utf-8"))
except (OSError, json.JSONDecodeError) as exc:
    raise SystemExit(f"invalid Phase 4 proof: {type(exc).__name__}") from None

required = {
    "schema": "orin.phase4-proof/v1",
    "status": "passed",
    "automatic_trigger": True,
    "automatic_worker": True,
    "shopify_create_count": 0,
    "shopify_published": False,
    "queue_changed": False,
}
if any(proof.get(key) != value for key, value in required.items()):
    raise SystemExit("Phase 4 proof invariants are not satisfied")
if proof.get("reconciliation_status") not in {"not_required", "reconciled"}:
    raise SystemExit("Phase 4 proof reconciliation is not terminal")
if not re.fullmatch(r"[0-9a-f]{40}", str(proof.get("code_version", ""))):
    raise SystemExit("Phase 4 proof code version is invalid")
if not str(proof.get("source_job_key", "")).startswith(
    "scheduler:orin-hbstore-prod:"
):
    raise SystemExit("Phase 4 proof source key is invalid")
PY

secret_path="${ORIN_SECRETS_DIR}/watchdog_database_url"
if [[ ! -f "${secret_path}" || -L "${secret_path}" ]]; then
  echo "watchdog database secret is missing or unsafe" >&2
  exit 1
fi
if [[ "$(stat -c %a "${secret_path}")" != "400" \
      || "$(stat -c %u "${secret_path}")" != "10003" \
      || "$(stat -c %g "${secret_path}")" != "10003" ]]; then
  echo "watchdog database secret must be 10003:10003 mode 0400" >&2
  exit 1
fi
if [[ "$(wc -l < "${secret_path}")" -gt 1 || ! -s "${secret_path}" ]]; then
  echo "watchdog database secret must contain one non-empty line" >&2
  exit 1
fi
if ! grep -q "orin_watchdog" "${secret_path}"; then
  echo "watchdog database URL does not identify the dedicated role" >&2
  exit 1
fi

if [[ ! -d "${ORIN_TRIGGER_SOCKET_DIR}" ]]; then
  echo "watchdog socket directory does not exist" >&2
  exit 1
fi
if docker ps --quiet \
    --filter label=com.docker.compose.project=orin-control \
    --filter label=com.docker.compose.service=watchdog | grep -q .; then
  echo "watchdog service is already running" >&2
  exit 1
fi

watchdog_jobs="$(
  docker exec openclaw-utgd-openclaw-1 openclaw cron list --all --json
)"
python3 - "${watchdog_jobs}" <<'PY'
import json
import sys

jobs = json.loads(sys.argv[1]).get("jobs", [])
enabled = [
    job
    for job in jobs
    if "watchdog" in str(job.get("name", "")).lower() and job.get("enabled")
]
if enabled:
    raise SystemExit("an OpenClaw watchdog schedule is already enabled")
PY

image="local/orin-watchdog:${ORIN_DEPLOY_SHA}"
if [[ "${require_image}" == true ]]; then
  if ! docker image inspect "${image}" >/dev/null 2>&1; then
    echo "immutable watchdog image is missing" >&2
    exit 1
  fi
  image_revision="$(
    docker image inspect "${image}" \
      --format '{{ index .Config.Labels "org.opencontainers.image.revision" }}'
  )"
  if [[ "${image_revision}" != "${ORIN_DEPLOY_SHA}" ]]; then
    echo "watchdog image revision does not match deployment revision" >&2
    exit 1
  fi
fi

echo "Phase 5 watchdog preflight passed; no service or schedule was changed"
