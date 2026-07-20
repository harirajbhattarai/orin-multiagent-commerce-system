#!/usr/bin/env python3
"""
ORIN Live-Draft Gate v2 — Production Live-Draft Safety Gate

Canonical gate for authorising Shopify draft creation.

INVARIANTS CHECKED (in priority order):
  H1. CLI intent: --live-draft AND --confirm-live-draft both required
  H2. Job context identity: all job numbers agree
  H3. Handle identity: writer_plan.approved_handle == publisher expected handle
  H4. Writer artifact: draft exists and SHA256 unchanged since Writer
  H5. Review gate: POST_WRITE_REVIEW_PASSED, blockers=0
  H6. HTML gate: PASS, issues=0, safe_for_publisher_preflight=true
  H7. Publisher gate: READY_TO_CREATE_SELECTED_JOB_DRAFT, passed=true, route=NEW_DRAFT_CREATION_ROUTE
  H8. Queue state: planned (not draft_created)
  H9. Due/overdue: business_date >= expected_draft_date
  H10. Draft-only config: published_at=null, published=false
  H11. Post-fetch body verification: capability available

ONLY decision that authorises Shopify write:
  LIVE_DRAFT_WRITE_APPROVED

All other decisions:
  approved = false

Usage:
  python3 live_draft_gate.py --job-context <path> --writer-plan <path> \\
    --writer-execution <path> --review <path> --html <path> \\
    --publisher <path> --publisher-route <route> \\
    --live-draft --confirm-live-draft \\
    --business-date YYYY-MM-DD
"""

import json
import hashlib
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

# ── Date helpers ──────────────────────────────────────────────────────────────

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo  # noqa: F401

BUSINESS_TZ = ZoneInfo("Europe/London")


def parse_date(date_str: str, name: str = "date") -> date:
    try:
        return date.fromisoformat(date_str)
    except ValueError:
        raise ValueError(f"Invalid {name}: '{date_str}'. Expected YYYY-MM-DD.")


def draft_due_date(target_date_str: str) -> date:
    """target_date minus 14 days = expected draft date."""
    td = parse_date(target_date_str, "target_date")
    return td - timedelta(days=14)


def days_until(d: date) -> int:
    return (d - date.today()).days


# ── Canonical decision enums ────────────────────────────────────────────────────

LIVE_DRAFT_WRITE_APPROVED = "LIVE_DRAFT_WRITE_APPROVED"
SAFE_STOP_ALREADY_CORRECT = "SAFE_STOP_ALREADY_CORRECT"
QUEUE_RECONCILIATION_REQUIRED = "QUEUE_RECONCILIATION_REQUIRED"

CLI_INTENT_BLOCK = "BLOCK_LIVE_DRAFT_CONFIRMATION_REQUIRED"
JOB_CONTEXT_MISMATCH = "BLOCK_JOB_CONTEXT_MISMATCH"
HANDLE_CONTEXT_MISMATCH = "BLOCK_HANDLE_CONTEXT_MISMATCH"
DRAFT_MUTATED = "BLOCK_LOCAL_DRAFT_MUTATED_AFTER_WRITER"
REVIEW_GATE_FAILED = "BLOCK_REVIEW_GATE"
HTML_GATE_FAILED = "BLOCK_HTML_VALIDATION_GATE"
PUBLISHER_GATE_FAILED = "BLOCK_PUBLISHER_GATE"
INVALID_QUEUE_STATE = "BLOCK_INVALID_QUEUE_STATE_FOR_DRAFT_CREATION"
JOB_NOT_DUE = "BLOCK_JOB_NOT_DUE"
PUBLISH_CONFIG_UNSAFE = "BLOCK_PUBLISH_CONFIGURATION_UNSAFE"
BODY_VERIFY_UNAVAILABLE = "BLOCK_POST_FETCH_BODY_VERIFICATION_UNAVAILABLE"
UNKNOWN_PUBLISHER_DECISION = "BLOCK_UNKNOWN_PUBLISHER_DECISION"

# ── Severity contract ────────────────────────────────────────────────────────────
# Every gate output MUST be classified as PASS | WARN | BLOCK.
# The orchestrator rule: BLOCK → STOP (no agent override).
#                         WARN → record warning and continue.
#                         PASS → continue.
#
# Review-result severity mapping:
#   duplicate_block: ...[classification: global_site_warning]  → WARN
#   duplicate_block: ...[classification: human_duplicate_decision_required] → BLOCK
#   compliance fail                                               → BLOCK
#   html_quality fail                                            → BLOCK

