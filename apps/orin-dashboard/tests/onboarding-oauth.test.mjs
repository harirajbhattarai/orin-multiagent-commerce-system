import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const repositoryRoot = new URL("../../../", import.meta.url);

test("customer onboarding uses Shopify OAuth without exposing a token field", async () => {
  const source = await readFile(new URL("apps/orin-dashboard/src/Onboarding.jsx", repositoryRoot), "utf8");
  assert.match(source, /Connect Shopify/);
  assert.match(source, /beginOnboardingShopifyOAuth/);
  assert.doesNotMatch(source, /Shopify Admin API access token/);
  assert.doesNotMatch(source, /shpat_/);
});

test("OAuth callback is HMAC checked and state is stored only as a digest", async () => {
  const source = await readFile(new URL("supabase/functions/orin-client-onboarding/index.ts", repositoryRoot), "utf8");
  assert.match(source, /validShopifyHmac/);
  assert.match(source, /service_consume_shopify_oauth_state/);
  assert.match(source, /p_state_hash: await sha256\(state\)/);
  assert.match(source, /service_store_onboarding_shopify_oauth_connection/);
});

test("official Commerce origin is accepted by onboarding and billing", async () => {
  const onboarding = await readFile(new URL("supabase/functions/orin-client-onboarding/index.ts", repositoryRoot), "utf8");
  const billing = await readFile(new URL("supabase/functions/orin-shopify-billing/index.ts", repositoryRoot), "utf8");
  for (const source of [onboarding, billing]) {
    assert.match(source, /"https:\/\/commerce\.navarna\.ai"/);
    assert.match(source, /"https:\/\/orin-hbstore-dashboard\.tooxic-ai\.chatgpt\.site"/);
  }
  assert.match(onboarding, /\?\? "https:\/\/commerce\.navarna\.ai\/\?view=onboarding"/);
  assert.match(onboarding, /searchParams\.get\("view"\) === "onboarding"/);
  assert.match(billing, /searchParams\.get\("view"\) === "plan"/);
});

test("OAuth service functions are not executable by browser roles", async () => {
  const migration = await readFile(new URL("supabase/migrations/20260823114031_shopify_oauth_onboarding.sql", repositoryRoot), "utf8");
  assert.match(migration, /revoke all on table public\.shopify_oauth_states from public, anon, authenticated/i);
  assert.match(migration, /revoke all on function public\.service_consume_shopify_oauth_state[\s\S]+from public, anon, authenticated/i);
  assert.match(migration, /grant execute on function public\.service_consume_shopify_oauth_state[\s\S]+to service_role/i);
});

test("the Shopify callback bypasses gateway JWT only because the function verifies POST sessions itself", async () => {
  const config = await readFile(new URL("supabase/config.toml", repositoryRoot), "utf8");
  const source = await readFile(new URL("supabase/functions/orin-client-onboarding/index.ts", repositoryRoot), "utf8");
  assert.match(config, /\[functions\.orin-client-onboarding\][\s\S]*verify_jwt = false/);
  assert.match(source, /request\.method === "GET"/);
  assert.match(source, /validShopifyHmac/);
  assert.match(source, /supabase\.auth\.getUser\(\)/);
  assert.match(source, /platform_operators/);
});

test("public-app OAuth requests expiring offline tokens and stores refresh material server-side", async () => {
  const source = await readFile(new URL("supabase/functions/orin-client-onboarding/index.ts", repositoryRoot), "utf8");
  const migration = await readFile(new URL("supabase/migrations/20260823114031_shopify_oauth_onboarding.sql", repositoryRoot), "utf8");
  assert.match(source, /expiring: "1"/);
  assert.match(source, /refresh_token/);
  assert.match(migration, /shopify_refresh_secret_id/);
  assert.doesNotMatch(await readFile(new URL("apps/orin-dashboard/src/Onboarding.jsx", repositoryRoot), "utf8"), /refresh_token/);
});

test("expired Shopify OAuth access tokens refresh and rotate only through service boundaries", async () => {
  const source = await readFile(new URL("supabase/functions/orin-client-onboarding/index.ts", repositoryRoot), "utf8");
  const migration = await readFile(new URL("supabase/migrations/20260824102413_rotate_expiring_shopify_oauth_tokens.sql", repositoryRoot), "utf8");
  assert.match(source, /grant_type: "refresh_token"/);
  assert.match(source, /service_rotate_client_shopify_oauth_tokens/);
  assert.match(source, /await ensureFreshShopifyConnection\(service, operatorId, clientId\)/);
  assert.match(migration, /perform orin_private\.assert_commissioning_boundary_closed\(p_client_id\)/i);
  assert.match(migration, /vault\.update_secret/i);
  assert.match(migration, /revoke all on function public\.service_rotate_client_shopify_oauth_tokens[\s\S]+from public, anon, authenticated/i);
  assert.match(migration, /grant execute on function public\.service_rotate_client_shopify_oauth_tokens[\s\S]+to service_role/i);
  assert.doesNotMatch(await readFile(new URL("apps/orin-dashboard/src/Onboarding.jsx", repositoryRoot), "utf8"), /refresh_token/);
});

