# ORIN control API

The control API is the only planned request boundary for customer users and
OpenClaw. It creates durable database jobs; it does not execute the runner,
contact Shopify, accept shell commands, or own a schedule.

## Request contract

```http
POST /v1/clients/{client_id}/run-requests
Authorization: Bearer <Supabase user access token>
Content-Type: application/json

{
  "request_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
  "mode": "dry-run"
}
```

`request_id` is mandatory and UUID-shaped. Replaying the same request returns
the existing job with HTTP 200. A new request returns HTTP 201. Reusing an ID
with different immutable inputs returns HTTP 409.

The request model rejects extra fields. There is no command, payload, schedule,
Shopify target, or hidden-draft field. `hidden-draft` is outside the Phase 3A
API contract.

## Authentication and authorization

The API:

1. accepts only a Bearer token;
2. requires the exact `ES256` algorithm;
3. verifies the token using the project's public JWKS;
4. verifies issuer, `authenticated` audience, expiry, issued-at, role, and UUID
   subject;
5. rejects anonymous and service-role tokens;
6. verifies client membership and owner/operator role again in PostgreSQL.

The database records the JWT subject in `content_jobs.requested_by`. Its RLS
insert policy independently checks active client status, request-intake gate,
dry-run mode, and owner/operator membership.

## Database credential boundary

The application refuses readiness and requests unless `current_user` is exactly
`orin_api`. The role is created as:

- `NOLOGIN` until separately provisioned;
- non-superuser;
- no role/database creation;
- no RLS bypass;
- SELECT only on clients, memberships, runtime settings, and jobs;
- column-limited INSERT on jobs;
- no UPDATE or DELETE;
- no run evidence, incidents, scheduler, storage, or Shopify access.

Do not run the API as `postgres` and do not give it a Supabase secret/service
key. The role password must be generated and installed outside migrations,
source control, chat, OpenClaw, and container images. Deployment is blocked
until that one-time provisioning step is designed and verified.

The VPS contract mounts the complete database URL as a mode-`0400` file and
sets only `ORIN_DATABASE_URL_FILE=/run/secrets/control_database_url`. A direct
`ORIN_DATABASE_URL` remains available for isolated development, but configuring
both sources is rejected. The disabled-by-default deployment sequence is in
`deploy/vps/README.md`.

## Safety gates

All current development gates remain closed:

- client status `maintenance`
- request intake disabled
- automation disabled
- Shopify writes disabled
- scheduler disabled

The API can be built and tested, but a real request cannot enter the queue.

## Run locally

Copy the example names into a private environment file and supply secrets only
through the local shell or secret manager:

```bash
uv run --frozen uvicorn orin_control.app:create_app \
  --factory --host 127.0.0.1 --port 8000 --workers 1
```

Endpoints:

- `/healthz`: process health; does not touch the database.
- `/readyz`: verifies database connectivity and the exact `orin_api` role.
- `/docs`: OpenAPI documentation.

Use the session pooler on an IPv4-only VPS. Use a direct connection only when
the VPS has verified IPv6 connectivity. Keep the SQLAlchemy pool and Uvicorn
worker count at one during initial reliability testing.
