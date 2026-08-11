# Phase 7 Prefect shadow

Phase 7 introduces Prefect as an isolated observer. It does not transfer
scheduler ownership and it cannot create ORIN jobs or Shopify articles.

## Fixed stack

- Prefect `3.8.1`, pinned by version and image digest.
- One self-hosted Prefect API/background process.
- One dedicated PostgreSQL 16 database with `pg_trgm`.
- One `process` work pool, paused with concurrency `1`.
- One paused deployment with no schedule.
- No Redis while the server has only one API/background process.

The API binds only to VPS loopback port `54200`. Open it through an SSH tunnel;
it has no Traefik labels or public route.

## Security boundary

The worker receives only:

- Prefect API basic authentication; and
- a unique `orin_prefect_shadow` Supabase session-pooler URL.

It never receives Shopify, model-writer, ORIN worker, scheduler, control API,
evidence service, OpenClaw, or Docker credentials. The database role has no
direct table privileges and can call only
`orin_private.get_prefect_shadow_snapshot(text)`. That function rejects every
client except `hoverboard_store` and excludes draft bodies, notes, paths, user
membership, and private evidence metadata.

## Commissioning order

1. Merge and apply the Phase 7 migration while existing ORIN gates stay
   closed.
2. In the Supabase SQL editor, create a unique password and enable only the new
   login:

   ```sql
   alter role orin_prefect_shadow login password 'REPLACE_WITH_UNIQUE_PASSWORD';
   ```

3. On the VPS, copy `deployment.env.example` to
   `/docker/orin-prefect-shadow/deployment.env`, set the exact reviewed commit,
   and keep it mode `0600`.
4. Generate the private Prefect credentials:

   ```bash
   deploy/prefect-shadow/install_server_secrets.sh
   ```

5. Build the Supabase session-pooler URL with username
   `orin_prefect_shadow.<project-ref>` and install it interactively:

   ```bash
   deploy/prefect-shadow/install_shadow_db_secret.sh
   ```

6. Run the preflight. It starts nothing:

   ```bash
   set -a
   source /docker/orin-prefect-shadow/deployment.env
   set +a
   deploy/prefect-shadow/preflight.sh --require-shadow-secret
   ```

7. Build and start only the private server, then apply the paused deployment:

   ```bash
   docker compose --env-file /docker/orin-prefect-shadow/deployment.env \
     -f deploy/prefect-shadow/compose.yml --profile server build prefect-server
   docker compose --env-file /docker/orin-prefect-shadow/deployment.env \
     -f deploy/prefect-shadow/compose.yml --profile server up -d
   docker compose --env-file /docker/orin-prefect-shadow/deployment.env \
     -f deploy/prefect-shadow/compose.yml --profile bootstrap run --rm prefect-bootstrap
   ```

The bootstrap must report `ORIN_PREFECT_SHADOW_BOOTSTRAP_OK`. Both the work pool
and deployment remain paused and the deployment has no schedules.

## First shadow comparison

Start the worker only for a supervised read-only run. Resume the work pool,
create one ad-hoc deployment run, wait for a terminal receipt, then pause the
pool and stop the worker. Do not add a schedule during the first comparison.

Promotion requires several same-date `match` receipts against the existing
OpenClaw dry-run owner. A future controlled live Prefect run is a separate
change: it requires review, retry/reconciliation proof, and an explicit
ownership transfer. Shopify writes stay disabled throughout this foundation.

The separately isolated one-shot ownership proof is specified in
`docs/PREFECT_OWNERSHIP_COMMISSIONING.md`. It does not widen the read-only
shadow role or add a recurring schedule.
