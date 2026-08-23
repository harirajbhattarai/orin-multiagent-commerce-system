export function clientIdFromName(value = "") {
  return value
    .toLowerCase()
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .slice(0, 63);
}

export function normalizeShopifyDomain(value = "") {
  const normalized = value.trim().toLowerCase()
    .replace(/^https?:\/\//, "")
    .split("/")[0];
  return /^[a-z0-9][a-z0-9-]*\.myshopify\.com$/.test(normalized)
    ? normalized
    : "";
}

export function productScopeFromText(value = "") {
  return value
    .split(/[,\n]/)
    .map((item) => item.trim())
    .filter(Boolean)
    .filter((item, index, all) => all.indexOf(item) === index)
    .slice(0, 100)
    .map((name) => ({ name }));
}

export function onboardingStepForRequest(request = {}) {
  if (["database_provisioned", "ready_to_provision"].includes(request.status)) return 4;
  if (request.status === "connection_verified" && request.credential_status === "stored") return 3;
  return 2;
}

export function discoveredProductScope(request = {}) {
  const discovery = request.shopify_discovery ?? {};
  const collectionNames = (discovery.collections ?? []).map((item) => item?.title);
  const productTypes = (discovery.products ?? []).map((item) => item?.productType);
  return [...collectionNames, ...productTypes]
    .map((item) => String(item ?? "").trim())
    .filter(Boolean)
    .filter((item, index, all) => all.findIndex((candidate) => candidate.toLowerCase() === item.toLowerCase()) === index)
    .slice(0, 100)
    .map((name) => ({ name }));
}

export function onboardingSafetyChecklist(request) {
  const safelyProvisioned = ["gates_closed", "identity_verified", "worker_pending", "dry_run_pending", "pilot_pending", "ready"]
    .includes(request?.commissioning_status);
  return [
    { label: "Business profile saved", complete: Boolean(request?.request_id) },
    { label: "Shopify token verified and encrypted", complete: request?.credential_status === "stored" },
    { label: "Isolated database tenant created", complete: request?.status === "database_provisioned" },
    { label: "Request intake and automation disabled", complete: safelyProvisioned },
    { label: "All Shopify write gates disabled", complete: safelyProvisioned },
    { label: "Scheduler disabled with no owner", complete: safelyProvisioned },
  ];
}

export const commissioningStageOrder = [
  "request_received",
  "worker_setup",
  "dry_run_proof",
  "scheduler_proof",
  "watchdog_proof",
  "complete",
];

export function commissioningProgress(request = null) {
  if (!request) return { active: false, terminal: false, currentIndex: -1, progress: 0 };
  const currentIndex = Math.max(0, commissioningStageOrder.indexOf(request.stage));
  const terminal = ["succeeded", "failed", "cancelled"].includes(request.status);
  return {
    active: ["queued", "running"].includes(request.status),
    terminal,
    currentIndex,
    progress: request.status === "succeeded"
      ? 100
      : Math.round(((currentIndex + 1) / commissioningStageOrder.length) * 100),
  };
}

export function clientManagementPresentation(client = {}) {
  const request = client.request ?? null;
  const runtime = client.runtime ?? null;
  const health = client.health ?? null;
  const identityVerified = ["identity_verified", "worker_pending", "dry_run_pending", "pilot_pending", "ready"]
    .includes(request?.commissioning_status);
  const recurringDryRun = client.status === "active"
    && runtime?.request_intake_enabled === true
    && runtime?.automation_enabled === true
    && runtime?.allowed_mode === "dry-run"
    && health?.state === "healthy"
    && Boolean(health?.scheduler_owner);
  const commissioning = commissioningProgress(client.commissioningRequest);

  let stage = { label: "Onboarding", tone: "neutral" };
  let nextAction = "Continue the safe onboarding steps.";
  if ((client.openIncidents ?? 0) > 0) {
    stage = { label: "Needs attention", tone: "orange" };
    nextAction = "Review the open incident before changing any execution gate.";
  } else if ((client.activeJobs ?? 0) > 0) {
    stage = { label: "Run active", tone: "blue" };
    nextAction = "Observe the active run and wait for its durable receipt.";
  } else if (commissioning.active) {
    stage = { label: client.commissioningRequest.status === "running" ? "Commissioning" : "Commissioning queued", tone: "blue" };
    nextAction = "ORIN is completing the isolated worker and dry-run proofs. Every Shopify write gate remains closed.";
  } else if (client.commissioningRequest?.status === "failed") {
    stage = { label: "Commissioning failed", tone: "orange" };
    nextAction = "Review the commissioning failure, keep every gate closed, then retry safely.";
  } else if (recurringDryRun) {
    stage = { label: "Recurring dry-run", tone: "green" };
    nextAction = "No setup action is required. Monitor the next scheduled proof.";
  } else if (identityVerified) {
    stage = { label: "Identity verified", tone: "blue" };
    nextAction = "Commission the isolated worker, automatic dry-run, and watchdog.";
  } else if (request?.status === "database_provisioned") {
    stage = { label: "Safely provisioned", tone: "blue" };
    nextAction = "Run the read-only Shopify identity audit.";
  } else if (request?.status === "ready_to_provision") {
    stage = { label: "Ready to provision", tone: "orange" };
    nextAction = "Create the fail-closed database workspace.";
  } else if (request?.credential_status === "stored") {
    stage = { label: "Scope required", tone: "orange" };
    nextAction = "Confirm the content scope and planning guardrails.";
  } else if (request) {
    stage = { label: "Shopify connection", tone: "orange" };
    nextAction = "Verify and encrypt the Shopify connection.";
  } else if (client.status === "maintenance") {
    stage = { label: "Maintenance", tone: "neutral" };
    nextAction = "Review the operational boundary before resuming commissioning.";
  }

  const credential = request?.credential_status === "stored"
    ? { label: "Encrypted", tone: "green" }
    : runtime ? { label: "Managed externally", tone: "neutral" }
      : { label: "Not connected", tone: "orange" };
  const shopify = runtime?.shopify_writes_enabled
    ? { label: "Hidden-draft gate", tone: "blue" }
    : runtime?.approved_draft_writes_enabled
      ? { label: "Approved drafts only", tone: "blue" }
      : { label: "Writes closed", tone: "neutral" };

  return {
    stage,
    nextAction,
    credential,
    shopify,
    canContinueOnboarding: Boolean(request) && !recurringDryRun,
    canRequestCommissioning: identityVerified && !recurringDryRun && !commissioning.active,
    commissioning,
    recurringDryRun,
  };
}
