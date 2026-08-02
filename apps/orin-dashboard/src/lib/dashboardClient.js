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

export async function loadDashboardData() {
  if (!supabase) {
    return { data: dashboardData, source: "demo", error: null };
  }

  const { data: sessionData } = await supabase.auth.getSession();
  if (!sessionData.session) {
    return { data: dashboardData, source: "demo", error: null };
  }

  const { data, error } = await supabase
    .from("client_dashboard_snapshot")
    .select("snapshot")
    .eq("client_id", dashboardData.client.id)
    .maybeSingle();

  if (error || !data?.snapshot) {
    return {
      data: dashboardData,
      source: "demo",
      error: error?.message ?? "No dashboard snapshot is available yet.",
    };
  }

  return { data: data.snapshot, source: "supabase", error: null };
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
