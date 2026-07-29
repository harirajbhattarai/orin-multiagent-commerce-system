# ORIN read-only watchdog

The Phase 5 watchdog is a fixed-scope observation boundary for the Hoverboard
Store production scheduler. It is implemented before activation so its
database, socket, agent, and container permissions can be reviewed
independently. It must not be scheduled or deployed until Phase 4 scheduler
ownership is proven.

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
- `ORIN_SCHEDULED_RUN_INVARIANT_VIOLATION` when a terminal receipt reports an
  unexpected publish, queue mutation, create count, reconciliation state, or
  invalid code version;
- `ORIN_SCHEDULER_NOT_ACTIVE` when production ownership or automation gates
  are not active.

An alert result exits with status 1. Configuration or database failures exit
with status 2 and expose only the exception type, never connection details.
The OpenClaw client treats an alert as a nonzero exit. Delivery remains
unconfigured until commissioning proves both a healthy receipt and a harmless
simulated alert.

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

## Fixed socket boundary

The watchdog server accepts only:

`CHECK ORIN-HBSTORE WATCHDOG V1`

over `/run/orin/orin-hbstore-watchdog.sock`. The corresponding OpenClaw path is
`/data/.openclaw/run/orin/orin-hbstore-watchdog.sock`. Unix peer credentials
must match the configured OpenClaw UID. Any argument, alternate request, peer,
or database failure is rejected with a redacted stable code.

OpenClaw receives no database URL. Its reviewed client
`deploy/openclaw/orin-watchdog/bin/orin_watchdog_check.py` accepts no arguments,
validates the response schema, and exits nonzero for alerts or service
failures.

## Disabled deployment

The `watchdog` Compose profile is disabled by default, has no port or writable
volume, runs as UID `10003`, uses a read-only root filesystem, and mounts only
its private database URL plus the Unix-socket directory. It is not activated
by merging this code. Its immutable image is pinned separately with
`ORIN_WATCHDOG_DEPLOY_SHA`; advancing the watchdog must not replace the proven
worker or scheduler-trigger images pinned by `ORIN_DEPLOY_SHA`.

After Phase 4 is proven:

1. migrate the reviewed role;
2. separately change only `orin_watchdog` to `LOGIN` and install its unique
   session-pooler URL;
3. install the URL with `deploy/vps/install_watchdog_db_secret.sh`;
4. seal the successful automatic scheduler receipt as root-owned mode `0400`
   at `/docker/orin/evidence/phase4/latest_automatic_proof.json`, using schema
   `orin.phase4-proof/v1`;
5. run `deploy/vps/watchdog_preflight.sh`;
6. build the immutable image from the reviewed commit;
7. run `deploy/vps/watchdog_preflight.sh --require-image`;
8. start the profile with every watchdog schedule still disabled;
9. verify unauthorized and malformed socket requests fail closed;
10. simulate a harmless missed-run snapshot and require an alert plus
   `ORIN_SCHEDULED_RUN_MISSED`;
11. verify a real completed receipt returns healthy;
12. create one disabled OpenClaw schedule for `11:15 Europe/London`;
13. run one near-term automatic check and verify its exact receipt;
14. only then enable read-only alert delivery after the production run.
