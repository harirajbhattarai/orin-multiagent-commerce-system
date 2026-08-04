const REVIEWABLE_STAGES = new Set(["Review"]);

export function reviewJobIdFromPath(pathname) {
  const match = /^\/review\/([1-9]\d*)\/?$/.exec(pathname ?? "");
  if (!match) return null;
  const jobId = Number(match[1]);
  return Number.isSafeInteger(jobId) ? jobId : null;
}

function sameBinding(article, item) {
  return (
    Number(article?.id) === Number(item.id)
    && article?.contentItemId === item.contentItemId
    && article?.version === item.version
  );
}

export function selectRouteBoundReviewArticle(data, jobId) {
  if (!Number.isSafeInteger(jobId)) return null;

  const item = (data?.queue ?? []).find((candidate) => Number(candidate.id) === jobId);
  if (!item || !item.contentItemId || !Number.isInteger(item.version)) return null;

  const isNextArticle = Number(data?.nextArticle?.id) === jobId;
  if (!REVIEWABLE_STAGES.has(item.stage) && !isNextArticle) return null;

  const richArticle = sameBinding(data?.article, item) ? data.article : null;
  const title = item.title || "Untitled content concept";
  const keyword = item.keyword || "Not assigned";

  return {
    ...(richArticle ?? {}),
    id: jobId,
    contentItemId: item.contentItemId,
    version: item.version,
    title,
    keyword,
    dek: richArticle?.dek ?? "Review this version-bound content concept before it enters the controlled drafting workflow.",
    metaTitle: richArticle?.metaTitle ?? title,
    metaDescription: richArticle?.metaDescription ?? "Metadata will be generated and quality-checked during drafting.",
    sections: richArticle?.sections ?? [
      {
        heading: "Content brief",
        paragraphs: [
          `Target keyword: ${keyword}.`,
          `Current workflow stage: ${item.stage}.`,
          "This decision is version-bound and cannot publish or create a Shopify article by itself.",
        ],
      },
    ],
    evidence: richArticle?.evidence ?? [
      "The selected job matches this route exactly",
      "Tenant and content-version binding verified",
      "Shopify publishing is outside this dashboard boundary",
      "All review decisions are immutable and tenant-scoped",
    ],
    readingTime: isNextArticle ? (data.nextArticle.readingTime ?? "Concept review") : "Concept review",
    qualityScore: isNextArticle ? (data.nextArticle.qualityScore ?? null) : null,
  };
}
