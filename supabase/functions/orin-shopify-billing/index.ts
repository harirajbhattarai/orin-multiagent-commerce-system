import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { createClient } from "npm:@supabase/supabase-js@2.57.4";

const SHOPIFY_API_VERSION = "2026-07";
const DAY_MS = 24 * 60 * 60 * 1000;
const REFRESH_WINDOW_MS = 5 * 60 * 1000;
const DEFAULT_ALLOWED_ORIGINS = new Set([
  "https://commerce.navarna.ai",
  "https://orin-hbstore-dashboard.tooxic-ai.chatgpt.site",
  "http://localhost:5173",
  "http://127.0.0.1:5173",
  "http://localhost:5174",
  "http://127.0.0.1:5174",
]);

const CREATE_SUBSCRIPTION = `mutation OrinCreateSubscription($name: String!, $returnUrl: URL!, $trialDays: Int!, $lineItems: [AppSubscriptionLineItemInput!]!, $test: Boolean!) {
  appSubscriptionCreate(name: $name, returnUrl: $returnUrl, trialDays: $trialDays, lineItems: $lineItems, test: $test) {
    appSubscription { id name status trialDays currentPeriodEnd test }
    confirmationUrl
    userErrors { field message }
  }
}`;

const CURRENT_SUBSCRIPTIONS = `query OrinCurrentSubscriptions {
  currentAppInstallation {
    activeSubscriptions { id name status trialDays currentPeriodEnd test }
  }
}`;

const CANCEL_SUBSCRIPTION = `mutation OrinCancelSubscription($id: ID!) {
  appSubscriptionCancel(id: $id, prorate: false) {
    appSubscription { id status currentPeriodEnd }
    userErrors { field message }
  }
}`;

function allowedOrigins() {
  const configured = (Deno.env.get("BILLING_ALLOWED_ORIGINS") ?? "")
    .split(",").map((value) => value.trim()).filter(Boolean);
  return new Set([...DEFAULT_ALLOWED_ORIGINS, ...configured]);
}

function headers(origin: string | null) {
  const result: Record<string, string> = {
    "Content-Type": "application/json",
    "Cache-Control": "no-store",
    Vary: "Origin",
  };
  if (origin && allowedOrigins().has(origin)) {
    result["Access-Control-Allow-Origin"] = origin;
    result["Access-Control-Allow-Headers"] = "authorization, apikey, content-type, x-client-info";
    result["Access-Control-Allow-Methods"] = "POST, OPTIONS";
  }
  return result;
}

function json(origin: string | null, status: number, body: Record<string, unknown>) {
  return new Response(JSON.stringify(body), { status, headers: headers(origin) });
}

function record(value: unknown): Record<string, any> | null {
  if (Array.isArray(value)) return value[0] ?? null;
  return value && typeof value === "object" ? value as Record<string, any> : null;
}

function validClientId(value: unknown) {
  return typeof value === "string" && /^[a-z0-9][a-z0-9_]{1,62}$/.test(value)
    ? value : null;
}

function validUuid(value: unknown) {
  return typeof value === "string"
    && /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(value)
    ? value : null;
}

function validReturnUrl(value: unknown, origin: string | null) {
  if (typeof value !== "string" || !origin || !allowedOrigins().has(origin)) return null;
  try {
    const parsed = new URL(value);
    const planRoute = parsed.pathname === "/plan"
      || (parsed.pathname === "/" && parsed.searchParams.get("view") === "plan");
    return parsed.origin === origin && planRoute ? parsed : null;
  } catch {
    return null;
  }
}

async function shopifyGraphql(
  storeDomain: string,
  accessToken: string,
  query: string,
  variables: Record<string, unknown>,
) {
  const response = await fetch(
    `https://${storeDomain}/admin/api/${SHOPIFY_API_VERSION}/graphql.json`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Shopify-Access-Token": accessToken,
      },
      body: JSON.stringify({ query, variables }),
    },
  );
  if (!response.ok) {
    throw new Error(response.status === 401 || response.status === 403
      ? "Shopify rejected the connection. Reconnect Shopify before managing billing."
      : `Shopify billing returned HTTP ${response.status}.`);
  }
  const payload = await response.json();
  if (Array.isArray(payload.errors) && payload.errors.length > 0) {
    throw new Error(payload.errors[0]?.message ?? "Shopify returned a billing API error.");
  }
  return payload.data as Record<string, any>;
}

