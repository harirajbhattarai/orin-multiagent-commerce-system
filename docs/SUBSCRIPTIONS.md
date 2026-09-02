# Subscription and entitlement foundation

ORIN Commerce has a tenant-scoped subscription and Shopify billing contract for no-code content planning. Billing changes entitlement only; it cannot open a content-execution or Shopify write gate.

## Commercial catalogue

| Plan | Price | Articles | Members |
| --- | ---: | ---: | ---: |
| 7-day trial | $0 | 2 | 1 |
| Starter | $29 every 30 days | 4 | 1 |
| Growth | $79 every 30 days | 12 | 3 |
| Scale | $149 every 30 days | 30 | 5 |

Each subscription covers one Shopify store. Growth is presented as the recommended plan. There is no permanent free plan and no usage overage: planning fails closed at the allowance and resumes after renewal or an approved upgrade. Existing pilot clients remain grandfathered until they deliberately choose a paid plan.

## Customer experience

- **Plan & usage** shows the current plan, exact 30-day usage, renewal or trial date, paid plan catalogue, cancellation policy, and Shopify billing source.
- **Plan next article** remains no-code and works only while the server reports an active entitlement with remaining monthly capacity.
- Inactive, expired, missing, or exhausted subscriptions fail closed in both the dashboard and database.
- Live publishing remains unavailable on every plan.

## Database contract

- `subscription_plans` is the server-owned entitlement catalogue. It contains capabilities and limits, but no unapproved prices.
- `client_subscriptions` binds exactly one subscription to each isolated client tenant.
- `client_subscription_summary` is a security-invoker, read-only customer projection with usage aligned to the subscription period.
- Existing commissioned clients receive managed `pilot` access during migration.
- New clients receive a 7-day `trial` subscription when their tenant record is created. Existing in-progress trials keep their previously promised end date.
- `subscription_checkout_attempts` is an idempotent checkout ledger. It stores no card data or Shopify token.
- A transaction-scoped advisory lock and `content_plan_items` trigger enforce the monthly tenant content allowance when a customer plans manually, without changing worker, scheduler, or Shopify state.

Authenticated customers can read only subscriptions for client workspaces where they are members. Browser roles cannot insert, update, or delete plans or subscriptions.

## Safety boundary

This phase never:

- creates a Shopify subscription or charge;
- enables request intake, automation, or scheduler ownership;
- enables broad Shopify writes or approved-draft writes;
- creates a Shopify article;
- adds a live-publish capability.

The `can_publish_live` entitlement is permanently constrained to `false` in the database and is also forced to `false` in dashboard normalization.

## Shopify billing lifecycle

The browser calls the `orin-shopify-billing` Edge Function, which verifies the current Supabase user and tenant-owner membership. The function reads the OAuth token through a service-role-only Vault boundary, refreshes it when needed, and invokes Shopify Admin GraphQL. Card details and the token never reach the browser.

Checkout uses `appSubscriptionCreate`, a maximum seven-day remaining trial, an `EVERY_30_DAYS` recurring line item, and Shopify's confirmation page. ORIN verifies the active subscription against `currentAppInstallation.activeSubscriptions` after Shopify returns. Cancellation uses `appSubscriptionCancel(prorate: false)` and keeps the entitlement through the recorded paid-through date.

`SHOPIFY_BILLING_TEST` defaults to `true`. Real charges must not be enabled until the development-store checkout, return, cancellation, and payment-failure exercises pass and the app is ready for commercial billing.

## Cancellation policy

Customers may cancel at any time. Access continues until the end of the current paid 30-day period and no further charge is created. There are no prorated refunds for unused time except for duplicate charges, billing errors, or where required by law. New planning and automation stop after access ends; history remains read-only for 30 days. Uninstalling the app must immediately disconnect Shopify and close every Shopify write gate. Live publishing remains unavailable.

Billing remains separate from content execution. A paid plan grants entitlement only; existing approval and Shopify write gates remain authoritative.

## Verification

```bash
npx --yes supabase@2.109.1 db test
npx --yes supabase@2.109.1 db lint --local --level error --fail-on error
npm test --prefix apps/orin-dashboard
npm run build --prefix apps/orin-dashboard
uvx --from uv==0.11.16 uv run pytest
```
