# ORIN HBStore scheduler trigger

The scheduler trigger is the only approved bridge from OpenClaw scheduling to
the durable ORIN job queue. It is deliberately split across three boundaries:

1. OpenClaw runs one fixed Python argv with no arguments.
2. The client sends one constant line over a private Unix socket.
3. A separate non-root sidecar calls one zero-argument private PostgreSQL
   function using the `orin_scheduler` role.

OpenClaw receives no shell, database URL, Supabase token, Shopify credential,
writer credential, client selector, mode selector, payload, or schedule input.

## Database capability

`orin_scheduler`:

- cannot log in until its password is separately provisioned;
- is non-superuser, non-admin, and cannot bypass RLS;
- has no direct table, sequence, worker-function, API-function, or evidence
  privileges;
- may execute only
  `orin_private.enqueue_hoverboard_scheduled_job()`.

The private function accepts no parameters. It is hard-wired to:

- client: `hoverboard_store`;
- scheduler owner: `openclaw:orin-hbstore-prod`;
- schedule identity: one London calendar date;
- mode: the database `allowed_mode`;
- concurrency: exactly one.

The resulting job has an empty payload—the worker rejects arbitrary job
payloads by design. The immutable `source_job_key`
(`scheduler:orin-hbstore-prod:<London-date>`) is the durable schedule identity.

Before inserting, the function requires active client, request intake,
automation, scheduler ownership, allowed mode, and—when the mode is
`hidden-draft`—the Shopify write gate. Retries on the same London date return
the same durable job.

## Unix socket boundary

The sidecar listens at:

`/run/orin/orin-hbstore-trigger.sock`

The corresponding path visible inside the OpenClaw container is:

`/data/.openclaw/run/orin/orin-hbstore-trigger.sock`

The only accepted request is:

`TRIGGER ORIN-HBSTORE V1`

The directory is mode `0710` and the socket is mode `0620`, owned by the
dedicated sidecar UID and the OpenClaw runtime group. Before reading the fixed
request, the server authenticates the connecting process with Unix peer
credentials and requires the configured OpenClaw runtime UID (`1000` on the
current VPS). Other UIDs and any other request bytes are rejected without
calling PostgreSQL. Database errors are redacted to a stable blocked response.

## Deployment state

The Compose service is profile-gated as `scheduler-trigger`, has no port, runs
as UID `10002` with the OpenClaw runtime GID solely for socket traversal, uses
a read-only root filesystem, drops all capabilities, and mounts only:

- its file-backed scheduler database URL;
- the private Unix-socket directory.

It does not mount the OpenClaw workspace, worker evidence, Shopify credential,
writer credential, or Docker socket.

The OpenClaw schedule must remain disabled while this boundary is commissioned.
First prove that closed gates return a blocked response. Then perform a
controlled dry-run with Shopify writes still disabled. Do not enable automatic
hidden-draft scheduling until the exact `final_result.json` and scheduler
ownership transition are verified.
