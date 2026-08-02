# ORIN Commerce dashboard

Client-facing prototype for the ORIN content operations system. It combines:

- an operational overview;
- a content queue and workflow board;
- an article review and approval workspace.

The current build is intentionally safe: all approval interactions are local UI state and cannot write to Shopify.

## Local preview

```bash
npm install --prefer-offline --no-audit --no-fund
npm run dev -- --host 127.0.0.1
```

## Data boundary

The app uses realistic HBStore preview data by default. An optional authenticated, read-only Supabase adapter is available through `VITE_SUPABASE_URL` and `VITE_SUPABASE_PUBLISHABLE_KEY`.

Before enabling live data, create a tenant-scoped `client_dashboard_snapshot` view or table with Row Level Security based on authenticated membership. Do not expose a Supabase secret key, raw worker evidence paths, or unrestricted operational JSON in the browser.

## Safety boundary

- No Shopify write credentials are loaded.
- No production approval endpoint is called.
- The UI says explicitly when a decision is preview-only.
- Publishing remains an OpenClaw/ORIN backend responsibility after an authenticated, durable approval record exists.
