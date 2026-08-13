import { createClient } from "@supabase/supabase-js";
import { dashboardData } from "../data.js";
import { deriveOperationalState } from "../operationalState.js";

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL;
const publishableKey = import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY;

export const isLiveReadEnabled = Boolean(supabaseUrl && publishableKey);
const maintenancePreviewEnabled = import.meta.env.DEV
  && new URLSearchParams(window.location.search).get("preview") === "maintenance";

const supabase = isLiveReadEnabled
  ? createClient(supabaseUrl, publishableKey, {
      auth: {
        persistSession: true,
        autoRefreshToken: true,
        detectSessionInUrl: true,
      },
    })
  : null;

export function dashboardSupabaseClient() {
  return supabase;
}

function formatMoment(value, options) {
  if (!value) return "Not observed yet";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return new Intl.DateTimeFormat("en-GB", options).format(date);
}

function normalizeSnapshot(snapshot, { client, runtime, health }) {
  const operations = deriveOperationalState({
    client,
    runtime,
    health,
    snapshotOperations: snapshot.operations,
  });
  return {
    ...snapshot,
    nextArticle: snapshot.nextArticle?.id ? snapshot.nextArticle : null,
    article: snapshot.article?.id ? snapshot.article : null,
    operations: {
      ...operations,
      lastChecked: `Checked ${formatMoment(operations.lastChecked, {
        day: "numeric",
        month: "short",
        hour: "2-digit",
        minute: "2-digit",
      })}`,
    },
    recentContent: (snapshot.recentContent ?? []).map((item) => ({
      ...item,
      updated: formatMoment(item.updated, {
        day: "numeric",
        month: "short",
        hour: "2-digit",
        minute: "2-digit",
      }),
    })),
    activity: (snapshot.activity ?? []).map((item) => ({
      ...item,
      time: formatMoment(item.time, { hour: "2-digit", minute: "2-digit" }),
    })),
  };
}

async function loadWorkspaceOptions() {
  const membershipResult = await supabase
    .from("client_members")
    .select("client_id,role")
    .order("created_at", { ascending: true });
  if (membershipResult.error) return { data: null, error: membershipResult.error };

  const memberships = membershipResult.data ?? [];
  if (memberships.length === 0) return { data: [], error: null };

  const clientResult = await supabase
    .from("clients")
    .select("client_id,display_name,status")
    .in("client_id", memberships.map((membership) => membership.client_id));
  if (clientResult.error) return { data: null, error: clientResult.error };

  const roleByClient = new Map(memberships.map((membership) => [membership.client_id, membership.role]));
  const clients = (clientResult.data ?? [])
    .map((client) => ({
      id: client.client_id,
      name: client.display_name,
      status: client.status,
      role: roleByClient.get(client.client_id),
    }))
    .sort((left, right) => left.name.localeCompare(right.name));
  return { data: clients, error: null };
}

