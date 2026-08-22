import { createClient } from "@supabase/supabase-js";
import { dashboardData, dashboardPreviewForClient, previewWorkspaces } from "../data.js";
import { functionInvokeError } from "../functionErrors.js";
import { deriveOperationalState } from "../operationalState.js";
import { authoritativeClientIdentity } from "../clientPresentation.js";

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL;
const publishableKey = import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY;

export const isLiveReadEnabled = Boolean(supabaseUrl && publishableKey);
const maintenancePreviewEnabled = import.meta.env.DEV
  && new URLSearchParams(window.location.search).get("preview") === "maintenance";
const clientOperationsPreviewEnabled = import.meta.env.DEV
  && new URLSearchParams(window.location.search).get("preview") === "clients";

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
    client: authoritativeClientIdentity(snapshot.client, client),
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
  if (!supabase || maintenancePreviewEnabled || clientOperationsPreviewEnabled) {
    const selectedClientId = previewWorkspaces.some((workspace) => workspace.id === requestedClientId)
      ? requestedClientId
      : dashboardData.client.id;
    const basePreview = dashboardPreviewForClient(selectedClientId);
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
            snapshotOperations: basePreview.operations,
          });
          return {
            ...basePreview,
            operations: { ...operations, lastChecked: "Checked moments ago" },
          };
        })()
      : basePreview;
    return {
      data,
      workspaces: previewWorkspaces,
      selectedClientId,
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
  if (!supabase || clientOperationsPreviewEnabled) {
    return { allowed: import.meta.env.DEV, role: import.meta.env.DEV ? "admin" : null, error: null };
  }
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

export async function loadClientManagementData() {
  if (!supabase || clientOperationsPreviewEnabled) {
    const hcsRequest = {
      request_id: "preview-hcs",
      client_id: "hcs_gadgets",
      display_name: "HCS Gadgets",
      owner_email: "Workspace owner",
      shopify_store_domain: "hcsgadgets-com.myshopify.com",
      shopify_blog_title: "Gadget Blog",
      credential_status: "stored",
      status: "database_provisioned",
      commissioning_status: "identity_verified",
      content_categories: ["Buying guides", "Product education", "Maintenance", "Safety"],
      product_scope: [],
    };
    const previewClients = [
      {
        id: "hoverboard_store",
        name: "Hoverboard Store",
        status: "active",
        role: "owner",
        request: null,
        runtime: { request_intake_enabled: true, automation_enabled: true, shopify_writes_enabled: false, approved_draft_writes_enabled: true, max_concurrency: 1, allowed_mode: "dry-run" },
        health: { state: "healthy", scheduler_owner: "prefect:orin-hbstore-prod", last_heartbeat_at: new Date().toISOString() },
        activeJobs: 0,
        openIncidents: 0,
        recentRuns: [
          { run_id: "hb_preview_20260822", status: "completed", decision: "no_job_due", requested_mode: "dry-run", shopify_create_count: 0, started_at: new Date().toISOString(), finished_at: new Date().toISOString() },
        ],
        incidents: [],
      },
      {
        id: "hcs_gadgets",
        name: "HCS Gadgets",
        status: "active",
        role: "owner",
        request: hcsRequest,
        runtime: { request_intake_enabled: true, automation_enabled: true, shopify_writes_enabled: false, approved_draft_writes_enabled: false, max_concurrency: 1, allowed_mode: "dry-run" },
        health: { state: "healthy", scheduler_owner: "prefect:orin-hcs-prod", last_heartbeat_at: new Date().toISOString() },
        activeJobs: 0,
        openIncidents: 0,
        recentRuns: [
          { run_id: "hcs_preview_20260822", status: "completed", decision: "no_job_due", requested_mode: "dry-run", shopify_create_count: 0, started_at: new Date().toISOString(), finished_at: new Date().toISOString() },
        ],
        incidents: [],
      },
    ];
    return { data: { clients: previewClients, requests: [hcsRequest] }, error: null };
  }

  const [workspaceResult, requestResult] = await Promise.all([
    loadWorkspaceOptions(),
    loadOnboardingRequests(),
  ]);
  if (workspaceResult.error || requestResult.error) {
    return {
      data: null,
      error: workspaceResult.error ?? requestResult.error,
    };
  }

  const workspaces = workspaceResult.data ?? [];
  const requests = requestResult.data ?? [];
  const clientIds = workspaces.map((workspace) => workspace.id);
  if (clientIds.length === 0) {
    return {
      data: {
        clients: requests.map((request) => ({
          id: request.client_id,
          name: request.display_name,
          status: "onboarding",
          role: "operator",
          request,
          runtime: null,
          health: null,
          activeJobs: 0,
          openIncidents: 0,
          recentRuns: [],
          incidents: [],
        })),
        requests,
      },
      error: null,
    };
  }

  const [runtimeResult, healthResult, jobsResult, incidentsResult, runsResult] = await Promise.all([
    supabase
      .from("client_runtime_settings")
      .select("client_id,request_intake_enabled,automation_enabled,shopify_writes_enabled,approved_draft_writes_enabled,max_concurrency,allowed_mode,updated_at")
      .in("client_id", clientIds),
    supabase
      .from("scheduler_health")
      .select("client_id,state,scheduler_owner,last_heartbeat_at,last_expected_run_at,last_observed_run_id,updated_at")
      .in("client_id", clientIds),
    supabase
      .from("content_jobs")
      .select("client_id,status")
      .in("client_id", clientIds)
      .in("status", ["queued", "leased", "running"]),
    supabase
      .from("incidents")
      .select("client_id,incident_id,severity,status,code,summary,opened_at,updated_at")
      .in("client_id", clientIds)
      .order("opened_at", { ascending: false })
      .limit(50),
    supabase
      .from("runs")
      .select("client_id,run_id,status,decision,requested_mode,shopify_create_count,shopify_published,queue_changed,reconciliation_status,started_at,finished_at")
      .in("client_id", clientIds)
      .order("started_at", { ascending: false })
      .limit(50),
  ]);
  const error = runtimeResult.error
    ?? healthResult.error
    ?? jobsResult.error
    ?? incidentsResult.error
    ?? runsResult.error;
  if (error) return { data: null, error };

  const runtimeByClient = new Map((runtimeResult.data ?? []).map((row) => [row.client_id, row]));
  const healthByClient = new Map((healthResult.data ?? []).map((row) => [row.client_id, row]));
  const requestByClient = new Map(requests.map((request) => [request.client_id, request]));
  const activeJobsByClient = new Map();
  const openIncidentsByClient = new Map();
  const incidentsByClient = new Map();
  const runsByClient = new Map();
  for (const row of jobsResult.data ?? []) {
    activeJobsByClient.set(row.client_id, (activeJobsByClient.get(row.client_id) ?? 0) + 1);
  }
  for (const row of incidentsResult.data ?? []) {
    if (["open", "acknowledged"].includes(row.status)) {
      openIncidentsByClient.set(row.client_id, (openIncidentsByClient.get(row.client_id) ?? 0) + 1);
    }
    const incidents = incidentsByClient.get(row.client_id) ?? [];
    if (incidents.length < 5) incidents.push(row);
    incidentsByClient.set(row.client_id, incidents);
  }
  for (const row of runsResult.data ?? []) {
    const runs = runsByClient.get(row.client_id) ?? [];
    if (runs.length < 5) runs.push(row);
    runsByClient.set(row.client_id, runs);
  }

  const clients = workspaces.map((workspace) => {
    const runtime = runtimeByClient.get(workspace.id) ?? null;
    const health = healthByClient.get(workspace.id) ?? null;
    return {
      ...workspace,
      request: requestByClient.get(workspace.id) ?? null,
      runtime,
      health,
      operations: runtime && health
        ? deriveOperationalState({ client: { status: workspace.status }, runtime, health })
        : null,
      activeJobs: activeJobsByClient.get(workspace.id) ?? 0,
      openIncidents: openIncidentsByClient.get(workspace.id) ?? 0,
      recentRuns: runsByClient.get(workspace.id) ?? [],
      incidents: incidentsByClient.get(workspace.id) ?? [],
    };
  });

  for (const request of requests) {
    if (clients.some((client) => client.id === request.client_id)) continue;
    clients.push({
      id: request.client_id,
      name: request.display_name,
      status: "onboarding",
      role: "operator",
      request,
      runtime: null,
      health: null,
      operations: null,
      activeJobs: 0,
      openIncidents: 0,
      recentRuns: [],
      incidents: [],
    });
  }

  clients.sort((left, right) => left.name.localeCompare(right.name));
  return { data: { clients, requests }, error: null };
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
  return { data: data?.request ?? null, error: await functionInvokeError(error, data) };
}

export async function verifyOnboardingShopify(payload) {
  if (!supabase) return { data: null, error: new Error("Live Supabase access is required.") };
  const { data, error } = await supabase.functions.invoke("orin-client-onboarding", {
    body: payload,
  });
  return {
    data,
    error: await functionInvokeError(error, data),
  };
}

export async function updateOnboardingScope(requestId, productScope) {
  if (!supabase) return { data: null, error: new Error("Live Supabase access is required.") };
  const { data, error } = await supabase.functions.invoke("orin-client-onboarding", {
    body: { action: "update_scope", request_id: requestId, product_scope: productScope },
  });
  return { data: data?.request ?? null, error: await functionInvokeError(error, data) };
}

export async function provisionOnboardingClient(requestId) {
  if (!supabase) return { data: null, error: new Error("Live Supabase access is required.") };
  const { data, error } = await supabase.functions.invoke("orin-client-onboarding", {
    body: { action: "provision_client", request_id: requestId },
  });
  return { data: data?.request ?? null, error: await functionInvokeError(error, data) };
}

export async function auditProvisionedClient(clientId) {
  if (!supabase) return { data: null, error: new Error("Live Supabase access is required.") };
  const { data, error } = await supabase.functions.invoke("orin-client-onboarding", {
    body: { action: "audit_provisioned_client", client_id: clientId },
  });
  return { data: data?.audit ?? null, error: await functionInvokeError(error, data) };
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
