import assert from "node:assert/strict";
import test from "node:test";
import {
  canPlanContent,
  normalizeSubscription,
  subscriptionPresentation,
} from "../src/subscription.js";

const activePilot = {
  plan_key: "pilot",
  plan_name: "Pilot access",
  description: "Founding-client access.",
  status: "active",
  billing_provider: "pilot",
  monthly_article_limit: 30,
  articles_used_this_month: 2,
  team_member_limit: 3,
  can_create_unpublished_drafts: true,
  can_publish_live: true,
  features: ["No-code Shopify onboarding"],
};

test("normalizes a server subscription without ever exposing live publishing", () => {
  const subscription = normalizeSubscription(activePilot);
  assert.equal(subscription.planName, "Pilot access");
  assert.equal(subscription.canCreateUnpublishedDrafts, true);
  assert.equal(subscription.canPublishLive, false);
});

test("shows exact monthly usage and remaining article allowance", () => {
  const presentation = subscriptionPresentation(normalizeSubscription(activePilot));
  assert.equal(presentation.active, true);
  assert.equal(presentation.remaining, 28);
  assert.equal(presentation.usagePercent, 7);
  assert.equal(presentation.allowanceAvailable, true);
  assert.equal(canPlanContent(normalizeSubscription(activePilot)), true);
});

test("fails closed when the plan is inactive or its allowance is exhausted", () => {
  const inactive = normalizeSubscription({ ...activePilot, status: "past_due" });
  const exhausted = normalizeSubscription({
    ...activePilot,
    articles_used_this_month: 30,
  });
  assert.equal(canPlanContent(inactive), false);
  assert.equal(subscriptionPresentation(inactive).statusLabel, "Payment needed");
  assert.equal(canPlanContent(exhausted), false);
  assert.match(subscriptionPresentation(exhausted).planningMessage, /allowance reached/i);
});

test("missing subscription data never enables planning", () => {
  assert.equal(canPlanContent(), false);
  assert.equal(subscriptionPresentation().statusTone, "orange");
});
