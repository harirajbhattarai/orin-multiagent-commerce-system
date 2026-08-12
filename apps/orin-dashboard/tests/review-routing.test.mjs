import assert from "node:assert/strict";
import test from "node:test";
import {
  isReviewableQueueItem,
  nextPlannedJobId,
  reviewJobIdFromPath,
  selectRouteBoundReviewArticle,
} from "../src/reviewArticle.js";

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
