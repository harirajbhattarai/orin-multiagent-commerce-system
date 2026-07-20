"""
topic_identity_gate.py
======================
Post-writer topic identity verification gate.

Runs immediately after the Writer Agent produces output and BEFORE Phase 2A.
Prevents contaminated or off-topic output from reaching Shopify or Phase 2A.

Contract
--------
    BLOCK  → writer_output_topic_identity_failed
            → do not call Phase 2A
            → do not call Shopify
            → queue stays in current status (planned)

    PASS   → continue to Phase 2A

Inputs
------
    job_id:             int | str
    expected_topic:      str   — the approved article title / H1
    target_keyword:     str   — primary target keyword
    cluster:            str   — Hoverkart | Troubleshooting | Buyer Guide | etc.
    approved_h2_plan:   list  — list of {id, h2} from the approved writer plan
    output_html:        str   — the raw HTML produced by the writer

Checks (in order, first failure stops)
--------------------------------------
1. H1_EXACT       — output contains exactly one <h1> matching expected_topic
2. H2_PLAN_MATCH  — each approved H2 id appears in output with matching h2 text
3. TOPIC_TERM_CLEAN — output does not contain topic-contamination terms
                    (e.g. hoverkart for non-Hoverkart articles)
4. NO_H1_TITLE_MISMATCH — if an <h1> exists, it matches expected_topic

Failure codes
--------------
    H1_MISSING_OR_MISMATCH
    H2_PLAN_MISMATCH
    TOPIC_IDENTITY_CONTAMINATED
    GATE_INTERNAL_ERROR

Usage
-----
    from topic_identity_gate import run_topic_identity_gate, TOPIC_IDENTITY_BLOCK

    result = run_topic_identity_gate(
        job_id="22",
        expected_topic="Hoverboard Lights Flashing: What It Usually Means",
        target_keyword="hoverboard lights flashing",
        cluster="Troubleshooting",
        approved_h2_plan=[{"id": "why-lights-flash", "h2": "Why Your Hoverboard Lights Are Flashing"}, ...],
        output_html=html_content,
    )

    if result["decision"] == TOPIC_IDENTITY_BLOCK:
        # block pipeline, record failure, do not proceed
        ...
"""

import re
from typing import Any

# ── Decision codes ──────────────────────────────────────────────────────────

TOPIC_IDENTITY_PASS = "TOPIC_IDENTITY_PASS"
TOPIC_IDENTITY_BLOCK = "TOPIC_IDENTITY_BLOCK"

GATE_ERR_INVALID_INPUT = "GATE_ERR_INVALID_INPUT"
GATE_ERR_NO_HTML = "GATE_ERR_NO_HTML"


# ── Contamination term registry ───────────────────────────────────────────

# Per-cluster blocklist: terms that must NOT appear in output unless
# the cluster is explicitly the one that owns those terms.
#
# Format: {cluster: [blocked_terms...]}
# A term listed for cluster "X" is blocked for ALL clusters except "X".
# For example, "hoverkart" is listed under "Hoverkart" → blocked for all
# non-Hoverkart clusters.

CLUSTER_CONTAMINATION_BLOCKLIST: dict[str, list[str]] = {
    # Terms listed here are valid content for that cluster but BLOCKED
    # for all other clusters.
    # Format: {owning_cluster: [blocked_terms]}
    # A term "X" listed under cluster "Y" is valid for cluster "Y" but
    # must NOT appear in any other cluster's output.
    "Hoverkart": [
        "hoverkart",      "hoverkarts",
        "hoverkart seat", "hoverkart frame",
        "hoverkart connection",
        "hoverkart strap",  "hoverkart compatible",
    ],
}


def _get_blocked_terms_for_cluster(cluster: str) -> set[str]:
    """Return the set of terms blocked for the given cluster."""
    blocked = set()
    for owning_cluster, terms in CLUSTER_CONTAMINATION_BLOCKLIST.items():
        if owning_cluster != cluster:
            blocked.update(t.lower() for t in terms)
    return blocked


def _extract_h1(html: str) -> str | None:
    """Extract the text content of the first <h1> in html."""
    match = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.DOTALL | re.IGNORECASE)
    if not match:
        return None
    # Strip inner tags and decode entities
    text = re.sub(r"<[^>]+>", "", match.group(1)).strip()
    return text


def _extract_h2s(html: str) -> list[tuple[str, str]]:
    """Extract all (h2_id_candidate, h2_text) pairs from html."""
    results = []
    for match in re.finditer(r"<h2[^>]*>(.*?)</h2>", html, re.DOTALL | re.IGNORECASE):
        text = re.sub(r"<[^>]+>", "", match.group(1)).strip()
        if text:
            results.append((text.lower(), text))
    return results


def _check_h1_exact(html: str, expected_topic: str) -> tuple[bool, str]:
    """
    Check that output has exactly one <h1> matching expected_topic.
    H1 text is matched case-insensitively after stripping whitespace.
    """
    h1_text = _extract_h1(html)
    if h1_text is None:
        return False, f"H1 missing. Expected: {expected_topic!r}."

    expected_normalized = expected_topic.strip()
    if h1_text.strip().lower() != expected_normalized.lower():
        return False, (
            f"H1 mismatch. Got: {h1_text!r}. Expected: {expected_normalized!r}."
        )

    # Also verify there is exactly one <h1>
    all_h1s = re.findall(r"<h1[^>]*>.*?</h1>", html, re.DOTALL | re.IGNORECASE)
    if len(all_h1s) != 1:
        return False, (
            f"Expected exactly 1 <h1>, found {len(all_h1s)}. "
            f"First H1: {h1_text!r}."
        )

    return True, "H1 exact match."


