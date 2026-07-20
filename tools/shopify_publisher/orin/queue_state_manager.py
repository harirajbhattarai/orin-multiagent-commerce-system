"""
ORIN Phase I7 — Canonical Selected-Job Queue Finaliser

tools/shopify_publisher/orin/queue_state_manager.py

Safe queue finalisation for selected job:
1. Verifies selected job identity
2. Verifies current queue status is 'planned'
3. Verifies Shopify verification passed
4. Updates Job 21 status: planned → draft_created
5. Records Shopify article ID, handle, timestamp
6. Creates timestamped queue backup
7. Atomic write with verification

Allowed transition: planned → draft_created
No other transitions allowed.
"""

from __future__ import annotations

import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ── Decision constants ────────────────────────────────────────────────────────

QUEUE_FINALISATION_APPROVED = "QUEUE_FINALISATION_APPROVED"
QUEUE_BLOCKED_INVALID_TRANSITION = "BLOCK_INVALID_QUEUE_STATE_TRANSITION"
QUEUE_BLOCKED_VERIFICATION_NOT_PASSED = "BLOCK_SHOPIFY_VERIFICATION_NOT_PASSED"
QUEUE_BLOCKED_JOB_MISMATCH = "BLOCK_JOB_CONTEXT_MISMATCH"
QUEUE_BLOCKED_ID_MISMATCH = "BLOCK_ARTICLE_ID_MISMATCH"
QUEUE_BLOCKED_HANDLE_MISMATCH = "BLOCK_HANDLE_MISMATCH"
QUEUE_BLOCKED_PUBLISHED_AT_NOT_NULL = "BLOCK_PUBLISHED_AT_NOT_NULL"
QUEUE_BLOCKED_UPDATE_FAILED = "BLOCK_QUEUE_UPDATE_FAILED"
QUEUE_BLOCKED_VERIFICATION_FAILED = "QUEUE_FINALISATION_VERIFICATION_FAILED"
QUEUE_BLOCKED_UNEXPECTED_ERROR = "BLOCK_UNEXPECTED_ERROR"

# Human-review decision constants
QUEUE_NEEDS_HUMAN_REVIEW_COMMITTED = "QUEUE_NEEDS_HUMAN_REVIEW_COMMITTED"
QUEUE_COMMIT_BLOCKED_INVALID_STATE = "BLOCK_COMMIT_INVALID_STATE"
QUEUE_COMMIT_BLOCKED_JOB_MISMATCH = "BLOCK_COMMIT_JOB_MISMATCH"
QUEUE_COMMIT_BLOCKED_TRANSITION_REJECTED = "BLOCK_COMMIT_TRANSITION_REJECTED"

QUEUE_TRANSITION_ALLOWED = {
    "planned": ["draft_created", "needs_human_review"],
    "draft_created": [],       # no further transitions
    "needs_human_review": [],  # no automatic transitions — human decides
    "published": [],           # no further transitions
    "archived": [],            # no further transitions
}

QUEUE_ALLOWED_TRANSITIONS = frozenset([
    QUEUE_FINALISATION_APPROVED,
])


