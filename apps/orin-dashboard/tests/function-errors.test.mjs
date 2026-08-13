import assert from "node:assert/strict";
import test from "node:test";
import { FunctionsHttpError } from "@supabase/supabase-js";
import { functionInvokeError } from "../src/functionErrors.js";

test("shows the Edge Function's actionable JSON error", async () => {
  const response = new Response(JSON.stringify({ error: "Shopify token needs read_products access." }), {
    status: 422,
    headers: { "Content-Type": "application/json" },
  });
  const result = await functionInvokeError(new FunctionsHttpError(response), null);
  assert.equal(result.message, "Shopify token needs read_products access.");
});

test("prefers an already-decoded function response", async () => {
  const result = await functionInvokeError(new Error("generic"), { error: "Exact server reason." });
  assert.equal(result.message, "Exact server reason.");
});
