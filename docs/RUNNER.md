# ORIN Runner

The deterministic runner is the only approved command boundary for ORIN pipeline execution. OpenClaw must not receive shell access or Shopify credentials; the control API creates a tenant-scoped job and the lease-bound worker invokes this runner.

## Install and test

```bash
uv sync --frozen --group dev
uv run --frozen pytest
```

The repository requires Python 3.12 and uv 0.11.16. Dependency resolution is fixed by `uv.lock`.

## Run contract

```bash
uv run --frozen python -m orin_runner run \
  --client-id hoverboard_store \
  --request-id 00000000-0000-4000-8000-000000000001 \
  --mode dry-run \
  --workspace-root /data/.openclaw/workspace
```

`--request-id` is mandatory and UUID-shaped. Reusing a request ID returns its existing durable result instead of executing the pipeline again.

`hidden-draft` maps to the existing double-confirmation safety gate. It must remain unscheduled until controlled write, retry, and reconciliation tests pass.

## Evidence

Each new request creates a private run directory under:

```text
<workspace>/clients/<client>/content_engine/automation_state/runs/<run_id>/
```

It contains:

- `events.jsonl`
- `stdout.log`
- `stderr.log`
- `pipeline_preview.json` when produced
- authoritative `final_result.json`

The result follows `schemas/final_result.v1.schema.json`. It always records `shopify_published: false`, a create count no greater than one, queue-change status, code version, timestamps, and a stable error code for failures.

The local file lock enforces one runner process per client artifact root. Supabase leases and database idempotency replace this local mechanism in the production worker phase.

## Container image

`Dockerfile.runner` builds a non-root, one-shot runner image from a digest-pinned Python 3.12 base. Source control commit is injected as `ORIN_CODE_VERSION` during the build.

GitHub publishes only immutable version and commit tags when a tag matching `orin-runner-v*` is pushed. It intentionally does not publish `latest`.

The image defaults to non-root UID/GID `10001:10001`. When bind-mounting an existing private workspace, run it as that workspace's non-root owner and make the evidence directory writable by the same identity. For example:

```bash
runtime_uid="$(stat -c %u /path/to/workspace)"
runtime_gid="$(stat -c %g /path/to/workspace)"
docker run --rm --network none --read-only \
  --user "${runtime_uid}:${runtime_gid}" \
  --tmpfs /tmp:rw,noexec,nosuid,size=64m \
  --mount type=bind,src=/path/to/workspace,dst=/runtime,readonly \
  --mount type=bind,src=/path/to/evidence,dst=/evidence \
  IMAGE run --client-id hoverboard_store --request-id UUID \
  --mode dry-run --workspace-root /runtime --artifact-root /evidence
```

Do not solve mount permissions by running the worker as root.
