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

export function onboardingSafetyChecklist(request) {
  return [
    { label: "Business profile saved", complete: Boolean(request?.request_id) },
    { label: "Shopify token verified and encrypted", complete: request?.credential_status === "stored" },
    { label: "Isolated database tenant created", complete: request?.status === "database_provisioned" },
    { label: "Request intake and automation disabled", complete: ["gates_closed", "identity_verified"].includes(request?.commissioning_status) },
    { label: "All Shopify write gates disabled", complete: ["gates_closed", "identity_verified"].includes(request?.commissioning_status) },
    { label: "Scheduler disabled with no owner", complete: ["gates_closed", "identity_verified"].includes(request?.commissioning_status) },
  ];
}