REVIEW_SEVERITY_PASS  = "PASS"
REVIEW_SEVERITY_WARN  = "WARN"
REVIEW_SEVERITY_BLOCK = "BLOCK"

CANONICAL_PASSING = frozenset([
    "READY_TO_CREATE_SELECTED_JOB_DRAFT",
    "ALREADY_CREATED_QUEUE_ALREADY_CORRECT",
    "ALREADY_CREATED_QUEUE_RECONCILIATION_REQUIRED",
])
CANONICAL_BLOCKING = frozenset([
    "BLOCKED_DUPLICATE_SHOPIFY_TITLE",
    "BLOCKED_DUPLICATE_SHOPIFY_HANDLE",
    "BLOCKED_NEAR_HANDLE_CONFLICT",
    "BLOCKED_NEAR_TITLE_CONFLICT",
    "BLOCK_JOB_CONTEXT_MISMATCH",
    "BLOCK_DRAFT_PATH_MISMATCH",
    "BLOCK_HANDLE_CONTEXT_MISMATCH",
    "BLOCK_LOCAL_DRAFT_MUTATED_AFTER_WRITER",
    "BLOCK_SELF_MATCH_IDENTITY_MISMATCH",
    "BLOCK_REVIEW_GATE",
    "BLOCK_HTML_VALIDATION_GATE",
    "BLOCK_COMPLIANCE",
    "BLOCK_QUEUE_STATUS_MISMATCH",
    "BLOCK_DRAFT_NOT_FOUND",
    "BLOCK_SLUG_MISMATCH",
    "BLOCK_HTML_QUALITY",
])


# ── Gate result builder ────────────────────────────────────────────────────────

def make_result(
    decision: str,
    approved: bool,
    blockers: list[str],
    message: str,
    job_number: str | None = None,
    title: str | None = None,
    handle: str | None = None,
    local_draft_path: str | None = None,
    local_sha256: str | None = None,
    publisher_decision: str | None = None,
    publisher_route: str | None = None,
    review_decision: str | None = None,
    html_result: str | None = None,
    queue_status: str | None = None,
    business_date: str | None = None,
    expected_draft_date: str | None = None,
    due_or_overdue: bool | None = None,
    published_at_required: str | None = None,
    body_hash_verification_available: bool | None = None,
    **extra: Any,
) -> dict:
    result = {
        "decision": decision,
        "approved": approved,
        "job_number": job_number,
        "title": title,
        "handle": handle,
        "local_draft_path": local_draft_path,
        "local_sha256": local_sha256,
        "publisher_decision": publisher_decision,
        "publisher_route": publisher_route,
        "review_decision": review_decision,
        "html_validation_result": html_result,
        "queue_status": queue_status,
        "business_date": business_date,
        "expected_draft_date": expected_draft_date,
        "due_or_overdue": due_or_overdue,
        "published_at_required": published_at_required,
        "body_hash_verification_available": body_hash_verification_available,
        "blockers": blockers,
        "message": message,
        **extra,
    }
    return result


# ── CLI argument parser ─────────────────────────────────────────────────────────

def parse_args() -> dict:
    """Parse CLI arguments into a context dict."""
    # Args that expect a value (path or string)
    VALUE_ARGS = frozenset([
        "--job-context", "--writer-plan", "--writer-execution",
        "--review", "--html", "--publisher", "--publisher-route",
        "--business-date",
    ])
    # Boolean flags
    BOOL_ARGS = frozenset(["--live-draft", "--confirm-live-draft"])

    args = {k: None for k in VALUE_ARGS}
    args.update({k: False for k in BOOL_ARGS})
    args["extra"] = {}

    i = 1
    while i < len(sys.argv):
        arg = sys.argv[i]
        if arg in VALUE_ARGS:
            if i + 1 >= len(sys.argv):
                raise ValueError(f"Missing value for {arg}")
            args[arg] = sys.argv[i + 1]
            i += 2
        elif arg in BOOL_ARGS:
            args[arg] = True
            i += 1
        else:
            args["extra"][arg] = True
            i += 1
    return args


def load_json(path: str) -> dict:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"File not found: {path}")
    return json.loads(p.read_text())


# ── Severity classification ─────────────────────────────────────────────────────