def get_current_timestamp() -> str:
    """Return current UTC timestamp in ISO format."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")


def parse_queue_file(queue_path: str) -> tuple[list[dict], str | None]:
    """
    Parse the Hoverboard Store production queue markdown file.
    Format: ## Job {number} followed by indented key: value fields.
    Returns (jobs_list, error_or_none).
    """
    content = Path(queue_path).read_text(encoding="utf-8")
    jobs = []
    # Match ## Job {number}  (production queue format)
    header_re = re.compile(r"^## Job (\d+)\s*$")
    # Key-value fields: 0-4 leading spaces, key, colon, value
    field_re = re.compile(r"^\s{0,4}(\w[\w\s/-]*?):\s+(.+)$")

    current_job = None
    for line in content.splitlines():
        hm = header_re.match(line.rstrip())
        if hm:
            if current_job:
                jobs.append(current_job)
            current_job = {
                "job_number": hm.group(1),
                "title": "",   # Title extracted from Topic field, not header
            }
            continue
        if current_job:
            fm = field_re.match(line)
            if fm:
                key = fm.group(1).strip()
                val = fm.group(2).strip()
                current_job[key] = val
    if current_job:
        jobs.append(current_job)
    return jobs, None


def build_queue_backup_path(queue_path: str) -> str:
    """Generate timestamped backup path for the queue file."""
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    p = Path(queue_path)
    return str(p.parent / f"{p.stem}_backup_{ts}{p.suffix}")


def write_queue_with_job_update(
    queue_path: str,
    backup_path: str,
    job_number: str,
    updates: dict,
) -> tuple[bool, str | None]:
    """
    Read queue, update only the specified job, write to backup then atomic-replace.
    Returns (success, error_or_none).
    """
    try:
        content = Path(queue_path).read_text(encoding="utf-8")
    except Exception as e:
        return False, f"Cannot read queue: {e}"

    # Create backup
    try:
        shutil.copy2(queue_path, backup_path)
    except Exception as e:
        return False, f"Cannot create backup: {e}"

    lines = content.splitlines()
    updated_lines = []
    current_job = None
    job_found = False   # True once updates have been written for target job
    in_target_job = False  # True while processing fields of target job
    updates_written = False  # True once updates are added (right after header)

    header_re = re.compile(r"^## Job (\d+)\s*$")
    # Key-value fields: 0-4 leading spaces, key, colon, value
    field_re = re.compile(r"^\s{0,4}(\w[\w\s/-]*?):\s+(.+)$")

    i = 0
    while i < len(lines):
        line = lines[i]
        hm = header_re.match(line.rstrip())
        if hm:
            # Close previous target job if still open
            if current_job and in_target_job and not job_found:
                # Header seen but no fields processed yet — add updates now
                for k, v in updates.items():
                    updated_lines.append(f"{k}: {v}")
                job_found = True
            # Reset for new job
            current_job = {"_raw": line}
            in_target_job = (hm.group(1) == job_number)
            updates_written = False
            job_found = False
            if in_target_job:
                # Add header THEN immediately add all updates
                updated_lines.append(line)
                for k, v in updates.items():
                    updated_lines.append(f"{k}: {v}")
                job_found = True
                updates_written = True
            else:
                updated_lines.append(line)
            i += 1
            continue

        if current_job is not None:
            fm = field_re.match(line)
            if fm:
                key = fm.group(1).strip()
                if in_target_job:
                    # For target job: skip fields that are being updated (already written)
                    # Copy fields that are NOT being updated (preserve them)
                    if key not in updates:
                        updated_lines.append(line)
                    i += 1
                    continue
                else:
                    updated_lines.append(line)
                    i += 1
                    continue

        # Non-field line (blank, comment, etc.)
        if in_target_job and not job_found:
            # We are in target job but haven't written updates yet
            # (this happens when target job has no fields before this blank line)
            for k, v in updates.items():
                updated_lines.append(f"{k}: {v}")
            job_found = True
        updated_lines.append(line)
        i += 1

    # Final close: if we ended inside target job block without reaching job_found
    if in_target_job and not job_found:
        for k, v in updates.items():
            updated_lines.append(f"{k}: {v}")
        job_found = True

    new_content = "\n".join(updated_lines) + "\n"

    # Atomic replace
    tmp_path = queue_path + ".tmp"
    try:
        Path(tmp_path).write_text(new_content, encoding="utf-8")
        Path(tmp_path).replace(queue_path)
    except Exception as e:
        return False, f"Cannot write queue: {e}"

    return True, None


def finalize_draft_created(
    queue_path: str,
    job_number: str,
    shopify_article_id: int | str,
    shopify_handle: str,
    draft_created_at: str,
    published_at: str | None,
    # Verification passthrough
    shopify_verification_passed: bool = False,
    expected_article_id: int | str | None = None,
    expected_handle: str | None = None,
    # Durable evidence reference
    run_dir: str | None = None,
) -> dict:
    """
    Canonical selected-job queue finaliser.

    Allowed transition: planned → draft_created

    Returns structured result with decision, approved, and details.
    """
    blockers = []
    job_number_str = str(job_number)

    # ── Precondition: Shopify verification must have passed ─────────────
    if not shopify_verification_passed:
        blockers.append(QUEUE_BLOCKED_VERIFICATION_NOT_PASSED)
        return _make_result(
            decision=QUEUE_BLOCKED_VERIFICATION_NOT_PASSED,
            approved=False,
            blockers=blockers,
            message="Shopify draft verification did not pass. Cannot finalise queue.",
            job_number=job_number_str,
        )

    # ── Parse queue ────────────────────────────────────────────────────
    jobs, parse_err = parse_queue_file(queue_path)
    if parse_err:
        blockers.append(QUEUE_BLOCKED_UPDATE_FAILED)
        return _make_result(
            decision=QUEUE_BLOCKED_UPDATE_FAILED,
            approved=False,
            blockers=blockers,
            message=f"Queue parse failed: {parse_err}",
            job_number=job_number_str,
        )

    # ── Find selected job ───────────────────────────────────────────────
    target_job = None
    for job in jobs:
        if str(job.get("job_number", "")) == job_number_str:
            target_job = job
            break

    if target_job is None:
        blockers.append(QUEUE_BLOCKED_JOB_MISMATCH)
        return _make_result(
            decision=QUEUE_BLOCKED_JOB_MISMATCH,
            approved=False,
            blockers=blockers,
            message=f"Job {job_number_str} not found in queue.",
            job_number=job_number_str,
        )

    # ── Verify current status is 'planned' ─────────────────────────────
    current_status = target_job.get("Status", "").strip().lower()
    if current_status != "planned":
        blockers.append(QUEUE_BLOCKED_INVALID_TRANSITION)
        return _make_result(
            decision=QUEUE_BLOCKED_INVALID_TRANSITION,
            approved=False,
            blockers=blockers,
            message=(
                f"Job {job_number_str} status is '{current_status}', expected 'planned'. "
                f"Only 'planned → draft_created' transition is allowed."
            ),
            job_number=job_number_str,
            current_status=current_status,
        )

    # ── Verify article ID matches expected ──────────────────────────────
    if expected_article_id is not None:
        actual_id = str(shopify_article_id)
        expected_id_str = str(expected_article_id)
        if actual_id != expected_id_str:
            blockers.append(QUEUE_BLOCKED_ID_MISMATCH)
            return _make_result(
                decision=QUEUE_BLOCKED_ID_MISMATCH,
                approved=False,
                blockers=blockers,
                message=(
                    f"Shopify article ID mismatch. "
                    f"Expected: {expected_id_str}, Got: {actual_id}"
                ),
                job_number=job_number_str,
                shopify_article_id=str(shopify_article_id),
                expected_article_id=expected_id_str,
            )

    # ── Verify handle matches expected ────────────────────────────────
    if expected_handle is not None:
        if shopify_handle != expected_handle:
            blockers.append(QUEUE_BLOCKED_HANDLE_MISMATCH)
            return _make_result(
                decision=QUEUE_BLOCKED_HANDLE_MISMATCH,
                approved=False,
                blockers=blockers,
                message=(
                    f"Shopify handle mismatch. "
                    f"Expected: {expected_handle!r}, Got: {shopify_handle!r}"
                ),
                job_number=job_number_str,
                shopify_handle=shopify_handle,
                expected_handle=expected_handle,
            )

    # ── Verify published_at is null ───────────────────────────────────
    if published_at is not None:
        blockers.append(QUEUE_BLOCKED_PUBLISHED_AT_NOT_NULL)
        return _make_result(
            decision=QUEUE_BLOCKED_PUBLISHED_AT_NOT_NULL,
            approved=False,
            blockers=blockers,
            message=f"published_at must be null for draft_created. Got: {published_at!r}",
            job_number=job_number_str,
            published_at=published_at,
        )

    # ── Build updates ───────────────────────────────────────────────────
    updates = {
        "Status": "draft_created",
        "Article ID": str(shopify_article_id),
        "Handle": shopify_handle,
        "Draft Created At": draft_created_at,
        "published_at": "null",
        "Last Updated": get_current_timestamp(),
    }
    # Persist the durable transaction evidence path so the run_dir is
    # recoverable from the queue record without needing to trace commit calls.
    if run_dir:
        updates["Transaction Evidence"] = run_dir

    # ── Create backup ───────────────────────────────────────────────────
    backup_path = build_queue_backup_path(queue_path)

    # ── Write queue update ───────────────────────────────────────────────
    success, write_err = write_queue_with_job_update(
        queue_path=queue_path,
        backup_path=backup_path,
        job_number=job_number_str,
        updates=updates,
    )

    if not success:
        blockers.append(QUEUE_BLOCKED_UPDATE_FAILED)
        return _make_result(
            decision=QUEUE_BLOCKED_UPDATE_FAILED,
            approved=False,
            blockers=blockers,
            message=f"Queue update failed: {write_err}",
            job_number=job_number_str,
            backup_path=backup_path,
        )

    # ── Verify queue update ────────────────────────────────────────────
    verify_jobs, _ = parse_queue_file(queue_path)
    verify_job = None
    for j in verify_jobs:
        if str(j.get("job_number", "")) == job_number_str:
            verify_job = j
            break

    if verify_job is None:
        blockers.append(QUEUE_BLOCKED_VERIFICATION_FAILED)
        return _make_result(
            decision=QUEUE_BLOCKED_VERIFICATION_FAILED,
            approved=False,
            blockers=blockers,
            message="Job disappeared from queue after write.",
            job_number=job_number_str,
        )

    verify_status = verify_job.get("Status", "").strip()
    verify_article_id = verify_job.get("Article ID", "").strip()
    verify_handle = verify_job.get("Handle", "").strip()

    if verify_status != "draft_created":
        blockers.append(QUEUE_BLOCKED_VERIFICATION_FAILED)
        return _make_result(
            decision=QUEUE_BLOCKED_VERIFICATION_FAILED,
            approved=False,
            blockers=blockers,
            message=f"Queue verification failed: status={verify_status!r}, expected 'draft_created'",
            job_number=job_number_str,
        )

    if verify_article_id != str(shopify_article_id):
        blockers.append(QUEUE_BLOCKED_VERIFICATION_FAILED)
        return _make_result(
            decision=QUEUE_BLOCKED_VERIFICATION_FAILED,
            approved=False,
            blockers=blockers,
            message=f"Queue verification failed: Article ID={verify_article_id!r}",
            job_number=job_number_str,
        )

    if verify_handle != shopify_handle:
        blockers.append(QUEUE_BLOCKED_VERIFICATION_FAILED)
        return _make_result(
            decision=QUEUE_BLOCKED_VERIFICATION_FAILED,
            approved=False,
            blockers=blockers,
            message=f"Queue verification failed: Handle={verify_handle!r}",
            job_number=job_number_str,
        )

    # ── Success ─────────────────────────────────────────────────────────
    return _make_result(
        decision=QUEUE_FINALISATION_APPROVED,
        approved=True,
        blockers=[],
        message=f"Job {job_number_str} queue finalised: planned → draft_created.",
        job_number=job_number_str,
        queue_status_before="planned",
        queue_status_after="draft_created",
        shopify_article_id=str(shopify_article_id),
        shopify_handle=shopify_handle,
        draft_created_at=draft_created_at,
        published_at=published_at,
        backup_path=backup_path,
        queue_verified=True,
        run_dir=run_dir,
    )


# ── Commit: needs_human_review ───────────────────────────────────────────────


def commit_job_needs_human_review(
    queue_path: str,
    job_number: str,
    shopify_article_id: int | str | None = None,
    failure_reason: str = "",
    failure_code: str = "",
    recovery_action: str = "AWAITING_HUMAN_REVIEW",
    failure_artifact_path: str = "",
    notes: str = "",
) -> dict:
    """
    Commit a Shopify transaction failure requiring human review to the queue.

    Allowed transition: planned → needs_human_review ONLY.
    Idempotent: if job is already needs_human_review and article_id matches,
    returns success without re-writing.

    Returns structured result with decision, approved, and details.
    """
    blockers = []
    job_number_str = str(job_number)
    ts = get_current_timestamp()

    # ── Parse queue ────────────────────────────────────────────────────
    jobs, parse_err = parse_queue_file(queue_path)
    if parse_err:
        blockers.append(QUEUE_BLOCKED_UPDATE_FAILED)
        return _make_result(
            decision=QUEUE_BLOCKED_UPDATE_FAILED,
            approved=False,
            blockers=blockers,
            message=f"Queue parse failed: {parse_err}",
            job_number=job_number_str,
        )

    # ── Find target job ────────────────────────────────────────────────
    target_job = None
    for job in jobs:
        if str(job.get("job_number", "")) == job_number_str:
            target_job = job
            break

    if target_job is None:
        blockers.append(QUEUE_BLOCKED_JOB_MISMATCH)
        return _make_result(
            decision=QUEUE_BLOCKED_JOB_MISMATCH,
            approved=False,
            blockers=blockers,
            message=f"Job {job_number_str} not found in queue.",
            job_number=job_number_str,
        )

    # ── Verify current status allows transition ─────────────────────────
    current_status = target_job.get("Status", "").strip().lower()
    allowed = QUEUE_TRANSITION_ALLOWED.get(current_status, [])
    if "needs_human_review" not in allowed:
        # Idempotency: if already needs_human_review, check article_id match
        if current_status == "needs_human_review":
            existing_article_id = target_job.get("Article ID", "").strip()
            incoming_article_id = str(shopify_article_id) if shopify_article_id else ""
            if incoming_article_id and existing_article_id == incoming_article_id:
                # Idempotent replay — no-op success
                return _make_result(
                    decision=QUEUE_NEEDS_HUMAN_REVIEW_COMMITTED,
                    approved=True,
                    blockers=[],
                    message=f"Job {job_number_str} already needs_human_review with matching article ID — idempotent replay.",
                    job_number=job_number_str,
                    queue_status_before=current_status,
                    queue_status_after=current_status,
                    idempotent=True,
                )
            elif not incoming_article_id:
                # No article ID to compare — treat as idempotent
                return _make_result(
                    decision=QUEUE_NEEDS_HUMAN_REVIEW_COMMITTED,
                    approved=True,
                    blockers=[],
                    message=f"Job {job_number_str} already needs_human_review — idempotent replay.",
                    job_number=job_number_str,
                    queue_status_before=current_status,
                    queue_status_after=current_status,
                    idempotent=True,
                )
        # Not idempotent — reject
        blockers.append(QUEUE_COMMIT_BLOCKED_INVALID_STATE)
        return _make_result(
            decision=QUEUE_COMMIT_BLOCKED_INVALID_STATE,
            approved=False,
            blockers=blockers,
            message=(
                f"Job {job_number_str} cannot transition to needs_human_review: "
                f"current status={current_status!r}, allowed={allowed}. "
                f"Only 'planned → needs_human_review' is allowed."
            ),
            job_number=job_number_str,
            current_status=current_status,
        )

    # ── Build updates ───────────────────────────────────────────────────
    updates = {
        "Status": "needs_human_review",
        "Last Updated": ts,
        "Failure Reason": failure_reason or "Post-fetch verification failed",
        "Failure Code": failure_code or "VERIFICATION_FAILED",
        "Recovery Action": recovery_action,
    }
    if shopify_article_id is not None:
        updates["Article ID"] = str(shopify_article_id)
    if failure_artifact_path:
        updates["Failure Artifact"] = failure_artifact_path
    if notes:
        updates["Notes"] = notes

    # ── Create backup ───────────────────────────────────────────────────
    backup_path = build_queue_backup_path(queue_path)

    # ── Write queue update ───────────────────────────────────────────────
    success, write_err = write_queue_with_job_update(
        queue_path=queue_path,
        backup_path=backup_path,
        job_number=job_number_str,
        updates=updates,
    )

    if not success:
        blockers.append(QUEUE_BLOCKED_UPDATE_FAILED)
        return _make_result(
            decision=QUEUE_BLOCKED_UPDATE_FAILED,
            approved=False,
            blockers=blockers,
            message=f"Queue update failed: {write_err}",
            job_number=job_number_str,
            backup_path=backup_path,
        )

    # ── Verify queue update ────────────────────────────────────────────
    verify_jobs, _ = parse_queue_file(queue_path)
    verify_job = None
    for j in verify_jobs:
        if str(j.get("job_number", "")) == job_number_str:
            verify_job = j
            break

    if verify_job is None:
        blockers.append(QUEUE_BLOCKED_UPDATE_FAILED)
        return _make_result(
            decision=QUEUE_BLOCKED_UPDATE_FAILED,
            approved=False,
            blockers=blockers,
            message="Job disappeared from queue after write.",
            job_number=job_number_str,
        )

    verify_status = verify_job.get("Status", "").strip()
    if verify_status != "needs_human_review":
        blockers.append(QUEUE_BLOCKED_UPDATE_FAILED)
        return _make_result(
            decision=QUEUE_BLOCKED_UPDATE_FAILED,
            approved=False,
            blockers=blockers,
            message=f"Queue verification failed: status={verify_status!r}, expected 'needs_human_review'",
            job_number=job_number_str,
        )

    # ── Success ─────────────────────────────────────────────────────────
    return _make_result(
        decision=QUEUE_NEEDS_HUMAN_REVIEW_COMMITTED,
        approved=True,
        blockers=[],
        message=f"Job {job_number_str} committed to needs_human_review: planned → needs_human_review.",
        job_number=job_number_str,
        queue_status_before="planned",
        queue_status_after="needs_human_review",
        shopify_article_id=str(shopify_article_id) if shopify_article_id else None,
        failure_reason=failure_reason,
        failure_code=failure_code,
        recovery_action=recovery_action,
        failure_artifact_path=failure_artifact_path,
        backup_path=backup_path,
    )


# ── Orchestration: transaction result → queue state ───────────────────────────

# Decision constants — SINGLE SOURCE OF TRUTH: shopify_draft_transaction.py.
# Do NOT maintain independent copies here. Import them directly.
# All queue commit decision-routing depends on exact string match with
# shopify_draft_transaction.py constant values.
from shopify_draft_transaction import (
    TRANSACTION_APPROVED_DRAFT_CREATED,
    TRANSACTION_BLOCKED_VERIFICATION_FAILED,
    TRANSACTION_BLOCKED_GATE_NOT_APPROVED,
)


# ── Historical State Reconciliation ──────────────────────────────────────

RECONCILE_DRAFT_CREATED_TO_HUMAN_REVIEW = "RECONCILE_DRAFT_CREATED_TO_HUMAN_REVIEW"
RECONCILE_BLOCKED_NO_CONFIRMATION = "RECONCILE_BLOCKED_NO_CONFIRMATION"
RECONCILE_BLOCKED_JOB_MISMATCH = "RECONCILE_BLOCKED_JOB_MISMATCH"
RECONCILE_BLOCKED_NOT_DRAFT_CREATED = "RECONCILE_BLOCKED_NOT_DRAFT_CREATED"
RECONCILE_BLOCKED_ARTICLE_MISMATCH = "RECONCILE_BLOCKED_ARTICLE_MISMATCH"


def reconcile_job_from_draft_created_to_needs_human_review(
    queue_path: str,
    job_number: str,
    shopify_article_id: int | str | None = None,
    failure_code: str = "",
    notes: str = "",
) -> dict:
    """
    Narrowly scoped reconciliation for confirmed historical state correction.

    Allows: draft_created → needs_human_review

    This function is NOT a general transition function. It exists solely for
    cases where a job was incorrectly committed to draft_created using an
    unapproved verification tier or unapproved gate override, and must be
    returned to needs_human_review for proper human review.

    Idempotent: if job is already needs_human_review and article_id matches,
    returns success without re-writing.

    Required confirmation inputs:
    - job_number must match an existing job
    - current status must be exactly draft_created
    - shopify_article_id must match the recorded article_id (if provided)
    - failure_code must be non-empty
    """
    blockers: list[str] = []
    job_number_str = str(job_number)
    ts = get_current_timestamp()

    # ── Validate required inputs ───────────────────────────────────────
    if not job_number_str:
        blockers.append(RECONCILE_BLOCKED_NO_CONFIRMATION)
        return _make_result(
            decision=RECONCILE_BLOCKED_NO_CONFIRMATION,
            approved=False,
            blockers=blockers,
            message="job_number is required for reconciliation",
        )

    if not failure_code:
        blockers.append(RECONCILE_BLOCKED_NO_CONFIRMATION)
        return _make_result(
            decision=RECONCILE_BLOCKED_NO_CONFIRMATION,
            approved=False,
            blockers=blockers,
            message="failure_code is required for reconciliation",
        )

    # ── Parse queue ────────────────────────────────────────────────────
    jobs, parse_err = parse_queue_file(queue_path)
    if parse_err:
        blockers.append(QUEUE_BLOCKED_UPDATE_FAILED)
        return _make_result(
            decision=QUEUE_BLOCKED_UPDATE_FAILED,
            approved=False,
            blockers=blockers,
            message=f"Queue parse failed: {parse_err}",
            job_number=job_number_str,
        )

    # ── Find target job ────────────────────────────────────────────────
    target_job = None
    for job in jobs:
        if str(job.get("job_number", "")) == job_number_str:
            target_job = job
            break

    if target_job is None:
        blockers.append(RECONCILE_BLOCKED_JOB_MISMATCH)
        return _make_result(
            decision=RECONCILE_BLOCKED_JOB_MISMATCH,
            approved=False,
            blockers=blockers,
            message=f"Job {job_number_str} not found in queue",
            job_number=job_number_str,
        )

    # ── Verify current status is draft_created ─────────────────────────
    current_status = target_job.get("Status", "")
    if current_status != "draft_created":
        blockers.append(RECONCILE_BLOCKED_NOT_DRAFT_CREATED)
        return _make_result(
            decision=RECONCILE_BLOCKED_NOT_DRAFT_CREATED,
            approved=False,
            blockers=blockers,
            message=(
                f"Job {job_number_str} is '{current_status}', not 'draft_created'. "
                "Reconciliation only allowed from 'draft_created'."
            ),
            job_number=job_number_str,
            current_status=current_status,
        )

    # ── Verify article_id matches if provided ───────────────────────────
    recorded_article_id = str(target_job.get("Article ID", "")).strip()
    if shopify_article_id is not None:
        provided_article_id = str(shopify_article_id).strip()
        if recorded_article_id and recorded_article_id != provided_article_id:
            blockers.append(RECONCILE_BLOCKED_ARTICLE_MISMATCH)
            return _make_result(
                decision=RECONCILE_BLOCKED_ARTICLE_MISMATCH,
                approved=False,
                blockers=blockers,
                message=(
                    f"Article ID mismatch. Recorded: {recorded_article_id}, "
                    f"Provided: {provided_article_id}."
                ),
                job_number=job_number_str,
                recorded_article_id=recorded_article_id,
                provided_article_id=provided_article_id,
            )

    # ── Idempotency: already needs_human_review with same failure_code ─
    existing_failure = target_job.get("Failure Reason", "") or target_job.get("failure_reason", "")
    if existing_failure == failure_code and current_status == "needs_human_review":
        return _make_result(
            decision=RECONCILE_DRAFT_CREATED_TO_HUMAN_REVIEW,
            approved=True,
            blockers=[],
            message=f"Job {job_number_str} already reconciled to needs_human_review.",
            job_number=job_number_str,
            queue_status_before="needs_human_review",
            queue_status_after="needs_human_review",
            shopify_article_id=shopify_article_id,
            failure_code=failure_code,
            notes=notes,
        )

    # ── Apply reconciliation ───────────────────────────────────────────
    updated_fields = {
        "Status": "needs_human_review",
        "Last Updated": ts,
        "Failure Reason": failure_code,
        "Recovery Action": "AWAITING_HUMAN_REVIEW",
    }
    if notes:
        updated_fields["Reconciliation Note"] = notes

    backup_path = build_queue_backup_path(queue_path)
    success, write_err = write_queue_with_job_update(
        queue_path=queue_path,
        backup_path=backup_path,
        job_number=job_number_str,
        updates=updated_fields,
    )
    if write_err:
        blockers.append(QUEUE_BLOCKED_UPDATE_FAILED)
        return _make_result(
            decision=QUEUE_BLOCKED_UPDATE_FAILED,
            approved=False,
            blockers=blockers,
            message=f"Queue write failed: {write_err}",
            job_number=job_number_str,
        )

    return _make_result(
        decision=RECONCILE_DRAFT_CREATED_TO_HUMAN_REVIEW,
        approved=True,
        blockers=[],
        message=f"Job {job_number_str} reconciled: draft_created → needs_human_review.",
        job_number=job_number_str,
        queue_status_before="draft_created",
        queue_status_after="needs_human_review",
        shopify_article_id=str(shopify_article_id) if shopify_article_id else recorded_article_id,
        failure_code=failure_code,
        notes=notes,
    )


def commit_transaction_result(
    queue_path: str,
    transaction_result: dict,
    dry_run: bool = False,
) -> dict:
    """
    Orchestration-layer commit function.

    Accepts a structured transaction result from run_safe_draft_transaction()
    and commits the appropriate queue state transition.

    Architecture rule: shopify_draft_transaction.py does NOT own global queue mutation.
    This function (in the ORIN orchestration/state layer) owns authoritative queue
    transitions based on transaction facts.

    Rules:
    - On verified success (TRANSACTION_APPROVED_DRAFT_CREATED) AND approved=True:
        planned → draft_created
    - On verification failure (TRANSACTION_BLOCKED_VERIFICATION_FAILED):
        planned → needs_human_review
    - On other failure (gate rejected, context mismatch, etc.):
        queue NOT mutated — return blockers
    - In dry_run mode: queue NOT mutated — return planned action
    - Idempotent: replaying same result does not corrupt state

    Args:
        queue_path: path to authoritative queue markdown file
        transaction_result: structured result from run_safe_draft_transaction()
        dry_run: if True, validate and return planned action without mutating queue

    Returns structured commit result.
    """
    decision = transaction_result.get("decision", "")
    approved = transaction_result.get("approved", False)
    job_number = str(transaction_result.get("job_number", ""))

    if not job_number:
        return _make_result(
            decision="BLOCK_COMMIT_NO_JOB_NUMBER",
            approved=False,
            blockers=["commit_transaction_result requires job_number in transaction_result"],
            message="Transaction result has no job_number — cannot commit.",
        )

    # DRY-RUN: validate without mutating
    if dry_run:
        if decision == TRANSACTION_APPROVED_DRAFT_CREATED and approved:
            return _make_result(
                decision="DRY_RUN_WOULD_COMMIT_DRAFT_CREATED",
                approved=True,
                blockers=[],
                message=f"[DRY RUN] Would commit: planned → draft_created for Job {job_number}.",
                job_number=job_number,
                dry_run=True,
                queue_status_before="planned",
                queue_status_after="draft_created",
            )
        elif decision == TRANSACTION_BLOCKED_VERIFICATION_FAILED:
            return _make_result(
                decision="DRY_RUN_WOULD_COMMIT_NEEDS_HUMAN_REVIEW",
                approved=True,
                blockers=[],
                message=f"[DRY RUN] Would commit: planned → needs_human_review for Job {job_number}.",
                job_number=job_number,
                dry_run=True,
                queue_status_before="planned",
                queue_status_after="needs_human_review",
            )
        else:
            return _make_result(
                decision="DRY_RUN_NO_COMMIT",
                approved=True,
                blockers=[],
                message=f"[DRY RUN] No queue commit for decision={decision}, approved={approved}.",
                job_number=job_number,
                dry_run=True,
            )

    # ── Success path: verified draft created ─────────────────────────────
    if decision == TRANSACTION_APPROVED_DRAFT_CREATED and approved:
        article_id = transaction_result.get("shopify_article_id")
        handle = transaction_result.get("shopify_handle", "")
        published_at = transaction_result.get("shopify_published_at")
        draft_created_at = get_current_timestamp()

        return finalize_draft_created(
            queue_path=queue_path,
            job_number=job_number,
            shopify_article_id=article_id,
            shopify_handle=handle,
            draft_created_at=draft_created_at,
            published_at=published_at,
            shopify_verification_passed=True,
            expected_article_id=article_id,
            expected_handle=handle,
            run_dir=transaction_result.get("run_dir"),
        )

    # ── Verification failure path: needs human review ───────────────────
    if decision == TRANSACTION_BLOCKED_VERIFICATION_FAILED:
        article_id = transaction_result.get("shopify_article_id")
        failures = transaction_result.get("verification_failures", [])
        failure_reason = "; ".join(failures) if failures else "Post-fetch body verification failed"
        failure_code = "POST_FETCH_BODY_VERIFICATION_FAILED"
        verification_details = transaction_result.get("verification_details", {})

        return commit_job_needs_human_review(
            queue_path=queue_path,
            job_number=job_number,
            shopify_article_id=article_id,
            failure_reason=failure_reason,
            failure_code=failure_code,
            recovery_action="AWAITING_HUMAN_REVIEW",
            failure_artifact_path=transaction_result.get("run_dir", ""),
            notes=f"Verification failed: {failure_reason}. Run: {transaction_result.get('run_dir', 'N/A')}",
        )

    # ── Other failure: do NOT mutate queue ─────────────────────────────
    blockers_list = transaction_result.get("blockers", [])
    return _make_result(
        decision="QUEUE_COMMIT_NO_OP",
        approved=True,
        blockers=blockers_list,
        message=(
            f"Queue not mutated for Job {job_number}: "
            f"transaction_decision={transaction_result.get('decision')}, approved={approved}. "
            f"This failure mode requires human review before queue change."
        ),
        job_number=job_number,
        transaction_decision=transaction_result.get("decision"),
    )


def _make_result(
    decision: str,
    approved: bool,
    blockers: list[str],
    message: str,
    job_number: str = "",
    **kwargs,
) -> dict:
    result = {
        "decision": decision,
        "approved": bool(approved),
        "job_number": job_number,
        "blockers": blockers,
        "message": message,
    }
    for k, v in kwargs.items():
        if v is not None:
            result[k] = v
    return result


# ── CLI entry point ─────────────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(description="ORIN Queue State Manager")
    parser.add_argument("--queue-path", required=True)
    parser.add_argument("--job-number", required=True)
    parser.add_argument("--shopify-article-id", required=True)
    parser.add_argument("--shopify-handle", required=True)
    parser.add_argument("--draft-created-at", required=True)
    parser.add_argument("--published-at", default="null")
    parser.add_argument("--shopify-verification-passed", type=lambda x: x.lower() == "true", default=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    result = finalize_draft_created(
        queue_path=args.queue_path,
        job_number=args.job_number,
        shopify_article_id=args.shopify_article_id,
        shopify_handle=args.shopify_handle,
        draft_created_at=args.draft_created_at,
        published_at=args.published_at if args.published_at != "null" else None,
        shopify_verification_passed=args.shopify_verification_passed,
    )

    Path(args.output).write_text(json.dumps(result, indent=2))
    print(f"Decision: {result['decision']}")
    print(f"Approved: {result['approved']}")
    if result.get("blockers"):
        print(f"Blockers: {result['blockers']}")


if __name__ == "__main__":
    main()
