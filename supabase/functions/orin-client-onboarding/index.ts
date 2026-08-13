import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { createClient } from "npm:@supabase/supabase-js@2.57.4";

const SHOPIFY_API_VERSION = "2026-07";
const DEFAULT_ALLOWED_ORIGINS = new Set([
  "https://orin-hbstore-dashboard.tooxic-ai.chatgpt.site",
  "http://localhost:5173",
  "http://127.0.0.1:5173",
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
            shop { name myshopifyDomain }
            blogs(first: 50) { nodes { id title handle } }
            productsCount { count }
          }`,
        }),
      },
    );
  } catch {
    throw new Error("The encrypted Shopify credential could not be used. Re-save the Admin API token.");
  }

  if (!shopifyResponse.ok) {
    throw new Error(
      shopifyResponse.status === 401 || shopifyResponse.status === 403
        ? "Shopify rejected the Admin API token. Check the app scopes and token."
        : `Shopify connection failed with HTTP ${shopifyResponse.status}.`,
    );
  }

  const payload = await shopifyResponse.json();
  if (Array.isArray(payload.errors) && payload.errors.length > 0) {
    throw new Error(payload.errors[0]?.message ?? "Shopify returned an API error.");
  }
  const shop = payload.data?.shop;
  const blogs = payload.data?.blogs?.nodes;
  if (!shop || !Array.isArray(blogs)) {
    throw new Error("Shopify returned an incomplete response.");
  }
  if (blogs.length === 0) {
    throw new Error("No Shopify blog is available for this store.");
  }
  return {
    shop: {
      name: String(shop.name ?? ""),
      domain: String(shop.myshopifyDomain ?? storeDomain),
    },
    blogs: blogs.map((blog: Record<string, unknown>) => ({
      id: String(blog.id ?? ""),
      title: String(blog.title ?? ""),
      handle: String(blog.handle ?? ""),
    })),
    productCount: Number(payload.data?.productsCount?.count ?? 0),
  };
}

Deno.serve(async (request: Request) => {
  const origin = request.headers.get("origin");
  if (origin && !allowedOrigins().has(origin)) {
    return json(origin, 403, { error: "Origin is not allowed." });
  }
  if (request.method === "OPTIONS") {
    return new Response(null, { status: 204, headers: responseHeaders(origin) });
  }
  if (request.method !== "POST") {
    return json(origin, 405, { error: "Method not allowed." });
  }

  const authorization = request.headers.get("authorization");
  if (!authorization?.startsWith("Bearer ")) {
    return json(origin, 401, { error: "Authentication required." });
  }

  const supabaseUrl = Deno.env.get("SUPABASE_URL");
  const publishableKey = Deno.env.get("SUPABASE_ANON_KEY");
  const serviceRoleKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");
  if (!supabaseUrl || !publishableKey || !serviceRoleKey) {
    return json(origin, 500, { error: "Server configuration is incomplete." });
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

  const service = createClient(supabaseUrl, serviceRoleKey, {
    auth: { persistSession: false, autoRefreshToken: false },
  });
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
      const connectionResult = await service.rpc("service_get_client_shopify_audit_connection", {
        p_operator_id: operatorId,
        p_client_id: clientId,
      });
      if (connectionResult.error) throw new Error(connectionResult.error.message);
      const connection = Array.isArray(connectionResult.data)
        ? connectionResult.data[0]
        : connectionResult.data;
      if (!connection?.store_domain || !connection?.access_token || !connection?.blog_gid) {
        throw new Error("The encrypted Shopify connection is incomplete.");
      }

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
  } catch (error) {
    const message = error instanceof Error ? error.message : "Onboarding action failed.";
    return json(origin, 422, { error: message });
  }

  const storeDomain = normalizeStoreDomain(body.store_domain);
  const accessToken = typeof body.access_token === "string" ? body.access_token.trim() : "";
  if (!storeDomain || accessToken.length < 20 || accessToken.length > 512) {
    return json(origin, 400, { error: "Enter a valid .myshopify.com domain and Admin API token." });
  }

  try {
    const shopify = await readShopify(storeDomain, accessToken);
    if (body.action === "validate_shopify") {
      return json(origin, 200, { ok: true, ...shopify });
    }
    if (body.action !== "save_shopify_connection") {
      return json(origin, 400, { error: "Unknown onboarding action." });
    }

    const selectedBlog = shopify.blogs.find((blog) => blog.id === body.blog_gid);
    if (!selectedBlog) {
      return json(origin, 400, { error: "Select a blog returned by the verified store." });
    }
    const requestId = typeof body.request_id === "string" ? body.request_id : "";
    const { data, error } = await service.rpc("service_store_onboarding_shopify_connection", {
      p_operator_id: operatorId,
      p_request_id: requestId,
      p_access_token: accessToken,
      p_shopify_blog_gid: selectedBlog.id,
      p_shopify_blog_title: selectedBlog.title,
    });
    if (error) throw new Error(error.message);
    return json(origin, 200, {
      ok: true,
      connection: Array.isArray(data) ? data[0] : data,
      shop: shopify.shop,
      blog: selectedBlog,
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Shopify verification failed.";
    return json(origin, 422, { error: message });
  }
});
