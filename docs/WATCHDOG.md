# ORIN read-only watchdog

The Phase 5 watchdog is a one-shot observation command for the fixed
Hoverboard Store production boundary. It is implemented before activation so
its database and container permissions can be reviewed independently. It must
not be scheduled or deployed until Phase 4 scheduler ownership is proven.

## Fixed policy

The watchdog accepts no client, schedule, mode, or command arguments. It checks:

- client `hoverboard_store`;
- scheduler owner `openclaw:orin-hbstore-prod`;
- source key `scheduler:orin-hbstore-prod:<London date>`;
- expected daily schedule `11:00 Europe/London`;
- a 15-minute grace period.

Before `11:15` it returns `pending`. After the grace period it returns:

- `healthy` when exactly the expected job and completed run are observable;
- `ORIN_SCHEDULED_RUN_MISSED` when no daily job exists;
- `ORIN_SCHEDULED_RUN_STUCK` when the job is still active;
- `ORIN_SCHEDULED_RUN_FAILED` when the job or run is not completed;
- `ORIN_SCHEDULER_NOT_ACTIVE` when production ownership or automation gates
  are not active.

An alert result exits with status 1. Configuration or database failures exit
with status 2 and expose only the exception type, never connection details.
Delivery is intentionally outside the watchdog process and remains
unconfigured.

## Database boundary

Migration `phase5_add_readonly_watchdog_role` creates `orin_watchdog` as
`NOLOGIN`, `NOINHERIT`, non-admin, and non-RLS-bypass. It receives column-level
`SELECT` only on the minimum client, runtime, scheduler, job, and run fields.
RLS restricts every table to `hoverboard_store`.

The role cannot:

- insert, update, or delete any row;
- execute trigger, claim, completion, or reconciliation functions;
- read client membership, incidents, or artifact metadata;
- access Shopify, model, worker, scheduler, or control credentials.

The eventual VPS credential must be installed as
`/docker/orin/secrets/watchdog_database_url`, owner `10003:10003`, mode `0400`.
Do not reuse any existing database password or URL.

## Disabled deployment

The `watchdog` Compose profile is disabled by default, has no port or writable
volume, runs as `10003:10003`, uses a read-only root filesystem, and exits after
one observation.

After Phase 4 is proven:

1. migrate the reviewed role;
2. separately change only `orin_watchdog` to `LOGIN` and install its unique
   session-pooler URL;
3. run `deploy/vps/preflight.sh --require-watchdog-secret`;
4. build the immutable image from the reviewed commit;
5. simulate a harmless missed-run snapshot and require exit 1 plus
   `ORIN_SCHEDULED_RUN_MISSED`;
6. verify a real completed receipt returns healthy;
7. only then attach read-only alert delivery after the production run.