export async function loadDashboardData(requestedClientId = null) {
  if (!supabase || maintenancePreviewEnabled) {
    const data = maintenancePreviewEnabled
      ? (() => {
          const operations = deriveOperationalState({
            client: { status: "maintenance" },
            runtime: {
              request_intake_enabled: false,
              automation_enabled: false,
              shopify_writes_enabled: false,
              approved_draft_writes_enabled: false,
              allowed_mode: "dry-run",
            },
            health: { state: "disabled", scheduler_owner: null, updated_at: new Date().toISOString() },
            snapshotOperations: dashboardData.operations,
          });
          return {
            ...dashboardData,
            operations: { ...operations, lastChecked: "Checked moments ago" },
          };
        })()
      : dashboardData;
    return {
      data,
      workspaces: [{ id: data.client.id, name: data.client.name, status: "active", role: "owner" }],
      selectedClientId: data.client.id,
      source: "demo",
      error: null,
      requiresAuth: false,
    };
  }

  const { data: sessionData, error: sessionError } = await supabase.auth.getSession();
  if (sessionError) {
    return { data: null, source: "error", error: sessionError.message, requiresAuth: false };
  }
  if (!sessionData.session) {
    return { data: null, source: "auth", error: null, requiresAuth: true };
  }

  const workspaceResult = await loadWorkspaceOptions();
  if (workspaceResult.error || !workspaceResult.data?.length) {
    return {
      data: null,
      source: "error",
      error: workspaceResult.error?.message ?? "Your account is not connected to a client workspace yet.",
      requiresAuth: false,
    };
  }
  const workspaces = workspaceResult.data;
  const selectedClientId = workspaces.some((workspace) => workspace.id === requestedClientId)
    ? requestedClientId
    : workspaces.some((workspace) => workspace.id === dashboardData.client.id)
      ? dashboardData.client.id
      : workspaces[0].id;

  const [snapshotResult, runtimeResult, clientResult, healthResult] = await Promise.all([
    supabase
      .from("client_dashboard_snapshot")
      .select("snapshot")
      .eq("client_id", selectedClientId)
      .maybeSingle(),
    supabase
      .from("client_runtime_settings")
      .select("request_intake_enabled,automation_enabled,shopify_writes_enabled,approved_draft_writes_enabled,allowed_mode")
      .eq("client_id", selectedClientId)
      .maybeSingle(),
    supabase
      .from("clients")
      .select("client_id,display_name,status")
      .eq("client_id", selectedClientId)
      .maybeSingle(),
    supabase
      .from("scheduler_health")
      .select("state,scheduler_owner,last_heartbeat_at,updated_at")
      .eq("client_id", selectedClientId)
      .maybeSingle(),
  ]);

  const { data, error } = snapshotResult;
  const runtime = runtimeResult.data;
  const client = clientResult.data;
  const health = healthResult.data;

  if (
    error
    || runtimeResult.error
    || clientResult.error
    || healthResult.error
    || !data?.snapshot
    || !runtime
    || !client
    || !health
  ) {
    return {
      data: null,
      source: "error",
      error: error?.message
        ?? runtimeResult.error?.message
        ?? clientResult.error?.message
        ?? healthResult.error?.message
        ?? "Your account is not connected to a client workspace yet.",
      requiresAuth: false,
    };
  }

  return {
    data: normalizeSnapshot(data.snapshot, { client, runtime, health }),
    workspaces,
    selectedClientId,
    source: "supabase",
    error: null,
    requiresAuth: false,
  };
}

export async function loadReviewItem(clientId, itemNumber) {
  if (!supabase) return { data: null, error: null };
  const { data, error } = await supabase
    .from("client_content_review_items")
    .select("client_id,item_number,content_item_id,version,status,review_kind,title,target_keyword,cluster,expected_draft_date,draft_version,body_html,body_sha256,word_count,meta_title,meta_description,quality_score,checks,source_run_id,latest_decision,latest_decision_status,latest_decision_outcome,latest_decision_at")
    .eq("client_id", clientId)
    .eq("item_number", itemNumber)
    .maybeSingle();
  if (error || !data) {
    return { data: null, error: error ?? new Error("This review item is no longer available.") };
  }
  return {
    data: {
      id: data.item_number,
      contentItemId: data.content_item_id,
      version: data.version,
      status: data.status,
      reviewKind: data.review_kind,
      title: data.title,
      keyword: data.target_keyword,
      intent: data.cluster,
      draftVersion: data.draft_version,
      bodyHtml: data.body_html,
      bodySha256: data.body_sha256,
      wordCount: data.word_count,
      metaTitle: data.meta_title || data.title,
      metaDescription: data.meta_description || "Metadata will be finalized before the Shopify draft is created.",
      qualityScore: data.quality_score,
      evidence: Array.isArray(data.checks) ? data.checks : [],
      latestDecision: data.latest_decision,
      latestDecisionStatus: data.latest_decision_status,
      latestDecisionOutcome: data.latest_decision_outcome,
    },
    error: null,
  };
}

export async function sendMagicLink(email) {
  if (!supabase) {
    return { error: new Error("Supabase sign-in is not enabled in this preview.") };
  }

  return supabase.auth.signInWithOtp({
    email,
    options: { emailRedirectTo: window.location.origin },
  });
}

export async function signOutDashboard() {
  if (!supabase) return { error: null };
  return supabase.auth.signOut();
}

export function subscribeToAuthChanges(callback) {
  if (!supabase) return () => {};
  const { data } = supabase.auth.onAuthStateChange(() => callback());
  return () => data.subscription.unsubscribe();
}

export async function loadOnboardingAccess() {
  if (!supabase) return { allowed: false, role: null, error: null };
  const { data: sessionData, error: sessionError } = await supabase.auth.getSession();
  if (sessionError || !sessionData.session?.user) {
    return { allowed: false, role: null, error: sessionError };
  }
  const { data, error } = await supabase
    .from("platform_operators")
    .select("role,active")
    .eq("user_id", sessionData.session.user.id)
    .eq("active", true)
    .maybeSingle();
  return { allowed: Boolean(data), role: data?.role ?? null, error };
}

