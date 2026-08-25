import { useEffect, useMemo, useState } from "react";
import {
  ArrowLeft,
  ArrowRight,
  Article,
  Bell,
  CaretDown,
  Check,
  CheckCircle,
  Clock,
  CloudCheck,
  Eye,
  FileText,
  Gauge,
  House,
  Info,
  ListChecks,
  MagnifyingGlass,
  NotePencil,
  PaperPlaneTilt,
  Robot,
  ShieldCheck,
  SignOut,
  Sparkle,
  Storefront,
  UserPlus,
  WarningCircle,
  X,
} from "@phosphor-icons/react";
import {
  loadDashboardData,
  loadOnboardingAccess,
  loadReviewItem,
  recordContentDecision,
  refreshApprovedDraftConnection,
  sendMagicLink,
  signOutDashboard,
  subscribeToAuthChanges,
} from "./lib/dashboardClient.js";
import {
  isReviewableQueueItem,
  nextPlannedJobId,
  reviewJobIdFromPath,
  selectRouteBoundReviewArticle,
} from "./reviewArticle.js";
import { approvalAvailability } from "./operationalState.js";
import { Onboarding } from "./Onboarding.jsx";
import {
  reviewPresentationForClient,
  validateArticleHtmlForClient,
} from "./clientPresentation.js";
import hcsArticleCss from "../../../clients/hcs_gadgets/shopify_theme/hcs-article.css?inline";

const BASE_DRAFT_PREVIEW_CSS = `
  html { background: #f4f6f7; }
  body { margin: 0; padding: 28px; color: #283a46; font: 16px/1.7 Georgia, serif; }
  h1, h2, h3 { color: #172a37; line-height: 1.25; }
  a { color: #0b7f68; }
  img { max-width: 100%; height: auto; }
  script { display: none; }
  @media (max-width: 720px) { body { padding: 12px; } }
`;

function readPath(path = window.location.pathname) {
  if (path.startsWith("/onboarding")) return "onboarding";
  if (path.startsWith("/review/")) return "review";
  if (path.startsWith("/queue")) return "queue";
  return "overview";
}

