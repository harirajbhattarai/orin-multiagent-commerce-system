import { useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowLeft,
  ArrowRight,
  ArrowClockwise,
  CalendarCheck,
  Check,
  CheckCircle,
  CloudCheck,
  Database,
  Key,
  ListChecks,
  LockKey,
  MagnifyingGlass,
  Plus,
  Robot,
  ShieldCheck,
  Storefront,
  UserPlus,
  WarningCircle,
} from "@phosphor-icons/react";
import {
  createOnboardingRequest,
  auditProvisionedClient,
  beginOnboardingShopifyOAuth,
  loadClientManagementData,
  provisionOnboardingClient,
  requestClientCommissioning,
  requestClientRecurringPilot,
  selectOnboardingShopifyBlog,
  updateOnboardingScope,
} from "./lib/dashboardClient.js";
import {
  clientIdFromName,
  clientManagementPresentation,
  commissioningProgress,
  commissioningStageOrder,
  discoveredProductScope,
  normalizeShopifyDomain,
  onboardingStepForRequest,
  onboardingSafetyChecklist,
  productScopeFromText,
} from "./onboarding.js";

const defaultForm = {
  displayName: "",
  clientId: "",
  ownerEmail: "",
  storeDomain: "",
  marketCountry: "GB",
  timezone: "Europe/London",
  brandVoice: "Helpful, practical, trustworthy, and clear.",
  categories: "Buying guides, Product education, Maintenance, Safety",
};

const steps = [
  { id: 1, label: "Business", icon: UserPlus },
  { id: 2, label: "Shopify", icon: Key },
  { id: 3, label: "Content scope", icon: Storefront },
  { id: 4, label: "Safe workspace", icon: ShieldCheck },
];