async function billingConnection(service: any, userId: string, clientId: string) {
  let result = await service.rpc("service_get_client_shopify_billing_connection", {
    p_user_id: userId,
    p_client_id: clientId,
  });
  if (result.error) throw new Error(result.error.message);
  let connection = record(result.data);
  if (!connection) throw new Error("The Shopify billing connection is unavailable.");

  const expiresAt = Date.parse(String(connection.access_token_expires_at ?? ""));
  if (Number.isFinite(expiresAt) && expiresAt > Date.now() + REFRESH_WINDOW_MS) {
    return connection;
  }

  const shopifyClientId = Deno.env.get("SHOPIFY_CLIENT_ID") ?? "";
  const shopifyClientSecret = Deno.env.get("SHOPIFY_CLIENT_SECRET") ?? "";
  if (!shopifyClientId || !shopifyClientSecret || !connection.refresh_token) {
    throw new Error("The Shopify connection needs to be refreshed. Reconnect Shopify.");
  }
  const response = await fetch(`https://${connection.store_domain}/admin/oauth/access_token`, {
    method: "POST",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/x-www-form-urlencoded",
    },
    body: new URLSearchParams({
      grant_type: "refresh_token",
      client_id: shopifyClientId,
      client_secret: shopifyClientSecret,
      refresh_token: connection.refresh_token,
    }),
  });
  if (!response.ok) throw new Error("Shopify could not refresh the connection. Reconnect Shopify.");
  const payload = await response.json();
  const accessToken = typeof payload.access_token === "string" ? payload.access_token.trim() : "";
  const refreshToken = typeof payload.refresh_token === "string" ? payload.refresh_token.trim() : "";
  const accessExpiresIn = Number(payload.expires_in);
  const refreshExpiresIn = Number(payload.refresh_token_expires_in);
  if (!accessToken || !refreshToken || !Number.isFinite(accessExpiresIn)
      || !Number.isFinite(refreshExpiresIn) || refreshExpiresIn <= accessExpiresIn) {
    throw new Error("Shopify returned an invalid refreshed connection. Reconnect Shopify.");
  }
  const accessTokenExpiresAt = new Date(Date.now() + accessExpiresIn * 1000).toISOString();
  const refreshTokenExpiresAt = new Date(Date.now() + refreshExpiresIn * 1000).toISOString();
  result = await service.rpc("service_rotate_client_shopify_billing_tokens", {
    p_user_id: userId,
    p_client_id: clientId,
    p_previous_refresh_token: connection.refresh_token,
    p_access_token: accessToken,
    p_refresh_token: refreshToken,
    p_access_token_expires_at: accessTokenExpiresAt,
    p_refresh_token_expires_at: refreshTokenExpiresAt,
  });
  if (result.error) throw new Error(result.error.message);
  connection = {
    ...connection,
    access_token: accessToken,
    refresh_token: refreshToken,
    access_token_expires_at: accessTokenExpiresAt,
    refresh_token_expires_at: refreshTokenExpiresAt,
  };
  return connection;
}

async function requireOwner(service: any, userId: string, clientId: string) {
  const result = await service.from("client_members")
    .select("role")
    .eq("client_id", clientId)
    .eq("user_id", userId)
    .eq("role", "owner")
    .maybeSingle();
  if (result.error || !result.data) throw new Error("Client owner access is required.");
}

