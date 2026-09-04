import assert from "node:assert/strict";
import test from "node:test";

import { approvalProgressForQueueItem } from "../src/queueProgress.js";

test("shows concept approval while scheduled drafting is pending", () => {
  assert.equal(
    approvalProgressForQueueItem(
      { stage: "Planned" },
      { latest_decision: "approve_concept", latest_decision_status: "consumed" },
    ),
    "Concept approved — waiting for scheduled drafting",
  );
});

test("shows unpublished-draft approval while Shopify reconciliation is pending", () => {
  assert.equal(
    approvalProgressForQueueItem(
      { stage: "Review" },
      { latest_decision: "approve_hidden_draft", latest_decision_status: "consumed" },
    ),
    "Approval recorded — finalizing the unpublished Shopify draft",
  );
});

test("does not imply progress before an approval is recorded", () => {
  assert.equal(
    approvalProgressForQueueItem(
      { stage: "Review" },
      { latest_decision: "request_changes", latest_decision_status: "recorded" },
    ),
    null,
  );
});
