const HEARTBEAT_MAX_AGE_MS = 48 * 60 * 60 * 1000;

function isRecent(value, nowMs) {
  if (!value) return false;
  const observedMs = new Date(value).getTime();
  return Number.isFinite(observedMs)
    && observedMs <= nowMs
    && nowMs - observedMs <= HEARTBEAT_MAX_AGE_MS;
}

function schedulerPresentation(state) {
  if (state === "disabled") return { label: "Paused", tone: "neutral" };
  if (state === "healthy") return { label: "Healthy", tone: "green" };
  if (state === "late") return { label: "Late", tone: "orange" };
  if (state === "error") return { label: "Error", tone: "orange" };
  return { label: "Needs attention", tone: "orange" };
}

export function deriveOperationalState({
  client = {},
  runtime = {},
  health = {},
  snapshotOperations = {},
  nowMs = Date.now(),
} = {}) {
  const clientActive = client.status === "active";
  const requestIntakeEnabled = runtime.request_intake_enabled === true;
  const automationEnabled = runtime.automation_enabled === true;
  const broadShopifyWritesEnabled = runtime.shopify_writes_enabled === true;
  const approvedDraftWritesEnabled = runtime.approved_draft_writes_enabled === true;
  const approvedDraftOnlyOpen = approvedDraftWritesEnabled
    && !broadShopifyWritesEnabled
    && runtime.allowed_mode === "dry-run";
  const broadHiddenDraftOpen = broadShopifyWritesEnabled
    && !approvedDraftWritesEnabled
    && runtime.allowed_mode === "hidden-draft";
  const scheduler = schedulerPresentation(health.state);
  const lastRunStatus = health.details?.last_run_status;
  const lastRunDecision = health.details?.last_run_decision;
  const heartbeatRecent = isRecent(
    health.last_heartbeat_at ?? snapshotOperations.lastChecked,
    nowMs,
  );
  const executionOpen = clientActive && requestIntakeEnabled && automationEnabled;
  const hiddenDraftApprovalOpen = executionOpen
    && (approvedDraftOnlyOpen || broadHiddenDraftOpen);
  const maintenancePaused = client.status === "maintenance";
  const executionPaused = !executionOpen;
  const attentionRequired = !executionPaused
    && (
      health.state === "late"
      || health.state === "error"
      || (health.state === "healthy" && !heartbeatRecent)
    );

  const workspaceLabel = maintenancePaused
    ? "Maintenance paused"
    : executionPaused ? "Execution paused" : attentionRequired ? "Needs attention" : "Live workspace";
  const workspaceMessage = maintenancePaused
    ? "Content execution is paused for a reliability checkpoint. Reviews remain readable, but approvals cannot start work."
    : executionPaused
      ? "One or more execution gates are closed. Approvals remain unavailable until operations are restored."
      : attentionRequired
        ? "The workspace is open, but operational health needs attention before approvals continue."
        : "The controlled content workflow is available. Shopify still requires an explicit unpublished-draft approval.";

  const worker = !executionOpen
    ? { label: "Idle", tone: "neutral", detail: "Intake and automation are closed; no content work can be claimed." }
    : heartbeatRecent
      ? { label: "Ready", tone: "green", detail: "Execution gates are open and the latest scheduler heartbeat is current." }
      : { label: "Needs attention", tone: "orange", detail: "Execution is open, but the latest scheduler heartbeat is stale or missing." };
  const watchdog = health.state === "disabled"
    ? { label: "Paused", tone: "neutral", detail: "Read-only schedule monitoring is paused with scheduler ownership." }
    : health.state === "healthy" && heartbeatRecent
      ? { label: "Observing", tone: "green", detail: "Read-only monitoring is aligned with the healthy scheduler heartbeat." }
      : { label: "Needs attention", tone: "orange", detail: "Scheduler health is late, errored, or missing a current heartbeat." };
  const shopify = maintenancePaused || !hiddenDraftApprovalOpen
    ? {
        label: maintenancePaused ? "Paused" : "Disabled",
        tone: "neutral",
        detail: broadShopifyWritesEnabled || approvedDraftWritesEnabled
          ? "A Shopify gate is configured, but the client execution boundary is closed."
          : "Both Shopify write gates are closed. No draft can be created.",
      }
    : broadShopifyWritesEnabled
      ? { label: "Broad drafts", tone: "blue", detail: "The broad hidden-draft gate is open." }
      : { label: "Approved drafts only", tone: "blue", detail: "Only an explicitly approved, version-bound draft can be created." };

  return {
    ...snapshotOperations,
    clientStatus: client.status ?? "unknown",
    schedulerOwner: health.scheduler_owner ?? null,
    scheduler: scheduler.label,
    schedulerTone: scheduler.tone,
    schedulerDetail: health.state === "disabled"
      ? "Scheduler ownership is disabled during maintenance."
      : health.state === "late"
        ? "The expected scheduled run has not been observed on time."
        : health.state === "error"
          ? `Latest scheduled run${lastRunStatus ? ` ${lastRunStatus}` : ""}${lastRunDecision ? `: ${lastRunDecision}` : "."}`
      : health.scheduler_owner
        ? `Owned by ${health.scheduler_owner}.`
        : "Scheduler ownership is not recorded.",
    worker: worker.label,
    workerTone: worker.tone,
    workerDetail: worker.detail,
    watchdog: watchdog.label,
    watchdogTone: watchdog.tone,
    watchdogDetail: watchdog.detail,
    shopifyWrites: shopify.label,
    shopifyTone: shopify.tone,
    shopifyDetail: shopify.detail,
    requestIntakeEnabled,
    automationEnabled,
    broadShopifyWritesEnabled,
    approvedDraftWritesEnabled,
    allowedMode: runtime.allowed_mode ?? snapshotOperations.allowedMode ?? "dry-run",
    canApproveConcept: executionOpen && !attentionRequired,
    canApproveHiddenDraft: hiddenDraftApprovalOpen && !attentionRequired,
    isPaused: executionPaused || attentionRequired,
    maintenancePaused,
    workspaceLabel,
    workspaceMessage,
    overallTone: attentionRequired ? "attention" : executionPaused ? "paused" : "healthy",
    overallLabel: attentionRequired ? "Operations need attention" : executionPaused ? "Workflow safely paused" : "Everything is protected",
    lastChecked: health.last_heartbeat_at ?? health.updated_at ?? snapshotOperations.lastChecked ?? null,
  };
}

export function approvalAvailability(operations, reviewKind) {
  if (reviewKind === "concept") {
    return operations?.canApproveConcept
      ? { allowed: true, reason: "" }
      : { allowed: false, reason: "Concept approval is paused until client intake, automation, and scheduler health are active." };
  }
  if (reviewKind === "draft") {
    return operations?.canApproveHiddenDraft
      ? { allowed: true, reason: "" }
      : { allowed: false, reason: "Shopify draft approval is paused until the client and approved-draft write gates are active." };
  }
  return { allowed: false, reason: "This content version is not in an approvable stage." };
}
