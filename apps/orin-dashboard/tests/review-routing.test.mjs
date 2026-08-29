import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import {
  isReviewableQueueItem,
  nextPlannedJobId,
  reviewJobIdFromPath,
  selectRouteBoundReviewArticle,
  stageArticleCount,
} from "../src/reviewArticle.js";
import { approvalAvailability, deriveOperationalState } from "../src/operationalState.js";
import {
  authoritativeClientIdentity,
  reviewPresentationForClient,
  validateArticleHtmlForClient,
} from "../src/clientPresentation.js";

const data = {
  nextArticle: { id: 33, readingTime: "Concept review", qualityScore: null },
  queue: [
    {
      id: 3,
      contentItemId: "item-3",
      version: 2,
      title: "Job Three",
      keyword: "job three keyword",
      stage: "Review",
    },
    {
      id: 33,
      contentItemId: "item-33",
      version: 5,
      title: "Job Thirty-Three",
      keyword: "job thirty-three keyword",
      stage: "Planned",
    },
    {
      id: 4,
      contentItemId: "item-4",
      version: 1,
      title: "Job Four",
      keyword: "job four keyword",
      stage: "Approved",
    },
  ],
  article: {
    id: 33,
    contentItemId: "item-33",
    version: 5,
    title: "Job Thirty-Three",
    keyword: "job thirty-three keyword",
    dek: "Rich article copy",
    metaTitle: "Rich metadata",
    metaDescription: "Rich description",
    sections: [{ heading: "Rich section", paragraphs: ["Rich paragraph"] }],
    evidence: ["Rich evidence"],
  },
};

test("parses only exact positive-integer review routes", () => {
  assert.equal(reviewJobIdFromPath("/review/3"), 3);
  assert.equal(reviewJobIdFromPath("/review/33/"), 33);
  assert.equal(reviewJobIdFromPath("/review/3-extra"), null);
  assert.equal(reviewJobIdFromPath("/queue"), null);
});

test("selects the preferred planned article for the primary queue action", () => {
  assert.equal(nextPlannedJobId(data), 33);
  assert.equal(nextPlannedJobId({
    nextArticle: { id: 999 },
    queue: [
      { id: 35, contentItemId: "item-35", version: 1, stage: "Planned" },
      { id: 36, contentItemId: "item-36", version: 1, stage: "Planned" },
    ],
  }), 35);
  assert.equal(nextPlannedJobId({ queue: [] }), null);
});

test("uses authoritative stage totals without double counting queue rows", () => {
  const stageData = {
    counts: { planned: 1, drafting: 0, review: 0, approved: 1 },
    queue: [
      { id: 1, stage: "Approved" },
      { id: 2, stage: "Planned" },
    ],
  };

  assert.equal(stageArticleCount(stageData, "Approved"), 1);
  assert.equal(stageArticleCount(stageData, "Planned"), 1);
  assert.equal(stageArticleCount(stageData, "Research"), 0);
});

test("allows only fully bound planned or review queue items to open", () => {
  assert.equal(isReviewableQueueItem(data.queue[0]), true);
  assert.equal(isReviewableQueueItem(data.queue[1]), true);
  assert.equal(isReviewableQueueItem(data.queue[2]), false);
  assert.equal(isReviewableQueueItem({ id: 35, stage: "Planned" }), false);
});

test("binds /review/3 to Job 3 instead of the snapshot's Job 33 article", () => {
  const article = selectRouteBoundReviewArticle(data, 3);
  assert.equal(article.id, 3);
  assert.equal(article.contentItemId, "item-3");
  assert.equal(article.version, 2);
  assert.equal(article.title, "Job Three");
  assert.notEqual(article.title, data.article.title);
});

test("uses rich article content only when its job and version binding match", () => {
  const article = selectRouteBoundReviewArticle(data, 33);
  assert.equal(article.id, 33);
  assert.equal(article.contentItemId, "item-33");
  assert.equal(article.dek, "Rich article copy");
  assert.deepEqual(article.sections, data.article.sections);
});

