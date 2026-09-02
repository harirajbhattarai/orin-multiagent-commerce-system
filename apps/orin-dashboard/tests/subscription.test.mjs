import assert from "node:assert/strict";
import test from "node:test";
import {
  canPlanContent,
  formatPlanPrice,
  normalizePlan,
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
  articles_used_this_period: 2,
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

test("normalizes a paid plan and formats its exact Shopify price", () => {
  const plan = normalizePlan({
    plan_key: "growth",
    display_name: "Growth",
    monthly_price_cents: 7900,
    currency_code: "USD",
    monthly_article_limit: 12,
    team_member_limit: 3,
    trial_days: 7,
    features: ["Automatic scheduling"],
  });
  assert.equal(plan.trialDays, 7);
  assert.equal(plan.monthlyArticleLimit, 12);
  assert.equal(formatPlanPrice(plan), "$79");
});

test("fails closed when the plan is inactive or its allowance is exhausted", () => {
  const inactive = normalizeSubscription({ ...activePilot, status: "past_due" });
  const exhausted = normalizeSubscription({
    ...activePilot,
    articles_used_this_period: 30,
  });
  assert.equal(canPlanContent(inactive), false);
  assert.equal(subscriptionPresentation(inactive).statusLabel, "Payment needed");
  assert.equal(canPlanContent(exhausted), false);
  assert.match(subscriptionPresentation(exhausted).planningMessage, /allowance reached/i);
});

test("expired trials and ended cancellations fail closed in the browser", () => {
  const expiredTrial = normalizeSubscription({
    ...activePilot,
    status: "trialing",
    trial_ends_at: "2020-01-01T00:00:00Z",
  });
  const endedCancellation = normalizeSubscription({
    ...activePilot,
    cancel_at_period_end: true,
    current_period_ends_at: "2020-01-01T00:00:00Z",
  });
  assert.equal(canPlanContent(expiredTrial), false);
  assert.equal(subscriptionPresentation(expiredTrial).statusLabel, "Trial ended");
  assert.equal(canPlanContent(endedCancellation), false);
});

test("an activated Shopify plan stays usable while its free trial is running", () => {
  const trialPlan = normalizeSubscription({
    ...activePilot,
    plan_key: "growth",
    plan_name: "Growth",
    status: "active",
    billing_provider: "shopify",
    trial_ends_at: "2099-01-01T00:00:00Z",
  });
  const presentation = subscriptionPresentation(trialPlan);
  assert.equal(presentation.active, true);
  assert.equal(presentation.statusLabel, "Trial active");
  assert.equal(presentation.allowanceAvailable, true);
});

test("missing subscription data never enables planning", () => {
  assert.equal(canPlanContent(), false);
  assert.equal(subscriptionPresentation().statusTone, "orange");
});
