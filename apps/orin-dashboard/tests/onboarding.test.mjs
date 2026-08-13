import assert from "node:assert/strict";
import test from "node:test";
import {
  clientIdFromName,
  normalizeShopifyDomain,
  onboardingSafetyChecklist,
  productScopeFromText,
} from "../src/onboarding.js";

test("creates stable tenant identifiers from client names", () => {
  assert.equal(clientIdFromName("Hariraj's Cycle Store"), "hariraj_s_cycle_store");
  assert.equal(clientIdFromName("  Café & Scooters  "), "cafe_scooters");
  assert.equal(clientIdFromName("***"), "");
});

test("accepts only permanent myshopify domains", () => {
  assert.equal(normalizeShopifyDomain("https://Example-Store.myshopify.com/admin"), "example-store.myshopify.com");
  assert.equal(normalizeShopifyDomain("example.com"), "");
  assert.equal(normalizeShopifyDomain("evil.myshopify.com.example.com"), "");
});

test("normalizes and deduplicates the product scope", () => {
  assert.deepEqual(productScopeFromText("Kids scooters\nSafety gear, Kids scooters"), [
    { name: "Kids scooters" },
    { name: "Safety gear" },
  ]);
});

test("provisioning checklist stays incomplete until the fail-closed tenant exists", () => {
  const before = onboardingSafetyChecklist({ credential_status: "stored", status: "ready_to_provision" });
  assert.equal(before.filter((item) => item.complete).length, 1);

  const after = onboardingSafetyChecklist({
    request_id: "request-1",
    credential_status: "stored",
    status: "database_provisioned",
    commissioning_status: "gates_closed",
  });
  assert.equal(after.every((item) => item.complete), true);

  const audited = onboardingSafetyChecklist({
    request_id: "request-1",
    credential_status: "stored",
    status: "database_provisioned",
    commissioning_status: "identity_verified",
  });
  assert.equal(audited.every((item) => item.complete), true);
});
