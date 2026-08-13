import { FunctionsHttpError } from "@supabase/supabase-js";

export async function functionInvokeError(error, data) {
  if (data?.error) return new Error(String(data.error));
  if (error instanceof FunctionsHttpError) {
    try {
      const payload = await error.context.json();
      if (payload?.error) return new Error(String(payload.error));
    } catch {
      // Fall through to the transport-level message when the response is not JSON.
    }
  }
  return error ?? null;
}
