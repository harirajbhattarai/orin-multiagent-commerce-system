const ACTIVE_STATUSES = new Set(["active", "trialing"]);

function safeInteger(value, fallback = 0) {
  const number = Number(value);
  return Number.isInteger(number) && number >= 0 ? number : fallback;
}

export function normalizeSubscription(row = {}) {
  const limit = Math.max(1, safeInteger(row.monthly_article_limit, 1));
  const used = Math.min(limit, safeInteger(row.articles_used_this_month));
  return {
    planKey: row.plan_key ?? "unavailable",
    planName: row.plan_name ?? "Plan unavailable",
    description: row.description ?? "Subscription details are unavailable.",
    status: row.status ?? "missing",
    billingProvider: row.billing_provider ?? null,
    trialEndsAt: row.trial_ends_at ?? null,
    currentPeriodEndsAt: row.current_period_ends_at ?? null,
    cancelAtPeriodEnd: Boolean(row.cancel_at_period_end),
    monthlyArticleLimit: limit,
    articlesUsedThisMonth: used,
    teamMemberLimit: Math.max(1, safeInteger(row.team_member_limit, 1)),
    canCreateUnpublishedDrafts: row.can_create_unpublished_drafts === true,
    canPublishLive: false,
    features: Array.isArray(row.features) ? row.features.filter(Boolean) : [],
  };
}

export function subscriptionPresentation(subscription = {}) {
  const normalized = normalizeSubscription({
    plan_key: subscription.planKey,
    plan_name: subscription.planName,
    description: subscription.description,
    status: subscription.status,
    billing_provider: subscription.billingProvider,
    trial_ends_at: subscription.trialEndsAt,
    current_period_ends_at: subscription.currentPeriodEndsAt,
    cancel_at_period_end: subscription.cancelAtPeriodEnd,
    monthly_article_limit: subscription.monthlyArticleLimit,
    articles_used_this_month: subscription.articlesUsedThisMonth,
    team_member_limit: subscription.teamMemberLimit,
    can_create_unpublished_drafts: subscription.canCreateUnpublishedDrafts,
    features: subscription.features,
  });
  const active = ACTIVE_STATUSES.has(normalized.status);
  const remaining = Math.max(0, normalized.monthlyArticleLimit - normalized.articlesUsedThisMonth);
  const allowanceAvailable = active && remaining > 0;
  const statusLabels = {
    active: "Active",
    trialing: "Trial active",
    past_due: "Payment needed",
    cancelled: "Cancelled",
    suspended: "Paused",
    missing: "Unavailable",
  };
  return {
    ...normalized,
    active,
    remaining,
    allowanceAvailable,
    usagePercent: Math.min(100, Math.round((normalized.articlesUsedThisMonth / normalized.monthlyArticleLimit) * 100)),
    statusLabel: statusLabels[normalized.status] ?? "Needs attention",
    statusTone: active ? "green" : "orange",
    billingLabel: normalized.billingProvider === "shopify" ? "Billed through Shopify" : "Managed pilot access",
    planningMessage: allowanceAvailable
      ? `${remaining} article${remaining === 1 ? "" : "s"} available this month.`
      : active
        ? "Monthly article allowance reached."
        : "Content planning is paused until the subscription is active.",
  };
}

export function canPlanContent(subscription = {}) {
  return subscriptionPresentation(subscription).allowanceAvailable;
}