function useRoute() {
  const [location, setLocation] = useState(() => `${window.location.pathname}${window.location.search}`);
  const path = location.split("?")[0];
  const route = readPath(path);

  useEffect(() => {
    const onPopState = () => setLocation(`${window.location.pathname}${window.location.search}`);
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, []);

  const navigate = (path) => {
    const currentClient = new URLSearchParams(window.location.search).get("client");
    const destination = currentClient && !path.includes("?")
      ? `${path}?client=${encodeURIComponent(currentClient)}`
      : path;
    window.history.pushState({}, "", destination);
    setLocation(`${window.location.pathname}${window.location.search}`);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  return { route, path, navigate, location };
}

function dashboardHeading(value) {
  const moment = value ? new Date(value) : new Date();
  const safeMoment = Number.isNaN(moment.getTime()) ? new Date() : moment;
  const date = new Intl.DateTimeFormat("en-GB", {
    weekday: "long",
    day: "numeric",
    month: "long",
    timeZone: "Europe/London",
  }).format(safeMoment);
  const hour = Number(new Intl.DateTimeFormat("en-GB", {
    hour: "2-digit",
    hourCycle: "h23",
    timeZone: "Europe/London",
  }).format(safeMoment));
  return {
    date,
    greeting: hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening",
  };
}

function Brand() {
  return (
    <div className="brand-lockup" aria-label="ORIN">
      <span className="brand-mark"><Sparkle size={18} weight="fill" /></span>
      <span className="brand-name">ORIN</span>
      <span className="brand-product">Commerce</span>
    </div>
  );
}

function StoreBadge({ client, workspaces = [], onChange, compact = false }) {
  const hasChoices = workspaces.length > 1 && !compact;
  return (
    <div className={`store-badge ${compact ? "compact" : ""} ${hasChoices ? "switchable" : ""}`}>
      <span className="store-icon"><Storefront size={18} weight="duotone" /></span>
      {!compact && (
        <span className="store-copy">
          <strong>{client.name}</strong>
          <small>{client.plan ?? "Client workspace"}</small>
        </span>
      )}
      {hasChoices && (
        <>
          <CaretDown size={14} weight="bold" />
          <select aria-label="Switch client workspace" value={client.id} onChange={(event) => onChange(event.target.value)}>
            {workspaces.map((workspace) => <option key={workspace.id} value={workspace.id}>{workspace.name}</option>)}
          </select>
        </>
      )}
    </div>
  );
}

function AppShell({ route, navigate, children, dataSource, operations, queueCount, onSignOut, operatorAccess, client, workspaces, onWorkspaceChange }) {
  const navItems = [
    { id: "overview", label: "Overview", icon: House, path: "/" },
    { id: "queue", label: "Content queue", icon: ListChecks, path: "/queue" },
    ...(operatorAccess ? [{ id: "onboarding", label: "Clients", icon: UserPlus, path: "/onboarding" }] : []),
  ];
  const liveSource = dataSource === "supabase";
  const environmentLabel = liveSource || operations.isPaused ? operations.workspaceLabel : "Safe preview";
  const environmentTone = liveSource || operations.isPaused ? operations.overallTone : "preview";

  return (
    <div className="app-shell">
      <aside className="side-nav">
        <div className="side-nav-top">
          <Brand />
          <StoreBadge client={client} workspaces={workspaces} onChange={onWorkspaceChange} />
          <nav aria-label="Primary navigation">
            {navItems.map((item) => {
              const Icon = item.icon;
              const active = route === item.id || (route === "review" && item.id === "queue");
              return (
                <button
                  key={item.id}
                  type="button"
                  className={`nav-item ${active ? "active" : ""}`}
                  onClick={() => navigate(item.path)}
                >
                  <Icon size={19} weight={active ? "fill" : "regular"} />
                  <span>{item.label}</span>
                  {item.id === "queue" && <span className="nav-count">{queueCount}</span>}
                </button>
              );
            })}
          </nav>
        </div>
        <div className="side-nav-bottom">
          <div className="safety-note">
            <ShieldCheck size={22} weight="duotone" />
            <div>
              <strong>Approval required</strong>
              <span>ORIN never publishes by itself.</span>
            </div>
          </div>
          <button className="nav-item subtle" type="button" onClick={onSignOut}>
            <SignOut size={18} />
            <span>Sign out</span>
          </button>
        </div>
      </aside>

      <div className="main-frame">
        <header className="topbar">
          <div className="mobile-brand"><Brand /></div>
          <div className="environment-pill">
            <span className={`live-dot ${environmentTone}`} />
            {environmentLabel}
          </div>
          <div className="topbar-actions">
            <button className="icon-button" type="button" aria-label="Search"><MagnifyingGlass size={20} /></button>
            <button className="icon-button notification" type="button" aria-label="Notifications">
              <Bell size={20} />
              <span />
            </button>
            <StoreBadge client={client} compact />
          </div>
        </header>
        <main className="page-content">
          {operations.isPaused && (
            <div className={`maintenance-banner ${operations.overallTone}`} role="status">
              <WarningCircle size={21} weight="duotone" />
              <div><strong>{operations.workspaceLabel}</strong><span>{operations.workspaceMessage}</span></div>
            </div>
          )}
          {children}
        </main>
        <nav className="mobile-nav" aria-label="Mobile navigation">
          {navItems.map((item) => {
            const Icon = item.icon;
            const active = route === item.id || (route === "review" && item.id === "queue");
            return (
              <button key={item.id} type="button" className={active ? "active" : ""} onClick={() => navigate(item.path)}>
                <Icon size={20} weight={active ? "fill" : "regular"} />
                {item.label}
              </button>
            );
          })}
        </nav>
      </div>
    </div>
  );
}

function AuthScreen() {
  const [email, setEmail] = useState("");
  const [state, setState] = useState({ status: "idle", message: "" });

  const submit = async (event) => {
    event.preventDefault();
    if (!email.trim()) return;
    setState({ status: "sending", message: "" });
    const { error } = await sendMagicLink(email.trim());
    if (error) {
      setState({ status: "error", message: error.message });
      return;
    }
    setState({
      status: "sent",
      message: "Check your inbox and open the secure sign-in link on this device.",
    });
  };

  return (
    <main className="auth-screen">
      <section className="auth-card">
        <Brand />
        <span className="auth-kicker"><ShieldCheck size={17} weight="duotone" /> Private client workspace</span>
        <h1>Sign in to ORIN Commerce</h1>
        <p>Use the email connected to your client workspace. We’ll send a one-time secure link—no password needed.</p>
        <form onSubmit={submit}>
          <label htmlFor="signin-email">Work email</label>
          <input
            id="signin-email"
            type="email"
            autoComplete="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            placeholder="you@company.com"
            required
          />
          <button className="primary-button" type="submit" disabled={state.status === "sending" || state.status === "sent"}>
            {state.status === "sending" ? "Sending link…" : state.status === "sent" ? "Link sent" : "Send secure sign-in link"}
          </button>
        </form>
        {state.message && <div className={`auth-message ${state.status}`} role="status">{state.message}</div>}
        <div className="auth-safeguard"><ShieldCheck size={20} weight="duotone" /><span><strong>Protected by tenant isolation</strong>Your account can only read its assigned client workspace.</span></div>
      </section>
    </main>
  );
}

function ErrorScreen({ message, onRetry }) {
  return (
    <main className="auth-screen">
      <section className="auth-card">
        <Brand />
        <span className="auth-kicker attention"><WarningCircle size={17} /> Workspace unavailable</span>
        <h1>We couldn’t open your workspace</h1>
        <p>{message}</p>
        <button className="primary-button" type="button" onClick={onRetry}>Try again</button>
        <button className="secondary-button" type="button" onClick={signOutDashboard}>Sign out</button>
      </section>
    </main>
  );
}

function PageHeading({ eyebrow, title, description, action }) {
  return (
    <div className="page-heading">
      <div>
        {eyebrow && <span className="eyebrow">{eyebrow}</span>}
        <h1>{title}</h1>
        {description && <p>{description}</p>}
      </div>
      {action}
    </div>
  );
}

function StatusPill({ children, tone = "neutral" }) {
  return <span className={`status-pill ${tone}`}>{children}</span>;
}

function MetricCard({ label, value, tone, icon: Icon }) {
  return (
    <article className={`metric-card ${tone}`}>
      <span className="metric-icon"><Icon size={18} weight="duotone" /></span>
      <div><span>{label}</span><strong>{value}</strong></div>
    </article>
  );
}

function Overview({ data, navigate }) {
  const paused = data.operations.isPaused;
  const heading = dashboardHeading(data.generatedAt);
  return (
    <div className="overview-page">
      <PageHeading
        eyebrow={heading.date}
        title={`${heading.greeting}, Hari.`}
        description={paused ? data.operations.workspaceMessage : "Your content system is healthy. One article is ready for your review."}
        action={<button className="secondary-button" type="button" onClick={() => navigate("/queue")}><ListChecks size={17} /> View queue</button>}
      />

      <section className="overview-grid">
        {data.nextArticle ? <article className="next-article-card">
          <div className="card-heading-row">
            <div>
              <span className="section-kicker">NEXT ARTICLE</span>
              <h2>{data.nextArticle.title}</h2>
            </div>
            <StatusPill tone="orange">{data.nextArticle.status}</StatusPill>
          </div>

          <div className="article-facts">
            <div><span>Target keyword</span><strong>{data.nextArticle.keyword}</strong></div>
            <div><span>Intent</span><strong>{data.nextArticle.intent}</strong></div>
            <div><span>Quality</span><strong>{data.nextArticle.qualityScore == null ? "Pending draft" : `${data.nextArticle.qualityScore}/100`}</strong></div>
          </div>

          <div className="check-strip">
            {data.nextArticle.checks.map((check) => (
              <span key={check}><CheckCircle size={17} weight="fill" />{check}</span>
            ))}
          </div>

          <div className="card-actions">
            <button className="primary-button" type="button" onClick={() => navigate(`/review/${data.nextArticle.id}`)}>
              Review article <ArrowRight size={17} weight="bold" />
            </button>
            <span><Clock size={16} /> {data.nextArticle.readingTime}</span>
          </div>
        </article> : <article className="next-article-card empty-workspace-card">
          <div>
            <span className="section-kicker">SAFE WORKSPACE</span>
            <h2>No content plan has been commissioned yet</h2>
            <p>This client is visible and isolated. ORIN will add its first concepts only after the read-only audit and dry-run checks pass.</p>
          </div>
          <ShieldCheck size={42} weight="duotone" />
        </article>}

        <article className="operations-card">
          <div className="card-heading-row compact">
            <div>
              <span className="section-kicker">OPERATIONS</span>
              <h2>System status</h2>
            </div>
            <span className={`health-ring ${data.operations.overallTone}`}>{paused ? <Clock size={17} weight="bold" /> : <Check size={17} weight="bold" />}</span>
          </div>
          <div className="operations-list">
            <div><span className="operation-copy"><span><Clock size={18} /> Daily schedule</span><small>{data.operations.schedulerDetail}</small></span><StatusPill tone={data.operations.schedulerTone}>{data.operations.scheduler}</StatusPill></div>
            <div><span className="operation-copy"><span><Robot size={18} /> Content worker</span><small>{data.operations.workerDetail}</small></span><StatusPill tone={data.operations.workerTone}>{data.operations.worker}</StatusPill></div>
            <div><span className="operation-copy"><span><Gauge size={18} /> Watchdog</span><small>{data.operations.watchdogDetail}</small></span><StatusPill tone={data.operations.watchdogTone}>{data.operations.watchdog}</StatusPill></div>
            <div><span className="operation-copy"><span><ShieldCheck size={18} /> Shopify draft access</span><small>{data.operations.shopifyDetail}</small></span><StatusPill tone={data.operations.shopifyTone}>{data.operations.shopifyWrites}</StatusPill></div>
          </div>
          <div className={`operations-footer ${data.operations.overallTone}`}>
            {paused ? <ShieldCheck size={19} weight="duotone" /> : <CloudCheck size={19} weight="duotone" />}
            <span><strong>{data.operations.overallLabel}</strong>{data.operations.lastChecked}</span>
          </div>
        </article>
      </section>

      <section className="metric-grid" aria-label="Content totals">
        <MetricCard label="Planned" value={data.counts.planned} tone="slate" icon={Article} />
        <MetricCard label="Drafting" value={data.counts.drafting} tone="blue" icon={NotePencil} />
        <MetricCard label="Needs review" value={data.counts.review} tone="orange" icon={Eye} />
        <MetricCard label="Approved" value={data.counts.approved} tone="green" icon={CheckCircle} />
      </section>

      <section className="recent-card">
        <div className="section-heading">
          <div><span className="section-kicker">RECENT CONTENT</span><h2>Latest work</h2></div>
          <button className="text-button" type="button" onClick={() => navigate("/queue")}>See all <ArrowRight size={15} /></button>
        </div>
        <div className="recent-table">
          {data.recentContent.map((item) => (
            <button className="recent-row" type="button" key={item.id} onClick={() => item.id === 32 && navigate("/review/32")}>
              <span className="document-icon"><FileText size={19} weight="duotone" /></span>
              <span className="recent-title"><strong>{item.title}</strong><small>Job {item.id} · {item.owner}</small></span>
              <StatusPill tone={item.stage === "Approved" ? "green" : "blue"}>{item.stage}</StatusPill>
              <span className="recent-time">{item.updated}</span>
              <ArrowRight size={16} />
            </button>
          ))}
        </div>
      </section>
    </div>
  );
}

const stages = ["Planned", "Research", "Drafting", "Review", "Approved"];

function Queue({ data, navigate }) {
  const [activeFilter, setActiveFilter] = useState("All");
  const [query, setQuery] = useState("");
  const plannedJobId = nextPlannedJobId(data);
  const filtered = useMemo(() => {
    return data.queue.filter((item) => {
      const matchesFilter = activeFilter === "All" || item.stage === activeFilter;
      const matchesQuery = item.title.toLowerCase().includes(query.toLowerCase()) || item.keyword.toLowerCase().includes(query.toLowerCase());
      return matchesFilter && matchesQuery;
    });
  }, [activeFilter, data.queue, query]);

  return (
    <div className="queue-page">
      <PageHeading
        eyebrow="CONTENT OPERATIONS"
        title="Content flightboard"
        description={data.operations.isPaused ? "Review the queue while execution remains safely paused." : "Follow every article from approved concept to Shopify draft."}
        action={(
          <button
            className="primary-button"
            type="button"
            disabled={plannedJobId == null}
            onClick={() => plannedJobId != null && navigate(`/review/${plannedJobId}`)}
          >
            <Sparkle size={17} weight="fill" /> Plan next article
          </button>
        )}
      />

      <section className="stage-board">
        {stages.map((stage, index) => {
          const count = data.queue.filter((item) => item.stage === stage).length + (stage === "Approved" ? data.counts.approved : 0);
          return (
            <button type="button" key={stage} className={`stage-column ${activeFilter === stage ? "selected" : ""}`} onClick={() => setActiveFilter(activeFilter === stage ? "All" : stage)}>
              <span className="stage-number">{String(index + 1).padStart(2, "0")}</span>
              <span><strong>{stage}</strong><small>{count} article{count === 1 ? "" : "s"}</small></span>
              {index < stages.length - 1 && <ArrowRight className="stage-arrow" size={17} />}
            </button>
          );
        })}
      </section>

      <section className="queue-workspace">
        <div className="queue-main">
          <div className="queue-toolbar">
            <div className="search-field"><MagnifyingGlass size={18} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search title or keyword" /></div>
            <div className="filter-buttons">
              {["All", "Review", "Drafting", "Planned"].map((filter) => (
                <button type="button" key={filter} className={activeFilter === filter ? "active" : ""} onClick={() => setActiveFilter(filter)}>{filter}</button>
              ))}
            </div>
          </div>
          <div className="queue-list">
            <div className="queue-header"><span>Article</span><span>Stage</span><span>Priority</span><span>Due</span><span /></div>
            {filtered.map((item) => {
              const reviewable = isReviewableQueueItem(item);
              return (
                <button type="button" className={`queue-row ${item.stage === "Review" ? "attention" : ""}`} key={item.id} onClick={() => reviewable && navigate(`/review/${item.id}`)}>
                  <span className="queue-article"><small>JOB {item.id}</small><strong>{item.title}</strong><em>{item.keyword}</em></span>
                  <span><StatusPill tone={item.stage === "Review" ? "orange" : item.stage === "Drafting" ? "blue" : "neutral"}>{item.stage}</StatusPill></span>
                  <span className="priority-cell"><i className={item.priority === "High" ? "high" : ""} />{item.priority}</span>
                  <span className="due-cell">{item.due}</span>
                  <span>{reviewable ? <ArrowRight size={17} /> : <span className="more-button">•••</span>}</span>
                </button>
              );
            })}
            {filtered.length === 0 && <div className="empty-state"><MagnifyingGlass size={26} /><strong>No matching articles</strong><span>Try a different keyword or stage.</span></div>}
          </div>
        </div>
        <aside className="activity-panel">
          <div className="section-heading"><div><span className="section-kicker">LIVE LOG</span><h2>Activity</h2></div><span className="pulse-dot" /></div>
          <div className="activity-list">
            {data.activity.map((item, index) => (
              <div className="activity-item" key={`${item.time}-${item.label}`}>
                <span className={`activity-marker ${index === 0 ? "latest" : ""}`} />
                <div><time>{item.time}</time><p>{item.label}</p></div>
              </div>
            ))}
          </div>
          <div className="activity-safe"><ShieldCheck size={21} weight="duotone" /><span><strong>{data.operations.isPaused ? "Workflow is paused" : "Write protection is on"}</strong>{data.operations.isPaused ? "No approval can start work while maintenance gates are closed." : "No article can go live without your approval."}</span></div>
        </aside>
      </section>
    </div>
  );
}

function Review({ data, jobId, navigate, dataSource }) {
  const [decision, setDecision] = useState(null);
  const [changesOpen, setChangesOpen] = useState(false);
  const [note, setNote] = useState("");
  const [evidenceOpen, setEvidenceOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [decisionError, setDecisionError] = useState("");
  const [reviewDetail, setReviewDetail] = useState({ data: null, loading: dataSource === "supabase", error: null });

  useEffect(() => {
    let active = true;
    setReviewDetail({ data: null, loading: dataSource === "supabase", error: null });
    if (dataSource !== "supabase") return () => { active = false; };
    loadReviewItem(data.client.id, jobId).then((result) => {
      if (active) setReviewDetail({ data: result.data, loading: false, error: result.error });
    });
    return () => { active = false; };
  }, [data.client.id, dataSource, jobId]);

  const article = useMemo(
    () => selectRouteBoundReviewArticle(data, jobId, reviewDetail.data),
    [data, jobId, reviewDetail.data],
  );

  if (reviewDetail.loading) {
    return <div className="loading-screen"><Brand /><span className="loading-line" /><p>Loading the version-bound review…</p></div>;
  }

  if (!article || reviewDetail.error) {
    return (
      <div className="review-page">
        <div className="review-topline">
          <button className="back-button" type="button" onClick={() => navigate("/queue")}><ArrowLeft size={17} /> Content queue</button>
        </div>
        <div className="empty-state" role="alert">
          <WarningCircle size={26} />
          <strong>Review item unavailable</strong>
          <span>{reviewDetail.error?.message ?? "This route does not match a current, version-bound review item. Return to the queue and select it again."}</span>
        </div>
      </div>
    );
  }

  const saveDecision = async (kind, decisionNote = "") => {
    setSaving(true);
    setDecisionError("");
    if (kind === "approve_hidden_draft") {
      const refreshed = await refreshApprovedDraftConnection(data.client.id);
      if (refreshed.error) {
        setSaving(false);
        setDecisionError(
          refreshed.error.message
            ?? "Shopify could not refresh the secure connection. Reconnect Shopify and try again.",
        );
        return;
      }
    }
    const result = await recordContentDecision({
      clientId: data.client.id,
      contentItemId: article.contentItemId,
      contentItemVersion: article.version,
      decision: kind,
      note: decisionNote,
    });
    setSaving(false);
    if (result.error) {
      setDecisionError(result.error.message ?? "The decision could not be saved.");
      return;
    }
    setDecision(kind === "request_changes" ? "changes" : "approved");
    setChangesOpen(false);
    if (kind === "request_changes") setNote("");
  };

  const approvalKind = article.reviewKind === "draft"
    ? "approve_hidden_draft"
    : article.reviewKind === "concept" ? "approve_concept" : null;
  const approve = () => approvalKind && saveDecision(approvalKind);
  const approvalLabel = article.reviewKind === "draft"
    ? "Approve unpublished Shopify draft"
    : article.reviewKind === "concept" ? "Approve concept for drafting" : "Revision required";
  const presentation = reviewPresentationForClient(data.client);
  const htmlIsolation = validateArticleHtmlForClient(article.bodyHtml, data.client);
  const runtimeApprovalState = approvalAvailability(data.operations, article.reviewKind);
  const approvalState = article.bodyHtml && !htmlIsolation.ok
    ? { allowed: false, reason: htmlIsolation.reason }
    : runtimeApprovalState;
  const clientPreviewCss = presentation.previewTheme === "hcs-gadgets" ? hcsArticleCss : "";
  const draftDocument = article.bodyHtml && htmlIsolation.ok
    ? `<!doctype html><html><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data:; style-src 'unsafe-inline'"><style>${BASE_DRAFT_PREVIEW_CSS}${clientPreviewCss}</style></head><body>${article.bodyHtml}</body></html>`
    : null;

  const submitChanges = () => {
    if (!note.trim()) return;
    saveDecision("request_changes", note.trim());
  };

  return (
    <div className="review-page">
      <div className="review-topline">
        <button className="back-button" type="button" onClick={() => navigate("/queue")}><ArrowLeft size={17} /> Content queue</button>
        <span className="review-job">JOB {article.id} <i /> READY FOR REVIEW</span>
      </div>

      {decision && (
        <div className={`decision-banner ${decision}`} role="status">
          {decision === "approved" ? <CheckCircle size={22} weight="fill" /> : <NotePencil size={22} weight="duotone" />}
          <div>
            <strong>{decision === "approved" ? `${article.reviewKind === "draft" ? "Hidden-draft" : "Concept"} approval recorded` : "Change request recorded"}</strong>
            <span>{dataSource === "supabase" ? "Saved durably. The controlled worker will act only when the matching gates are open." : "Saved in this local preview. No Shopify action was performed."}</span>
          </div>
          <button type="button" onClick={() => setDecision(null)} aria-label="Dismiss"><X size={17} /></button>
        </div>
      )}

      <div className="review-layout">
        <article className="article-preview">
          <header className="article-header">
            <span className="article-label">{presentation.articleLabel}</span>
            <h1>{article.title}</h1>
            <p>{article.dek}</p>
            <div className="article-byline">
              <span className="author-mark"><Robot size={17} weight="duotone" /></span>
              <span><strong>Prepared by ORIN</strong><small>{presentation.policyLabel}</small></span>
              <span className="article-length"><Clock size={15} /> {article.readingTime}</span>
            </div>
          </header>

          {article.bodyHtml && !htmlIsolation.ok ? (
            <div className="article-contract-error" role="alert">
              <WarningCircle size={23} weight="duotone" />
              <div><strong>Client design contract mismatch</strong><span>{htmlIsolation.reason} Shopify approval remains unavailable until this draft is regenerated correctly.</span></div>
            </div>
          ) : draftDocument ? (
            <iframe className="draft-preview-frame" title={`Full draft preview for ${article.title}`} sandbox="" srcDoc={draftDocument} />
          ) : <div className="article-body">
            {article.sections.map((section) => (
              <section key={section.heading}>
                <h2>{section.heading}</h2>
                {section.paragraphs?.map((paragraph) => <p key={paragraph}>{paragraph}</p>)}
                {section.bullets && (
                  <ul>{section.bullets.map((bullet) => <li key={bullet}><CheckCircle size={17} weight="fill" />{bullet}</li>)}</ul>
                )}
              </section>
            ))}
            <div className="article-disclaimer"><Info size={20} weight="duotone" /><p><strong>A practical reminder</strong>Always follow the scooter and protective equipment manufacturers’ instructions. Supervision and local rules still apply.</p></div>
          </div>}
        </article>

        <aside className="decision-rail">
          <div className="decision-card">
            <div className="decision-card-header"><span className="section-kicker">YOUR DECISION</span><h2>{article.reviewKind === "draft" ? "Ready for Shopify?" : article.reviewKind === "concept" ? "Ready to draft?" : "Revision required"}</h2><p>{article.reviewKind === "draft" ? "Approval can create one unpublished Shopify draft only when every production gate is open." : article.reviewKind === "concept" ? "Approval queues the controlled drafting and quality-check run. It cannot contact Shopify." : "This version did not reach an approvable stage. Record the needed changes before a new version is generated."}</p></div>

            <div className="review-score">
              <span className="score-ring"><strong>{article.qualityScore ?? "—"}</strong><small>{article.qualityScore == null ? "brief" : "/100"}</small></span>
              <div><strong>{article.reviewKind === "concept" ? "Concept is version-bound" : "Full draft is version-bound"}</strong><span>{article.reviewKind === "concept" ? "Draft quality checks run later in the controlled worker." : `${article.wordCount ?? "—"} words captured from the exact generation run.`}</span></div>
            </div>

            <dl className="seo-details">
              <div><dt>Target keyword</dt><dd>{article.keyword}</dd></div>
              <div><dt>Meta title</dt><dd>{article.metaTitle}</dd></div>
              <div><dt>Meta description</dt><dd>{article.metaDescription}</dd></div>
            </dl>

            <button className="evidence-toggle" type="button" onClick={() => setEvidenceOpen(!evidenceOpen)} aria-expanded={evidenceOpen}>
              <span><ShieldCheck size={18} /> Evidence & safeguards</span><CaretDown size={15} className={evidenceOpen ? "rotated" : ""} />
            </button>
            {evidenceOpen && <ul className="evidence-list">{article.evidence.map((item) => <li key={item}><Check size={14} weight="bold" />{item}</li>)}</ul>}

            {!changesOpen ? (
              <div className="decision-actions">
                <button className="approve-button" type="button" onClick={approve} disabled={saving || !approvalKind || !approvalState.allowed} title={approvalState.allowed ? "" : approvalState.reason}><CheckCircle size={19} weight="fill" /> {saving ? "Saving…" : approvalLabel}</button>
                {!approvalState.allowed && approvalKind && <p className="approval-paused-note"><WarningCircle size={15} /> {approvalState.reason}</p>}
                <button className="changes-button" type="button" onClick={() => setChangesOpen(true)} disabled={saving}><NotePencil size={18} /> Request changes</button>
              </div>
            ) : (
              <div className="change-form">
                <label htmlFor="change-note">What should change?</label>
                <textarea id="change-note" value={note} onChange={(event) => setNote(event.target.value)} placeholder="Example: simplify the helmet section and add a link to our safety collection." autoFocus />
                <div><button type="button" className="text-button" onClick={() => setChangesOpen(false)} disabled={saving}>Cancel</button><button type="button" className="primary-button" onClick={submitChanges} disabled={!note.trim() || saving}><PaperPlaneTilt size={17} /> {saving ? "Saving…" : "Send request"}</button></div>
              </div>
            )}
            {decisionError && <p className="decision-error" role="alert"><WarningCircle size={15} /> {decisionError}</p>}
            {article.latestDecision && <p className="decision-receipt"><CloudCheck size={15} /> Latest: {article.latestDecision.replaceAll("_", " ")} · {article.latestDecisionStatus}{article.latestDecisionOutcome ? ` — ${article.latestDecisionOutcome}` : ""}</p>}
            <p className="no-publish-note"><WarningCircle size={15} /> This dashboard has no live-publish capability.</p>
          </div>
        </aside>
      </div>
    </div>
  );
}

export function App() {
  const { route, path, navigate, location } = useRoute();
  const [state, setState] = useState({ data: null, source: "loading", error: null, requiresAuth: false });
  const [operatorAccess, setOperatorAccess] = useState(false);

  const reload = () => {
    setState((current) => ({ ...current, source: "loading", error: null }));
    loadDashboardData(new URLSearchParams(window.location.search).get("client")).then(setState);
  };

  const switchWorkspace = (clientId) => {
    navigate(`${path || "/"}?client=${encodeURIComponent(clientId)}`);
  };

  const openWorkspace = (clientId) => navigate(`/?client=${encodeURIComponent(clientId)}`);

  useEffect(() => {
    let active = true;
    const requestedClientId = new URLSearchParams(window.location.search).get("client");
    Promise.all([loadDashboardData(requestedClientId), loadOnboardingAccess()]).then(([result, access]) => {
      if (!active) return;
      setState(result);
      setOperatorAccess(access.allowed);
    });
    const unsubscribe = subscribeToAuthChanges(() => {
      if (!active) return;
      Promise.all([loadDashboardData(new URLSearchParams(window.location.search).get("client")), loadOnboardingAccess()]).then(([result, access]) => {
        if (!active) return;
        setState(result);
        setOperatorAccess(access.allowed);
      });
    });
    return () => { active = false; unsubscribe(); };
  }, [location]);

  useEffect(() => {
    document.title = state.data?.client?.name
      ? `ORIN Commerce — ${state.data.client.name}`
      : "ORIN Commerce";
  }, [state.data?.client?.name]);

  if (state.requiresAuth) return <AuthScreen />;
  if (state.source === "error") return <ErrorScreen message={state.error} onRetry={reload} />;
  if (!state.data) {
    return <div className="loading-screen"><Brand /><span className="loading-line" /><p>Preparing your workspace…</p></div>;
  }

  return (
    <AppShell route={route} navigate={navigate} dataSource={state.source} operations={state.data.operations} queueCount={state.data.counts.review} onSignOut={signOutDashboard} operatorAccess={operatorAccess} client={state.data.client} workspaces={state.workspaces ?? []} onWorkspaceChange={switchWorkspace}>
      {route === "overview" && <Overview data={state.data} navigate={navigate} />}
      {route === "queue" && <Queue data={state.data} navigate={navigate} />}
      {route === "review" && <Review data={state.data} jobId={reviewJobIdFromPath(path)} navigate={navigate} dataSource={state.source} />}
      {route === "onboarding" && (operatorAccess
        ? <Onboarding requestedClientId={state.data.client.id} onSelectWorkspace={switchWorkspace} onOpenWorkspace={openWorkspace} />
        : <div className="empty-state"><WarningCircle size={26} /><strong>Platform operator access required</strong><span>This route cannot create or view onboarding records for your account.</span></div>)}
    </AppShell>
  );
}
