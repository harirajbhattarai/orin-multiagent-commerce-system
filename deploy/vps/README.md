# VPS deployment contract

This directory defines the maintenance-only deployment boundary for
`srv1532965`. It does not replace or modify the Hostinger OpenClaw Compose
project.

The current verified production state and next approved step are recorded in
[`docs/MAINTENANCE_STATUS.md`](../../docs/MAINTENANCE_STATUS.md).

## Invariants

- Every service requires an explicit Compose profile; a normal `compose up`
  starts nothing.
- The API binds to `127.0.0.1` only and has no Traefik labels.
- The manual worker is one-shot with no restart policy. The automatic worker
  repeats only the same fixed atomic claim path and has no port or scheduler.
- No service mounts the Docker socket or OpenClaw configuration.
- The worker mounts operational workspace data read-only and a separate private
  evidence directory read-write.
- The scheduler bridge is a fixed-input Unix-socket sidecar with no port,
  Shopify credential, writer credential, worker credential, or OpenClaw
  workspace mount.
- Database URLs and the Shopify access token are file-backed Compose secrets,
  not environment values.
- Containers are non-root, read-only, capability-free, resource-limited, and
  use `no-new-privileges`.
- Portable evidence sync is an isolated one-shot profile. It mounts local
  evidence read-only and never receives Shopify or database credentials.
- Images are built from one exact reviewed Git commit and tagged with that
  commit. `latest` and moving branches are prohibited.

## Verified host facts

- Host persistent data root: `/docker/openclaw-utgd/data`
- Canonical checkout: `/docker/openclaw-utgd/data/orin-multiagent-commerce-system`
- Runtime workspace: `/docker/openclaw-utgd/data/.openclaw/workspace`
- Runtime owner: UID/GID `1000:1000` (`ubuntu`)
- Existing OpenClaw port: public `50083`
- Existing reverse proxy: Traefik on ports 80/443
- ORIN API maintenance port: loopback `58080`
- Legacy OpenClaw scheduler job remains defined but disabled, with no next wake

The VPS checkout was at `33e84b6` during inventory while reviewed `main` was at
`bcd82fe`. The ORIN deploy key works when explicitly selected, but the existing
SSH alias points to a different repository key. Do not rely on the alias during
the controlled source update.

## Controlled sequence

1. Keep the OpenClaw scheduler disabled and verify `nextWakeAtMs` is null.
2. Fetch with the existing repository-scoped key explicitly selected:

   ```bash
   export GIT_SSH_COMMAND='ssh -i /docker/openclaw-utgd/data/.ssh/orin_multiagent_github -o IdentitiesOnly=yes -o UserKnownHostsFile=/docker/openclaw-utgd/data/.ssh/known_hosts'
   sudo -u ubuntu --preserve-env=GIT_SSH_COMMAND \
     git -C /docker/openclaw-utgd/data/orin-multiagent-commerce-system fetch origin main
   ```

3. Verify the exact target commit exists, the checkout is clean, and update
   `main` using fast-forward only. Never reset the worktree.
4. Create `/docker/orin/secrets` as root mode `0700` and
   `/docker/orin/evidence` as `ubuntu:ubuntu` mode `0700`.
   Create `/docker/openclaw-utgd/data/.openclaw/run/orin` as UID/GID
   `10002:1000` mode `0710`. The trigger creates its socket as
   `10002:1000` mode `0620`, allowing only the OpenClaw runtime group to
   traverse the directory and call the fixed endpoint.
5. Copy `deployment.env.example` to `/docker/orin/deployment.env`, set its exact
   reviewed commit, and keep it mode `0600`. It contains no credential.
6. Export that non-secret configuration and run preflight before creating any
   login or starting any service:

   ```bash
   set -a
   source /docker/orin/deployment.env
   set +a
   deploy/vps/preflight.sh
   ```

7. Build both local images from the exact checkout. Building does not start a
   container:

   ```bash
   docker compose \
     --env-file /docker/orin/deployment.env \
     -f deploy/vps/compose.yml \
     --profile manual-api --profile manual-worker build
   ```

8. Perform the credential handoff described below, then rerun preflight with
   `deploy/vps/preflight.sh --require-secrets`.
9. Start only the API and verify both endpoints from the VPS loopback interface:

   ```bash
   docker compose --env-file /docker/orin/deployment.env \
     -f deploy/vps/compose.yml --profile manual-api up -d control-api
   curl --fail http://127.0.0.1:58080/healthz
   curl --fail http://127.0.0.1:58080/readyz
   ```

10. Stop the API. Invoke the worker once manually while maintenance and
    automation remain disabled. The required result is `no_job_due`:

    ```bash
    docker compose --env-file /docker/orin/deployment.env \
      -f deploy/vps/compose.yml --profile manual-worker run --rm worker
    ```

