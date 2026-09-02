export const dashboardData = {
  generatedAt: "2026-08-13T13:00:00Z",
  client: {
    id: "hoverboard_store",
    name: "Hoverboard Store",
    shortName: "HS",
    plan: "Pilot access",
  },
  subscription: {
    planKey: "pilot",
    planName: "Pilot access",
    description: "Founding-client access while ORIN Commerce billing is commissioned.",
    status: "active",
    billingProvider: "pilot",
    trialEndsAt: null,
    currentPeriodEndsAt: null,
    cancelAtPeriodEnd: false,
    monthlyArticleLimit: 30,
    articlesUsedThisMonth: 2,
    teamMemberLimit: 3,
    canCreateUnpublishedDrafts: true,
    canPublishLive: false,
    features: [
      "No-code Shopify onboarding",
      "Thirty planned articles each month",
      "Approval-only unpublished drafts",
      "Daily dry-run automation",
      "Read-only watchdog",
    ],
  },
  nextArticle: {
    id: 33,
    contentItemId: "33333333-3333-4333-8333-333333333333",
    version: 1,
    title: "Electric Scooter Safety Gear for Children: A Parent’s Checklist",
    keyword: "electric scooter safety gear for kids",
    intent: "Commercial guide",
    status: "Ready for review",
    dueLabel: "Ready now",
    wordCount: 1248,
    readingTime: "6 min read",
    qualityScore: 92,
    checks: [
      "Safety language checked",
      "No unsupported speed claims",
      "Internal links included",
    ],
  },
  operations: {
    scheduler: "Healthy",
    schedulerTone: "green",
    schedulerDetail: "Safe preview scheduler state.",
    worker: "Online",
    workerTone: "green",
    workerDetail: "Safe preview worker state.",
    watchdog: "Observing",
    watchdogTone: "green",
    watchdogDetail: "Safe preview monitoring state.",
    shopifyWrites: "Approval only",
    shopifyTone: "blue",
    shopifyDetail: "Safe preview decisions never contact Shopify.",
    canApproveConcept: true,
    canApproveHiddenDraft: true,
    isPaused: false,
    maintenancePaused: false,
    workspaceLabel: "Live workspace",
    workspaceMessage: "The controlled content workflow is available.",
    overallTone: "healthy",
    overallLabel: "Everything is protected",
    approvedDraftWritesEnabled: true,
    lastChecked: "Checked moments ago",
  },
  counts: {
    planned: 30,
    drafting: 2,
    review: 3,
    approved: 5,
  },
  recentContent: [
    {
      id: 32,
      title: "Electric Scooter Handlebar Height for Children: Fit Guide",
      stage: "Shopify draft",
      updated: "Today, 20:01",
      owner: "ORIN",
    },
    {
      id: 31,
      title: "Kids Electric Scooter Buying Checklist for Parents",
      stage: "Shopify draft",
      updated: "Today, 11:03",
      owner: "ORIN",
    },
    {
      id: 30,
      title: "Hoverboard Bundle Buying Guide: What Parents Should Compare",
      stage: "Approved",
      updated: "30 Jul, 19:42",
      owner: "You",
    },
  ],
  queue: [
    {
      id: 33,
      contentItemId: "33333333-3333-4333-8333-333333333333",
      version: 1,
      title: "Electric Scooter Safety Gear for Children: A Parent’s Checklist",
      keyword: "electric scooter safety gear for kids",
      stage: "Review",
      status: "Needs you",
      priority: "High",
      due: "Ready now",
    },
    {
      id: 34,
      title: "Hoverboard Battery Care: Charging and Storage Guide",
      keyword: "hoverboard battery care",
      stage: "Drafting",
      status: "Writing",
      priority: "Normal",
      due: "Today",
    },
    {
      id: 35,
      title: "Electric Scooter Tyre Pressure and Everyday Maintenance",
      keyword: "electric scooter tyre pressure",
      stage: "Planned",
      status: "Queued",
      priority: "Normal",
      due: "Tomorrow",
    },
    {
      id: 36,
      title: "Hoverboard Size Guide for Younger and Older Riders",
      keyword: "hoverboard size guide",
      stage: "Planned",
      status: "Queued",
      priority: "Normal",
      due: "4 Aug",
    },
    {
      id: 37,
      title: "Where Can Children Ride Electric Scooters Safely?",
      keyword: "where can kids ride electric scooters",
      stage: "Research",
      status: "Researching",
      priority: "Normal",
      due: "5 Aug",
    },
  ],
  activity: [
    { time: "20:01", label: "Job 32 created as an unpublished Shopify draft" },
    { time: "19:58", label: "Content quality checks passed for Job 32" },
    { time: "11:03", label: "Scheduled dry-run completed with zero Shopify writes" },
    { time: "10:59", label: "Watchdog confirmed the production schedule" },
  ],
  article: {
    id: 33,
    contentItemId: "33333333-3333-4333-8333-333333333333",
    version: 1,
    title: "Electric Scooter Safety Gear for Children: A Parent’s Checklist",
    dek: "A calm, practical guide to choosing everyday protection for young riders, with fit checks parents can repeat before every journey.",
    keyword: "electric scooter safety gear for kids",
    metaTitle: "Electric Scooter Safety Gear for Kids | Parent Checklist",
    metaDescription: "Use this parent-friendly checklist to choose and fit children’s electric scooter safety gear, from helmets to visibility essentials.",
    sections: [
      {
        heading: "Start with the riding environment",
        paragraphs: [
          "The right protective setup starts with where a child will ride, their experience, and the manufacturer’s guidance for the scooter. A quiet, supervised practice area calls for the same careful fit checks as a familiar route.",
          "Before adding any accessory, check that it does not affect steering, braking, visibility, or the rider’s ability to step off safely.",
        ],
      },
      {
        heading: "A helmet that stays in position",
        paragraphs: [
          "Choose a helmet intended for the activity and follow the maker’s sizing instructions. It should sit level, feel secure without pressure points, and remain in place when the rider gently moves their head.",
          "Replace equipment after a significant impact or whenever the manufacturer advises. Damage is not always obvious from the outside.",
        ],
      },
      {
        heading: "Add protection without restricting movement",
        paragraphs: [
          "Wrist, elbow, and knee protection should be snug, correctly oriented, and comfortable through a full range of movement. Loose straps and oversized pads can create new distractions.",
        ],
      },
      {
        heading: "The 60-second pre-ride check",
        bullets: [
          "Helmet level, secure, and comfortable",
          "Pads fastened with no loose straps",
          "Bright clothing and clear visibility",
          "Shoelaces, cuffs, and bags away from moving parts",
          "Scooter checked according to its manual",
        ],
      },
    ],
    evidence: [
      "Draft created from the approved HBStore content plan",
      "Automated checks passed: structure, duplication, safety phrasing",
      "Shopify action is blocked until explicit approval",
      "This prototype records decisions locally only",
    ],
  },
};