Deno.serve(async (request: Request) => {
  const origin = request.headers.get("origin");
  if (origin && !allowedOrigins().has(origin)) return json(origin, 403, { error: "Origin is not allowed." });
  if (request.method === "OPTIONS") return new Response(null, { status: 204, headers: headers(origin) });
  if (request.method !== "POST") return json(origin, 405, { error: "Method not allowed." });

  const supabaseUrl = Deno.env.get("SUPABASE_URL") ?? "";
  const publishableKey = Deno.env.get("SUPABASE_ANON_KEY") ?? "";
  const serviceRoleKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") ?? "";
  const authorization = request.headers.get("authorization") ?? "";
  if (!supabaseUrl || !publishableKey || !serviceRoleKey) {
    return json(origin, 500, { error: "Server configuration is incomplete." });
  }
  if (!authorization.startsWith("Bearer ")) return json(origin, 401, { error: "Authentication required." });

  const authenticated = createClient(supabaseUrl, publishableKey, {
    global: { headers: { Authorization: authorization } },
    auth: { persistSession: false, autoRefreshToken: false },
  });
  const userResult = await authenticated.auth.getUser();
  if (userResult.error || !userResult.data.user) {
    return json(origin, 401, { error: "Your session has expired. Sign in again." });
  }
  const service = createClient(supabaseUrl, serviceRoleKey, {
    auth: { persistSession: false, autoRefreshToken: false },
  });

  let body: Record<string, unknown>;
  try {
    body = await request.json();
  } catch {
    return json(origin, 400, { error: "A JSON request body is required." });
  }

  const userId = userResult.data.user.id;
  const clientId = validClientId(body.client_id);
  if (!clientId) return json(origin, 400, { error: "A valid client workspace is required." });

  try {
    await requireOwner(service, userId, clientId);

    if (body.action === "start_checkout") {
      const planKey = typeof body.plan_key === "string" ? body.plan_key.trim() : "";
      const requestId = validUuid(body.request_id);
      const returnUrl = validReturnUrl(body.return_url, origin);
      if (!planKey || !requestId || !returnUrl) {
        return json(origin, 400, { error: "A valid plan and secure return URL are required." });
      }

      const existing = await service.from("subscription_checkout_attempts")
        .select("attempt_id,status,confirmation_url")
        .eq("client_id", clientId).eq("requested_by", userId).eq("request_id", requestId)
        .maybeSingle();
      if (existing.error) throw new Error(existing.error.message);
      if (existing.data?.status === "confirmation_required" && existing.data.confirmation_url) {
        return json(origin, 200, {
          ok: true, confirmation_url: existing.data.confirmation_url,
          attempt_id: existing.data.attempt_id, replayed: true,
          test: (Deno.env.get("SHOPIFY_BILLING_TEST") ?? "true") !== "false",
        });
      }

      const planResult = await service.from("subscription_plans")
        .select("plan_key,display_name,monthly_price_cents,currency_code,trial_days")
        .eq("plan_key", planKey).eq("active", true).eq("publicly_selectable", true)
        .gt("monthly_price_cents", 0).maybeSingle();
      if (planResult.error || !planResult.data) throw new Error("The selected plan is unavailable.");

      const subscriptionResult = await service.from("client_subscriptions")
        .select("status,trial_ends_at")
        .eq("client_id", clientId).maybeSingle();
      if (subscriptionResult.error || !subscriptionResult.data) {
        throw new Error("The client subscription is unavailable.");
      }
      const trialEndsAt = Date.parse(subscriptionResult.data.trial_ends_at ?? "");
      const trialDays = subscriptionResult.data.status === "trialing" && trialEndsAt > Date.now()
        ? Math.min(planResult.data.trial_days, Math.max(0, Math.ceil((trialEndsAt - Date.now()) / DAY_MS)))
        : 0;

      const attemptId = crypto.randomUUID();
      const inserted = await service.from("subscription_checkout_attempts").insert({
        attempt_id: attemptId,
        client_id: clientId,
        requested_plan_key: planKey,
        requested_by: userId,
        request_id: requestId,
        trial_days: trialDays,
      });
      if (inserted.error) throw new Error(inserted.error.message);

      const billingReturn = new URL(returnUrl);
      billingReturn.searchParams.set("client", clientId);
      billingReturn.searchParams.set("billing", "return");
      billingReturn.searchParams.set("billing_attempt", attemptId);
      const connection = await billingConnection(service, userId, clientId);
      const test = (Deno.env.get("SHOPIFY_BILLING_TEST") ?? "true") !== "false";
      const shopify = await shopifyGraphql(
        connection.store_domain,
        connection.access_token,
        CREATE_SUBSCRIPTION,
        {
          name: `ORIN Commerce ${planResult.data.display_name}`,
          returnUrl: billingReturn.toString(),
          trialDays,
          test,
          lineItems: [{
            plan: {
              appRecurringPricingDetails: {
                interval: "EVERY_30_DAYS",
                price: {
                  amount: (planResult.data.monthly_price_cents / 100).toFixed(2),
                  currencyCode: planResult.data.currency_code,
                },
              },
            },
          }],
        },
      );
      const payload = shopify.appSubscriptionCreate;
      if (payload?.userErrors?.length) throw new Error(payload.userErrors[0].message);
      if (!payload?.appSubscription?.id || !payload?.confirmationUrl) {
        throw new Error("Shopify did not return a subscription confirmation URL.");
      }
      const updated = await service.from("subscription_checkout_attempts").update({
        status: "confirmation_required",
        provider_subscription_id: payload.appSubscription.id,
        confirmation_url: payload.confirmationUrl,
      }).eq("attempt_id", attemptId);
      if (updated.error) throw new Error(updated.error.message);
      return json(origin, 200, {
        ok: true,
        confirmation_url: payload.confirmationUrl,
        attempt_id: attemptId,
        replayed: false,
        test,
      });
    }

    if (body.action === "confirm_checkout") {
      const attemptId = validUuid(body.attempt_id);
      if (!attemptId) return json(origin, 400, { error: "A valid checkout attempt is required." });
      const attemptResult = await service.from("subscription_checkout_attempts")
        .select("attempt_id,provider_subscription_id,trial_days,status")
        .eq("attempt_id", attemptId).eq("client_id", clientId).eq("requested_by", userId)
        .maybeSingle();
      if (attemptResult.error || !attemptResult.data?.provider_subscription_id) {
        throw new Error("Subscription checkout attempt not found.");
      }
      const connection = await billingConnection(service, userId, clientId);
      const shopify = await shopifyGraphql(
        connection.store_domain, connection.access_token, CURRENT_SUBSCRIPTIONS, {},
      );
      const subscription = (shopify.currentAppInstallation?.activeSubscriptions ?? [])
        .find((item: Record<string, unknown>) => item.id === attemptResult.data.provider_subscription_id);
      if (!subscription || subscription.status !== "ACTIVE" || !subscription.currentPeriodEnd) {
        return json(origin, 409, { error: "Shopify has not activated this plan. Approve it in Shopify, then retry." });
      }
      const activated = await service.rpc("service_activate_shopify_subscription", {
        p_user_id: userId,
        p_attempt_id: attemptId,
        p_provider_subscription_id: subscription.id,
        p_current_period_end: subscription.currentPeriodEnd,
        p_trial_days: Math.min(7, Number(subscription.trialDays ?? attemptResult.data.trial_days ?? 0)),
      });
      if (activated.error) throw new Error(activated.error.message);
      return json(origin, 200, { ok: true, subscription: record(activated.data) });
    }

    if (body.action === "cancel_subscription") {
      const current = await service.from("client_subscriptions")
        .select("billing_provider,provider_subscription_id,status")
        .eq("client_id", clientId).maybeSingle();
      if (current.error || current.data?.billing_provider !== "shopify"
          || !current.data.provider_subscription_id
          || !["trialing", "active"].includes(current.data.status)) {
        throw new Error("An active Shopify subscription was not found.");
      }
      const connection = await billingConnection(service, userId, clientId);
      const shopify = await shopifyGraphql(
        connection.store_domain, connection.access_token, CANCEL_SUBSCRIPTION,
        { id: current.data.provider_subscription_id },
      );
      const payload = shopify.appSubscriptionCancel;
      if (payload?.userErrors?.length) throw new Error(payload.userErrors[0].message);
      if (!payload?.appSubscription?.currentPeriodEnd) {
        throw new Error("Shopify did not return the paid-through date.");
      }
      const scheduled = await service.rpc("service_schedule_shopify_subscription_cancellation", {
        p_user_id: userId,
        p_client_id: clientId,
        p_provider_subscription_id: current.data.provider_subscription_id,
        p_current_period_end: payload.appSubscription.currentPeriodEnd,
      });
      if (scheduled.error) throw new Error(scheduled.error.message);
      return json(origin, 200, {
        ok: true, cancel_at_period_end: true,
        current_period_ends_at: payload.appSubscription.currentPeriodEnd,
      });
    }

    return json(origin, 400, { error: "Unknown billing action." });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Shopify billing action failed.";
    return json(origin, 422, { error: message });
  }
});
