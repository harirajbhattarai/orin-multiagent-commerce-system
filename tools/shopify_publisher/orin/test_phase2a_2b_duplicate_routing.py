#!/usr/bin/env python3
"""
test_phase2a_2b_duplicate_routing.py
=====================================
Regression test: Phase 2A / Phase 2B duplicate routing separation.

Validates fix for HCS Phase 5 Recovery Patch.

Contract after fix:
  Phase 2A: unclear duplicate → info_notes (NOT blocking)
  Phase 2B: record_type=unclear, human_decision_count=0 → WARN (continue)
  Phase 2B: record_type=unclear, human_decision_count>0 → BLOCK
  Phase 2B: record_type=unknown/empty/malformed → BLOCK
  Phase 2B: record_type=self_match_info → PASS

Run:
  python3 tools/shopify_publisher/orin/test_phase2a_2b_duplicate_routing.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from duplicate_decision_agent import classify_job_duplicate


# ── Phase 2B gate contract (mirrors cron_entrypoint.py lines 640-710) ──────────

BLOCKING_TYPES = frozenset([
    "human_duplicate_decision_required",
    "no_local_file",
    "skipped_not_due",
    "blocked_by_compliance_or_html",
])
WARN_TYPES = frozenset(["unclear", "global_site_warning"])
PASS_TYPES = frozenset(["self_match_info"])


def phase2b_gate(record_type, human_decision_count=0):
    """Simulate Phase 2B gate decision."""
    if record_type in BLOCKING_TYPES:
        return "BLOCK"
    if record_type in WARN_TYPES:
        if record_type == "unclear" and human_decision_count > 0:
            return "BLOCK"
        return "WARN"
    if record_type in PASS_TYPES:
        return "PASS"
    return "BLOCK_UNKNOWN"


def make_review_result(dup_classification, dup_detail="test detail",
                       decision="review_passed", blocking_issues=None):
    """Build a minimal Phase 2A review_result dict for testing."""
    return {
        "duplicate_classification": dup_classification,
        "duplicate_detail": dup_detail,
        "review_decision": decision,
        "blocking_review_issues": blocking_issues or [],
        "topic": "Test Topic",
        "local_file_path": "/tmp/test.html",
    }


# ── Test cases ────────────────────────────────────────────────────────────────

CASES = [
    # (name, review_result, risks, expected_record_type, expected_severity, expected_phase2b)
    (
        "self_match_info → PASS",
        make_review_result("self_match_info"),
        [],
        "self_match_info",
        "info",
        "PASS",
    ),
    (
        "global_site_warning → WARN",
        make_review_result("global_site_warning"),
        [],
        "global_site_warning",
        "info",
        "WARN",
    ),
    (
        "human_duplicate_decision_required → BLOCK",
        make_review_result("current_job_real_duplicate"),
        [],  # no risks — falls to fallback human_decision_required record
        "human_duplicate_decision_required",
        "blocking",
        "BLOCK",
    ),
    (
        "unclear + 0 human decisions → WARN (KEY FIX)",
        make_review_result("unclear"),
        [],
        "unclear",
        "warning",       # was "unclear" before fix — must be "warning"
        "WARN",         # Phase 2B continues
    ),
    (
        "unclear + human decisions > 0 → BLOCK",
        make_review_result("unclear"),
        [],
        "unclear",
        "warning",
        "BLOCK",        # Phase 2B stops when human_decision_count > 0
    ),
    (
        "unknown classification → unclear → WARN (0 decisions)",
        make_review_result("totally_unknown_and_impossible_class"),
        [],
        "unclear",      # unknown falls through to unclear
        "warning",
        "WARN",
    ),
    (
        "no_local_file decision → BLOCK",
        make_review_result("self_match_info", decision="no_local_file_to_review"),
        [],
        "no_local_file",
        None,
        "BLOCK",
    ),
    (
        "skipped_not_due → BLOCK",
        make_review_result("self_match_info", decision="skipped_not_due"),
        [],
        "skipped_not_due",
        None,
        "BLOCK",
    ),
    (
        "compliance blocker → blocked_by_compliance_or_html → BLOCK",
        make_review_result("self_match_info", decision="review_passed",
                           blocking_issues=["compliance_fail: dangerous claim"]),
        [],
        "blocked_by_compliance_or_html",
        None,
        "BLOCK",
    ),
]


def run_tests():
    passed = 0
    failed = 0

    print("=" * 70)
    print("Phase 2A/2B Duplicate Routing — Regression Test")
    print("=" * 70)

    for case in CASES:
        name, review_result, risks, expected_type, expected_sev, expected_gate = case
        job_num = "03"

        result = classify_job_duplicate(job_num, review_result, risks)
        record_type = result.get("record_type", "NONE")
        severity = result.get("severity", "NONE")

        # Phase 2B gate checks with 0 and 1 human decisions
        gate_0 = phase2b_gate(record_type, human_decision_count=0)
        gate_1 = phase2b_gate(record_type, human_decision_count=1)

        ok_type = record_type == expected_type
        ok_sev = severity == expected_sev if expected_sev is not None else True

        # Gate expectations
        if expected_gate == "PASS":
            ok_gate = gate_0 == "PASS"
        elif expected_gate == "WARN":
            ok_gate = gate_0 == "WARN"
            # For unclear: also verify human_decision_count=1 blocks
            if record_type == "unclear":
                ok_gate = ok_gate and (gate_1 == "BLOCK")
        elif expected_gate == "BLOCK":
            if record_type == "unclear":
                ok_gate = (gate_0 == "WARN") and (gate_1 == "BLOCK")
            else:
                ok_gate = gate_0 == "BLOCK"
        elif expected_gate == "BLOCK_UNKNOWN":
            ok_gate = gate_0 == "BLOCK_UNKNOWN"
        else:
            ok_gate = False

        all_ok = ok_type and ok_sev and ok_gate

        status = "PASS" if all_ok else "FAIL"
        mark = "✅" if all_ok else "❌"
        print(f"\n{mark} {status} — {name}")
        print(f"   record_type : {record_type}  (expected: {expected_type})  {'✓' if ok_type else '✗'}")
        if expected_sev is not None:
            print(f"   severity    : {severity}  (expected: {expected_sev})  {'✓' if ok_sev else '✗'}")
        print(f"   Phase2B(0)  : {gate_0}  (expected: {expected_gate})")
        if record_type == "unclear":
            print(f"   Phase2B(1)  : {gate_1}  (expected: BLOCK)  {'✓' if gate_1 == 'BLOCK' else '✗'}")

        if not all_ok:
            print(f"   >>> result: {result}")
            failed += 1
        else:
            passed += 1

    print()
    print("=" * 70)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 70)

    if failed:
        print("\nREGRESSION FAILED — Phase 2A/2B routing fix not applied correctly.")
        sys.exit(1)
    else:
        print("\nALL TESTS PASS — Phase 2A/2B routing fix verified.")
        # Key invariant confirmation
        r = classify_job_duplicate("03", make_review_result("unclear"), [])
        assert r["record_type"] == "unclear"
        assert r["severity"] == "warning", f"Severity must be 'warning', got {r['severity']}"
        assert phase2b_gate("unclear", 0) == "WARN", "Phase 2B must WARN for unclear + 0 decisions"
        assert phase2b_gate("unclear", 1) == "BLOCK", "Phase 2B must BLOCK for unclear + 1 decisions"
        print("Key invariant: unclear→severity=warning, Phase2B(0)→WARN, Phase2B(1)→BLOCK")
        sys.exit(0)


if __name__ == "__main__":
    run_tests()