test("uses a full draft only when the fetched route binding is exact", () => {
  const loaded = {
    id: 3,
    contentItemId: "item-3",
    version: 2,
    reviewKind: "draft",
    bodyHtml: "<article><h1>Job Three</h1></article>",
    wordCount: 440,
  };
  const article = selectRouteBoundReviewArticle(data, 3, loaded);
  assert.equal(article.reviewKind, "draft");
  assert.equal(article.bodyHtml, loaded.bodyHtml);
  assert.equal(article.readingTime, "2 min read");
  assert.equal(selectRouteBoundReviewArticle(data, 3, { ...loaded, version: 3 }), null);
});

test("fails closed for missing, unbound, or non-reviewable jobs", () => {
  assert.equal(selectRouteBoundReviewArticle(data, 4), null);
  assert.equal(selectRouteBoundReviewArticle(data, 999), null);
  assert.equal(selectRouteBoundReviewArticle({ ...data, queue: [{ id: 3, stage: "Review" }] }, 3), null);
});

test("projects maintenance as paused and blocks both approval paths", () => {
  const operations = deriveOperationalState({
    client: { status: "maintenance" },
    runtime: {
      request_intake_enabled: false,
      automation_enabled: false,
      shopify_writes_enabled: false,
      approved_draft_writes_enabled: false,
      allowed_mode: "dry-run",
    },
    health: {
      state: "disabled",
      scheduler_owner: null,
      last_heartbeat_at: "2026-08-13T10:00:00Z",
      updated_at: "2026-08-13T12:00:00Z",
    },
    nowMs: Date.parse("2026-08-13T13:00:00Z"),
  });

  assert.equal(operations.workspaceLabel, "Maintenance paused");
  assert.equal(operations.scheduler, "Paused");
  assert.equal(operations.worker, "Idle");
  assert.equal(operations.watchdog, "Paused");
  assert.equal(operations.shopifyWrites, "Paused");
  assert.equal(approvalAvailability(operations, "concept").allowed, false);
  assert.equal(approvalAvailability(operations, "draft").allowed, false);
});

test("allows only the approval path covered by the open gates", () => {
  const conceptOnly = deriveOperationalState({
    client: { status: "active" },
    runtime: {
      request_intake_enabled: true,
      automation_enabled: true,
      shopify_writes_enabled: false,
      approved_draft_writes_enabled: false,
      allowed_mode: "dry-run",
    },
    health: {
      state: "healthy",
      scheduler_owner: "prefect:orin-hbstore-prod",
      last_heartbeat_at: "2026-08-13T12:30:00Z",
    },
    nowMs: Date.parse("2026-08-13T13:00:00Z"),
  });
  assert.equal(approvalAvailability(conceptOnly, "concept").allowed, true);
  assert.equal(approvalAvailability(conceptOnly, "draft").allowed, false);

  const approvedDrafts = deriveOperationalState({
    client: { status: "active" },
    runtime: {
      request_intake_enabled: true,
      automation_enabled: true,
      shopify_writes_enabled: false,
      approved_draft_writes_enabled: true,
      allowed_mode: "dry-run",
    },
    health: {
      state: "healthy",
      scheduler_owner: "prefect:orin-hbstore-prod",
      last_heartbeat_at: "2026-08-13T12:30:00Z",
    },
    nowMs: Date.parse("2026-08-13T13:00:00Z"),
  });
  assert.equal(approvalAvailability(approvedDrafts, "draft").allowed, true);
  assert.equal(approvedDrafts.shopifyWrites, "Approved drafts only");
});