export const previewWorkspaces = Object.freeze([
  { id: "hoverboard_store", name: "Hoverboard Store", status: "active", role: "owner" },
  { id: "hcs_gadgets", name: "HCS Gadgets", status: "active", role: "owner" },
]);

function clonePreview(value) {
  return JSON.parse(JSON.stringify(value));
}

export function dashboardPreviewForClient(clientId = "hoverboard_store") {
  if (clientId !== "hcs_gadgets") return clonePreview(dashboardData);

  const data = clonePreview(dashboardData);
  const article = {
    id: 2,
    contentItemId: "22222222-2222-4222-8222-222222222222",
    version: 1,
    reviewKind: "draft",
    title: "Electric Scooter IP Ratings and Water Resistance Explained",
    dek: "A practical UK guide to reading IP ratings, checking manufacturer guidance, and understanding what water resistance does—and does not—cover.",
    keyword: "electric scooter IP rating explained",
    metaTitle: "Electric Scooter IP Ratings and Water Resistance Explained",
    metaDescription: "Understand electric scooter IP ratings, water-resistance limits, and the checks UK buyers should make before riding or storing a scooter.",
    wordCount: 2112,
    readingTime: "10 min read",
    qualityScore: 91,
    sections: [
      {
        heading: "Read the complete rating",
        paragraphs: [
          "An IP code describes controlled test conditions. It is not a promise that every component can tolerate every kind of rain, spray, puddle, or storage environment.",
          "Check the exact model listing and manual, then follow the manufacturer’s cleaning, charging, and storage instructions.",
        ],
      },
      {
        heading: "What buyers should verify",
        bullets: [
          "The IP rating applies to the exact model and revision",
          "Charging instructions are followed in a dry environment",
          "Ports and covers are closed as the manufacturer requires",
          "Any water exposure is handled according to the manual",
        ],
      },
    ],
    evidence: [
      "HCS Gadgets tenant and content version are bound to this review",
      "The HCS article design contract is checked before Shopify approval",
      "Live publishing is unavailable from this dashboard",
    ],
  };

  return {
    ...data,
    client: {
      id: "hcs_gadgets",
      name: "HCS Gadgets",
      shortName: "HCS",
      plan: "Pilot access",
    },
    operations: {
      ...data.operations,
      shopifyWrites: "Writes closed",
      shopifyDetail: "The HCS preview keeps both Shopify write gates closed.",
      canApproveHiddenDraft: false,
      approvedDraftWritesEnabled: false,
      workspaceLabel: "Safe preview",
      workspaceMessage: "HCS Gadgets is isolated in a client-specific preview.",
    },
    counts: { planned: 28, drafting: 0, review: 1, approved: 1 },
    nextArticle: {
      ...article,
      status: "Ready for review",
      dueLabel: "Ready now",
      intent: "Buyer education",
      checks: article.evidence,
    },
    queue: [
      {
        id: 2,
        contentItemId: article.contentItemId,
        version: article.version,
        title: article.title,
        keyword: article.keyword,
        stage: "Review",
        status: "Needs you",
        priority: "High",
        due: "Ready now",
      },
      {
        id: 3,
        title: "Adult Electric Scooter Suspension: What UK Buyers Should Compare",
        keyword: "adult electric scooter suspension guide",
        stage: "Planned",
        status: "Queued",
        priority: "Normal",
        due: "Tomorrow",
      },
    ],
    recentContent: [
      { id: 1, title: "Adult Electric Scooter Suspension: What UK Buyers Should Compare", stage: "Shopify draft", updated: "Today, 12:09", owner: "ORIN" },
    ],
    activity: [
      { time: "12:09", label: "HCS dry-run completed with zero Shopify creates" },
      { time: "11:45", label: "HCS watchdog observed the scheduled run" },
    ],
    article,
  };
}