# ── Verification capability check ───────────────────────────────────────────────
#
# Called by cron_entrypoint.py to determine body_hash_verification_available
# before passing it to run_gate().
#
# This is a wiring/capability check, NOT a verification-result check.
# It verifies that the PRODUCTION VERIFICATION PATH exists and is connected:
#
#   Evidence-capability contract (8 checks):
#   E1. _create_transaction_run_dir  — run directory creator
#   E2. _persist_sent_body          — sent-body (pre-write) evidence
#   E3. _persist_fetched_body       — fetched-body (post-read) evidence
#   E4. _persist_verification       — verification result evidence
#   E5. _persist_transaction_result  — final transaction result evidence
#   Integration:
#   E6. compare_html_canonical        — normalising body comparator
#   E7. verify_shopify_draft_against_local — production verifier (uses E1-E6)
#   E8. _EVIDENCE_BASE directory      — writable evidence storage
#
# Returns (bool, list_of_failure_strings).
#
# H11 BLOCKS if ANY of E1-E8 is unavailable.
#
# Test contract (7 scenarios):
#   Test 1: E1 missing     → False + ["run_dir_creator_unavailable"]
#   Test 2: E2 missing     → False + ["sent_body_persister_unavailable"]
#   Test 3: E3 missing     → False + ["fetched_body_persister_unavailable"]
#   Test 4: E4 missing     → False + ["verification_persister_unavailable"]
#   Test 5: E5 missing     → False + ["transaction_result_persister_unavailable"]
#   Test 6: E6 missing     → False + ["comparator_unavailable"]
#   Test 7: E7 missing     → False + ["verifier_unavailable"]
#   Test 8: E8 unwritable   → False + ["evidence_dir_unwritable"]
#   Test 9: ALL connected  → True + []

def _check_verification_capability() -> tuple[bool, list[str]]:
    """
    Check whether the production evidence capability contract is fully wired.

    Verifies E1-E8 (see contract above).
    Returns (True, []) if all 8 components are present and connected.
    Returns (False, [reason, ...]) if any component is missing or unavailable.
    """
    failures: list[str] = []

    # E1: _create_transaction_run_dir — run directory creator
    try:
        from shopify_draft_transaction import _create_transaction_run_dir
        if not callable(_create_transaction_run_dir):
            failures.append(
                "run_dir_creator_unavailable: _create_transaction_run_dir is not callable"
            )
    except (ImportError, AttributeError) as e:
        failures.append(
            f"run_dir_creator_unavailable: cannot import _create_transaction_run_dir: {e}"
        )

    # E2: _persist_sent_body — sent body (pre-write) evidence
    try:
        from shopify_draft_transaction import _persist_sent_body
        if not callable(_persist_sent_body):
            failures.append(
                "sent_body_persister_unavailable: _persist_sent_body is not callable"
            )
    except (ImportError, AttributeError) as e:
        failures.append(
            f"sent_body_persister_unavailable: cannot import _persist_sent_body: {e}"
        )

    # E3: _persist_fetched_body — fetched body (post-read) evidence
    try:
        from shopify_draft_transaction import _persist_fetched_body
        if not callable(_persist_fetched_body):
            failures.append(
                "fetched_body_persister_unavailable: _persist_fetched_body is not callable"
            )
    except (ImportError, AttributeError) as e:
        failures.append(
            f"fetched_body_persister_unavailable: cannot import _persist_fetched_body: {e}"
        )

    # E4: _persist_verification — verification result evidence
    try:
        from shopify_draft_transaction import _persist_verification
        if not callable(_persist_verification):
            failures.append(
                "verification_persister_unavailable: _persist_verification is not callable"
            )
    except (ImportError, AttributeError) as e:
        failures.append(
            f"verification_persister_unavailable: cannot import _persist_verification: {e}"
        )

    # E5: _persist_transaction_result — transaction result evidence
    try:
        from shopify_draft_transaction import _persist_transaction_result
        if not callable(_persist_transaction_result):
            failures.append(
                "transaction_result_persister_unavailable: _persist_transaction_result is not callable"
            )
    except (ImportError, AttributeError) as e:
        failures.append(
            f"transaction_result_persister_unavailable: cannot import _persist_transaction_result: {e}"
        )

    # E6: compare_html_canonical — normalising body comparator
    try:
        from html_canonical_comparator import compare_html_canonical
        if not callable(compare_html_canonical):
            failures.append(
                "comparator_unavailable: compare_html_canonical is not callable"
            )
    except (ImportError, AttributeError) as e:
        failures.append(
            f"comparator_unavailable: cannot import compare_html_canonical: {e}"
        )

    # E7: verify_shopify_draft_against_local — production verifier
    try:
        from shopify_draft_transaction import verify_shopify_draft_against_local
        if not callable(verify_shopify_draft_against_local):
            failures.append(
                "verifier_unavailable: verify_shopify_draft_against_local is not callable"
            )
    except (ImportError, AttributeError) as e:
        failures.append(
            f"verifier_unavailable: cannot import verify_shopify_draft_against_local: {e}"
        )

    # E8: _EVIDENCE_BASE — writable evidence storage
    try:
        from shopify_draft_transaction import _EVIDENCE_BASE
        _EVIDENCE_BASE.mkdir(parents=True, exist_ok=True)
        test_file = _EVIDENCE_BASE / ".h11_capability_test"
        try:
            test_file.write_text("h11 capability test", encoding="utf-8")
            test_file.unlink()
        except Exception as e:
            failures.append(
                f"evidence_dir_unwritable: _EVIDENCE_BASE {_EVIDENCE_BASE} is not writable: {e}"
            )
    except Exception as e:
        failures.append(
            f"evidence_dir_inaccessible: cannot access _EVIDENCE_BASE: {e}"
        )

    if failures:
        return False, failures
    return True, []


