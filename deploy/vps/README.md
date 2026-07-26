# VPS deployment contract

This directory defines the maintenance-only deployment boundary for
`srv1532965`. It does not replace or modify the Hostinger OpenClaw Compose
project.

The current verified production state and next approved step are recorded in
[`docs/MAINTENANCE_STATUS.md`](../../docs/MAINTENANCE_STATUS.md).

## Invariants

- Both services require explicit Compose profiles; a normal `compose up` starts
  nothing.
- The API binds to `127.0.0.1` only and has no Traefik labels.
- The worker has no port, polling loop, scheduler, or restart policy.
- Neither service mounts the Docker socket or OpenClaw configuration.
- The worker mounts operational workspace data read-only and a separate private
  evidence directory read-write.
- The scheduler bridge is a fixed-input Unix-socket sidecar with no port,
  Shopify credential, writer credential, worker credential, or OpenClaw
  workspace mount.
- Database URLs and the Shopify access token are file-backed Compose secrets,
  not environment values.
- Containers are non-root, read-only, capability-free, resource-limited, and
  use `no-new-privileges`.
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
   `10002:10002` mode `0700` for the private scheduler socket.
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