export async function loadOnboardingRequests() {
  if (!supabase) return { data: [], error: null };
  return supabase
    .from("client_onboarding_requests")
    .select("request_id,client_id,display_name,owner_email,shopify_store_domain,market_country,timezone,brand_voice,content_categories,product_scope,shopify_blog_gid,shopify_blog_title,credential_status,status,commissioning_status,last_error,created_at,updated_at")
    .order("created_at", { ascending: false });
}

export async function createOnboardingRequest(payload) {
  if (!supabase) return { data: null, error: new Error("Live Supabase access is required.") };
  const { data, error } = await supabase.functions.invoke("orin-client-onboarding", {
    body: {
      action: "create_request",
      client_id: payload.clientId,
      display_name: payload.displayName,
      owner_email: payload.ownerEmail,
      store_domain: payload.storeDomain,
      market_country: payload.marketCountry,
      timezone: payload.timezone,
      brand_voice: payload.brandVoice,
      content_categories: payload.contentCategories,
    },
  });
  return { data: data?.request ?? null, error: error ?? (data?.error ? new Error(data.error) : null) };
}

export async function verifyOnboardingShopify(payload) {
  if (!supabase) return { data: null, error: new Error("Live Supabase access is required.") };
  const { data, error } = await supabase.functions.invoke("orin-client-onboarding", {
    body: payload,
  });
  return {
    data,
    error: error ?? (data?.error ? new Error(data.error) : null),
  };
}

export async function updateOnboardingScope(requestId, productScope) {
  if (!supabase) return { data: null, error: new Error("Live Supabase access is required.") };
  const { data, error } = await supabase.functions.invoke("orin-client-onboarding", {
    body: { action: "update_scope", request_id: requestId, product_scope: productScope },
  });
  return { data: data?.request ?? null, error: error ?? (data?.error ? new Error(data.error) : null) };
}

export async function provisionOnboardingClient(requestId) {
  if (!supabase) return { data: null, error: new Error("Live Supabase access is required.") };
  const { data, error } = await supabase.functions.invoke("orin-client-onboarding", {
    body: { action: "provision_client", request_id: requestId },
  });
  return { data: data?.request ?? null, error: error ?? (data?.error ? new Error(data.error) : null) };
}

function decisionRequestStorageKey({ clientId, contentItemId, contentItemVersion, decision }) {
  return `orin-decision:${clientId}:${contentItemId}:${contentItemVersion}:${decision}`;
}

export async function recordContentDecision({
  clientId,
  contentItemId,
  contentItemVersion,
  decision,
  note = "",
}) {
  if (!supabase) {
    return { data: { decision, replayed: false }, error: null };
  }
  if (!contentItemId || !Number.isInteger(contentItemVersion)) {
    return { data: null, error: new Error("Refresh the article before recording a decision.") };
  }

  const storageKey = decisionRequestStorageKey({
    clientId,
    contentItemId,
    contentItemVersion,
    decision,
  });
  const requestId = window.sessionStorage.getItem(storageKey) ?? crypto.randomUUID();
  window.sessionStorage.setItem(storageKey, requestId);
  const payload = {
    client_id: clientId,
    content_item_id: contentItemId,
    content_item_version: contentItemVersion,
    decision,
    note,
    request_id: requestId,
  };

  const inserted = await supabase
    .from("content_decisions")
    .insert(payload)
    .select("decision_id,decision,processing_status,created_at,request_id")
    .single();

  if (!inserted.error) {
    window.sessionStorage.removeItem(storageKey);
    return { data: { ...inserted.data, replayed: false }, error: null };
  }

  if (inserted.error.code !== "23505") {
    return { data: null, error: inserted.error };
  }

  const existing = await supabase
    .from("content_decisions")
    .select("decision_id,decision,note,content_item_id,content_item_version,processing_status,created_at,request_id")
    .eq("client_id", clientId)
    .eq("request_id", requestId)
    .maybeSingle();
  if (
    existing.error
    || !existing.data
    || existing.data.decision !== decision
    || existing.data.note !== note
    || existing.data.content_item_id !== contentItemId
    || existing.data.content_item_version !== contentItemVersion
  ) {
    return {
      data: null,
      error: existing.error ?? new Error("This decision request conflicts with an existing record."),
    };
  }

  window.sessionStorage.removeItem(storageKey);
  return { data: { ...existing.data, replayed: true }, error: null };
}
