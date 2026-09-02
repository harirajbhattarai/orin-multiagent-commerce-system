const ACTIVE_STATUSES = new Set(["active", "trialing"]);

function safeInteger(value, fallback = 0) {
  const number = Number(value);
  return Number.isInteger(number) && number >= 0 ? number : fallback;
}

export function normalizeSubscription(row = {}) {
  const limit = Math.max(1, safeInteger(row.monthly_article_limit, 1));
  const used = Math.min(limit, safeInteger(row.articles_used_this_period ?? row.articles_used_this_month));
  return {
    planKey: row.plan_key ?? "unavailable",
    planName: row.plan_name ?? "Plan unavailable",
    description: row.description ?? "Subscription details are unavailable.",
    status: row.status ?? "missing",
    billingProvider: row.billing_provider ?? null,
    pendingPlanKey: row.pending_plan_key ?? null,
    pendingPlanName: row.pending_plan_name ?? null,
    trialEndsAt: row.trial_ends_at ?? null,
    currentPeriodStartedAt: row.current_period_started_at ?? null,
    currentPeriodEndsAt: row.current_period_ends_at ?? null,
    usagePeriodStartedAt: row.usage_period_started_at ?? null,
    usagePeriodEndsAt: row.usage_period_ends_at ?? null,
    cancelAtPeriodEnd: Boolean(row.cancel_at_period_end),
    cancelledAt: row.cancelled_at ?? null,
    monthlyArticleLimit: limit,
    articlesUsedThisPeriod: used,
    articlesUsedThisMonth: used,
    teamMemberLimit: Math.max(1, safeInteger(row.team_member_limit, 1)),
    monthlyPriceCents: safeInteger(row.monthly_price_cents),
    currencyCode: /^[A-Z]{3}$/.test(row.currency_code ?? "") ? row.currency_code : "USD",
    canCreateUnpublishedDrafts: row.can_create_unpublished_drafts === true,
    canPublishLive: false,
    features: Array.isArray(row.features) ? row.features.filter(Boolean) : [],
  };
}

export function normalizePlan(row = {}) {
  return {
    planKey: row.plan_key ?? "",
    planName: row.display_name ?? "Plan",
    description: row.description ?? "",
    monthlyPriceCents: safeInteger(row.monthly_price_cents),
    currencyCode: /^[A-Z]{3}$/.test(row.currency_code ?? "") ? row.currency_code : "USD",
    monthlyArticleLimit: Math.max(1, safeInteger(row.monthly_article_limit, 1)),
    teamMemberLimit: Math.max(1, safeInteger(row.team_member_limit, 1)),
    trialDays: Math.min(90, safeInteger(row.trial_days)),
    features: Array.isArray(row.features) ? row.features.filter(Boolean) : [],
    sortOrder: safeInteger(row.sort_order, 100),
  };
}

export function formatPlanPrice(plan = {}) {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: plan.currencyCode ?? "USD",
    maximumFractionDigits: 0,
  }).format((plan.monthlyPriceCents ?? 0) / 100);
}

export function subscriptionPresentation(subscription = {}) {
  const normalized = normalizeSubscription({
    plan_key: subscription.planKey,
    plan_name: subscription.planName,
    description: subscription.description,
    status: subscription.status,
    billing_provider: subscription.billingProvider,
    pending_plan_key: subscription.pendingPlanKey,
    pending_plan_name: subscription.pendingPlanName,
    trial_ends_at: subscription.trialEndsAt,
    current_period_started_at: subscription.currentPeriodStartedAt,
    current_period_ends_at: subscription.currentPeriodEndsAt,
    usage_period_started_at: subscription.usagePeriodStartedAt,
    usage_period_ends_at: subscription.usagePeriodEndsAt,
    cancel_at_period_end: subscription.cancelAtPeriodEnd,
    cancelled_at: subscription.cancelledAt,
    monthly_article_limit: subscription.monthlyArticleLimit,
    articles_used_this_period: subscription.articlesUsedThisPeriod ?? subscription.articlesUsedThisMonth,
    team_member_limit: subscription.teamMemberLimit,
    monthly_price_cents: subscription.monthlyPriceCents,
    currency_code: subscription.currencyCode,
    can_create_unpublished_drafts: subscription.canCreateUnpublishedDrafts,
    features: subscription.features,
  });
  const now = Date.now();
  const freeTrialActive = normalized.billingProvider === "shopify"
    && Number.isFinite(Date.parse(normalized.trialEndsAt))
    && Date.parse(normalized.trialEndsAt) > now;
  const trialExpired = normalized.status === "trialing"
    && Number.isFinite(Date.parse(normalized.trialEndsAt))
    && Date.parse(normalized.trialEndsAt) <= now;
  const cancelledPeriodEnded = normalized.cancelAtPeriodEnd
    && Number.isFinite(Date.parse(normalized.currentPeriodEndsAt))
    && Date.parse(normalized.currentPeriodEndsAt) <= now;
  const active = ACTIVE_STATUSES.has(normalized.status) && !trialExpired && !cancelledPeriodEnded;
  const remaining = Math.max(0, normalized.monthlyArticleLimit - normalized.articlesUsedThisPeriod);
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
    usagePercent: Math.min(100, Math.round((normalized.articlesUsedThisPeriod / normalized.monthlyArticleLimit) * 100)),
    statusLabel: normalized.cancelAtPeriodEnd
      ? "Cancels at period end"
      : freeTrialActive ? "Trial active"
      : trialExpired ? "Trial ended" : statusLabels[normalized.status] ?? "Needs attention",
    statusTone: active ? "green" : "orange",
    billingLabel: normalized.billingProvider === "shopify"
      ? "Billed through Shopify"
      : normalized.planKey === "trial" ? "Free trial" : "Grandfathered pilot",
    planningMessage: allowanceAvailable
      ? `${remaining} article${remaining === 1 ? "" : "s"} available this billing period.`
      : active
        ? "Article allowance reached for this billing period."
        : "Content planning is paused until the subscription is active.",
  };
}

export function canPlanContent(subscription = {}) {
  return subscriptionPresentation(subscription).allowanceAvailable;
}
