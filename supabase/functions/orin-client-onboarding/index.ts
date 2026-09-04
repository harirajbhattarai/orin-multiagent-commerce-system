import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { createClient } from "npm:@supabase/supabase-js@2.57.4";

const SHOPIFY_API_VERSION = "2026-07";
const DEFAULT_SHOPIFY_SCOPES = "read_products,write_content";
const SHOPIFY_REFRESH_WINDOW_MS = 5 * 60 * 1000;
const DEFAULT_ALLOWED_ORIGINS = new Set([
  "https://commerce.navarna.ai",
  "https://orin-hbstore-dashboard.tooxic-ai.chatgpt.site",
  "http://localhost:5173",
  "http://127.0.0.1:5173",
  "http://localhost:5174",
  "http://127.0.0.1:5174",
]);

function allowedOrigins() {
  const configured = (Deno.env.get("ONBOARDING_ALLOWED_ORIGINS") ?? "")
    .split(",")
    .map((value) => value.trim())
    .filter(Boolean);
  return new Set([...DEFAULT_ALLOWED_ORIGINS, ...configured]);
}

function responseHeaders(origin: string | null) {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    "Cache-Control": "no-store",
    Vary: "Origin",
  };
  if (origin && allowedOrigins().has(origin)) {
    headers["Access-Control-Allow-Origin"] = origin;
    headers["Access-Control-Allow-Headers"] = "authorization, apikey, content-type, x-client-info";
    headers["Access-Control-Allow-Methods"] = "POST, OPTIONS";
  }
  return headers;
}

function json(origin: string | null, status: number, body: Record<string, unknown>) {
  return new Response(JSON.stringify(body), {
    status,
    headers: responseHeaders(origin),
  });
}

const encoder = new TextEncoder();

function bytesToHex(value: ArrayBuffer) {
  return Array.from(new Uint8Array(value))
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
}

async function sha256(value: string) {
  return bytesToHex(await crypto.subtle.digest("SHA-256", encoder.encode(value)));
}

function oauthState() {
  const bytes = crypto.getRandomValues(new Uint8Array(32));
  return btoa(String.fromCharCode(...bytes))
    .replaceAll("+", "-")
    .replaceAll("/", "_")
    .replace(/=+$/, "");
}

function timingSafeEqual(left: string, right: string) {
  if (left.length !== right.length) return false;
  let result = 0;
  for (let index = 0; index < left.length; index += 1) {
    result |= left.charCodeAt(index) ^ right.charCodeAt(index);
  }
  return result === 0;
}

async function validShopifyHmac(url: URL, secret: string) {
  const received = url.searchParams.get("hmac")?.toLowerCase() ?? "";
  if (!/^[0-9a-f]{64}$/.test(received)) return false;
  const message = Array.from(url.searchParams.entries())
    .filter(([key]) => key !== "hmac" && key !== "signature")
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([key, value]) => `${key}=${value}`)
    .join("&");
  const key = await crypto.subtle.importKey(
    "raw",
    encoder.encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const expected = bytesToHex(await crypto.subtle.sign("HMAC", key, encoder.encode(message)));
  return timingSafeEqual(received, expected);
}

function validReturnUrl(value: unknown, origin: string | null) {
  if (typeof value !== "string" || !origin || !allowedOrigins().has(origin)) return null;
  try {
    const parsed = new URL(value);
    return parsed.origin === origin && parsed.pathname === "/onboarding" ? parsed : null;
  } catch {
    return null;
  }
}

function redirectResult(returnUrl: string, result: "connected" | "error", requestId?: string) {
  const url = new URL(returnUrl);
  url.searchParams.set("shopify", result);
  if (requestId) url.searchParams.set("request_id", requestId);
  return Response.redirect(url.toString(), 302);
}

