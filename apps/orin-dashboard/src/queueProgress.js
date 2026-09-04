export function approvalProgressForQueueItem(item, review) {
  if (!["recorded", "consumed"].includes(review?.latest_decision_status)) return null;
  if (item.stage === "Planned" && review?.latest_decision === "approve_concept") {
    return "Concept approved — waiting for scheduled drafting";
  }
  if (item.stage === "Review" && review?.latest_decision === "approve_hidden_draft") {
    return "Approval recorded — finalizing the unpublished Shopify draft";
  }
  return null;
}