11. Stop and remove the new Compose project. Do not enable request intake,
    automation, Shopify writes, or any scheduler during this test.

    Before scheduler transfer, start the automatic worker with every database
    gate closed and verify repeated `no_job_due` receipts:

    ```bash
    docker compose --env-file /docker/orin/deployment.env \
      -f deploy/vps/compose.yml --profile automatic-worker \
      up -d worker-daemon

    docker compose --env-file /docker/orin/deployment.env \
      -f deploy/vps/compose.yml --profile automatic-worker \
      logs --tail 20 worker-daemon
    ```

    The daemon command is fixed to `serve`, client concurrency remains one in
    PostgreSQL, and neither `--as-of-date` nor `--job-number` is accepted.
    Stop it after commissioning unless the dedicated scheduler is being tested:

    ```bash
    docker compose --env-file /docker/orin/deployment.env \
      -f deploy/vps/compose.yml --profile automatic-worker \
      stop worker-daemon
    ```

12. Before the controlled hidden-draft test, install the Hoverboard Store
    Shopify token at the path below and run:

    ```bash
    deploy/vps/preflight.sh --require-secrets --require-shopify-secret
    ```

    A supervised test may select a future planned item without editing the
    Markdown queue by adding an explicit worker argument:

    ```bash
    docker compose --env-file /docker/orin/deployment.env \
      -f deploy/vps/compose.yml --profile manual-worker \
      run --rm worker once \
      --workspace-root /runtime \
      --artifact-root /evidence \
      --as-of-date 2026-08-08
    ```

    This flag is for a supervised manual test only. It is absent from the
    Compose service command and every scheduler.

## Scheduler trigger commissioning

The trigger design and database capability are documented in
[`docs/SCHEDULER_TRIGGER.md`](../../docs/SCHEDULER_TRIGGER.md).

After the `orin_scheduler` role has been migrated and separately changed to
`LOGIN`, install its complete session-pooler URL:

```bash
deploy/vps/install_scheduler_db_secret.sh
```

Then run:

```bash
deploy/vps/preflight.sh --require-secrets --require-scheduler-secret
```

Build and start only the trigger profile while every OpenClaw schedule remains
disabled:

```bash
docker compose --env-file /docker/orin/deployment.env \
  -f deploy/vps/compose.yml --profile scheduler-trigger build scheduler-trigger

docker compose --env-file /docker/orin/deployment.env \
  -f deploy/vps/compose.yml --profile scheduler-trigger up -d scheduler-trigger
```

The first fixed-client call must be tested with database gates closed and must
return a blocked response. Open gates only for a separately supervised dry-run.

## Read-only watchdog preparation

The disabled Phase 5 watchdog contract is documented in
[`docs/WATCHDOG.md`](../../docs/WATCHDOG.md). Do not migrate its role, install
its credential, build its image, or attach an alert schedule until Phase 4
scheduler ownership is proven.

Its credential installer and eventual preflight are:

```bash
deploy/vps/install_watchdog_db_secret.sh
deploy/vps/watchdog_preflight.sh
deploy/vps/watchdog_preflight.sh --require-image
```

The Compose profile is `watchdog`. It is a fixed-request, read-only Unix-socket
server for Hoverboard Store and must receive a unique `orin_watchdog`
session-pooler URL owned by UID/GID `10003:10003` at
`/docker/orin/secrets/watchdog_database_url`.

The OpenClaw-side client is
`deploy/openclaw/orin-watchdog/bin/orin_watchdog_check.py`. It accepts no
arguments and receives no database credential. Keep its schedule and delivery
disabled until the Phase 5 commissioning sequence in `docs/WATCHDOG.md`
passes.

Unlike the maintenance deployment preflight, `watchdog_preflight.sh` permits
the approved automatic worker and scheduler-trigger sidecar to remain running.
It requires a sealed successful Phase 4 automatic proof and refuses to make
any service or schedule change itself.

Set `ORIN_WATCHDOG_DEPLOY_SHA` to the separately reviewed watchdog commit.
Do not change `ORIN_DEPLOY_SHA` or replace the proven worker and
scheduler-trigger images merely to commission the watchdog.

## Credential handoff — user action required

Create independent random passwords for `orin_api` and `orin_worker` without
placing either password in chat, Git, OpenClaw, shell history, or a container
environment variable.

The user must change both PostgreSQL roles from `NOLOGIN` to `LOGIN` in the
Supabase dashboard and create two complete PostgreSQL URLs. Store only the URLs
on the VPS:

- `/docker/orin/secrets/control_database_url`, owner UID `10001`, mode `0400`
- `/docker/orin/secrets/worker_database_url`, owner UID `1000`, mode `0400`

Do not use `postgres`, `service_role`, or one shared credential. The application
verifies the exact database role on every operation and fails readiness if the
URL points at an overprivileged role.

Store the existing Hoverboard Store Admin API token separately at:

- `/docker/orin/secrets/hoverboard_shopify_access_token`, owner UID `1000`,
  mode `0400`

The worker receives only the token file path. The store domain, pinned API
version, and blog ID are non-secret reviewed Compose configuration. OpenClaw
does not receive or mount this secret.