function normalizeStoreDomain(value: unknown) {
  if (typeof value !== "string") return null;
  const normalized = value.trim().toLowerCase()
    .replace(/^https?:\/\//, "")
    .split("/")[0];
  return /^[a-z0-9][a-z0-9-]*\.myshopify\.com$/.test(normalized)
    ? normalized
    : null;
}

async function readShopify(storeDomain: string, accessToken: string) {
  let shopifyResponse: Response;
  try {
    shopifyResponse = await fetch(
      `https://${storeDomain}/admin/api/${SHOPIFY_API_VERSION}/graphql.json`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Shopify-Access-Token": accessToken,
        },
        body: JSON.stringify({
          query: `query OrinOnboarding {
            shop { name myshopifyDomain currencyCode primaryDomain { url } }
            blogs(first: 50) { nodes { id title handle } }
            productsCount { count }
            collections(first: 50, sortKey: TITLE) { nodes { id title handle } }
            products(first: 50, sortKey: TITLE) {
              nodes { id title handle productType vendor status }
            }
          }`,
        }),
      },
    );
  } catch {
    throw new Error("The encrypted Shopify connection could not be used. Reconnect Shopify.");
  }

  if (!shopifyResponse.ok) {
    throw new Error(
      shopifyResponse.status === 401 || shopifyResponse.status === 403
        ? "Shopify rejected the connection. Reconnect Shopify and approve the required access."
        : `Shopify connection failed with HTTP ${shopifyResponse.status}.`,
    );
  }

  const payload = await shopifyResponse.json();
  if (Array.isArray(payload.errors) && payload.errors.length > 0) {
    throw new Error(payload.errors[0]?.message ?? "Shopify returned an API error.");
  }
  const shop = payload.data?.shop;
  const blogs = payload.data?.blogs?.nodes;
  const collections = payload.data?.collections?.nodes;
  const products = payload.data?.products?.nodes;
  if (!shop || !Array.isArray(blogs) || !Array.isArray(collections) || !Array.isArray(products)) {
    throw new Error("Shopify returned an incomplete response.");
  }
  if (blogs.length === 0) {
    throw new Error("No Shopify blog is available for this store.");
  }
  return {
    shop: {
      name: String(shop.name ?? ""),
      domain: String(shop.myshopifyDomain ?? storeDomain),
      currencyCode: String(shop.currencyCode ?? ""),
      storefrontUrl: String(shop.primaryDomain?.url ?? ""),
    },
    blogs: blogs.map((blog: Record<string, unknown>) => ({
      id: String(blog.id ?? ""),
      title: String(blog.title ?? ""),
      handle: String(blog.handle ?? ""),
    })),
    productCount: Number(payload.data?.productsCount?.count ?? 0),
    collections: collections.map((collection: Record<string, unknown>) => ({
      id: String(collection.id ?? ""),
      title: String(collection.title ?? ""),
      handle: String(collection.handle ?? ""),
    })),
    products: products.map((product: Record<string, unknown>) => ({
      id: String(product.id ?? ""),
      title: String(product.title ?? ""),
      handle: String(product.handle ?? ""),
      productType: String(product.productType ?? ""),
      vendor: String(product.vendor ?? ""),
      status: String(product.status ?? ""),
    })),
  };
}

function requiredShopifyScopes() {
  return (Deno.env.get("SHOPIFY_OAUTH_SCOPES") ?? DEFAULT_SHOPIFY_SCOPES)
    .split(",").map((scope) => scope.trim()).filter(Boolean);
}

function connectionRecord(value: unknown) {
  return Array.isArray(value) ? value[0] : value;
}

async function getShopifyConnection(
  service: ReturnType<typeof createClient>,
  operatorId: string,
  clientId: string,
  approvalBoundary = false,
) {
  const result = await service.rpc(
    approvalBoundary
      ? "service_get_client_shopify_approval_connection"
      : "service_get_client_shopify_audit_connection",
    {
      p_operator_id: operatorId,
      p_client_id: clientId,
    },
  );
  if (result.error) throw new Error(result.error.message);
  const connection = connectionRecord(result.data);
  if (!connection?.store_domain || !connection?.access_token || !connection?.blog_gid) {
    throw new Error("The encrypted Shopify connection is incomplete.");
  }
  return connection;
}