function statusLabel(value = "") {
  return value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function OnboardingProgress({ step }) {
  return (
    <ol className="onboarding-progress" aria-label="Onboarding progress">
      {steps.map((item) => {
        const Icon = item.icon;
        const complete = item.id < step;
        return (
          <li key={item.id} className={item.id === step ? "active" : complete ? "complete" : ""}>
            <span>{complete ? <Check size={16} weight="bold" /> : <Icon size={17} weight="duotone" />}</span>
            <div><small>STEP {item.id}</small><strong>{item.label}</strong></div>
          </li>
        );
      })}
    </ol>
  );
}

function Field({ label, hint, children }) {
  return (
    <label className="onboarding-field">
      <span>{label}</span>
      {children}
      {hint && <small>{hint}</small>}
    </label>
  );
}

function formatMoment(value) {
  if (!value) return "Not observed yet";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return new Intl.DateTimeFormat("en-GB", {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "Europe/London",
  }).format(date);
}

function ManagementMetric({ icon: Icon, label, value, tone }) {
  return (
    <div className={`metric-card ${tone}`}>
      <span className="metric-icon"><Icon size={21} weight="duotone" /></span>
      <div><span>{label}</span><strong>{value}</strong></div>
    </div>
  );
}

function GateStatus({ label, detail, active, attention = false }) {
  return (
    <div className="client-gate-row">
      <span className={`gate-indicator ${attention ? "attention" : active ? "active" : "closed"}`}>
        {attention ? <WarningCircle size={17} weight="fill" /> : active ? <CheckCircle size={17} weight="fill" /> : <LockKey size={16} weight="duotone" />}
      </span>
      <div><strong>{label}</strong><small>{detail}</small></div>
    </div>
  );
}

function RunStatus({ run }) {
  const safeRun = run.shopify_create_count === 0 && run.shopify_published !== true;
  return (
    <div className="client-activity-row">
      <span className={`activity-status ${run.status === "completed" && safeRun ? "green" : run.status === "failed" ? "orange" : "blue"}`}>
        {run.status === "completed" && safeRun ? <CheckCircle size={17} weight="fill" /> : <Robot size={17} weight="duotone" />}
      </span>
      <div><strong>{run.decision?.replaceAll("_", " ") || run.status}</strong><small>{run.run_id} · {run.requested_mode} · {run.shopify_create_count ?? 0} Shopify creates</small></div>
      <time>{formatMoment(run.finished_at ?? run.started_at)}</time>
    </div>
  );
}

function CommissioningJourney({ client, presentation }) {
  const identityVerified = ["identity_verified", "worker_pending", "dry_run_pending", "pilot_pending", "ready"].includes(client.request?.commissioning_status) || presentation.recurringDryRun;
  const workerReady = Boolean(client.runtime) && (client.runtime.automation_enabled || presentation.recurringDryRun);
  const schedulerReady = client.health?.state === "healthy" && Boolean(client.health?.scheduler_owner);
  const steps = [
    { label: "Workspace isolated", detail: "Tenant, credentials, and write gates are separated.", complete: Boolean(client.runtime || client.request?.status === "database_provisioned") },
    { label: "Read-only identity", detail: "Store, blog, and catalogue access verified without writes.", complete: identityVerified },
    { label: "Dry-run worker", detail: "Client-specific worker can process controlled requests.", complete: workerReady },
    { label: "Schedule and watchdog", detail: "Recurring ownership and monitoring are durable.", complete: schedulerReady },
  ];
  return (
    <ol className="commissioning-journey">
      {steps.map((item, index) => <li key={item.label} className={item.complete ? "complete" : "pending"}><span>{item.complete ? <Check size={15} weight="bold" /> : index + 1}</span><div><strong>{item.label}</strong><small>{item.detail}</small></div></li>)}
    </ol>
  );
}

const commissioningStageLabels = {
  request_received: "Request accepted",
  worker_setup: "Isolated worker",
  dry_run_proof: "Automatic dry-run proof",
  scheduler_proof: "Recurring schedule",
  watchdog_proof: "Read-only watchdog",
  complete: "Read-only boundary complete",
};

function CommissioningProgress({ request }) {
  if (!request) return null;
  const progress = commissioningProgress(request);
  return (
    <div className={`commissioning-progress-card ${request.status}`}>
      <div className="commissioning-progress-heading">
        <div><span className="section-kicker">SAFE COMMISSIONING</span><strong>{request.status === "succeeded" ? "Read-only commissioning complete" : request.status === "failed" ? "Commissioning needs attention" : "ORIN is preparing this client"}</strong></div>
        <span className={`status-pill ${request.status === "failed" ? "orange" : request.status === "succeeded" ? "green" : "blue"}`}>{statusLabel(request.status)}</span>
      </div>
      <div className="commissioning-progress-track"><span style={{ width: `${progress.progress}%` }} /></div>
      <ol>
        {commissioningStageOrder.map((stage, index) => {
          const event = [...(request.events ?? [])].reverse().find((item) => item.stage === stage);
          const complete = request.status === "succeeded" || index < progress.currentIndex || event?.status === "passed";
          const current = !complete && index === progress.currentIndex;
          return <li key={stage} className={complete ? "complete" : current ? "current" : "pending"}><span>{complete ? <Check size={13} weight="bold" /> : index + 1}</span><div><strong>{commissioningStageLabels[stage]}</strong><small>{event?.summary ?? (current ? "Waiting for a trusted commissioning worker." : "Not started")}</small></div></li>;
        })}
      </ol>
      <p><LockKey size={15} /> Shopify writes and live publishing remain unavailable throughout commissioning.</p>
      {request.last_error && <div className="commissioning-error"><WarningCircle size={16} /> {request.last_error}</div>}
    </div>
  );
}

function ClientManagement({
  clients,
  selectedClientId,
  onSelect,
  onNewClient,
  onContinue,
  onOpenWorkspace,
  onRefresh,
  onRequestCommissioning,
  onStartRecurringPilot,
  commissioningBusy,
  recurringPilotBusy,
  refreshing,
  lastRefreshed,
  message,
}) {
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("all");
  const [tab, setTab] = useState("overview");
  const selected = clients.find((client) => client.id === selectedClientId) ?? clients[0] ?? null;
  const selectedPresentation = clientManagementPresentation(selected ?? {});
  const activeCount = clients.filter((client) => client.status === "active").length;
  const pausedCount = clients.filter((client) => client.status === "maintenance" || client.status === "onboarding").length;
  const attentionCount = clients.filter((client) => clientManagementPresentation(client).stage.tone === "orange").length;
  const visibleClients = clients.filter((client) => {
    const presentation = clientManagementPresentation(client);
    const matchesQuery = [client.name, client.id, client.request?.shopify_store_domain]
      .filter(Boolean)
      .some((value) => value.toLowerCase().includes(query.trim().toLowerCase()));
    if (!matchesQuery) return false;
    if (filter === "active") return client.status === "active";
    if (filter === "paused") return client.status === "maintenance" || client.status === "onboarding";
    if (filter === "attention") return presentation.stage.tone === "orange" || client.openIncidents > 0;
    return true;
  });

  useEffect(() => { setTab("overview"); }, [selectedClientId]);

  return (
    <div className="client-management-page">
      <div className="page-heading onboarding-heading">
        <div>
          <span className="eyebrow">PLATFORM OPERATIONS</span>
          <h1>Client operations</h1>
          <p>Onboard, commission, and monitor every isolated client from one safe workspace.</p>
        </div>
        <div className="client-heading-actions">
          <span className="management-updated">Updated {lastRefreshed ? formatMoment(lastRefreshed) : "when refreshed"}</span>
          <button className="secondary-button" type="button" onClick={onRefresh} disabled={refreshing}><ArrowClockwise size={17} className={refreshing ? "spinning" : ""} /> {refreshing ? "Refreshing…" : "Refresh"}</button>
          <button className="primary-button" type="button" onClick={onNewClient}><Plus size={17} /> New client</button>
        </div>
      </div>

      {message?.text && <div className={`onboarding-message ${message.tone}`} role="status">{message.tone === "error" ? <WarningCircle size={20} /> : <CheckCircle size={20} weight="fill" />}<span>{message.text}</span></div>}

      <div className="metric-grid client-metrics">
        <ManagementMetric icon={Storefront} label="Clients" value={clients.length} tone="slate" />
        <ManagementMetric icon={CloudCheck} label="Active" value={activeCount} tone="green" />
        <ManagementMetric icon={LockKey} label="Safely paused" value={pausedCount} tone="blue" />
        <ManagementMetric icon={WarningCircle} label="Needs action" value={attentionCount} tone="orange" />
      </div>

      {selected ? (
        <div className="client-management-layout">
          <section className="client-directory" aria-label="Client directory">
            <div className="section-heading"><div><span className="section-kicker">WORKSPACES</span><h2>All clients</h2></div><span className="status-pill neutral">{clients.length}</span></div>
            <div className="client-directory-tools">
              <label className="client-search"><MagnifyingGlass size={16} /><span className="sr-only">Search clients</span><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search client or store" /></label>
              <div className="client-filter-chips" aria-label="Filter clients">
                {[{ id: "all", label: "All" }, { id: "active", label: "Active" }, { id: "paused", label: "Paused" }, { id: "attention", label: "Needs action" }].map((item) => <button key={item.id} type="button" className={filter === item.id ? "active" : ""} aria-pressed={filter === item.id} onClick={() => setFilter(item.id)}>{item.label}</button>)}
              </div>
            </div>
            <div className="client-directory-list">
              {visibleClients.map((client) => {
                const presentation = clientManagementPresentation(client);
                return (
                  <button type="button" key={client.id} className={selected.id === client.id ? "active" : ""} onClick={() => onSelect(client.id)}>
                    <span className="client-avatar">{client.name.slice(0, 1).toUpperCase()}</span>
                    <span className="client-directory-copy"><strong>{client.name}</strong><small>{client.id}</small><span className={`status-pill ${presentation.stage.tone}`}>{presentation.stage.label}</span></span>
                    <ArrowRight size={16} />
                  </button>
                );
              })}
              {visibleClients.length === 0 && <div className="client-directory-empty"><MagnifyingGlass size={20} /><strong>No matching clients</strong><span>Clear the search or choose another filter.</span></div>}
            </div>
            <div className="vault-note"><LockKey size={21} weight="duotone" /><span><strong>Credentials stay server-side</strong>No Shopify token or database credential is exposed here.</span></div>
          </section>

          <section className="client-operations-detail">
            <div className="client-detail-header">
              <div><span className="section-kicker">{selected.role ?? "CLIENT"} WORKSPACE</span><h2>{selected.name}</h2><p>{selected.request?.shopify_store_domain ?? "Existing operational client"}</p></div>
              <span className={`status-pill ${selectedPresentation.stage.tone}`}>{selectedPresentation.stage.label}</span>
            </div>

            <div className="client-facts">
              <div><span>Shopify blog</span><strong>{selected.request?.shopify_blog_title ?? "Managed operationally"}</strong></div>
              <div><span>Owner</span><strong>{selected.request?.owner_email ?? "Existing client membership"}</strong></div>
              <div><span>Credentials</span><strong className={`fact-tone ${selectedPresentation.credential.tone}`}>{selectedPresentation.credential.label}</strong></div>
              <div><span>Mode</span><strong>{selected.runtime?.allowed_mode ?? "Not commissioned"}</strong></div>
            </div>
            <div className="client-detail-tabs" role="tablist" aria-label="Client operations sections">
              {[{ id: "overview", label: "Overview" }, { id: "activity", label: `Activity (${selected.recentRuns?.length ?? 0})` }, { id: "setup", label: "Setup journey" }].map((item) => <button key={item.id} type="button" role="tab" aria-selected={tab === item.id} className={tab === item.id ? "active" : ""} onClick={() => setTab(item.id)}>{item.label}</button>)}
            </div>

            {tab === "overview" && <>
              <div className="client-operations-grid">
                <div className="client-operations-panel">
                  <div className="panel-heading"><ShieldCheck size={20} weight="duotone" /><div><strong>Execution boundary</strong><span>Authoritative gates for this client</span></div></div>
                  <GateStatus label="Request intake" detail={selected.runtime?.request_intake_enabled ? "New controlled work may be queued." : "No new work can enter the worker queue."} active={selected.runtime?.request_intake_enabled === true} />
                  <GateStatus label="Automation" detail={selected.runtime?.automation_enabled ? "The isolated worker may claim approved work." : "The worker cannot claim client work."} active={selected.runtime?.automation_enabled === true} />
                  <GateStatus label="Shopify access" detail={selectedPresentation.shopify.label} active={selected.runtime?.approved_draft_writes_enabled === true || selected.runtime?.shopify_writes_enabled === true} />
                </div>

                <div className="client-operations-panel">
                  <div className="panel-heading"><Robot size={20} weight="duotone" /><div><strong>Automation & monitoring</strong><span>Scheduler ownership and durable health</span></div></div>
                  <GateStatus label="Scheduler" detail={selected.health?.scheduler_owner ? `Owned by ${selected.health.scheduler_owner}` : "No scheduler owner is assigned."} active={selected.health?.state === "healthy"} attention={["late", "error"].includes(selected.health?.state)} />
                  <GateStatus label="Watchdog signal" detail={selected.health?.state === "healthy" ? "Aligned with the latest healthy scheduler receipt." : "Monitoring is paused or needs attention."} active={selected.health?.state === "healthy"} attention={["late", "error"].includes(selected.health?.state)} />
                  <div className="client-observation"><CalendarCheck size={17} /><span><strong>Last observed</strong>{formatMoment(selected.health?.last_heartbeat_at ?? selected.health?.updated_at)}</span></div>
                  {selected.recurringSchedule && <div className="client-observation"><CalendarCheck size={17} /><span><strong>Next dry-run</strong>{formatMoment(selected.recurringSchedule.next_run_at)} · {selected.recurringSchedule.timezone}</span></div>}
                </div>
              </div>

              <div className={`client-next-action ${selectedPresentation.stage.tone}`}>
                <ListChecks size={22} weight="duotone" />
                <div><strong>Next safe action</strong><span>{selectedPresentation.nextAction}</span></div>
                <div className="client-action-facts"><span>{selected.activeJobs} active jobs</span><span>{selected.openIncidents} open incidents</span></div>
              </div>
            </>}

            {tab === "activity" && <div className="client-activity-panel">
              <div className="panel-heading"><CalendarCheck size={20} weight="duotone" /><div><strong>Durable activity</strong><span>Latest tenant-scoped runs and incidents from the operational database</span></div></div>
              <div className="client-activity-list">{selected.recentRuns?.length ? selected.recentRuns.map((run) => <RunStatus key={run.run_id} run={run} />) : <div className="client-activity-empty"><Robot size={22} /><strong>No durable runs yet</strong><span>The first dry-run receipt will appear here after commissioning.</span></div>}</div>
              <div className="incident-summary"><strong>Incidents</strong>{selected.incidents?.length ? selected.incidents.map((incident) => <div key={incident.incident_id}><WarningCircle size={16} /><span><strong>{incident.summary || incident.code}</strong><small>{statusLabel(incident.status)} · {formatMoment(incident.updated_at || incident.opened_at)}</small></span></div>) : <span className="no-incidents"><CheckCircle size={16} weight="fill" /> No incidents recorded for this client.</span>}</div>
            </div>}

            {tab === "setup" && <div className="client-setup-panel"><div className="panel-heading"><ListChecks size={20} weight="duotone" /><div><strong>Commissioning journey</strong><span>Every production capability is earned through a durable proof</span></div></div><CommissioningJourney client={selected} presentation={selectedPresentation} /><div className={`client-next-action ${selectedPresentation.stage.tone}`}><ShieldCheck size={22} weight="duotone" /><div><strong>Current safe boundary</strong><span>{selectedPresentation.nextAction}</span></div></div></div>}

            {selected.commissioningRequest && <CommissioningProgress request={selected.commissioningRequest} />}

            <div className="client-detail-actions">
              {selectedPresentation.canContinueOnboarding && selected.request && <button className="secondary-button" type="button" onClick={() => onContinue(selected.request)}>Continue setup</button>}
              {selectedPresentation.canRequestCommissioning && <button className="primary-button" type="button" onClick={() => onRequestCommissioning(selected.id)} disabled={commissioningBusy === selected.id}>{commissioningBusy === selected.id ? "Requesting…" : selected.commissioningRequest?.status === "failed" ? "Retry safe commissioning" : "Start safe commissioning"}<ArrowRight size={17} /></button>}
              {selectedPresentation.canStartRecurringPilot && <button className="primary-button" type="button" onClick={() => onStartRecurringPilot(selected.id)} disabled={recurringPilotBusy === selected.id}>{recurringPilotBusy === selected.id ? "Starting…" : "Start recurring dry-runs"}<ArrowRight size={17} /></button>}
              {selected.runtime && <button className="primary-button" type="button" onClick={() => onOpenWorkspace(selected.id)}>Open workspace<ArrowRight size={17} /></button>}
            </div>
          </section>
        </div>
      ) : (
        <div className="empty-state"><Database size={26} /><strong>No clients yet</strong><span>Create the first fail-closed workspace to begin.</span><button className="primary-button" type="button" onClick={onNewClient}>Create client</button></div>
      )}
    </div>
  );
}

export function Onboarding({ requestedClientId, onSelectWorkspace, onOpenWorkspace }) {
  const [requests, setRequests] = useState([]);
  const [clients, setClients] = useState([]);
  const [selectedClientId, setSelectedClientId] = useState("");
  const [activeRequest, setActiveRequest] = useState(null);
  const [screen, setScreen] = useState("manage");
  const [step, setStep] = useState(1);
  const [form, setForm] = useState(defaultForm);
  const [blogs, setBlogs] = useState([]);
  const [shop, setShop] = useState(null);
  const [selectedBlog, setSelectedBlog] = useState("");
  const [productText, setProductText] = useState("");
  const [busy, setBusy] = useState("");
  const [managementLoading, setManagementLoading] = useState(false);
  const [lastRefreshed, setLastRefreshed] = useState("");
  const [message, setMessage] = useState({ tone: "", text: "" });
  const oauthCallbackHandled = useRef(false);

  const refreshRequests = async (preferredId) => {
    setManagementLoading(true);
    const result = await loadClientManagementData();
    setManagementLoading(false);
    if (result.error) {
      setMessage({ tone: "error", text: result.error.message });
      return { ok: false, error: result.error, match: null };
    }
    const nextRequests = result.data?.requests ?? [];
    const nextClients = result.data?.clients ?? [];
    setRequests(nextRequests);
    setClients(nextClients);
    setLastRefreshed(new Date().toISOString());
    setSelectedClientId((current) => preferredId && nextClients.some((client) => client.id === preferredId)
      ? preferredId
      : nextClients.some((client) => client.id === current) ? current : nextClients[0]?.id ?? "");
    const match = nextRequests.find((item) => item.request_id === preferredId);
    if (match) setActiveRequest(match);
    return { ok: true, error: null, match: match ?? null };
  };

  useEffect(() => { refreshRequests(requestedClientId); }, [requestedClientId]);

  useEffect(() => {
    if (oauthCallbackHandled.current || requests.length === 0) return;
    const params = new URLSearchParams(window.location.search);
    const oauthStatus = params.get("shopify");
    const requestId = params.get("request_id");
    if (!oauthStatus || !requestId) return;
    const request = requests.find((item) => item.request_id === requestId);
    if (!request) return;
    oauthCallbackHandled.current = true;
    openRequest(request, false);
    setMessage(oauthStatus === "connected"
      ? {
          tone: "success",
          text: request.status === "oauth_connected"
            ? "Shopify connected securely. Choose the blog ORIN should use."
            : "Shopify connected securely. Store, blog, products, and collections were discovered automatically.",
        }
      : { tone: "error", text: "Shopify connection was not completed. Try Connect Shopify again." });
    params.delete("shopify");
    params.delete("request_id");
    const query = params.toString();
    window.history.replaceState({}, "", `${window.location.pathname}${query ? `?${query}` : ""}${window.location.hash}`);
  }, [requests]);

  const selectManagedClient = (clientId) => {
    setSelectedClientId(clientId);
    onSelectWorkspace?.(clientId);
  };

  const refreshManagement = async () => {
    const result = await refreshRequests(selectedClientId);
    if (result.ok) setMessage({ tone: "success", text: "Client activity and operational gates refreshed." });
  };

  const categories = useMemo(
    () => form.categories.split(/[,\n]/).map((item) => item.trim()).filter(Boolean),
    [form.categories],
  );
  const productScope = useMemo(() => productScopeFromText(productText), [productText]);
  const checklist = onboardingSafetyChecklist(activeRequest);

  const updateForm = (field, value) => {
    setForm((current) => {
      const next = { ...current, [field]: value };
      if (field === "displayName" && (!current.clientId || current.clientId === clientIdFromName(current.displayName))) {
        next.clientId = clientIdFromName(value);
      }
      return next;
    });
  };

  const startNew = () => {
    setActiveRequest(null);
    setForm(defaultForm);
    setBlogs([]);
    setShop(null);
    setSelectedBlog("");
    setProductText("");
    setMessage({ tone: "", text: "" });
    setStep(1);
    setScreen("wizard");
  };

  function openRequest(request, clearMessage = true) {
    const discovery = request.shopify_discovery ?? {};
    const savedScope = request.product_scope ?? [];
    const suggestedScope = savedScope.length > 0 ? savedScope : discoveredProductScope(request);
    setActiveRequest(request);
    setForm({
      displayName: request.display_name,
      clientId: request.client_id,
      ownerEmail: request.owner_email,
      storeDomain: request.shopify_store_domain,
      marketCountry: request.market_country,
      timezone: request.timezone,
      brandVoice: request.brand_voice,
      categories: request.content_categories.join(", "),
    });
    setBlogs(discovery.blogs ?? []);
    setShop(discovery.shop ?? null);
    setSelectedBlog(request.shopify_blog_gid ?? discovery.blogs?.[0]?.id ?? "");
    setProductText(suggestedScope.map((item) => item.name ?? String(item)).join("\n"));
    if (clearMessage) setMessage({ tone: "", text: "" });
    setStep(onboardingStepForRequest(request));
    setScreen("wizard");
  }

  const resume = (request) => openRequest(request);

  const saveBusiness = async (event) => {
    event.preventDefault();
    const storeDomain = normalizeShopifyDomain(form.storeDomain);
    if (!storeDomain || categories.length === 0) {
      setMessage({ tone: "error", text: "Use the permanent .myshopify.com domain and add at least one content category." });
      return;
    }
    setBusy("business");
    setMessage({ tone: "", text: "" });
    const result = await createOnboardingRequest({ ...form, storeDomain, contentCategories: categories });
    setBusy("");
    if (result.error) {
      setMessage({ tone: "error", text: result.error.message });
      return;
    }
    const refresh = await refreshRequests(result.data.request_id);
    const request = refresh.match;
    setActiveRequest(request ?? { ...result.data, ...form, shopify_store_domain: storeDomain });
    setStep(2);
    setMessage({ tone: "success", text: "Business profile saved. No execution gates were opened." });
  };

  const connectShopify = async () => {
    setBusy("shopify-oauth");
    setMessage({ tone: "", text: "" });
    const returnUrl = new URL("/onboarding", window.location.origin);
    returnUrl.searchParams.set("client", activeRequest.client_id);
    const result = await beginOnboardingShopifyOAuth(
      activeRequest.request_id,
      activeRequest.shopify_store_domain,
      returnUrl.toString(),
    );
    setBusy("");
    if (result.error) {
      setMessage({ tone: "error", text: result.error.message });
      return;
    }
    if (!result.data?.authorization_url) {
      setMessage({ tone: "error", text: "Shopify did not return a secure connection URL." });
      return;
    }
    window.location.assign(result.data.authorization_url);
  };

  const chooseShopifyBlog = async () => {
    setBusy("shopify-blog");
    setMessage({ tone: "", text: "" });
    const result = await selectOnboardingShopifyBlog(activeRequest.request_id, selectedBlog);
    setBusy("");
    if (result.error) {
      setMessage({ tone: "error", text: result.error.message });
      return;
    }
    const refresh = await refreshRequests(activeRequest.request_id);
    const request = refresh.match;
    const connectedRequest = request ?? {
      ...activeRequest,
      credential_status: "stored",
      status: "connection_verified",
      shopify_blog_gid: selectedBlog,
      shopify_blog_title: blogs.find((blog) => blog.id === selectedBlog)?.title ?? "Shopify blog",
    };
    openRequest(connectedRequest, false);
    setStep(3);
    setMessage({ tone: "success", text: "Shopify blog selected. The encrypted connection and discovered catalogue are ready." });
  };

  const saveScope = async () => {
    setBusy("scope");
    setMessage({ tone: "", text: "" });
    const result = await updateOnboardingScope(activeRequest.request_id, productScope);
    setBusy("");
    if (result.error) {
      setMessage({ tone: "error", text: result.error.message });
      return;
    }
    const refresh = await refreshRequests(activeRequest.request_id);
    const request = refresh.match;
    setActiveRequest(request ?? { ...activeRequest, status: "ready_to_provision", product_scope: productScope });
    setStep(4);
    setMessage({ tone: "success", text: "Content scope saved. The isolated workspace is ready to be created safely." });
  };

  const provision = async () => {
    setBusy("provision");
    setMessage({ tone: "", text: "" });
    const result = await provisionOnboardingClient(activeRequest.request_id);
    setBusy("");
    if (result.error) {
      setMessage({ tone: "error", text: result.error.message });
      return;
    }
    const refresh = await refreshRequests(activeRequest.request_id);
    const request = refresh.match;
    setActiveRequest(request ?? { ...activeRequest, ...result.data });
    setMessage({ tone: "success", text: "Isolated client workspace created with every execution and Shopify gate closed." });
  };

  const auditClient = async () => {
    setBusy("audit");
    setMessage({ tone: "", text: "" });
    const result = await auditProvisionedClient(activeRequest.client_id);
    setBusy("");
    if (result.error) {
      setMessage({ tone: "error", text: result.error.message });
      return;
    }
    const refresh = await refreshRequests(activeRequest.request_id);
    const request = refresh.match;
    setActiveRequest(request ?? { ...activeRequest, commissioning_status: "identity_verified" });
    setMessage({
      tone: "success",
      text: `Read-only identity verified: ${result.data.store_domain} · ${result.data.blog_title} · ${result.data.product_count} products. No Shopify write was attempted.`,
    });
  };

  const commissionClient = async (clientId) => {
    setBusy(`commission:${clientId}`);
    setMessage({ tone: "", text: "" });
    const retry = clients.find((client) => client.id === clientId)?.commissioningRequest?.status === "failed";
    const result = await requestClientCommissioning(clientId, { retry });
    setBusy("");
    if (result.error) {
      setMessage({ tone: "error", text: result.error.message });
      return;
    }
    await refreshRequests(clientId);
    setActiveRequest((current) => current?.client_id === clientId
      ? { ...current, commissioning_status: "worker_pending" }
      : current);
    setMessage({
      tone: "success",
      text: result.data?.replayed
        ? "The existing safe commissioning request is still active. No duplicate was created."
        : "Safe commissioning requested. Every Shopify and execution gate remains closed until its proofs pass.",
    });
  };

  const startRecurringPilot = async (clientId) => {
    setBusy(`recurring:${clientId}`);
    setMessage({ tone: "", text: "" });
    const result = await requestClientRecurringPilot(clientId);
    setBusy("");
    if (result.error) {
      setMessage({ tone: "error", text: result.error.message });
      return;
    }
    await refreshRequests(clientId);
    setMessage({
      tone: "success",
      text: result.data?.replayed
        ? "Recurring dry-runs were already activated. No duplicate schedule was created."
        : "Recurring dry-runs activated. The first automatic proof is due within a few minutes; Shopify publishing remains unavailable.",
    });
  };

  if (screen === "manage") {
    return (
      <ClientManagement
        clients={clients}
        selectedClientId={selectedClientId}
        onSelect={selectManagedClient}
        onNewClient={startNew}
        onContinue={resume}
        onOpenWorkspace={onOpenWorkspace}
        onRefresh={refreshManagement}
        onRequestCommissioning={commissionClient}
        onStartRecurringPilot={startRecurringPilot}
        commissioningBusy={busy.startsWith("commission:") ? busy.slice("commission:".length) : ""}
        recurringPilotBusy={busy.startsWith("recurring:") ? busy.slice("recurring:".length) : ""}
        refreshing={managementLoading}
        lastRefreshed={lastRefreshed}
        message={message}
      />
    );
  }

  return (
    <div className="onboarding-page">
      <div className="page-heading onboarding-heading">
        <div>
          <span className="eyebrow">PLATFORM OPERATIONS</span>
          <h1>Client onboarding</h1>
          <p>Add a client without using SSH. ORIN verifies the store, encrypts credentials, and creates a fail-closed tenant.</p>
        </div>
        <button className="secondary-button" type="button" onClick={() => setScreen("manage")}><ArrowLeft size={17} /> Client operations</button>
      </div>

      {message.text && (
        <div className={`onboarding-message ${message.tone}`} role="status">
          {message.tone === "error" ? <WarningCircle size={20} /> : <CheckCircle size={20} weight="fill" />}
          <span>{message.text}</span>
        </div>
      )}

      <OnboardingProgress step={step} />

      <div className="onboarding-layout">
        <section className="onboarding-card">
          {step === 1 && (
            <form onSubmit={saveBusiness}>
              <div className="onboarding-section-heading"><span><UserPlus size={20} weight="duotone" /></span><div><h2>Business and workspace</h2><p>These details define the isolated client boundary and first content plan.</p></div></div>
              <div className="onboarding-form-grid">
                <Field label="Business name"><input required value={form.displayName} onChange={(event) => updateForm("displayName", event.target.value)} placeholder="Example Store" /></Field>
                <Field label="Client ID" hint="Lowercase database identifier; cannot be changed later."><input required pattern="[a-z0-9][a-z0-9_]{1,62}" value={form.clientId} onChange={(event) => updateForm("clientId", event.target.value.toLowerCase())} placeholder="example_store" /></Field>
                <Field label="Client owner email"><input required type="email" value={form.ownerEmail} onChange={(event) => updateForm("ownerEmail", event.target.value)} placeholder="owner@example.com" /></Field>
                <Field label="Shopify store domain" hint="Use the permanent domain, not the storefront URL."><input required value={form.storeDomain} onChange={(event) => updateForm("storeDomain", event.target.value)} placeholder="example-store.myshopify.com" /></Field>
                <Field label="Primary market"><select value={form.marketCountry} onChange={(event) => updateForm("marketCountry", event.target.value)}><option value="GB">United Kingdom</option><option value="US">United States</option><option value="CA">Canada</option><option value="AU">Australia</option><option value="IE">Ireland</option></select></Field>
                <Field label="Timezone"><select value={form.timezone} onChange={(event) => updateForm("timezone", event.target.value)}><option>Europe/London</option><option>Europe/Dublin</option><option>America/New_York</option><option>America/Los_Angeles</option><option>Australia/Sydney</option></select></Field>
                <Field label="Brand voice"><textarea value={form.brandVoice} onChange={(event) => updateForm("brandVoice", event.target.value)} /></Field>
                <Field label="Content categories" hint="Comma-separated; these become planning guardrails."><textarea required value={form.categories} onChange={(event) => updateForm("categories", event.target.value)} /></Field>
              </div>
              <div className="onboarding-actions"><span><LockKey size={17} /> No scheduler or Shopify write access is created here.</span><button className="primary-button" type="submit" disabled={busy === "business"}>{busy === "business" ? "Saving…" : "Save and connect Shopify"}<ArrowRight size={17} /></button></div>
            </form>
          )}

          {step === 2 && (
            <div>
              <div className="onboarding-section-heading"><span><Key size={20} weight="duotone" /></span><div><h2>Connect Shopify</h2><p>Sign in to Shopify and approve ORIN. No API token, code, or terminal is required.</p></div></div>
              <div className="connection-summary"><Storefront size={22} /><div><strong>{shop?.name ?? activeRequest.display_name ?? form.displayName}</strong><span>{activeRequest.shopify_store_domain}</span></div><span className={`status-pill ${activeRequest.status === "oauth_connected" ? "green" : "neutral"}`}>{activeRequest.status === "oauth_connected" ? "Connected" : "Not connected"}</span></div>
              {activeRequest.status === "oauth_connected" ? (
                <div className="onboarding-stack">
                  <div className="oauth-success-panel"><CloudCheck size={25} weight="duotone" /><div><strong>Store connected securely</strong><span>ORIN discovered {activeRequest.shopify_discovery?.productCount ?? 0} products, {activeRequest.shopify_discovery?.collections?.length ?? 0} collections, and {blogs.length} blogs. Shopify writes remain disabled.</span></div></div>
                  <Field label="Choose the blog ORIN should use" hint="Only unpublished, approved drafts can be sent later, after separate commissioning."><select value={selectedBlog} onChange={(event) => setSelectedBlog(event.target.value)}>{blogs.map((blog) => <option key={blog.id} value={blog.id}>{blog.title} ({blog.handle})</option>)}</select></Field>
                </div>
              ) : (
                <div className="oauth-connect-panel">
                  <div><ShieldCheck size={27} weight="duotone" /><span><strong>Safe one-click connection</strong>ORIN requests product reading and blog-draft access, verifies the permanent store identity, encrypts the credential, and discovers the catalogue automatically.</span></div>
                  <ul><li><CheckCircle size={17} weight="fill" /> No password or API key is entered here</li><li><CheckCircle size={17} weight="fill" /> No product or article is changed during setup</li><li><CheckCircle size={17} weight="fill" /> Publishing remains unavailable</li></ul>
                </div>
              )}
              <div className="onboarding-actions"><button className="text-button" type="button" onClick={() => setStep(1)}><ArrowLeft size={16} /> Back</button>{activeRequest.status === "oauth_connected" ? <button className="primary-button" type="button" onClick={chooseShopifyBlog} disabled={!selectedBlog || busy === "shopify-blog"}>{busy === "shopify-blog" ? "Saving…" : "Use this blog"}<ArrowRight size={17} /></button> : <button className="primary-button" type="button" onClick={connectShopify} disabled={busy === "shopify-oauth"}>{busy === "shopify-oauth" ? "Opening Shopify…" : "Connect Shopify"}<ArrowRight size={17} /></button>}</div>
            </div>
          )}

          {step === 3 && (
            <div>
              <div className="onboarding-section-heading"><span><Storefront size={20} weight="duotone" /></span><div><h2>Content and product scope</h2><p>Tell ORIN what it may research. This does not yet generate or publish content.</p></div></div>
              <div className="verified-strip"><ShieldCheck size={21} weight="duotone" /><div><strong>Encrypted Shopify connection ready</strong><span>{activeRequest.shopify_blog_title} · {activeRequest.shopify_store_domain}</span></div></div>
              {activeRequest.shopify_discovery?.observedAt && <div className="discovery-summary"><span><strong>{activeRequest.shopify_discovery.productCount ?? 0}</strong> products found</span><span><strong>{activeRequest.shopify_discovery.collections?.length ?? 0}</strong> collections found</span><span><strong>{activeRequest.shopify_discovery.blogs?.length ?? 0}</strong> blogs found</span></div>}
              <Field label="Products, collections, or services" hint="One per line. Leave blank if ORIN should discover the catalogue during the read-only audit."><textarea className="scope-textarea" value={productText} onChange={(event) => setProductText(event.target.value)} placeholder={"Kids scooters\nHoverboards\nSafety accessories"} /></Field>
              <div className="scope-preview"><strong>Planning guardrails</strong><div>{form.categories.split(",").map((item) => item.trim()).filter(Boolean).map((item) => <span key={item}>{item}</span>)}</div><small>{productScope.length === 0 ? "Catalogue discovery will be read-only." : `${productScope.length} product scope item${productScope.length === 1 ? "" : "s"} selected.`}</small></div>
              <div className="onboarding-actions"><button className="text-button" type="button" onClick={() => setStep(2)}><ArrowLeft size={16} /> Back</button><button className="primary-button" type="button" onClick={saveScope} disabled={busy === "scope"}>{busy === "scope" ? "Saving…" : "Review safe setup"}<ArrowRight size={17} /></button></div>
            </div>
          )}

          {step === 4 && (
            <div>
              <div className="onboarding-section-heading"><span><Database size={20} weight="duotone" /></span><div><h2>{activeRequest.status === "database_provisioned" ? "Workspace safely provisioned" : "Create the isolated workspace"}</h2><p>The database tenant starts in maintenance. Commissioning remains a separate controlled process.</p></div></div>
              <div className="provision-summary"><div><span>Client</span><strong>{activeRequest.display_name}</strong></div><div><span>Workspace ID</span><strong>{activeRequest.client_id}</strong></div><div><span>Shopify blog</span><strong>{activeRequest.shopify_blog_title}</strong></div><div><span>Initial mode</span><strong>Maintenance · dry-run</strong></div></div>
              <ul className="safety-checklist">{checklist.map((item) => <li key={item.label} className={item.complete ? "complete" : "pending"}>{item.complete ? <CheckCircle size={19} weight="fill" /> : <span className="check-placeholder" />}<span>{item.label}</span></li>)}</ul>
              {activeRequest.status !== "database_provisioned" ? <div className="onboarding-actions"><button className="text-button" type="button" onClick={() => setStep(3)}><ArrowLeft size={16} /> Back</button><button className="primary-button" type="button" onClick={provision} disabled={busy === "provision"}><ShieldCheck size={18} weight="fill" />{busy === "provision" ? "Provisioning…" : "Create safely disabled workspace"}</button></div> : <><div className={`commissioning-next ${["identity_verified", "worker_pending", "dry_run_pending", "pilot_pending", "ready"].includes(activeRequest.commissioning_status) ? "verified" : ""}`}>{["identity_verified", "worker_pending", "dry_run_pending", "pilot_pending", "ready"].includes(activeRequest.commissioning_status) ? <CheckCircle size={21} weight="fill" /> : <WarningCircle size={21} weight="duotone" />}<div><strong>{activeRequest.commissioning_status === "identity_verified" ? "Read-only identity verified" : activeRequest.commissioning_status === "worker_pending" ? "Safe commissioning queued" : activeRequest.commissioning_status === "pilot_pending" ? "Pilot draft ready" : "Not production-ready yet"}</strong><span>{activeRequest.commissioning_status === "identity_verified" ? "The exact Shopify store, target blog, and product-read access passed. Start commissioning without using SSH or opening write gates." : activeRequest.commissioning_status === "worker_pending" ? "A trusted worker will run the isolated dry-run, schedule, and watchdog proofs. No Shopify write gate is open." : activeRequest.commissioning_status === "pilot_pending" ? "Review the version-bound pilot draft. Approval-only Shopify setup remains a separate controlled step; both Shopify write gates are closed." : "Run the server-side read-only identity audit next. It can inspect the store and product count, but cannot create, edit, or publish Shopify content."}</span></div></div>{clients.find((client) => client.id === activeRequest.client_id)?.commissioningRequest && <CommissioningProgress request={clients.find((client) => client.id === activeRequest.client_id).commissioningRequest} />}<div className="onboarding-actions"><span><ShieldCheck size={17} /> Every execution and Shopify gate remains closed.</span><div>{!["identity_verified", "worker_pending", "dry_run_pending", "pilot_pending", "ready"].includes(activeRequest.commissioning_status) && <button className="primary-button" type="button" onClick={auditClient} disabled={busy === "audit"}>{busy === "audit" ? "Checking…" : "Run read-only identity audit"}</button>}{activeRequest.commissioning_status === "identity_verified" && <button className="primary-button" type="button" onClick={() => commissionClient(activeRequest.client_id)} disabled={busy === `commission:${activeRequest.client_id}`}>{busy === `commission:${activeRequest.client_id}` ? "Requesting…" : "Start safe commissioning"}</button>}<button className="secondary-button" type="button" onClick={() => onOpenWorkspace(activeRequest.client_id)}>Open {activeRequest.display_name}</button></div></div></>}
            </div>
          )}
        </section>

        <aside className="onboarding-history">
          <div className="section-heading"><div><span className="section-kicker">DURABLE INTAKE</span><h2>Client setups</h2></div><span className="status-pill green">{requests.length}</span></div>
          {requests.length === 0 ? <div className="history-empty"><Database size={24} /><span>No onboarding records yet.</span></div> : <div className="history-list">{requests.map((request) => <button type="button" key={request.request_id} className={activeRequest?.request_id === request.request_id ? "active" : ""} onClick={() => resume(request)}><span className="history-mark">{request.display_name.slice(0, 1).toUpperCase()}</span><span><strong>{request.display_name}</strong><small>{statusLabel(request.status)}</small></span><ArrowRight size={16} /></button>)}</div>}
          <div className="vault-note"><LockKey size={21} weight="duotone" /><span><strong>Credentials stay server-side</strong>Shopify tokens are encrypted in Supabase Vault. This page can never read one back.</span></div>
        </aside>
      </div>
    </div>
  );
}
