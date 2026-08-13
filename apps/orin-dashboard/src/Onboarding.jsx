import { useEffect, useMemo, useState } from "react";
import {
  ArrowLeft,
  ArrowRight,
  Check,
  CheckCircle,
  Database,
  Key,
  LockKey,
  Plus,
  ShieldCheck,
  Storefront,
  UserPlus,
  WarningCircle,
} from "@phosphor-icons/react";
import {
  createOnboardingRequest,
  auditProvisionedClient,
  loadOnboardingRequests,
  provisionOnboardingClient,
  updateOnboardingScope,
  verifyOnboardingShopify,
} from "./lib/dashboardClient.js";
import {
  clientIdFromName,
  normalizeShopifyDomain,
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

function stepForRequest(request) {
  if (request.status === "database_provisioned") return 4;
  if (request.status === "ready_to_provision") return 4;
  if (request.credential_status === "stored") return 3;
  return 2;
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

export function Onboarding({ onOpenWorkspace }) {
  const [requests, setRequests] = useState([]);
  const [activeRequest, setActiveRequest] = useState(null);
  const [step, setStep] = useState(1);
  const [form, setForm] = useState(defaultForm);
  const [token, setToken] = useState("");
  const [blogs, setBlogs] = useState([]);
  const [shop, setShop] = useState(null);
  const [selectedBlog, setSelectedBlog] = useState("");
  const [productText, setProductText] = useState("");
  const [busy, setBusy] = useState("");
  const [message, setMessage] = useState({ tone: "", text: "" });

  const refreshRequests = async (preferredId) => {
    const result = await loadOnboardingRequests();
    if (result.error) {
      setMessage({ tone: "error", text: result.error.message });
      return null;
    }
    setRequests(result.data ?? []);
    const match = (result.data ?? []).find((item) => item.request_id === preferredId);
    if (match) setActiveRequest(match);
    return match ?? null;
  };

  useEffect(() => { refreshRequests(); }, []);

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
    setToken("");
    setBlogs([]);
    setShop(null);
    setSelectedBlog("");
    setProductText("");
    setMessage({ tone: "", text: "" });
    setStep(1);
  };

  const resume = (request) => {
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
    setProductText((request.product_scope ?? []).map((item) => item.name ?? String(item)).join("\n"));
    setMessage({ tone: "", text: "" });
    setStep(stepForRequest(request));
  };

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
    const request = await refreshRequests(result.data.request_id);
    setActiveRequest(request ?? { ...result.data, ...form, shopify_store_domain: storeDomain });
    setStep(2);
    setMessage({ tone: "success", text: "Business profile saved. No execution gates were opened." });
  };

  const validateShopify = async () => {
    if (!token.trim()) return;
    setBusy("validate");
    setMessage({ tone: "", text: "" });
    const result = await verifyOnboardingShopify({
      action: "validate_shopify",
      store_domain: activeRequest.shopify_store_domain,
      access_token: token.trim(),
    });
    setBusy("");
    if (result.error) {
      setMessage({ tone: "error", text: result.error.message });
      return;
    }
    setShop(result.data.shop);
    setBlogs(result.data.blogs ?? []);
    setSelectedBlog(result.data.blogs?.[0]?.id ?? "");
    setMessage({ tone: "success", text: `Connected to ${result.data.shop.name}. Choose the target blog before the token is encrypted.` });
  };

  const saveShopify = async () => {
    setBusy("shopify");
    setMessage({ tone: "", text: "" });
    const result = await verifyOnboardingShopify({
      action: "save_shopify_connection",
      request_id: activeRequest.request_id,
      store_domain: activeRequest.shopify_store_domain,
      access_token: token.trim(),
      blog_gid: selectedBlog,
    });
    setBusy("");
    if (result.error) {
      setMessage({ tone: "error", text: result.error.message });
      return;
    }
    setToken("");
    const request = await refreshRequests(activeRequest.request_id);
    setActiveRequest(request ?? { ...activeRequest, credential_status: "stored", status: "connection_verified" });
    setStep(3);
    setMessage({ tone: "success", text: "Shopify verified. The token is encrypted in Vault and was removed from this form." });
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
    const request = await refreshRequests(activeRequest.request_id);
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
    const request = await refreshRequests(activeRequest.request_id);
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
    const request = await refreshRequests(activeRequest.request_id);
    setActiveRequest(request ?? { ...activeRequest, commissioning_status: "identity_verified" });
    setMessage({
      tone: "success",
      text: `Read-only identity verified: ${result.data.store_domain} · ${result.data.blog_title} · ${result.data.product_count} products. No Shopify write was attempted.`,
    });
  };

  return (
    <div className="onboarding-page">
      <div className="page-heading onboarding-heading">
        <div>
          <span className="eyebrow">PLATFORM OPERATIONS</span>
          <h1>Client onboarding</h1>
          <p>Add a client without using SSH. ORIN verifies the store, encrypts credentials, and creates a fail-closed tenant.</p>
        </div>
        <button className="secondary-button" type="button" onClick={startNew}><Plus size={17} /> New client</button>
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
              <div className="onboarding-section-heading"><span><Key size={20} weight="duotone" /></span><div><h2>Verify Shopify</h2><p>Token input is sent only to the authenticated server function and encrypted after verification.</p></div></div>
              <div className="connection-summary"><Storefront size={22} /><div><strong>{activeRequest.display_name ?? form.displayName}</strong><span>{activeRequest.shopify_store_domain}</span></div><span className="status-pill neutral">Not connected</span></div>
              <div className="onboarding-stack">
                <Field label="Shopify Admin API access token" hint="Required read_content and write_content scopes. The token is never returned to the browser."><input type="password" autoComplete="new-password" value={token} onChange={(event) => setToken(event.target.value)} placeholder="shpat_••••••••••••••••" /></Field>
                {blogs.length > 0 && <Field label="Target Shopify blog"><select value={selectedBlog} onChange={(event) => setSelectedBlog(event.target.value)}>{blogs.map((blog) => <option key={blog.id} value={blog.id}>{blog.title} ({blog.handle})</option>)}</select></Field>}
              </div>
              <div className="onboarding-actions"><button className="text-button" type="button" onClick={() => setStep(1)}><ArrowLeft size={16} /> Back</button><div>{blogs.length === 0 ? <button className="secondary-button" type="button" onClick={validateShopify} disabled={!token.trim() || busy === "validate"}>{busy === "validate" ? "Checking…" : "Test connection"}</button> : <button className="primary-button" type="button" onClick={saveShopify} disabled={!selectedBlog || busy === "shopify"}>{busy === "shopify" ? "Encrypting…" : "Save encrypted connection"}<ArrowRight size={17} /></button>}</div></div>
            </div>
          )}

          {step === 3 && (
            <div>
              <div className="onboarding-section-heading"><span><Storefront size={20} weight="duotone" /></span><div><h2>Content and product scope</h2><p>Tell ORIN what it may research. This does not yet generate or publish content.</p></div></div>
              <div className="verified-strip"><ShieldCheck size={21} weight="duotone" /><div><strong>Encrypted Shopify connection ready</strong><span>{activeRequest.shopify_blog_title} · {activeRequest.shopify_store_domain}</span></div></div>
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
              {activeRequest.status !== "database_provisioned" ? <div className="onboarding-actions"><button className="text-button" type="button" onClick={() => setStep(3)}><ArrowLeft size={16} /> Back</button><button className="primary-button" type="button" onClick={provision} disabled={busy === "provision"}><ShieldCheck size={18} weight="fill" />{busy === "provision" ? "Provisioning…" : "Create safely disabled workspace"}</button></div> : <><div className={`commissioning-next ${activeRequest.commissioning_status === "identity_verified" ? "verified" : ""}`}>{activeRequest.commissioning_status === "identity_verified" ? <CheckCircle size={21} weight="fill" /> : <WarningCircle size={21} weight="duotone" />}<div><strong>{activeRequest.commissioning_status === "identity_verified" ? "Read-only identity verified" : "Not production-ready yet"}</strong><span>{activeRequest.commissioning_status === "identity_verified" ? "The exact Shopify store, target blog, and product-read access passed with every execution and write gate closed. Dedicated dry-run worker commissioning is next." : "Run the server-side read-only identity audit next. It can inspect the store and product count, but cannot create, edit, or publish Shopify content."}</span></div></div><div className="onboarding-actions"><span><ShieldCheck size={17} /> Every execution and Shopify gate remains closed.</span><div>{activeRequest.commissioning_status !== "identity_verified" && <button className="primary-button" type="button" onClick={auditClient} disabled={busy === "audit"}>{busy === "audit" ? "Checking…" : "Run read-only identity audit"}</button>}<button className="secondary-button" type="button" onClick={() => onOpenWorkspace(activeRequest.client_id)}>Open {activeRequest.display_name}</button></div></div></>}
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
