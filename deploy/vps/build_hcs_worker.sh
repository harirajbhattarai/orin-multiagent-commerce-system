#!/usr/bin/env bash
set -euo pipefail

deploy_sha="${ORIN_DEPLOY_SHA:-}"
project_root="${ORIN_PROJECT_ROOT:-}"
deployment_env="${ORIN_DEPLOY_ENV_FILE:-/docker/orin/deployment.env}"

if [[ ! "${deploy_sha}" =~ ^[0-9a-f]{40}$ ]]; then
  echo "ORIN_DEPLOY_SHA must be a full Git commit" >&2
  exit 1
fi
if [[ -z "${project_root}" || ! -d "${project_root}/.git" ]]; then
  echo "ORIN_PROJECT_ROOT must identify the exact Git checkout" >&2
  exit 1
fi
if [[ ! -f "${deployment_env}" ]]; then
  echo "deployment environment file does not exist: ${deployment_env}" >&2
  exit 1
fi
if [[ -n "$(git -c safe.directory="${project_root}" -C "${project_root}" status --porcelain)" ]]; then
  echo "HCS worker build checkout is not clean" >&2
  exit 1
fi
actual_sha="$(git -c safe.directory="${project_root}" -C "${project_root}" rev-parse HEAD)"
if [[ "${actual_sha}" != "${deploy_sha}" ]]; then
  echo "HCS worker build checkout mismatch: expected ${deploy_sha}, received ${actual_sha}" >&2
  exit 1
fi

compose_file="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/compose.yml"
docker compose --env-file "${deployment_env}" -f "${compose_file}" \
  --profile hcs-automatic-worker build hcs-worker-daemon

image="local/orin-worker:${deploy_sha}"
image_revision="$(docker image inspect "${image}" \
  --format '{{index .Config.Labels "org.opencontainers.image.revision"}}')"
if [[ "${image_revision}" != "${deploy_sha}" ]]; then
  echo "HCS worker image revision mismatch" >&2
  exit 1
fi
docker run --rm --entrypoint python "${image}" -c \
  'from orin_worker.cli import build_parser; parsed = build_parser().parse_args(["serve", "--client-id", "hcs_gadgets"]); assert parsed.client_id == "hcs_gadgets"'

echo "HCS worker image built from verified commit ${deploy_sha}"
