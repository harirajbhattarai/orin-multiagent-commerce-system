# ORIN Phase 3.5 content quality

Last updated: 2026-07-26

## Purpose

Phase 3 proved that ORIN can create exactly one unpublished Shopify article
with durable ownership, idempotency, and reconciliation. It did not prove that
the generated article is good enough for a customer-facing SEO product.

Phase 3.5 closes that gap before scheduler transfer.

## Production rule

No Hoverboard Store article may reach the Shopify transaction unless the exact
writer HTML passes the `phase3.5-blog-v2` content-quality contract.

The contract is deterministic and evaluates rendered text. HTML tags, comments,
and metadata do not count toward article length.

## Blocking contract

- At least 1,500 visible words
- SEO title between 30 and 60 characters
- Meta description between 120 and 160 characters
- At least 5 H2 headings
- At least 10 developed paragraphs
- At least 3 FAQ items
- At least 5 distinct internal links
- At least 4 substantive sections
- At least 100 visible words in each substantive section
- H1 represents the target keyword or exactly matches the version-bound,
  human-approved title; the exact target keyword remains mandatory near the
  opening
- Natural target-keyword usage between 2 and 12 exact occurrences
- No repeated substantive paragraphs
- No placeholders or unfinished content
- Quick-answer and CTA blocks present

Failures produce stable `CQ_*` codes in a machine-readable quality receipt.
The receipt is embedded in both the post-write review and job-scoped HTML
validation evidence.

## Current result

The existing deterministic template is intentionally blocked:

- Visible words: 598
- H2 headings: 10
- Paragraphs: 11
- FAQ items: 3
- Internal links: 6
- SEO title: valid
- Meta description: valid
- Blocking reasons: thin content, shallow sections, unnatural keyword usage,
  and repeated paragraphs

This matches the manual observation that the controlled Shopify draft was
technically valid but not useful enough as production SEO content.

## Writer model and adapter

The production writer is pinned to `MiniMax-M3`, matching the dedicated
`orin-hbstore-prod` OpenClaw agent.

The adapter:

- uses MiniMax's OpenAI-compatible HTTPS endpoint directly;
- has no additional Python SDK dependency;
- is disabled by default;
- accepts only a file-backed API credential with mode `0400`;
- rejects incomplete responses, unexpected model names, sensitive-response
  flags, Markdown fences, text outside the expected sentinels, and active or
  document-level HTML tags;
- writes the non-secret request and extracted response to the private run
  evidence directory;
- normalizes the SEO title, meta description, approved handle, target keyword,
  cluster, and job identity from the approved plan before validation, so the
  model cannot introduce random structured-metadata failures;
- never falls back silently to the deterministic template;
- still requires the complete content-quality receipt to pass.

The worker Compose contract includes the writer secret but
`ORIN_MODEL_WRITER_ENABLED` defaults to `0`.

## Isolation

The first contract applies only to Hoverboard Store. HCS Gadgets retains its
existing client-specific validation until it receives a separate quality
profile.

## Verification

- Focused quality-gate tests: 6 passed
- Repository/CI test selection: 113 passed
- HCS isolation and writer tests: 12 passed
- Shopify writes performed: zero
- Scheduler state changed: no
- Supabase runtime gates changed: no

## Next implementation

1. Install a dedicated MiniMax writer credential using
   `deploy/vps/install_writer_secret.sh`. Do not reuse or expose the OpenClaw
   credential store.
2. Keep the deterministic writer as a test fixture and fail-safe fallback only;
   fallback output must remain blocked unless it independently passes the
   contract.
3. Commit, run CI/security review, merge, and deploy the reviewed code while
   keeping `ORIN_MODEL_WRITER_ENABLED=0`.
4. Enable the model writer only for one supervised dry-run with Shopify
   credentials removed from the child process.
5. Produce one local article and its quality receipt without Shopify access.
6. Review the article manually for usefulness, accuracy, tone, and brand fit.
7. If the article requires code or prompt changes, review and deploy those
   changes before any controlled write.
8. Run one controlled hidden-draft test.

Scheduler transfer remains out of scope until Phase 3.5 passes.
