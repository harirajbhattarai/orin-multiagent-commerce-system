const CLIENT_PRESENTATIONS = Object.freeze({
  hoverboard_store: Object.freeze({
    articleLabel: "PARENT BUYING GUIDE",
    policyLabel: "Reviewed against Hoverboard Store policy",
    previewTheme: "hoverboard-store",
    requiredWrapper: { element: "div", className: "hs-article" },
    forbiddenClassNames: ["hcs-article", "orin-article"],
  }),
  hcs_gadgets: Object.freeze({
    articleLabel: "HCS GADGETS GUIDE",
    policyLabel: "Reviewed against HCS Gadgets policy",
    previewTheme: "hcs-gadgets",
    requiredWrapper: { element: "article", className: "hcs-article" },
    forbiddenClassNames: ["hs-article", "orin-article"],
  }),
});

const GENERIC_PRESENTATION = Object.freeze({
  previewTheme: "generic",
  requiredWrapper: Object.freeze({ element: "article", className: "orin-article" }),
  forbiddenClassNames: Object.freeze(["hs-article", "hcs-article"]),
});

function normalizedClientId(client) {
  return String(client?.id ?? client?.client_id ?? "").trim().toLowerCase();
}

export function reviewPresentationForClient(client) {
  const clientId = normalizedClientId(client);
  const known = CLIENT_PRESENTATIONS[clientId];
  if (known) return { clientId, ...known };

  const clientName = String(client?.name ?? client?.display_name ?? "Client").trim() || "Client";
  return {
    clientId,
    articleLabel: "CLIENT CONTENT REVIEW",
    policyLabel: `Reviewed against ${clientName} policy`,
    ...GENERIC_PRESENTATION,
  };
}

function hasElementWithClass(html, { element, className }) {
  const escapedClass = className.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const pattern = new RegExp(
    `<${element}\\b[^>]*\\bclass\\s*=\\s*["'][^"']*\\b${escapedClass}\\b[^"']*["'][^>]*>`,
    "i",
  );
  return pattern.test(html);
}

function hasClass(html, className) {
  if (!className) return false;
  const escapedClass = className.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return new RegExp(
    `\\bclass\\s*=\\s*["'][^"']*\\b${escapedClass}\\b[^"']*["']`,
    "i",
  ).test(html);
}

export function validateArticleHtmlForClient(bodyHtml, client) {
  if (!bodyHtml) return { ok: true, reason: "No generated article body is present." };

  const presentation = reviewPresentationForClient(client);
  if (!presentation.requiredWrapper) {
    return {
      ok: false,
      reason: "This client does not have a registered article design contract.",
    };
  }
  const forbiddenClassName = presentation.forbiddenClassNames
    .find((className) => hasClass(bodyHtml, className));
  if (forbiddenClassName) {
    return {
      ok: false,
      reason: `The draft contains another client's ${forbiddenClassName} wrapper.`,
    };
  }
  if (!hasElementWithClass(bodyHtml, presentation.requiredWrapper)) {
    return {
      ok: false,
      reason: `The draft is missing the required ${presentation.requiredWrapper.element}.${presentation.requiredWrapper.className} wrapper.`,
    };
  }
  return { ok: true, reason: "The article body matches this client's design contract." };
}

export function authoritativeClientIdentity(snapshotClient, databaseClient) {
  if (!databaseClient?.client_id || !databaseClient?.display_name) return snapshotClient;
  return {
    ...(snapshotClient ?? {}),
    id: databaseClient.client_id,
    name: databaseClient.display_name,
    status: databaseClient.status,
  };
}