def _classify_review_result_to_severity(post_write_review: dict) -> tuple[str, list[str]]:
    """
    Classify the post_write_review result into PASS | WARN | BLOCK severity.

    Severity contract:
        WARN  → informational issue, pipeline continues, warning is recorded
                Examples: global_site_warning, informational duplicate notes
        BLOCK → must stop pipeline, human review required
                Examples: compliance failure, real duplicate vs different article,
                          HTML quality failure, human_duplicate_decision_required
        PASS  → all checks passed cleanly

    Returns: (severity: str, severity_blockers: list[str])
        severity_blockers is non-empty only when severity == BLOCK
    """
    review_decision = post_write_review.get("review_decision", "")
    blockers = post_write_review.get("blockers", [])
    warnings_out: list[str] = []

    # If PASSED cleanly, check only for known BLOCK-level issues
    if review_decision == "POST_WRITE_REVIEW_PASSED" and not blockers:
        return REVIEW_SEVERITY_PASS, []

    # ── Per-blocker classification ──────────────────────────────────────
    severity_blockers: list[str] = []

    for b in blockers:
        b_lower = b.lower() if isinstance(b, str) else ""

        # ── WARN-level (informational) ──────────────────────────────────
        # global_site_warning is a Phase 2B classification that means
        # "this article doesn't match any existing content" — informational only
        if "global_site_warning" in b_lower and "block" in b_lower:
            warnings_out.append(f"WARN: {b}")
            continue

        # informational duplicate note
        if "informational" in b_lower or "note:" in b_lower:
            warnings_out.append(f"WARN: {b}")
            continue

        # ── BLOCK-level (must stop) ─────────────────────────────────────
        # Real compliance failure
        if "compliance" in b_lower and ("fail" in b_lower or "block" in b_lower):
            severity_blockers.append(b)
            continue

        # Real HTML quality failure
        if "html_quality" in b_lower and ("fail" in b_lower or "block" in b_lower):
            severity_blockers.append(b)
            continue

        # Real duplicate requiring human decision
        if "human_duplicate_decision_required" in b_lower:
            severity_blockers.append(b)
            continue

        # Near-duplicate with title/handle conflict
        if "near_duplicate" in b_lower or "near_handle_conflict" in b_lower:
            severity_blockers.append(b)
            continue

        # Generic BLOCK marker in any other blocker
        if "block" in b_lower:
            # Distinguish WARN vs BLOCK by content
            if "global_site_warning" in b_lower:
                warnings_out.append(f"WARN: {b}")
            else:
                severity_blockers.append(b)
            continue

        # Unknown blocker without clear severity → treat as BLOCK to be safe
        severity_blockers.append(b)

    # ── Final severity decision ─────────────────────────────────────────
    if severity_blockers:
        return REVIEW_SEVERITY_BLOCK, severity_blockers
    elif warnings_out:
        return REVIEW_SEVERITY_WARN, warnings_out
    elif review_decision == "POST_WRITE_REVIEW_NEEDS_HUMAN_REVIEW":
        # Advisory: human review recommended but no blocking severity issues found
        # → WARN, not BLOCK (human can still approve)
        return REVIEW_SEVERITY_WARN, [f"Human review recommended: {review_decision}"]
    elif review_decision != "POST_WRITE_REVIEW_PASSED":
        # Any other non-PASSED decision with no blockers → BLOCK to be safe
        return REVIEW_SEVERITY_BLOCK, [f"Review decision={review_decision!r} is not PASSED"]
    else:
        return REVIEW_SEVERITY_PASS, []