test("Shopify billing refresh authenticates with both app credentials", async () => {
  const source = await readFile(new URL("supabase/functions/orin-shopify-billing/index.ts", repositoryRoot), "utf8");
  assert.match(source, /Deno\.env\.get\("SHOPIFY_CLIENT_ID"\)/);
  assert.match(source, /Deno\.env\.get\("SHOPIFY_CLIENT_SECRET"\)/);
  assert.match(source, /grant_type: "refresh_token"/);
  assert.match(source, /client_id: shopifyClientId/);
  assert.match(source, /client_secret: shopifyClientSecret/);
  assert.match(source, /service_rotate_client_shopify_billing_tokens/);
});

test("draft approval uses one server-mediated scheduler handoff", async () => {
  const app = await readFile(new URL("apps/orin-dashboard/src/App.jsx", repositoryRoot), "utf8");
  const client = await readFile(new URL("apps/orin-dashboard/src/lib/dashboardClient.js", repositoryRoot), "utf8");
  const source = await readFile(new URL("supabase/functions/orin-client-onboarding/index.ts", repositoryRoot), "utf8");
  const migration = await readFile(new URL("supabase/migrations/20260829091501_oauth_approval_handoff.sql", repositoryRoot), "utf8");
  assert.match(app, /kind === "approve_hidden_draft"[\s\S]+approveUnpublishedDraft/);
  assert.match(client, /action: "approve_unpublished_draft"/);
  assert.match(source, /body\.action === "approve_unpublished_draft"/);
  assert.match(source, /service_begin_oauth_approval_handoff/);
  assert.match(source, /ensureFreshShopifyConnection\([\s\S]*service,[\s\S]*operatorId,[\s\S]*clientId,[\s\S]*true,[\s\S]*\)/);
  assert.match(source, /service_bind_oauth_approval_handoff/);
  assert.match(source, /service_cancel_oauth_approval_handoff/);
  assert.match(migration, /service_begin_oauth_approval_handoff[\s\S]+to service_role/i);
  assert.doesNotMatch(app, /refresh_token/);
});

test("no-code commissioning is service mediated and fail closed", async () => {
  const source = await readFile(new URL("supabase/functions/orin-client-onboarding/index.ts", repositoryRoot), "utf8");
  const migration = await readFile(new URL("supabase/migrations/20260823211817_no_code_client_commissioning_requests.sql", repositoryRoot), "utf8");
  assert.match(source, /body\.action === "request_commissioning"/);
  assert.match(source, /service_request_client_commissioning/);
  assert.match(migration, /commissioning requires maintenance with every execution and Shopify gate closed/i);
  assert.match(migration, /commissioning requires zero active jobs/i);
  assert.match(migration, /commissioning requires zero open incidents/i);
  assert.match(migration, /grant execute on function public\.service_request_client_commissioning[\s\S]+to service_role/i);
  assert.doesNotMatch(migration, /grant execute on function public\.service_request_client_commissioning[\s\S]+to authenticated/i);
});

test("recurring pilot activation is no-code, idempotent, and Shopify-blind", async () => {
  const source = await readFile(new URL("supabase/functions/orin-client-onboarding/index.ts", repositoryRoot), "utf8");
  const client = await readFile(new URL("apps/orin-dashboard/src/lib/dashboardClient.js", repositoryRoot), "utf8");
  const migration = await readFile(new URL("supabase/migrations/20260826113000_generic_recurring_pilot.sql", repositoryRoot), "utf8");
  assert.match(source, /body\.action === "request_recurring_pilot"/);
  assert.match(source, /service_activate_client_recurring_pilot/);
  assert.match(client, /requestClientRecurringPilot/);
  assert.match(client, /activation_request_id: activationRequestId/);
  assert.match(migration, /shopify_writes_enabled = false/i);
  assert.match(migration, /requested_mode[\s\S]+dry-run/i);
  assert.match(migration, /grant execute on function public\.service_activate_client_recurring_pilot[\s\S]+to service_role/i);
  assert.doesNotMatch(migration, /grant execute on function public\.service_activate_client_recurring_pilot[\s\S]+to authenticated/i);
});