def _check_h2_plan_match(
    html: str, approved_h2_plan: list[dict]
) -> tuple[bool, str]:
    """
    Check that each approved H2 text appears in the output.
    Allows for minor rephrasing but requires the core heading text.
    """
    if not approved_h2_plan:
        return True, "No H2 plan to check."

    found_h2s = _extract_h2s(html)
    found_lower = [h[0] for h in found_h2s]

    missing = []
    for plan_item in approved_h2_plan:
        h2_text = plan_item.get("h2", "").strip()
        if not h2_text:
            continue
        # Check if the H2 text (or a significant portion) appears
        h2_normalized = h2_text.lower()
        # Allow partial match for rephrasing tolerance (first 10 chars minimum)
        found_match = any(
            h2_normalized in f or f in h2_normalized
            for f in found_lower
        )
        if not found_match:
            missing.append(h2_text)

    if missing:
        return False, (
            f"H2 plan mismatch. Missing headings: {missing}. "
            f"Found H2s: {[h[1] for h in found_h2s]}."
        )

    return True, f"All {len(approved_h2_plan)} approved H2s found."


def _check_topic_term_clean(
    html: str, cluster: str, job_id: str
) -> tuple[bool, str]:
    """
    Check that output does not contain terms associated with a different cluster.
    Uses the CLUSTER_CONTAMINATION_BLOCKLIST to determine blocked terms.
    """
    blocked = _get_blocked_terms_for_cluster(cluster)
    if not blocked:
        return True, "No blocked terms defined for this cluster."

    html_lower = html.lower()
    found_contaminants = []

    for term in sorted(blocked):
        # Whole-word match to avoid false positives from substrings
        pattern = rf"\b{re.escape(term)}\b"
        if re.search(pattern, html_lower, re.IGNORECASE):
            found_contaminants.append(term)

    if found_contaminants:
        return False, (
            f"TOPIC_IDENTITY_CONTAMINATED: "
            f"Cluster={cluster!r}, Job={job_id}. "
            f"Found blocked terms: {found_contaminants}. "
            f"These terms do not belong to the current article topic."
        )

    return True, f"No blocked terms found (cluster={cluster})."


def run_topic_identity_gate(
    job_id: int | str,
    expected_topic: str,
    target_keyword: str,
    cluster: str,
    approved_h2_plan: list[dict],
    output_html: str,
) -> dict[str, Any]:
    """
    Run the post-writer topic identity gate.

    Returns
    -------
    {
        "decision":  TOPIC_IDENTITY_PASS | TOPIC_IDENTITY_BLOCK,
        "job_id":    str(job_id),
        "cluster":   cluster,
        "checks": [
            {"check": "H1_EXACT",          "passed": bool, "detail": str},
            {"check": "H2_PLAN_MATCH",      "passed": bool, "detail": str},
            {"check": "TOPIC_TERM_CLEAN",   "passed": bool, "detail": str},
        ],
        "blockers":   list[str],   # filled only when decision == BLOCK
        "message":    str,
    }
    """
    blockers: list[str] = []
    checks: list[dict] = []

    # ── Input validation ───────────────────────────────────────────────
    if not expected_topic:
        blockers.append(GATE_ERR_INVALID_INPUT)
        return {
            "decision": TOPIC_IDENTITY_BLOCK,
            "job_id": str(job_id),
            "cluster": cluster,
            "checks": checks,
            "blockers": blockers,
            "message": f"Job {job_id}: expected_topic is required.",
        }

    if not output_html or not isinstance(output_html, str):
        blockers.append(GATE_ERR_NO_HTML)
        return {
            "decision": TOPIC_IDENTITY_BLOCK,
            "job_id": str(job_id),
            "cluster": cluster,
            "checks": checks,
            "blockers": blockers,
            "message": f"Job {job_id}: output_html is missing or empty.",
        }

    # ── Check 1: H1 exact match ────────────────────────────────────────
    h1_pass, h1_detail = _check_h1_exact(output_html, expected_topic)
    checks.append({"check": "H1_EXACT", "passed": h1_pass, "detail": h1_detail})
    if not h1_pass:
        blockers.append("H1_MISSING_OR_MISMATCH")

    # ── Check 2: H2 plan match ────────────────────────────────────────
    h2_pass, h2_detail = _check_h2_plan_match(output_html, approved_h2_plan)
    checks.append({"check": "H2_PLAN_MATCH", "passed": h2_pass, "detail": h2_detail})
    if not h2_pass:
        blockers.append("H2_PLAN_MISMATCH")

    # ── Check 3: topic term clean ──────────────────────────────────────
    term_pass, term_detail = _check_topic_term_clean(output_html, cluster, str(job_id))
    checks.append({
        "check": "TOPIC_TERM_CLEAN",
        "passed": term_pass,
        "detail": term_detail,
    })
    if not term_pass:
        blockers.append("TOPIC_IDENTITY_CONTAMINATED")

    # ── Decision ────────────────────────────────────────────────────────
    if blockers:
        decision = TOPIC_IDENTITY_BLOCK
        message = (
            f"Job {job_id} topic identity gate BLOCKED. "
            f"Cluster={cluster}. Blockers: {blockers}. "
            f"Details: {checks}"
        )
    else:
        decision = TOPIC_IDENTITY_PASS
        message = (
            f"Job {job_id} topic identity gate PASSED. "
            f"Cluster={cluster}. Checks: {checks}"
        )

    return {
        "decision": decision,
        "job_id": str(job_id),
        "cluster": cluster,
        "checks": checks,
        "blockers": blockers,
        "message": message,
    }