async function ensureFreshShopifyConnection(
  service: ReturnType<typeof createClient>,
  operatorId: string,
  clientId: string,
  approvalBoundary = false,
) {
  let connection = await getShopifyConnection(
    service, operatorId, clientId, approvalBoundary,
  );
  if (connection.connection_method !== "oauth") return connection;

  const accessExpiresAt = Date.parse(String(connection.access_token_expires_at ?? ""));
  const refreshExpiresAt = Date.parse(String(connection.refresh_token_expires_at ?? ""));
  if (!connection.refresh_token || !Number.isFinite(accessExpiresAt) || !Number.isFinite(refreshExpiresAt)) {
    throw new Error("The Shopify OAuth refresh connection is incomplete. Reconnect Shopify.");
  }
  if (accessExpiresAt > Date.now() + SHOPIFY_REFRESH_WINDOW_MS) return connection;
  if (refreshExpiresAt <= Date.now() + SHOPIFY_REFRESH_WINDOW_MS) {
    throw new Error("The Shopify connection has expired. Reconnect Shopify.");
  }

  const appClientId = Deno.env.get("SHOPIFY_CLIENT_ID") ?? "";
  const appClientSecret = Deno.env.get("SHOPIFY_CLIENT_SECRET") ?? "";
  if (!appClientId || !appClientSecret) {
    throw new Error("Shopify OAuth refresh is not configured.");
  }

  const refreshResponse = await fetch(
    `https://${connection.store_domain}/admin/oauth/access_token`,
    {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/x-www-form-urlencoded",
      },
      body: new URLSearchParams({
        client_id: appClientId,
        client_secret: appClientSecret,
        grant_type: "refresh_token",
        refresh_token: connection.refresh_token,
      }),
    },
  );

  if (!refreshResponse.ok) {
    const latest = await getShopifyConnection(
      service, operatorId, clientId, approvalBoundary,
    );
    const latestExpiry = Date.parse(String(latest.access_token_expires_at ?? ""));
    if (latest.connection_method === "oauth" && latestExpiry > Date.now() + SHOPIFY_REFRESH_WINDOW_MS) {
      return latest;
    }
    throw new Error("Shopify could not refresh the connection. Reconnect Shopify.");
  }

  const payload = await refreshResponse.json();
  const accessToken = typeof payload.access_token === "string" ? payload.access_token.trim() : "";
  const refreshToken = typeof payload.refresh_token === "string" ? payload.refresh_token.trim() : "";
  const accessExpiresIn = Number(payload.expires_in);
  const refreshExpiresIn = Number(payload.refresh_token_expires_in);
  const grantedScopes = new Set(
    String(payload.scope ?? "").split(",").map((scope) => scope.trim()).filter(Boolean),
  );
  if (
    !accessToken
    || !refreshToken
    || !Number.isFinite(accessExpiresIn)
    || accessExpiresIn <= 0
    || !Number.isFinite(refreshExpiresIn)
    || refreshExpiresIn <= accessExpiresIn
    || requiredShopifyScopes().some((scope) => !grantedScopes.has(scope))
  ) {
    throw new Error("Shopify returned an invalid refreshed connection. Reconnect Shopify.");
  }

  const issuedAt = Date.now();
  const nextAccessExpiry = new Date(issuedAt + accessExpiresIn * 1000).toISOString();
  const nextRefreshExpiry = new Date(issuedAt + refreshExpiresIn * 1000).toISOString();
  const rotation = await service.rpc(
    approvalBoundary
      ? "service_rotate_client_shopify_approval_tokens"
      : "service_rotate_client_shopify_oauth_tokens",
    {
      p_operator_id: operatorId,
      p_client_id: clientId,
      p_previous_refresh_token: connection.refresh_token,
      p_access_token: accessToken,
      p_refresh_token: refreshToken,
      p_access_token_expires_at: nextAccessExpiry,
      p_refresh_token_expires_at: nextRefreshExpiry,
    },
  );
  if (rotation.error) {
    connection = await getShopifyConnection(
      service, operatorId, clientId, approvalBoundary,
    );
    const latestExpiry = Date.parse(String(connection.access_token_expires_at ?? ""));
    if (latestExpiry > Date.now() + SHOPIFY_REFRESH_WINDOW_MS) return connection;
    throw new Error("Shopify connection rotation did not complete. Try again.");
  }
  return {
    ...connection,
    access_token: accessToken,
    refresh_token: refreshToken,
    access_token_expires_at: nextAccessExpiry,
    refresh_token_expires_at: nextRefreshExpiry,
  };
}

