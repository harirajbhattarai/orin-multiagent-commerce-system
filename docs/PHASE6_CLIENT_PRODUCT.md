# Phase 6 client-product boundary

## Status

The database and application implementation is complete. Production
commissioning remains deliberately split into two user-owned handoffs:

1. the first Supabase Auth user and `client_members` owner row;
2. the server-side evidence-sync key installed directly on the VPS.

Shopify writes remain disabled. Dashboard decisions do not enqueue jobs or
call Shopify.

## Database contract

Migration `20260802223938_phase6_client_product_boundary.sql` adds:

- `content_decisions`, an immutable tenant- and version-bound ledger;
- `client_dashboard_snapshot`, a `security_invoker` view over RLS-protected
  tables;
- a durable scheduler-health refresh trigger on scheduler-owned run insertion;
- column-level customer grants that exclude `runs.final_result`, local artifact
  paths, and the raw execution queue.

Authenticated members can read only their tenant. Only `owner` and `operator`
members can append decisions. `viewer` members cannot insert. A stale content
version fails closed, and `request_id` is the idempotency key.

`approve_hidden_draft` records client intent only. It does not change
`client_runtime_settings`, create a `content_job`, enable Shopify writes, or
publish anything.

## Dashboard contract

The dashboard uses a browser-safe Supabase publishable key and magic-link
authentication. It no longer falls back to demo data when a live authenticated
workspace fails to load. The production behaviors are:

- no session: show the sign-in screen;
- authenticated member: load the redacted tenant snapshot;
- authenticated nonmember: fail closed with a workspace error;
- owner/operator decision: append one immutable ledger row;
- duplicate browser retry: replay the existing row only when every field
  matches.

Never place a server secret, service-role key, database URL, Shopify token, or
writer key in a `VITE_` variable.

## Portable evidence

`orin-evidence-sync` is a one-shot service. It reads completed local evidence,
validates `orin.final-result/v2`, uploads supported files to the private
`orin-evidence` bucket, and indexes SHA-256 metadata in `run_artifacts`.

Safety properties:

- local evidence is mounted read-only;
- the sync service has no Shopify, writer, OpenClaw, or database credential;
- existing objects are never overwritten;
- an existing object is accepted only when its digest matches;
- object paths are fixed to `<client_id>/<run_id>/<filename>`;
- only terminal runs already present in `public.runs` are accepted.

Install the server-side key interactively on the VPS:

```bash
deploy/vps/install_evidence_service_key.sh
deploy/vps/preflight.sh --require-secrets --require-evidence-secret
```

Then run the isolated one-shot profile:

```bash
docker compose --env-file /docker/orin/deployment.env \
  -f deploy/vps/compose.yml --profile evidence-sync build evidence-sync
docker compose --env-file /docker/orin/deployment.env \
  -f deploy/vps/compose.yml --profile evidence-sync run --rm evidence-sync
```

## Commissioning checklist

1. Create or sign in the intended HBStore user through Supabase Auth.
2. Insert one `client_members` row with `client_id='hoverboard_store'` and
   `role='owner'` through a controlled admin action.
3. Sign in to the dashboard and prove the snapshot is live.
4. Record one harmless `request_changes` decision and verify no job is queued.
5. Retry the same request and prove one decision row exists.
6. Install the evidence key without exposing it in chat or shell history.
7. Run evidence sync and verify Storage objects and matching `run_artifacts`.
8. Download one object as the authenticated owner and verify its SHA-256.
9. Re-run the Supabase security advisor.

Phase 6 is complete only after all nine checks pass. An approval-to-worker
bridge is a later product phase and must retain separate runtime and Shopify
write gates.
