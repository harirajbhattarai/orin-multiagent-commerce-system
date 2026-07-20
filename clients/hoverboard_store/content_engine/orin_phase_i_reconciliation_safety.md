# ORIN Phase I8 — Already-Created Reconciliation Safety

**Report Date:** 2026-07-08
**Phase:** I8 — Already-Created Reconciliation Safety

---

## Reconciliation Branch Goal

To safely reconcile queue status for jobs already existing in Shopify as drafts, but where the queue still shows `Status: planned`.

**Trigger:** `publisher_decision == ALREADY_CREATED_QUEUE_RECONCILIATION_REQUIRED`

## Pre-Conditions for Reconciliation (all required)

| Check | Failure |
|---|---|
| Existing Shopify article ID (from Publisher) matches selected job | `BLOCK_SELF_MATCH_IDENTITY_MISMATCH` |
| Existing article `title` matches expected | `BLOCK_SELF_MATCH_IDENTITY_MISMATCH` |
| Existing article `handle` matches expected | `BLOCK_SELF_MATCH_IDENTITY_MISMATCH` |
| Existing article `published_at` is `null` | `BLOCK_EXISTING_DRAFT_NOT_HIDDEN` |
| Existing article is draft/hidden | `BLOCK_EXISTING_DRAFT_NOT_HIDDEN` |
| Fetched Shopify body SHA256 == expected local Writer SHA256 | `BLOCK_EXISTING_DRAFT_BODY_MISMATCH` |

## Reconciliation Process

1. Fetch existing Shopify Article ID (from Publisher preflight result).
2. Fetch the exact existing article from Shopify by ID.
3. Verify all identity and status invariants (title, handle, `published_at=null`, draft status).
4. Resolve the expected Writer artifact (local HTML and SHA256).
5. Compare fetched Shopify body SHA256 against expected local Writer SHA256.
6. **ONLY IF** body hash matches: Allow queue reconciliation `planned → draft_created`.

## Unsafe Reconciliation Scenarios (BLOCKING)

| Scenario | Decision |
|---|---|
| Existing draft has body hash mismatch | `BLOCK_EXISTING_DRAFT_BODY_MISMATCH` |
| Existing draft is published (not hidden) | `BLOCK_EXISTING_DRAFT_NOT_HIDDEN` |
| Existing draft belongs to different job (ID/title/handle mismatch) | `BLOCK_SELF_MATCH_IDENTITY_MISMATCH` |

## Reconciliation Regressions (Phase I8 §51) — *Design Only*

*(These regressions are designed to be run once the reconciliation logic is implemented, but were not executed in Phase I due to the overall `STOP` condition.)*

| Case | Scenario | Expected Decision |
|---|---|---|
| A | Existing verified draft + matching body + queue planned | `QUEUE_FINALISATION_APPROVED` (for reconciliation) |
| B | Existing draft + body hash mismatch | `BLOCK_EXISTING_DRAFT_BODY_MISMATCH` |
| C | Existing draft + `published_at` non-null | `BLOCK_EXISTING_DRAFT_NOT_HIDDEN` |
| D | Existing draft belongs to different job | `BLOCK_SELF_MATCH_IDENTITY_MISMATCH` |

## Phase I8 Status

**Reconciliation safety NOT executed** —原因是 Phase I6 stopped at body verification failure. This phase will be addressed in a future development cycle when body hash verification can be reliably performed.

**Queue status for Job 21:** remains `planned`

**Note:** The recovery path for reconciliation (`ALREADY_CREATED_QUEUE_RECONCILIATION_REQUIRED`) is distinct from new draft creation. It is not currently callable by the pipeline due to the Phase I `STOP`.
