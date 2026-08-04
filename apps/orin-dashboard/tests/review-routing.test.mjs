import assert from "node:assert/strict";
import test from "node:test";
import {
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

test("fails closed for missing, unbound, or non-reviewable jobs", () => {
  assert.equal(selectRouteBoundReviewArticle(data, 4), null);
  assert.equal(selectRouteBoundReviewArticle(data, 999), null);
  assert.equal(selectRouteBoundReviewArticle({ ...data, queue: [{ id: 3, stage: "Review" }] }, 3), null);
});