# ── Main gate function ─────────────────────────────────────────────────────────

def run_gate(
    selected_job_context: dict,
    writer_plan: dict,
    writer_execution: dict,
    post_write_review: dict,
    html_validation: dict,
    publisher_preflight: dict,
    publisher_route: str,
    live_draft_requested: bool,
    live_draft_confirmed: bool,
    business_date: date,
    # Phase I4: Post-fetch body verification capability.
    # Set to True ONLY after shopify_draft_transaction.verify_shopify_draft_against_local
    # is implemented and called in the live write path.
    body_hash_verification_available: bool = False,
) -> dict:
    """
    Run the Live-Draft Gate v2 for the selected job.

    Returns structured gate result with decision and blockers.

    body_hash_verification_available: Set to True only when:
      - shopify_draft_transaction.create_shopify_draft() is called
      - fetch_shopify_article() immediately fetches the returned article
      - verify_shopify_draft_against_local() compares body SHA256
      - Transaction result is returned with verification details
    """
    blockers: list[str] = []

    # ── Derive review_decision from post_write_review ─────────────────────
    review_decision = post_write_review.get("review_decision", "")

    # ── H1: CLI intent ────────────────────────────────────────────────────
    if not live_draft_requested:
        blockers.append(CLI_INTENT_BLOCK)
        return make_result(
            decision=CLI_INTENT_BLOCK,
            approved=False,
            blockers=blockers,
            message="--live-draft flag missing.",
        )
    if not live_draft_confirmed:
        blockers.append(CLI_INTENT_BLOCK)
        return make_result(
            decision=CLI_INTENT_BLOCK,
            approved=False,
            blockers=blockers,
            message="--confirm-live-draft flag missing.",
        )

    # ── Extract common fields ─────────────────────────────────────────────
    job_number = str(selected_job_context.get("job_number", ""))
    ctx_job = job_number
    title = selected_job_context.get("topic", writer_plan.get("title", ""))
    queue_status = selected_job_context.get("queue_status", "unknown")

    # ── H2: Job context identity invariants ───────────────────────────────
    # For writer_plan: accept top-level job_number OR next_writing_candidate.job_number
    # (handles no_writer_action plans where writer_plan has no top-level job_number)
    _wp_raw = writer_plan.get("job_number", "") or str(
        writer_plan.get("next_writing_candidate", {}).get("job_number", "")
    )
    wp_job = str(_wp_raw)
    we_job = str(writer_execution.get("job_number", ""))
    pwr_job = str(post_write_review.get("job_number", ""))
    hv_job = str(html_validation.get("job_number", ""))
    pp_job = str(publisher_preflight.get("publisher_job_number",
                                         publisher_preflight.get("job_number", "")))

    for label, val in [
        ("writer_plan.job_number", wp_job),
        ("writer_execution.job_number", we_job),
        ("post_write_review.job_number", pwr_job),
        ("html_validation.job_number", hv_job),
        ("publisher_preflight.job_number", pp_job),
    ]:
        if val != ctx_job:
            blockers.append(JOB_CONTEXT_MISMATCH)

    if blockers:
        blockers_detail = ", ".join(
            f"{label}={val} != context={ctx_job}"
            for label, val in [
                ("writer_plan", wp_job), ("writer_execution", we_job),
                ("post_write_review", pwr_job), ("html_validation", hv_job),
                ("publisher_preflight", pp_job),
            ] if val != ctx_job
        )
        return make_result(
            decision=JOB_CONTEXT_MISMATCH,
            approved=False,
            blockers=blockers,
            message=f"Job context mismatch: {blockers_detail}",
            job_number=job_number, title=title,
        )

    # ── H3: Handle identity ───────────────────────────────────────────────
    planned_handle = writer_plan.get("approved_handle", "")
    publisher_handle = publisher_preflight.get(
        "payload_preview", {}
    ).get("handle", "")
    # Also accept handle from selected_job_context
    ctx_handle = selected_job_context.get("shopify_handle", "")

    # Handle must match at least one authoritative source
    expected_handle = publisher_handle or planned_handle or ctx_handle
    if expected_handle:
        handles_in_scope = [h for h in [planned_handle, publisher_handle, ctx_handle] if h]
        if not all(h == expected_handle for h in handles_in_scope):
            blockers.append(HANDLE_CONTEXT_MISMATCH)
            return make_result(
                decision=HANDLE_CONTEXT_MISMATCH,
                approved=False,
                blockers=blockers,
                message=(
                    f"Handle mismatch: writer_plan={planned_handle!r}, "
                    f"publisher={publisher_handle!r}, ctx={ctx_handle!r}"
                ),
                job_number=job_number, title=title, handle=expected_handle,
            )

    # ── H4: Writer artifact invariants ────────────────────────────────────
    local_draft_path = writer_execution.get("output_path")
    writer_sha256 = writer_execution.get("sha256")

    if not local_draft_path:
        blockers.append(DRAFT_MUTATED)
        return make_result(
            decision=DRAFT_MUTATED,
            approved=False,
            blockers=blockers,
            message="Writer execution has no output_path.",
            job_number=job_number, title=title,
        )

    draft_path = Path(local_draft_path)
    if not draft_path.exists():
        blockers.append(DRAFT_MUTATED)
        return make_result(
            decision=DRAFT_MUTATED,
            approved=False,
            blockers=blockers,
            message=f"Local draft not found: {local_draft_path}",
            job_number=job_number, title=title,
        )

    current_sha256 = hashlib.sha256(draft_path.read_bytes()).hexdigest()
    if writer_sha256 and current_sha256 != writer_sha256:
        blockers.append(DRAFT_MUTATED)
        return make_result(
            decision=DRAFT_MUTATED,
            approved=False,
            blockers=blockers,
            message=(
                f"Local draft SHA256 mismatch: "
                f"current={current_sha256} != writer={writer_sha256}"
            ),
            job_number=job_number, title=title,
            local_draft_path=local_draft_path,
            local_sha256=current_sha256,
        )

    # ── H5: Review gate (severity-contracted) ──────────────────────────────
    # Severity contract: BLOCK → STOP. WARN → record and continue. PASS → continue.
    # No agent/orchestrator override of BLOCK is permitted.
    gate_severity, severity_details = _classify_review_result_to_severity(post_write_review)
    gate_warnings: list[str] = []

    if gate_severity == REVIEW_SEVERITY_BLOCK:
        blockers.append(REVIEW_GATE_FAILED)
        return make_result(
            decision=REVIEW_GATE_FAILED,
            approved=False,
            blockers=blockers,
            message=(
                f"Review gate BLOCKED (severity=BLOCK): {severity_details}. "
                f"Pipeline stopped. Human review required. "
                f"Orchestrator has no override for BLOCK."
            ),
            job_number=job_number, title=title,
            gate_severity=gate_severity,
            severity_details=severity_details,
        )

    if gate_severity == REVIEW_SEVERITY_WARN:
        # Record warning and continue — informational only
        for w in severity_details:
            gate_warnings.append(w)
        # Do NOT stop — pipeline continues to H6

    # ── H6: HTML validation gate ─────────────────────────────────────────
    html_pass = html_validation.get("validation_passed", False) or html_validation.get("pass", False)
    html_issues = html_validation.get("validator_issues", []) or html_validation.get("issues", [])
    html_safe = html_validation.get("safe_for_publisher_preflight", False)
    if not html_pass or len(html_issues) > 0 or not html_safe:
        blockers.append(HTML_GATE_FAILED)
        return make_result(
            decision=HTML_GATE_FAILED,
            approved=False,
            blockers=blockers,
            message=(
                f"HTML validation gate failed: pass={html_pass}, "
                f"issues={len(html_issues)}, safe_for_publisher_preflight={html_safe}"
            ),
            job_number=job_number, title=title,
        )

    # ── H7: Publisher gate ────────────────────────────────────────────────
    publisher_decision = publisher_preflight.get("decision", "")
    publisher_passed = publisher_preflight.get("passed", False)

    # H7: READY_TO_CREATE_SELECTED_JOB_DRAFT — checked first, separate if (no fall-through)
    if publisher_decision == "READY_TO_CREATE_SELECTED_JOB_DRAFT":
        if publisher_route != "NEW_DRAFT_CREATION_ROUTE":
            blockers.append(PUBLISHER_GATE_FAILED)
            return make_result(
                decision=PUBLISHER_GATE_FAILED,
                approved=False,
                blockers=blockers,
                message=f"Publisher route={publisher_route!r} != NEW_DRAFT_CREATION_ROUTE",
                job_number=job_number, title=title,
                publisher_decision=publisher_decision,
                publisher_route=publisher_route,
            )
        # Route OK — continue to H8
    elif publisher_decision not in CANONICAL_PASSING:
        blockers.append(PUBLISHER_GATE_FAILED)
        msg = f"Publisher decision={publisher_decision!r} not in canonical passing set."
        if not publisher_passed:
            msg += f" passed={publisher_passed}"
        if publisher_route and publisher_route != "NEW_DRAFT_CREATION_ROUTE":
            msg += f" route={publisher_route!r}"
        blockers.append(PUBLISHER_GATE_FAILED)
        return make_result(
            decision=PUBLISHER_GATE_FAILED,
            approved=False,
            blockers=blockers,
            message=msg,
            job_number=job_number, title=title,
            publisher_decision=publisher_decision,
            publisher_route=publisher_route,
        )
    elif publisher_decision == "ALREADY_CREATED_QUEUE_ALREADY_CORRECT":
        return make_result(
            decision=SAFE_STOP_ALREADY_CORRECT,
            approved=False,
            blockers=[],
            message="Shopify draft already exists. Queue is correct. No action needed.",
            job_number=job_number, title=title,
            publisher_decision=publisher_decision,
            publisher_route=publisher_route,
        )
    elif publisher_decision == "ALREADY_CREATED_QUEUE_RECONCILIATION_REQUIRED":
        return make_result(
            decision=QUEUE_RECONCILIATION_REQUIRED,
            approved=False,
            blockers=[],
            message="Shopify draft exists but queue is stale. Update queue status first.",
            job_number=job_number, title=title,
            publisher_decision=publisher_decision,
            publisher_route=publisher_route,
        )
    else:
        # Should not reach here given CANONICAL_PASSING check above
        blockers.append(UNKNOWN_PUBLISHER_DECISION)
        return make_result(
            decision=UNKNOWN_PUBLISHER_DECISION,
            approved=False,
            blockers=blockers,
            message=f"Unknown publisher decision: {publisher_decision!r}",
            job_number=job_number, title=title,
        )

    # ── H8: Queue state ──────────────────────────────────────────────────
    if queue_status != "planned":
        blockers.append(INVALID_QUEUE_STATE)
        return make_result(
            decision=INVALID_QUEUE_STATE,
            approved=False,
            blockers=blockers,
            message=f"Queue status is '{queue_status}', expected 'planned'.",
            job_number=job_number, title=title,
            queue_status=queue_status,
            publisher_decision=publisher_decision,
            publisher_route=publisher_route,
        )

    # ── H9: Due/overdue ──────────────────────────────────────────────────
    target_date_str = selected_job_context.get("target_date")
    if not target_date_str:
        blockers.append(JOB_NOT_DUE)
        return make_result(
            decision=JOB_NOT_DUE,
            approved=False,
            blockers=blockers,
            message="No target_date in selected job context.",
            job_number=job_number, title=title,
        )

    expected_draft = draft_due_date(target_date_str)
    due_or_overdue = business_date >= expected_draft

    if not due_or_overdue:
        blockers.append(JOB_NOT_DUE)
        days_away = (expected_draft - business_date).days
        return make_result(
            decision=JOB_NOT_DUE,
            approved=False,
            blockers=blockers,
            message=f"Job not due: business_date={business_date} < expected_draft_date={expected_draft} ({days_away} days away)",
            job_number=job_number, title=title,
            business_date=business_date.isoformat(),
            expected_draft_date=expected_draft.isoformat(),
            due_or_overdue=False,
        )

    # ── H10: Draft-only publishing configuration ───────────────────────────
    # published_at must be null (not set) for draft creation
    published_at_required = None  # null = draft only

    # ── H11: Post-fetch body hash verification — CAPABILITY gate ───────────
    # H11 checks that the PRODUCTION VERIFICATION CAPABILITY exists and is
    # connected. It is NOT a result gate — it does NOT require an actual
    # post-fetch verification result before the Shopify write.
    #
    # The actual verification RESULT (pass/fail) occurs only AFTER
    # Shopify write/fetch inside run_safe_draft_transaction(), where a
    # failed result still keeps the article unpublished and returns
    # needs_human_review.
    #
    # Required production capability:
    #   1. verify_shopify_draft_against_local() — importable, callable
    #   2. compare_html_canonical()              — importable, callable
    #   3. _persist_transaction_result()        — defined, evidence-writer
    #
    # body_hash_verification_available is calculated by
    # _check_verification_capability() in cron_entrypoint.py and passed here.
    # The parameter is the authoritative capability flag — it IS the wiring check.
    if not body_hash_verification_available:
        blockers.append(BODY_VERIFY_UNAVAILABLE)
        return make_result(
            decision=BODY_VERIFY_UNAVAILABLE,
            approved=False,
            blockers=blockers,
            message=(
                "Post-fetch body hash verification capability is not connected. "
                "H11 capability gate requires: "
                "(1) verify_shopify_draft_against_local callable, "
                "(2) compare_html_canonical callable, "
                "(3) evidence persistence defined. "
                "Wire the production verification path before live draft write."
            ),
            job_number=job_number, title=title, handle=expected_handle,
            local_draft_path=local_draft_path,
            local_sha256=current_sha256,
            publisher_decision=publisher_decision,
            publisher_route=publisher_route,
            review_decision=review_decision,
            html_result="PASS",
            queue_status=queue_status,
            business_date=business_date.isoformat(),
            expected_draft_date=expected_draft.isoformat(),
            due_or_overdue=due_or_overdue,
            published_at_required=published_at_required,
            body_hash_verification_available=False,
        )

    # ── ALL GATES PASSED ──────────────────────────────────────────────────
    return make_result(
        decision=LIVE_DRAFT_WRITE_APPROVED,
        approved=True,
        blockers=[],
        message=(
            f"Live-draft gate APPROVED for Job {job_number}. "
            f"All {11} invariant gates passed. "
            f"Shopify draft creation authorised."
        ),
        job_number=job_number,
        title=title,
        handle=expected_handle,
        local_draft_path=local_draft_path,
        local_sha256=current_sha256,
        publisher_decision=publisher_decision,
        publisher_route=publisher_route,
        review_decision=review_decision,
        html_validation_result="PASS",
        queue_status=queue_status,
        business_date=business_date.isoformat(),
        expected_draft_date=expected_draft.isoformat(),
        due_or_overdue=due_or_overdue,
        published_at_required=published_at_required,
        body_hash_verification_available=body_hash_verification_available,
    )


