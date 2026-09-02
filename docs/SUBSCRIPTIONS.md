# Subscription and entitlement foundation

ORIN Commerce now has a tenant-scoped subscription contract for no-code content planning. This phase records plan access and usage; it does not create a Shopify charge or open any content-execution or Shopify write gate.

## Customer experience

- **Plan & usage** shows the current plan, subscription state, monthly article allowance, team allowance, included capabilities, and billing source.
- **Plan next article** remains no-code and works only while the server reports an active entitlement with remaining monthly capacity.
- Inactive, expired, missing, or exhausted subscriptions fail closed in both the dashboard and database.
- Live publishing remains unavailable on every plan.

## Database contract

- `subscription_plans` is the server-owned entitlement catalogue. It contains capabilities and limits, but no unapproved prices.
- `client_subscriptions` binds exactly one subscription to each isolated client tenant.
- `client_subscription_summary` is a security-invoker, read-only customer projection with current-month usage.
- Existing commissioned clients receive managed `pilot` access during migration.
- New clients receive a 14-day `trial` subscription when their tenant record is created.
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

## Next commercial milestone

After product names, monthly prices, trial rules, and cancellation policy are approved:

1. Add a server-only Shopify billing start endpoint using `appSubscriptionCreate`.
2. Bind Shopify subscription IDs to the tenant after a verified return URL.
3. Process billing lifecycle webhooks idempotently and update `client_subscriptions` server-side.
4. Add customer upgrade, cancellation, and payment-recovery states to **Plan & usage**.
5. Verify trial, approval-only draft creation, cancellation, and payment-failure paths in a development store before production activation.

Billing must remain separate from content execution. A paid plan grants entitlement only; existing approval and Shopify write gates remain authoritative.

## Verification

```bash
npx --yes supabase@2.109.1 db test
npx --yes supabase@2.109.1 db lint --local --level error --fail-on error
npm test --prefix apps/orin-dashboard
npm run build --prefix apps/orin-dashboard
uvx --from uv==0.11.16 uv run pytest
```
