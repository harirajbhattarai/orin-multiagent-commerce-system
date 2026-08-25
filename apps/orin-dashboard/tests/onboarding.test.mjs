import assert from "node:assert/strict";
import test from "node:test";
import {
  clientIdFromName,
  clientManagementPresentation,
  commissioningProgress,
  discoveredProductScope,
  normalizeShopifyDomain,
  onboardingStepForRequest,
  onboardingSafetyChecklist,
  productScopeFromText,
} from "../src/onboarding.js";
import { dashboardPreviewForClient } from "../src/data.js";

test("keeps preview data inside the requested tenant", () => {
  const hcs = dashboardPreviewForClient("hcs_gadgets");
  assert.equal(hcs.client.id, "hcs_gadgets");
  assert.equal(hcs.client.name, "HCS Gadgets");
  assert.equal(hcs.queue.some((article) => article.id === 2), true);
  assert.equal(hcs.queue.some((article) => article.id === 33), false);
});

test("creates stable tenant identifiers from client names", () => {
  assert.equal(clientIdFromName("Hariraj's Cycle Store"), "hariraj_s_cycle_store");
  assert.equal(clientIdFromName("  Café & Scooters  "), "cafe_scooters");
  assert.equal(clientIdFromName("***"), "");
});

test("presents a proven recurring client without offering more onboarding", () => {
  const presentation = clientManagementPresentation({
    status: "active",
    runtime: {
      request_intake_enabled: true,
      automation_enabled: true,
      shopify_writes_enabled: false,
      approved_draft_writes_enabled: false,
      allowed_mode: "dry-run",
    },
    health: { state: "healthy", scheduler_owner: "prefect:orin-hcs-prod" },
    request: { credential_status: "stored", commissioning_status: "identity_verified" },
  });
  assert.equal(presentation.stage.label, "Recurring dry-run");
  assert.equal(presentation.shopify.label, "Writes closed");
  assert.equal(presentation.canContinueOnboarding, false);
});

test("prioritizes incidents over otherwise healthy client state", () => {
  const presentation = clientManagementPresentation({
    status: "active",
    openIncidents: 1,
    runtime: {
      request_intake_enabled: true,
      automation_enabled: true,
      allowed_mode: "dry-run",
    },
    health: { state: "healthy", scheduler_owner: "prefect:orin-hcs-prod" },
  });
  assert.equal(presentation.stage.label, "Needs attention");
  assert.match(presentation.nextAction, /incident/i);
});

test("keeps an unprovisioned client in the safe onboarding path", () => {
  const presentation = clientManagementPresentation({
    status: "onboarding",
    request: { credential_status: "stored", status: "ready_to_provision" },
  });
  assert.equal(presentation.stage.label, "Ready to provision");
  assert.equal(presentation.credential.label, "Encrypted");
  assert.equal(presentation.canContinueOnboarding, true);
});

test("presents an idempotent commissioning request without claiming production readiness", () => {
  const presentation = clientManagementPresentation({
    status: "maintenance",
    request: { credential_status: "stored", commissioning_status: "worker_pending" },
    commissioningRequest: { status: "queued", stage: "request_received" },
    runtime: {
      request_intake_enabled: false,
      automation_enabled: false,
      shopify_writes_enabled: false,
      approved_draft_writes_enabled: false,
      allowed_mode: "dry-run",
    },
    health: { state: "disabled", scheduler_owner: null },
  });
  assert.equal(presentation.stage.label, "Commissioning queued");
  assert.equal(presentation.canRequestCommissioning, false);
  assert.match(presentation.nextAction, /write gate remains closed/i);
});

test("maps commissioning stages to bounded progress", () => {
  assert.deepEqual(commissioningProgress(null), {
    active: false,
    terminal: false,
    currentIndex: -1,
    progress: 0,
  });
  assert.equal(commissioningProgress({ status: "running", stage: "dry_run_proof" }).progress, 50);
  assert.equal(commissioningProgress({ status: "succeeded", stage: "complete" }).progress, 100);
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

test("keeps a multi-blog OAuth connection on the blog selection step", () => {
  assert.equal(onboardingStepForRequest({
    status: "oauth_connected",
    credential_status: "stored",
  }), 2);
  assert.equal(onboardingStepForRequest({
    status: "connection_verified",
    credential_status: "stored",
  }), 3);
});

test("suggests a deduplicated scope from discovered collections and product types", () => {
  assert.deepEqual(discoveredProductScope({
    shopify_discovery: {
      collections: [{ title: "Adult Scooters" }, { title: "Hoverboards" }],
      products: [
        { productType: "Electric Scooter" },
        { productType: "adult scooters" },
        { productType: "" },
      ],
    },
  }), [
    { name: "Adult Scooters" },
    { name: "Hoverboards" },
    { name: "Electric Scooter" },
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

test("labels a completed read-only pilot accurately while Shopify remains closed", () => {
  const presentation = clientManagementPresentation({
    status: "maintenance",
    request: { status: "database_provisioned", commissioning_status: "pilot_pending", credential_status: "stored" },
    commissioningRequest: { status: "succeeded", stage: "complete" },
    runtime: {
      request_intake_enabled: false,
      automation_enabled: false,
      shopify_writes_enabled: false,
      approved_draft_writes_enabled: false,
      allowed_mode: "dry-run",
    },
    health: { state: "disabled", scheduler_owner: null },
    activeJobs: 0,
    openIncidents: 0,
  });

  assert.equal(presentation.stage.label, "Pilot draft ready");
  assert.match(presentation.nextAction, /Review the version-bound pilot draft/);
});