### HCS split dry-run and approval workers

HCS has two non-overlapping principals. The persistent
`hcs-dry-run-worker-daemon` uses `orin_hcs_worker`, the writer API key, and
public storefront product truth. It has no Shopify token mount and can claim
only dry-run work. The temporary `hcs-approval-worker` uses
`orin_hcs_shopify_worker` plus the HCS Shopify token, has no writer API key,
runs exactly one claim with `once`, and can claim only an exact version/hash-
bound human-approved hidden draft. Broad Shopify writes and live publishing
remain unavailable.

Create unique passwords for both database roles without putting them in chat,
Git, shell history, OpenClaw, or a container environment variable. Change only
the role needed for the current commissioning step from `NOLOGIN` to `LOGIN`
in the Supabase SQL editor, build its complete session-pooler URL, and install
it interactively:

```bash
deploy/vps/install_hcs_worker_db_secret.sh
deploy/vps/install_hcs_writer_secret.sh
deploy/vps/install_hcs_shopify_worker_db_secret.sh
deploy/vps/install_hcs_shopify_secret.sh
deploy/vps/prepare_hcs_worker_storage.sh
deploy/vps/preflight.sh --require-secrets --require-hcs-worker-secret \
  --require-hcs-writer-secret
deploy/vps/preflight.sh --require-secrets \
  --require-hcs-approval-worker-secret --require-hcs-shopify-secret
```

Build the HCS image only through the provenance-checking wrapper. The exported
commit and checkout must be identical; the wrapper refuses to build when a
new image tag would otherwise be applied to an older release directory:

```bash
export ORIN_DEPLOY_SHA="$(git -C /exact/release rev-parse HEAD)"
export ORIN_PROJECT_ROOT=/exact/release
deploy/vps/build_hcs_worker.sh
```

The database installer writes only
`/docker/orin/secrets/hcs_worker_database_url`, owned by UID `10005` with mode
`0400`, and refuses to overwrite an existing file. The writer installer stores
the platform model credential separately at
`/docker/orin/secrets/hcs_writer_api_key`, also owned by UID `10005` with mode
`0400`. The Shopify installer stores the HCS Admin API token separately at
`/docker/orin/secrets/hcs_shopify_access_token`, owned by UID `10006` with mode
`0400`; it refuses to overwrite an existing token and is mounted only into the
one-shot approval worker. Its database URL is stored separately at
`/docker/orin/secrets/hcs_shopify_worker_database_url`, also owned by UID
`10006` with mode `0400`. The storage preparation keeps dry-run evidence under
`/docker/orin/evidence/hcs_gadgets` and creates the UID `10006`-only
`/docker/orin/evidence/hcs_gadgets/approval` directory for Shopify replay
evidence. Neither HCS service receives access to Hoverboard Store evidence.

Keep HCS in maintenance, with request intake, automation, both Shopify write
gates, and scheduler ownership closed, while proving that the credential-free
dry-run daemon can return `no_job_due`. For a hidden-draft proof, stop the
dry-run daemon, enable only the narrow
`approved_draft_writes_enabled` gate after an exact version-and-hash-bound
human approval exists, and invoke only the one-shot approval service. Keep
`shopify_writes_enabled=false`. Return the Shopify role to `NOLOGIN`, close all
gates, and remove both UID `10006` secrets after the transaction unless the
next controlled approval begins immediately.

## Portable evidence sync

Completed run evidence remains authoritative on the private VPS filesystem
until it is copied to the private `orin-evidence` Supabase Storage bucket. The
copy is immutable and idempotent: an existing object is accepted only when its
SHA-256 digest matches, and metadata is indexed in `public.run_artifacts`.

Install a server-side Supabase secret key without pasting it into chat or a
shell command:

```bash
deploy/vps/install_evidence_service_key.sh
deploy/vps/preflight.sh --require-secrets --require-evidence-secret
```

Then build and run only the one-shot profile:

```bash
docker compose --env-file /docker/orin/deployment.env \
  -f deploy/vps/compose.yml --profile evidence-sync build evidence-sync
docker compose --env-file /docker/orin/deployment.env \
  -f deploy/vps/compose.yml --profile evidence-sync run --rm evidence-sync
```

The key is mounted only into that one-shot container. It is never included in
the dashboard, worker daemon, OpenClaw workspace, logs, or Git. Keep the
`orin-evidence` bucket private; client downloads remain subject to Storage RLS.

## Rollback

The deployment is additive. Rollback does not touch OpenClaw or operational
workspace data:

```bash
docker compose --env-file /docker/orin/deployment.env \
  -f deploy/vps/compose.yml \
  --profile manual-api --profile manual-worker down
```

After rollback, verify no `orin-control` container is running, loopback port
58080 is closed, and the OpenClaw scheduler still has no next wake. Keep the
database roles and secret files disabled/unavailable until the next approved
test; do not delete evidence from any completed execution.
