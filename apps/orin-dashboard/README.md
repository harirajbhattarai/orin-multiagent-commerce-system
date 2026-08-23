# ORIN Commerce dashboard

Authenticated, tenant-isolated content operations and client onboarding for ORIN. The dashboard provides:

- operational health, schedules, and durable run receipts;
- the content queue and version-bound approval workflow;
- fail-closed client onboarding;
- Shopify OAuth, catalogue discovery, blog selection, and encrypted credential storage.

## Local development

```bash
npm install --prefer-offline --no-audit --no-fund
cp .env.example .env.local
npm run dev -- --host 127.0.0.1
```

Only browser-safe Supabase values belong in `.env.local`. Service-role keys, Shopify secrets, OAuth tokens, database URLs, and model credentials must never be exposed through Vite variables.

## Shopify OAuth onboarding

The customer flow is intentionally no-code:

1. The operator saves the business name, owner email, and permanent `.myshopify.com` domain.
2. **Connect Shopify** opens Shopify's authorization screen.
3. The callback validates Shopify's HMAC and a one-time, ten-minute state binding.
4. The server exchanges the code for an offline token, verifies the required scopes, discovers the store, blogs, collections, and products, and encrypts the token in Supabase Vault.
5. If the store has one blog it is selected automatically. If it has more than one, the operator chooses from the discovered list.
6. The workspace is provisioned in maintenance with intake, automation, scheduler ownership, and both Shopify write gates closed.

Configure these Edge Function secrets through Supabase, never through the dashboard build:

```text
SHOPIFY_CLIENT_ID
SHOPIFY_CLIENT_SECRET
SHOPIFY_OAUTH_REDIRECT_URI
SHOPIFY_OAUTH_SCOPES=read_products,write_content
ONBOARDING_APP_URL
ONBOARDING_ALLOWED_ORIGINS
```

`SHOPIFY_OAUTH_REDIRECT_URI` must exactly match the HTTPS callback URL registered in the Shopify app, normally:

```text
https://<project-ref>.supabase.co/functions/v1/orin-client-onboarding
```

`ONBOARDING_APP_URL` is the deployed dashboard `/onboarding` URL. Add local origins only for development; Shopify's registered callback itself must remain HTTPS.

## Safety boundary

- The browser never receives or reads a Shopify Admin API token.
- OAuth state is stored only as a SHA-256 digest and is single-use.
- Authenticated browser roles cannot execute OAuth service functions or read OAuth state rows.
- Connecting Shopify does not open execution, scheduler, or Shopify write gates.
- Customer approval can create only an unpublished draft after the separate worker commissioning boundary passes.
- The dashboard has no live-publish capability.

## Verification

```bash
npm test
npm run test:sites
npm run build
```