test("reads only the scheduler-health columns granted to dashboard users", async () => {
  const source = await readFile(
    new URL("../src/lib/dashboardClient.js", import.meta.url),
    "utf8",
  );
  const query = source.match(
    /\.from\("scheduler_health"\)\s*\.select\("([^"]+)"\)/,
  );

  assert.ok(query, "scheduler-health query should be present");
  assert.equal(
    query[1],
    "state,scheduler_owner,last_heartbeat_at,updated_at",
  );
  assert.equal(query[1].includes("details"), false);
});

test("uses client-specific review labels instead of leaking HBStore policy", () => {
  const hcs = reviewPresentationForClient({ id: "hcs_gadgets", name: "HCS GADGETS" });
  const hbstore = reviewPresentationForClient({ id: "hoverboard_store", name: "Hoverboard Store" });

  assert.equal(hcs.policyLabel, "Reviewed against HCS Gadgets policy");
  assert.equal(hcs.articleLabel, "HCS GADGETS GUIDE");
  assert.equal(hcs.previewTheme, "hcs-gadgets");
  assert.equal(hbstore.policyLabel, "Reviewed against Hoverboard Store policy");
  assert.notEqual(hcs.policyLabel, hbstore.policyLabel);
});

test("fails closed when article HTML belongs to another client", () => {
  const hcsClient = { id: "hcs_gadgets", name: "HCS GADGETS" };
  const hbstoreClient = { id: "hoverboard_store", name: "Hoverboard Store" };

  assert.equal(validateArticleHtmlForClient('<article class="hcs-article"></article>', hcsClient).ok, true);
  assert.equal(validateArticleHtmlForClient('<div class="hs-article"></div>', hcsClient).ok, false);
  assert.equal(validateArticleHtmlForClient('<div class="hs-article"></div>', hbstoreClient).ok, true);
  assert.equal(validateArticleHtmlForClient('<article class="hcs-article"></article>', hbstoreClient).ok, false);
  assert.equal(validateArticleHtmlForClient("<article></article>", hcsClient).ok, false);
});

test("registers the generic OAuth article contract without accepting fixed-client wrappers", () => {
  const oauthClient = { id: "orin_oauth_test", name: "ORIN OAuth Test" };
  const presentation = reviewPresentationForClient(oauthClient);

  assert.deepEqual(presentation.requiredWrapper, { element: "article", className: "orin-article" });
  assert.equal(validateArticleHtmlForClient('<article class="orin-article"></article>', oauthClient).ok, true);
  assert.equal(validateArticleHtmlForClient('<article class="hcs-article"></article>', oauthClient).ok, false);
  assert.equal(validateArticleHtmlForClient('<div class="hs-article"></div>', oauthClient).ok, false);
  assert.equal(validateArticleHtmlForClient("<article></article>", oauthClient).ok, false);
});

test("uses the database tenant identity instead of stale snapshot branding", () => {
  const identity = authoritativeClientIdentity(
    { id: "hoverboard_store", name: "Hoverboard Store", plan: "Pilot workspace" },
    { client_id: "hcs_gadgets", display_name: "HCS GADGETS", status: "maintenance" },
  );

  assert.deepEqual(identity, {
    id: "hcs_gadgets",
    name: "HCS GADGETS",
    plan: "Pilot workspace",
    status: "maintenance",
  });
});

test("ships the canonical HCS stylesheet without HBStore selectors", async () => {
  const css = await readFile(
    new URL("../../../clients/hcs_gadgets/shopify_theme/hcs-article.css", import.meta.url),
    "utf8",
  );

  assert.match(css, /\.hcs-article\s*\{/);
  assert.match(css, /\.hcs-hero\s*\{/);
  assert.match(css, /\.hcs-cta\s*\{/);
  assert.match(css, /\.hcs-button(?:\s*,|\s*\{)/);
  assert.equal(css.includes("@import"), false);
  assert.equal(css.includes("overflow: hidden !important;\n  background-color: var(--hcs-bg)"), false);
  assert.equal(css.includes(".hs-article"), false);
  assert.equal(css.includes(".hs-cta"), false);
});