Deno.serve(async (request: Request) => {
  const origin = request.headers.get("origin");
  if (request.method !== "GET" && origin && !allowedOrigins().has(origin)) {
    return json(origin, 403, { error: "Origin is not allowed." });
  }
  if (request.method === "OPTIONS") {
    return new Response(null, { status: 204, headers: responseHeaders(origin) });
  }

  const supabaseUrl = Deno.env.get("SUPABASE_URL");
  const publishableKey = Deno.env.get("SUPABASE_ANON_KEY");
  const serviceRoleKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");
  const appUrl = Deno.env.get("ONBOARDING_APP_URL")
    ?? "https://commerce.navarna.ai/onboarding";
  if (!supabaseUrl || !publishableKey || !serviceRoleKey) {
    return request.method === "GET"
      ? redirectResult(appUrl, "error")
      : json(origin, 500, { error: "Server configuration is incomplete." });
  }

  const service = createClient(supabaseUrl, serviceRoleKey, {
    auth: { persistSession: false, autoRefreshToken: false },
  });

  if (request.method === "GET") {
    const requestUrl = new URL(request.url);
    const clientId = Deno.env.get("SHOPIFY_CLIENT_ID") ?? "";
    const clientSecret = Deno.env.get("SHOPIFY_CLIENT_SECRET") ?? "";
    const redirectUri = Deno.env.get("SHOPIFY_OAUTH_REDIRECT_URI") ?? "";
    if (!clientId || !clientSecret || !redirectUri) return redirectResult(appUrl, "error");
    if (!(await validShopifyHmac(requestUrl, clientSecret))) return redirectResult(appUrl, "error");

    const storeDomain = normalizeStoreDomain(requestUrl.searchParams.get("shop"));
    const code = requestUrl.searchParams.get("code") ?? "";
    const state = requestUrl.searchParams.get("state") ?? "";
    if (!storeDomain || !state) return redirectResult(appUrl, "error");

    const stateResult = await service.rpc("service_consume_shopify_oauth_state", {
      p_state_hash: await sha256(state),
      p_store_domain: storeDomain,
    });
    if (stateResult.error) return redirectResult(appUrl, "error");
    const binding = Array.isArray(stateResult.data) ? stateResult.data[0] : stateResult.data;
    if (!binding?.operator_id || !binding?.request_id || !binding?.return_url) {
      return redirectResult(appUrl, "error");
    }
    if (!code || requestUrl.searchParams.has("error")) {
      return redirectResult(binding.return_url, "error", binding.request_id);
    }

    try {
      const exchange = await fetch(`https://${storeDomain}/admin/oauth/access_token`, {
        method: "POST",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/x-www-form-urlencoded",
        },
        body: new URLSearchParams({
          client_id: clientId,
          client_secret: clientSecret,
          code,
          expiring: "1",
        }),
      });
      if (!exchange.ok) throw new Error("Shopify OAuth exchange failed.");
      const tokenPayload = await exchange.json();
      const accessToken = typeof tokenPayload.access_token === "string"
        ? tokenPayload.access_token.trim()
        : "";
      const refreshToken = typeof tokenPayload.refresh_token === "string"
        ? tokenPayload.refresh_token.trim()
        : "";
      const accessExpiresIn = Number(tokenPayload.expires_in);
      const refreshExpiresIn = Number(tokenPayload.refresh_token_expires_in);
      const grantedScopes = new Set(
        String(tokenPayload.scope ?? "").split(",").map((scope) => scope.trim()).filter(Boolean),
      );
      const requiredScopes = requiredShopifyScopes();
      if (
        !accessToken
        || !refreshToken
        || !Number.isFinite(accessExpiresIn)
        || !Number.isFinite(refreshExpiresIn)
        || refreshExpiresIn <= accessExpiresIn
        || requiredScopes.some((scope) => !grantedScopes.has(scope))
      ) {
        throw new Error("Required Shopify scopes were not granted.");
      }
      const issuedAt = Date.now();
      const accessExpiresAt = new Date(issuedAt + accessExpiresIn * 1000).toISOString();
      const refreshExpiresAt = new Date(issuedAt + refreshExpiresIn * 1000).toISOString();

      const shopify = await readShopify(storeDomain, accessToken);
      if (shopify.shop.domain.toLowerCase() !== storeDomain) {
        throw new Error("Shopify returned a different permanent store domain.");
      }
      const discovery = {
        schema: "orin.shopify-discovery/v1",
        observedAt: new Date().toISOString(),
        scopes: Array.from(grantedScopes).sort(),
        ...shopify,
      };
      const saveResult = await service.rpc("service_store_onboarding_shopify_oauth_connection", {
        p_operator_id: binding.operator_id,
        p_request_id: binding.request_id,
        p_access_token: accessToken,
        p_refresh_token: refreshToken,
        p_access_token_expires_at: accessExpiresAt,
        p_refresh_token_expires_at: refreshExpiresAt,
        p_shopify_discovery: discovery,
        p_selected_blog_gid: shopify.blogs.length === 1 ? shopify.blogs[0].id : null,
      });
      if (saveResult.error) throw new Error(saveResult.error.message);
      return redirectResult(binding.return_url, "connected", binding.request_id);
    } catch {
      return redirectResult(binding.return_url, "error", binding.request_id);
    }
  }

  if (request.method !== "POST") {
    return json(origin, 405, { error: "Method not allowed." });
  }

  const authorization = request.headers.get("authorization");
  if (!authorization?.startsWith("Bearer ")) {
    return json(origin, 401, { error: "Authentication required." });
  }
  const supabase = createClient(supabaseUrl, publishableKey, {
    global: { headers: { Authorization: authorization } },
    auth: { persistSession: false, autoRefreshToken: false },
  });
  const { data: userData, error: userError } = await supabase.auth.getUser();
  if (userError || !userData.user) {
    return json(origin, 401, { error: "Your session has expired. Sign in again." });
  }
  const { data: operator, error: operatorError } = await supabase
    .from("platform_operators")
    .select("role,active")
    .eq("user_id", userData.user.id)
    .eq("active", true)
    .maybeSingle();
  if (operatorError || !operator) {
    return json(origin, 403, { error: "Platform operator access is required." });
  }

  let body: Record<string, unknown>;
  try {
    body = await request.json();
  } catch {
    return json(origin, 400, { error: "A JSON request body is required." });
  }
  const operatorId = userData.user.id;

  try {
    if (body.action === "create_request") {
      const { data, error } = await service.rpc("service_create_client_onboarding_request", {
        p_operator_id: operatorId,
        p_client_id: body.client_id,
        p_display_name: body.display_name,
        p_owner_email: body.owner_email,
        p_shopify_store_domain: body.store_domain,
        p_market_country: body.market_country,
        p_timezone: body.timezone,
        p_brand_voice: body.brand_voice,
        p_content_categories: body.content_categories,
      });
      if (error) throw new Error(error.message);
      return json(origin, 200, { ok: true, request: Array.isArray(data) ? data[0] : data });
    }
    if (body.action === "begin_shopify_oauth") {
      const clientId = Deno.env.get("SHOPIFY_CLIENT_ID") ?? "";
      const redirectUri = Deno.env.get("SHOPIFY_OAUTH_REDIRECT_URI") ?? "";
      const scopes = Deno.env.get("SHOPIFY_OAUTH_SCOPES") ?? DEFAULT_SHOPIFY_SCOPES;
      const storeDomain = normalizeStoreDomain(body.store_domain);
      const returnUrl = validReturnUrl(body.return_url, origin);
      const requestId = typeof body.request_id === "string" ? body.request_id : "";
      if (!clientId || !redirectUri) {
        return json(origin, 503, { error: "Shopify OAuth is not configured yet." });
      }
      if (!storeDomain || !returnUrl || !requestId) {
        return json(origin, 400, { error: "A valid onboarding request and return URL are required." });
      }
      const state = oauthState();
      const stateResult = await service.rpc("service_create_shopify_oauth_state", {
        p_operator_id: operatorId,
        p_request_id: requestId,
        p_state_hash: await sha256(state),
        p_return_url: returnUrl.toString(),
      });
      if (stateResult.error) throw new Error(stateResult.error.message);
      const authorizationUrl = new URL(`https://${storeDomain}/admin/oauth/authorize`);
      authorizationUrl.searchParams.set("client_id", clientId);
      authorizationUrl.searchParams.set("scope", scopes);
      authorizationUrl.searchParams.set("redirect_uri", redirectUri);
      authorizationUrl.searchParams.set("state", state);
      return json(origin, 200, { ok: true, authorization_url: authorizationUrl.toString() });
    }
    if (body.action === "select_shopify_blog") {
      const { data, error } = await service.rpc("service_select_onboarding_shopify_blog", {
        p_operator_id: operatorId,
        p_request_id: body.request_id,
        p_shopify_blog_gid: body.blog_gid,
      });
      if (error) throw new Error(error.message);
      return json(origin, 200, { ok: true, connection: Array.isArray(data) ? data[0] : data });
    }
    if (body.action === "update_scope") {
      const { data, error } = await service.rpc("service_update_client_onboarding_scope", {
        p_operator_id: operatorId,
        p_request_id: body.request_id,
        p_product_scope: body.product_scope,
      });
      if (error) throw new Error(error.message);
      return json(origin, 200, { ok: true, request: Array.isArray(data) ? data[0] : data });
    }
    if (body.action === "provision_client") {
      const { data, error } = await service.rpc("service_provision_client_from_onboarding", {
        p_operator_id: operatorId,
        p_request_id: body.request_id,
      });
      if (error) throw new Error(error.message);
      return json(origin, 200, { ok: true, request: Array.isArray(data) ? data[0] : data });
    }
    if (body.action === "audit_provisioned_client") {
      const clientId = typeof body.client_id === "string" ? body.client_id.trim() : "";
      if (!/^[a-z0-9][a-z0-9_]{1,62}$/.test(clientId)) {
        return json(origin, 400, { error: "A valid provisioned client ID is required." });
      }
      const connection = await ensureFreshShopifyConnection(service, operatorId, clientId);
      const shopify = await readShopify(connection.store_domain, connection.access_token);
      const observedBlog = shopify.blogs.find((blog) => blog.id === connection.blog_gid);
      if (shopify.shop.domain.toLowerCase() !== connection.store_domain.toLowerCase() || !observedBlog) {
        throw new Error("Shopify identity does not match the provisioned client workspace.");
      }
      const auditResult = await service.rpc("service_record_client_shopify_identity_audit", {
        p_operator_id: operatorId,
        p_client_id: clientId,
        p_observed_store_domain: shopify.shop.domain,
        p_observed_blog_gid: observedBlog.id,
        p_observed_blog_title: observedBlog.title,
        p_observed_product_count: shopify.productCount,
      });
      if (auditResult.error) throw new Error(auditResult.error.message);
      const audit = Array.isArray(auditResult.data) ? auditResult.data[0] : auditResult.data;
      return json(origin, 200, {
        ok: true,
        audit: {
          ...audit,
          store_domain: shopify.shop.domain,
          blog_title: observedBlog.title,
          product_count: shopify.productCount,
        },
      });
    }
    if (body.action === "request_commissioning") {
      const clientId = typeof body.client_id === "string" ? body.client_id.trim() : "";
      const commissioningRequestId = typeof body.commissioning_request_id === "string"
        ? body.commissioning_request_id.trim()
        : "";
      if (!/^[a-z0-9][a-z0-9_]{1,62}$/.test(clientId)) {
        return json(origin, 400, { error: "A valid provisioned client ID is required." });
      }
      if (!/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(commissioningRequestId)) {
        return json(origin, 400, { error: "A valid commissioning request ID is required." });
      }
      await ensureFreshShopifyConnection(service, operatorId, clientId);
      const { data, error } = await service.rpc("service_request_client_commissioning", {
        p_operator_id: operatorId,
        p_client_id: clientId,
        p_commissioning_request_id: commissioningRequestId,
      });
      if (error) throw new Error(error.message);
      return json(origin, 200, {
        ok: true,
        commissioning: Array.isArray(data) ? data[0] : data,
      });
    }
    if (body.action === "request_recurring_pilot") {
      const clientId = typeof body.client_id === "string" ? body.client_id.trim() : "";
      const activationRequestId = typeof body.activation_request_id === "string"
        ? body.activation_request_id.trim()
        : "";
      if (!/^[a-z0-9][a-z0-9_]{1,62}$/.test(clientId)) {
        return json(origin, 400, { error: "A valid provisioned client ID is required." });
      }
      if (!/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(activationRequestId)) {
        return json(origin, 400, { error: "A valid recurring-pilot request ID is required." });
      }
      await ensureFreshShopifyConnection(service, operatorId, clientId);
      const { data, error } = await service.rpc("service_activate_client_recurring_pilot", {
        p_operator_id: operatorId,
        p_client_id: clientId,
        p_activation_request_id: activationRequestId,
      });
      if (error) throw new Error(error.message);
      return json(origin, 200, {
        ok: true,
        recurring_pilot: Array.isArray(data) ? data[0] : data,
      });
    }
    if (body.action === "approve_unpublished_draft") {
      const clientId = typeof body.client_id === "string" ? body.client_id.trim() : "";
      const contentItemId = typeof body.content_item_id === "string"
        ? body.content_item_id.trim()
        : "";
      const contentItemVersion = Number(body.content_item_version);
      const requestId = typeof body.request_id === "string" ? body.request_id.trim() : "";
      const note = typeof body.note === "string" ? body.note.trim() : "";
      const uuidPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
      if (!/^[a-z0-9][a-z0-9_]{1,62}$/.test(clientId)
        || !uuidPattern.test(contentItemId)
        || !Number.isInteger(contentItemVersion)
        || contentItemVersion < 2
        || !uuidPattern.test(requestId)
        || note.length > 4000) {
        return json(origin, 400, { error: "A valid exact draft approval is required." });
      }

      let handoffId = "";
      try {
        const begun = await service.rpc("service_begin_oauth_approval_handoff", {
          p_operator_id: operatorId,
          p_client_id: clientId,
          p_content_item_id: contentItemId,
          p_content_item_version: contentItemVersion,
          p_request_id: requestId,
        });
        if (begun.error) throw new Error(begun.error.message);
        const handoff = connectionRecord(begun.data);
        handoffId = String(handoff?.handoff_id ?? "");
        const decisionRequestId = String(handoff?.decision_request_id ?? "");
        if (!uuidPattern.test(handoffId) || !uuidPattern.test(decisionRequestId)) {
          throw new Error("The secure approval handoff did not start.");
        }
        if (handoff?.status === "processing") {
          return json(origin, 200, {
            ok: true,
            approval: { handoff_id: handoffId, status: "processing", replayed: true },
          });
        }

        await ensureFreshShopifyConnection(service, operatorId, clientId, true);
        let decision: Record<string, unknown> | null = null;
        const inserted = await supabase
          .from("content_decisions")
          .insert({
            client_id: clientId,
            content_item_id: contentItemId,
            content_item_version: contentItemVersion,
            decision: "approve_hidden_draft",
            note,
            request_id: decisionRequestId,
          })
          .select("decision_id,decision,processing_status,created_at,request_id")
          .single();
        if (!inserted.error) {
          decision = inserted.data;
        } else if (inserted.error.code === "23505") {
          const existing = await supabase
            .from("content_decisions")
            .select("decision_id,decision,note,content_item_id,content_item_version,processing_status,created_at,request_id")
            .eq("client_id", clientId)
            .eq("request_id", decisionRequestId)
            .maybeSingle();
          if (existing.error
            || !existing.data
            || existing.data.decision !== "approve_hidden_draft"
            || existing.data.note !== note
            || existing.data.content_item_id !== contentItemId
            || existing.data.content_item_version !== contentItemVersion) {
            throw new Error("This approval request conflicts with an existing decision.");
          }
          decision = existing.data;
        } else {
          throw new Error(inserted.error.message);
        }

        const bound = await service.rpc("service_bind_oauth_approval_handoff", {
          p_operator_id: operatorId,
          p_handoff_id: handoffId,
          p_decision_id: decision?.decision_id,
        });
        if (bound.error) throw new Error(bound.error.message);
        const approval = connectionRecord(bound.data);
        return json(origin, 200, {
          ok: true,
          approval: {
            handoff_id: handoffId,
            decision_id: decision?.decision_id,
            content_job_id: approval?.content_job_id,
            status: approval?.status ?? "processing",
            replayed: Boolean(handoff?.replayed || approval?.replayed),
          },
        });
      } catch (error) {
        if (handoffId) {
          await service.rpc("service_cancel_oauth_approval_handoff", {
            p_operator_id: operatorId,
            p_handoff_id: handoffId,
            p_error: "Approval preparation did not complete.",
          });
        }
        throw error;
      }
    }
    if (body.action === "refresh_approved_draft_connection") {
      const clientId = typeof body.client_id === "string" ? body.client_id.trim() : "";
      if (!/^[a-z0-9][a-z0-9_]{1,62}$/.test(clientId)) {
        return json(origin, 400, { error: "A valid client ID is required." });
      }
      const connection = await ensureFreshShopifyConnection(
        service, operatorId, clientId, true,
      );
      return json(origin, 200, {
        ok: true,
        connection: {
          store_domain: connection.store_domain,
          blog_gid: connection.blog_gid,
          access_token_expires_at: connection.access_token_expires_at,
        },
      });
    }
  } catch (error) {
    const message = error instanceof Error ? error.message : "Onboarding action failed.";
    return json(origin, 422, { error: message });
  }

  // Temporary operator fallback for existing custom-app tokens. The customer
  // onboarding UI does not expose this path; OAuth is the default product flow.
  const storeDomain = normalizeStoreDomain(body.store_domain);
  const accessToken = typeof body.access_token === "string" ? body.access_token.trim() : "";
  if (!storeDomain || accessToken.length < 20 || accessToken.length > 512) {
    return json(origin, 400, { error: "Unknown onboarding action." });
  }
  try {
    const shopify = await readShopify(storeDomain, accessToken);
    if (body.action === "validate_shopify") return json(origin, 200, { ok: true, ...shopify });
    if (body.action !== "save_shopify_connection") {
      return json(origin, 400, { error: "Unknown onboarding action." });
    }
    const selectedBlog = shopify.blogs.find((blog) => blog.id === body.blog_gid);
    if (!selectedBlog) return json(origin, 400, { error: "Select a blog returned by Shopify." });
    const { data, error } = await service.rpc("service_store_onboarding_shopify_connection", {
      p_operator_id: operatorId,
      p_request_id: body.request_id,
      p_access_token: accessToken,
      p_shopify_blog_gid: selectedBlog.id,
      p_shopify_blog_title: selectedBlog.title,
    });
    if (error) throw new Error(error.message);
    return json(origin, 200, { ok: true, connection: Array.isArray(data) ? data[0] : data });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Shopify verification failed.";
    return json(origin, 422, { error: message });
  }
});