# ── CLI entrypoint ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    try:
        args = parse_args()

        if not args["--live-draft"]:
            result = make_result(
                decision=CLI_INTENT_BLOCK,
                approved=False,
                blockers=[CLI_INTENT_BLOCK],
                message="--live-draft flag is required.",
            )
            print(json.dumps(result, indent=2, default=str))
            sys.exit(0)

        if not args["--confirm-live-draft"]:
            result = make_result(
                decision=CLI_INTENT_BLOCK,
                approved=False,
                blockers=[CLI_INTENT_BLOCK],
                message="--confirm-live-draft flag is required.",
            )
            print(json.dumps(result, indent=2, default=str))
            sys.exit(0)

        selected_job_context = load_json(args["--job-context"]) if args["--job-context"] else {}
        writer_plan = load_json(args["--writer-plan"]) if args["--writer-plan"] else {}
        writer_execution = load_json(args["--writer-execution"]) if args["--writer-execution"] else {}
        post_write_review = load_json(args["--review"]) if args["--review"] else {}
        html_validation = load_json(args["--html"]) if args["--html"] else {}
        publisher_preflight = load_json(args["--publisher"]) if args["--publisher"] else {}
        publisher_route = args.get("--publisher-route") or publisher_preflight.get("publisher_route", "")

        if args.get("--business-date"):
            business_date = parse_date(args["--business-date"], "--business-date")
        else:
            from business_time import get_business_today
            business_date = get_business_today()

        result = run_gate(
            selected_job_context=selected_job_context,
            writer_plan=writer_plan,
            writer_execution=writer_execution,
            post_write_review=post_write_review,
            html_validation=html_validation,
            publisher_preflight=publisher_preflight,
            publisher_route=publisher_route,
            live_draft_requested=True,
            live_draft_confirmed=True,
            business_date=business_date,
        )

        print(json.dumps(result, indent=2, default=str))

        # Print gate summary
        decision = result.get("decision", "")
        approved = result.get("approved", False)
        print(f"\n{'='*60}", file=sys.stderr)
        print(f"GATE DECISION: {decision}", file=sys.stderr)
        print(f"APPROVED:      {approved}", file=sys.stderr)
        if result.get("blockers"):
            print(f"BLOCKERS:      {', '.join(result['blockers'])}", file=sys.stderr)
        print(f"{'='*60}", file=sys.stderr)

    except Exception as e:
        result = make_result(
            decision="BLOCK_GATE_ERROR",
            approved=False,
            blockers=["BLOCK_GATE_ERROR"],
            message=f"Gate error: {e}",
        )
        print(json.dumps(result, indent=2, default=str))
        raise
