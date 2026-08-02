import { createClient } from "@supabase/supabase-js";
import { dashboardData } from "../data.js";

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL;
const publishableKey = import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY;

export const isLiveReadEnabled = Boolean(supabaseUrl && publishableKey);

const supabase = isLiveReadEnabled
  ? createClient(supabaseUrl, publishableKey, {
      auth: {
        persistSession: true,
        autoRefreshToken: true,
        detectSessionInUrl: true,
      },
    })
  : null;

function formatMoment(value, options) {
  if (!value) return "Not observed yet";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return new Intl.DateTimeFormat("en-GB", options).format(date);
}

function normalizeSnapshot(snapshot) {
  return {
    ...snapshot,
    operations: {
      ...snapshot.operations,
      lastChecked: `Checked ${formatMoment(snapshot.operations?.lastChecked, {
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

export async function loadDashboardData() {
  if (!supabase) {
    return { data: dashboardData, source: "demo", error: null, requiresAuth: false };
  }

  const { data: sessionData, error: sessionError } = await supabase.auth.getSession();
  if (sessionError) {
    return { data: null, source: "error", error: sessionError.message, requiresAuth: false };
  }
  if (!sessionData.session) {
    return { data: null, source: "auth", error: null, requiresAuth: true };
  }

  const { data, error } = await supabase
    .from("client_dashboard_snapshot")
    .select("snapshot")
    .eq("client_id", dashboardData.client.id)
    .maybeSingle();

  if (error || !data?.snapshot) {
    return {
      data: null,
      source: "error",
      error: error?.message ?? "Your account is not connected to a client workspace yet.",
      requiresAuth: false,
    };
  }

  return { data: normalizeSnapshot(data.snapshot), source: "supabase", error: null, requiresAuth: false };
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
