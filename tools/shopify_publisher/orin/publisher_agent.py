#!/usr/bin/env python3
"""
ORIN Publisher Agent — Phase 2G
Publisher Preflight Hardening — live inventory refresh + exact title + near-handle blocking

Mode: DRY-RUN ONLY — no Shopify API calls, no queue updates, no publishing

Usage:
  python3 publisher_agent.py                      # human-readable + JSON
  python3 publisher_agent.py --json              # JSON-only (for scripts/wrappers)
  python3 publisher_agent.py "Job 21" <draft_path> --expected-slug <slug> --json
  python3 publisher_agent.py --job-context <path> --json
"""

import json
import re
import sys
import hashlib
from datetime import datetime, timezone
from pathlib import Path

# Canonical queue parser — single source of truth for queue file parsing
sys.path.insert(0, str(Path(__file__).parent))
from queue_parser import get_queue_job, parse_queue_file
from shopify_draft_transaction import fetch_blog_articles_paginated
from workspace_paths import workspace_root

# ─── JSON-only mode ────────────────────────────────────────────────────────────
JSON_MODE = "--json" in sys.argv
sys.argv = [a for a in sys.argv if a != "--json"]

JOB_CONTEXT_ARG = "--job-context"
EXPECTED_SLUG_ARG = "--expected-slug"
WRITER_EXECUTION_ARG = "--writer-execution"

# ─── CANONICAL PATHS ──────────────────────────────────────────────────────────

BASE_DIR = workspace_root()
QUEUE_PATH = BASE_DIR / "clients/hoverboard_store/content_engine/content_queue_3_months.md"
INVENTORY_PATH = BASE_DIR / "clients/hoverboard_store/content_engine/shopify_inventory.json"
DRAFT_INVENTORY_PATH = BASE_DIR / "clients/hoverboard_store/content_engine/draft_inventory.md"

# ─── Shopify config (lazy load) ──────────────────────────────────────────────

BLOG_TARGET = "Journal Insights"

# ─── RESOLVE JOB CONTEXT ───────────────────────────────────────────────────────

_job_ctx = None
_parsed_job_number = None
_parsed_draft_path = None
_parsed_expected_slug = None
_parsed_queue_status = None

def _resolve_job_context():
    """
    Resolve job parameters from:
      1. --job-context <path>  → read job context JSON
      2. positional args        → job_id, draft_path
      3. --expected-slug <slug> → override expected slug
    """
    global _job_ctx, _parsed_job_number, _parsed_draft_path
    global _parsed_expected_slug, _parsed_queue_status, _parsed_writer_execution

    _parsed_writer_execution = None

    # --job-context takes priority
    if JOB_CONTEXT_ARG in sys.argv:
        idx = sys.argv.index(JOB_CONTEXT_ARG)
        ctx_path = sys.argv[idx + 1]
        ctx_path = Path(ctx_path)
        if ctx_path.exists():
            _job_ctx = json.loads(ctx_path.read_text())
        else:
            print(f"WARNING: job context not found: {ctx_path}", file=sys.stderr)

    if _job_ctx:
        _parsed_job_number = _job_ctx.get("job_number", "")
        _parsed_expected_slug = _job_ctx.get("shopify_handle")
        _parsed_queue_status = _job_ctx.get("queue_status", "planned")
        # PHASE G.1 FIX: Use Writer execution preview for draft path if context path is null
        # This prevents requiring manual context patching after Writer execution
        if WRITER_EXECUTION_ARG in sys.argv:
            idx = sys.argv.index(WRITER_EXECUTION_ARG)
            we_path = Path(sys.argv[idx + 1])
            if we_path.exists():
                _parsed_writer_execution = json.loads(we_path.read_text())
        # Resolve draft path: prefer Writer execution output path over null context path
        ctx_draft_path = _job_ctx.get("local_draft_path")
        writer_output_path = (
            _parsed_writer_execution.get("output_path")
            if _parsed_writer_execution else None
        )
        _parsed_draft_path = writer_output_path or ctx_draft_path
        return

    # Positional args: job_id draft_path
    _parsed_job_number = sys.argv[1] if len(sys.argv) > 1 else None
    _parsed_draft_path = sys.argv[2] if len(sys.argv) > 2 else None

    # Writer execution preview path
    if WRITER_EXECUTION_ARG in sys.argv:
        idx = sys.argv.index(WRITER_EXECUTION_ARG)
        we_path = Path(sys.argv[idx + 1])
        if we_path.exists():
            _parsed_writer_execution = json.loads(we_path.read_text())
            # Use Writer output path as draft path if not set via positional
            if not _parsed_draft_path and _parsed_writer_execution.get("output_path"):
                _parsed_draft_path = _parsed_writer_execution.get("output_path")

    if EXPECTED_SLUG_ARG in sys.argv:
        idx = sys.argv.index(EXPECTED_SLUG_ARG)
        _parsed_expected_slug = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else None

    _parsed_queue_status = "planned"  # default; override via --queue-status if needed

_resolve_job_context()

TARGET_JOB = _parsed_job_number or "Unknown"
DRAFT_PATH = _parsed_draft_path
EXPECTED_SLUG = _parsed_expected_slug
EXPECTED_STATUS = _parsed_queue_status

# ─── HELPERS ──────────────────────────────────────────────────────────────────

def log(msg):
    """Human-readable timestamped log. Silenced in --json mode."""
    if not JSON_MODE:
        print(f"  [{datetime.now().strftime('%H:%M:%S')}] {msg}")

def _silent_print(*args, **kwargs):
    pass

def read_file(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

def extract_html_body(html_content):
    """Strip comment block and extract body HTML length."""
    stripped = re.sub(r"<!--.*?-->\s*", "", html_content, flags=re.DOTALL)
    return stripped.strip(), len(stripped)

def extract_meta_from_comment(html_content):
    """Extract slug, title, meta title, meta description from comment block."""
    match = re.search(r"<!--(.*?)-->", html_content, re.DOTALL)
    if not match:
        return {}
    lines = match.group(1).strip().split("\n")
    meta = {}
    for line in lines:
        if ":" in line:
            key, _, value = line.partition(":")
            meta[key.strip().lower().replace(" ", "_")] = value.strip()
    return meta

# ─── INVENTORY ANALYSIS ───────────────────────────────────────────────────────

def analyse_shopify_conflicts(inventory, handle, title, queue_article_id=None):
    """
    PHASE 2G: Analyse live inventory for all conflict types.

    Returns dict with:
      - exact_handle_match: article with same handle (or None)
      - exact_title_match:  article with identical title, different handle (or None)
      - near_handle_matches: articles with near handle variants (list)
      - near_title_matches:  articles with meaningful title overlap (list)
      - self_match:          exact handle match AND matches queue article ID (already created)
    """
    handle_lower = handle.lower()
    title_lower = title.lower()

    result = {
        "exact_handle_match": None,
        "exact_title_match": None,
        "near_handle_matches": [],
        "near_title_matches": [],
        "self_match": False,
        "self_match_article": None,
    }

    for article in inventory:
        art_handle = article.get("handle", "").lower()
        art_title = article.get("title", "").lower()
        art_id = article.get("id")

        # Exact handle match
        if art_handle == handle_lower:
            result["exact_handle_match"] = article
            # Self-match: exact handle AND matches queue-recorded article ID
            if queue_article_id and art_id == queue_article_id:
                result["self_match"] = True
                result["self_match_article"] = article

        # Exact title match — same title, DIFFERENT handle
        if art_title == title_lower and art_handle != handle_lower:
            result["exact_title_match"] = article

        # Near-handle variant: same base slug, one insertion/deletion/variant
        # Detect: same prefix (hoverboard-accessories), contains "safer-riding"
        # but not identical to our handle
        if art_handle != handle_lower:
            if _is_near_handle(handle_lower, art_handle):
                result["near_handle_matches"].append(article)

        # Near-title overlap (meaningful word match)
        title_words = set(title_lower.split())
        art_words = set(art_title.split())
        skip = {"the", "a", "an", "for", "and", "or", "to", "of", "in", "on", "uk", "2026"}
        meaningful = (title_words & art_words) - skip
        if len(meaningful) >= 4 and art_handle != handle_lower:
            result["near_title_matches"].append(article)

    return result


def _is_near_handle(handle_a, handle_b):
    """
    Detect near-handle slug variants.
    Flags:
      - one handle is the other with a single word inserted (e.g. "for" inserted)
      - same prefix, same suffix, minor token difference
    Examples:
      best-hoverboard-accessories-safer-riding-uk-2026
      best-hoverboard-accessories-FOR-safer-riding-uk-2026  ← flagged
    """
    # Same article type prefix check
    if not handle_a.startswith("best-hoverboard") and not handle_b.startswith("best-hoverboard"):
        return False

    a_parts = set(handle_a.split("-"))
    b_parts = set(handle_b.split("-"))

    # If the difference is exactly one small token (like "for", "the", "best")
    diff = a_parts ^ b_parts
    small_tokens = {"for", "the", "best", "a", "an", "to", "of", "in", "on"}
    diff_meaningful = diff - small_tokens

    # Same base: if they share the core topic terms and differ by <= 1 small token
    core_a = a_parts - small_tokens
    core_b = b_parts - small_tokens
    if core_a == core_b and len(diff_meaningful) == 0:
        return True  # differ only by small token
    if core_a == core_b and len(diff_meaningful) == 1:
        return True  # differ by one meaningful token
    if len(diff) == 1 and (diff & small_tokens):
        return True  # differ by exactly one small token

    return False


def get_queue_article_id(queue_path, job_id):
    """Extract Shopify article ID from queue job notes if present."""
    try:
        content = read_file(queue_path)
        # Look for Shopify article ID in job notes
        pattern = rf"##\s+{re.escape(job_id)}.*?Shopify article ID:\s*(\d+)"
        match = re.search(pattern, content, re.DOTALL)
        if match:
            return int(match.group(1))
        return None
    except Exception:
        return None


# ─── LEGACY INVENTORY CHECK (for backwards compat / fallback) ─────────────────

def check_shopify_inventory_local(inventory_path, handle, title):
    """
    Check LOCAL inventory file (non-live). Used as fallback when live fetch fails.
    Returns (handle_match, title_matches, error)
    """
    try:
        with open(inventory_path, "r", encoding="utf-8") as f:
            inventory = json.load(f)
    except Exception as e:
        return None, [], f"LOCAL_INVENTORY_READ_ERROR: {e}"

    handle_lower = handle.lower()
    title_lower = title.lower()
    handle_match = None
    title_matches = []

    for article in inventory:
        art_handle = article.get("handle", "").lower()
        art_title = article.get("title", "").lower()
        if art_handle == handle_lower:
            handle_match = article
        title_words = set(title_lower.split())
        art_words = set(art_title.split())
        skip = {"the", "a", "an", "for", "and", "or", "to", "of", "in", "on", "uk", "2026"}
        if len((title_words & art_words) - skip) >= 4:
            title_matches.append(article)

    return handle_match, title_matches, None


def refresh_shopify_inventory():
    """
    Refresh Shopify inventory, falling back to the checked-in snapshot.

    Dry-run execution deliberately removes Shopify credentials. Configuration
    loading therefore raises before ``fetch_blog_articles_paginated`` can
    return its normal error tuple. Treat that as an unavailable live source,
    never expose the exception message, and use the local snapshot for the
    read-only simulation. If neither source is available, callers must block.
    """
    live_error = None
    try:
        inventory, live_error = fetch_blog_articles_paginated(
            limit=250,
            max_pages=20,
        )
    except Exception as exc:
        inventory = []
        live_error = f"LIVE_FETCH_EXCEPTION:{type(exc).__name__}"

    if live_error is None:
        return {
            "inventory": inventory,
            "live_fetch_success": True,
            "fallback_used": False,
            "inventory_available": True,
            "source": "live",
            "error": None,
        }

    try:
        with open(INVENTORY_PATH, "r", encoding="utf-8") as inventory_file:
            fallback_inventory = json.load(inventory_file)
        if not isinstance(fallback_inventory, list):
            raise ValueError("inventory snapshot must be a list")
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return {
            "inventory": [],
            "live_fetch_success": False,
            "fallback_used": False,
            "inventory_available": False,
            "source": "unavailable",
            "error": live_error,
        }

    return {
        "inventory": fallback_inventory,
        "live_fetch_success": False,
        "fallback_used": True,
        "inventory_available": True,
        "source": "local_snapshot",
        "error": live_error,
    }

# ─── QUALITY CHECKS ────────────────────────────────────────────────────────────

def compliance_check(html_content):
    """
    PHASE G.1 FIX: Context-aware compliance checking.

    Distinguishes:
      AFFIRMATIVE_PROHIBITED_CLAIM — "This hoverkart guarantees safe operation."
      NEGATED_CAUTION              — "No hoverkart guarantees safe operation."
      DISCLAIMER                  — "Compatibility does not guarantee safe operation."
      UNRELATED_CONTEXT           — "Check the manufacturer's guarantee."

    Only affirmative prohibited safety/compliance claims block.
    Negated cautions, disclaimers, and unrelated mentions do NOT block.
    "guarantee" alone is insufficient for blocking — negation context required.
    """    # Patterns that represent affirmative (prohibited) safety/performance claims
    # These ALWAYS block when found without a negation modifier
    AFFIRMATIVE_PATTERNS = [
        (r"prevents all injuries", "PREVENTS_ALL_INJURIES"),
        (r"eliminates.*risk", "ELIMINATES_RISK"),
        (r"\bno risk\b", "NO_RISK"),
        (r"100% safe", "100_PERCENT_SAFE"),
        (r"guarantee[d]?s?\s+(?:your\s+)?(?:safety|safe|secure)", "GUARANTEE_SAFETY", "affirmative"),
        (r"will prevent", "WILL_PREVENT"),
        (r"clinically proven", "CLINICALLY_PROVEN"),
        (r"award[- ]?winning", "AWARD_WINNING"),
        (r" UK's #1", "UK_NUMBER_ONE"),
        (r"single most effective", "SINGLE_MOST_EFFECTIVE"),
    ]
    # Negation modifiers that flip a prohibited claim into a safe negated caution
    NEGATION_PATTERNS = [
        r"\bno\b",
        r"\bnot\b",
        r"\bnever\b",
        r"\bdoesn't\b",
        r"\bdoes\s+not\b",
        r"\bcan\s+not\b",
        r"\bcannot\b",
        r"\bwithout\b",
        r"\bdoes\b.*\bno\b",   # "does no" as negation
    ]

    issues = []
    lines = html_content.split("\n")

    for i, line in enumerate(lines, 1):
        # Skip HTML comments
        if re.match(r"\s*<!--", line) or "-->" in line:
            continue

        # Check each affirmative pattern
        for item in AFFIRMATIVE_PATTERNS:
            if len(item) == 2:
                pattern, code = item
                claim_type = "affirmative"
            else:
                pattern, code, claim_type = item

            match = re.search(pattern, line, re.IGNORECASE)
            if not match:
                continue

            matched_text = match.group(0)

            # Check if this is a negated/caution context
            # Look for negation words within ~50 chars before the match
            context_start = max(0, match.start() - 50)
            context_before = line[context_start:match.start()].lower()

            is_negated = any(
                re.search(neg_pat, context_before)
                for neg_pat in NEGATION_PATTERNS
            )

            # Also check for "does not guarantee" / "no guarantee" patterns
            # These are strong negation signals even if not immediately adjacent
            full_line_lower = line.lower()

            # Check for disclaimer pattern: something does not/don't guarantee
            disclaimer_patterns = [
                r"does\s+not\s+guarantee",
                r"don['\s]+t\s+guarantee",
                r"cannot\s+guarantee",
                r"can\s+not\s+guarantee",
                r"will\s+not\s+guarantee",
            ]
            is_disclaimer = any(
                re.search(dp, full_line_lower)
                for dp in disclaimer_patterns
            )

            # Check for unrelated guarantee mentions
            # e.g., "manufacturer's guarantee", "check the guarantee"
            unrelated_patterns = [
                r"manufacturer['\s]+s?\s+guarantee",
                r"product\s+guarantee",
                r"return\s+guarantee",
                r"check\s+(?:the\s+)?(?:manufacturer['\s]+s?\s+)?guarantee",
                r"guarantee\s+(?:is\s+)?(?:valid\s+)?(?:on\s+)?(?:product|purchase)",
            ]
            is_unrelated = any(
                re.search(up, full_line_lower)
                for up in unrelated_patterns
            )

            if is_negated or is_disclaimer:
                classification = "NEGATED_CAUTION" if is_negated and not is_disclaimer else "DISCLAIMER"
                issues.append((i, f"{code}_{classification}", line.strip()[:80], classification))
            elif is_unrelated:
                issues.append((i, f"{code}_UNRELATED", line.strip()[:80], "UNRELATED_CONTEXT"))
            else:
                issues.append((i, code, line.strip()[:80], "AFFIRMATIVE_PROHIBITED_CLAIM"))

    return issues

def html_quality_check(html_content):
    issues = []
    warnings = []
    required_classes = ["hs-article", "hs-container"]
    for cls in required_classes:
        if cls not in html_content:
            issues.append(f"Missing required HBS class: {cls}")
    if not re.search(r"<h1>", html_content):
        issues.append("Missing <h1>")
    h2_count = len(re.findall(r"<h2>", html_content))
    if h2_count < 5:
        warnings.append(f"Low H2 count: {h2_count} (expected >= 5)")
    if "hs-faq" not in html_content:
        warnings.append("No FAQ section found")
    if "hs-cta" not in html_content:
        warnings.append("No CTA block found")
    if "Hoverboard Store" not in html_content:
        issues.append("Missing byline / Hoverboard Store attribution")
    return len(issues) == 0, issues, warnings

# ─── MAIN ─────────────────────────────────────────────────────────────────────

def run_dryrun(job_id, draft_path):
    """
    Phase 2G: Publisher preflight with live inventory refresh.
    - Always fetches live Shopify inventory before checks
    - Checks exact handle, exact title, near-handle, near-title
    - Self-match detection: if canonical article already queued, flags as already_created
    - Blocks on any unacknowledged duplicate
    """
    if JSON_MODE:
        _saved_print = print
        globals()["print"] = _silent_print

    print(f"\n{'='*60}")   # noqa: F405
    print(f"ORIN PUBLISHER AGENT — PHASE 2G PREFLIGHT")   # noqa: F405
    print(f"Target: {job_id}")   # noqa: F405
    print(f"{'='*60}\n")   # noqa: F405

    results = {
        "phase": "Phase 2G",
        "mode": "dry_run",
        "target_job": job_id,
        "publisher_job_number": job_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "checks": {},
        "payload_preview": None,
        "decision": None,
        "passed": False,
    }

    # ── Step 0: Queue article ID lookup (canonical parser) ─────────────────
    print(f"STEP 0 — Queue Article ID Lookup (Canonical Parser)")   # noqa: F405
    queue_job = get_queue_job(str(QUEUE_PATH), job_id)
    queue_article_id = queue_job.get("shopify_article_id") if queue_job else None
    queue_status = queue_job.get("queue_status", "not_found") if queue_job else "not_found"
    queue_handle_from_notes = queue_job.get("shopify_handle") if queue_job else None
    log(f"Queue article ID: {queue_article_id}")
    log(f"Queue status: {queue_status}")
    log(f"Queue handle from notes: {queue_handle_from_notes}")
    print(f"  Queue Shopify article ID: {queue_article_id or 'not recorded'}")
    print(f"  Queue status: {queue_status}")
    print(f"  Queue handle from notes: {queue_handle_from_notes or 'not recorded'}")
    results["checks"]["queue_article_id"] = queue_article_id
    results["checks"]["queue_status"] = {
        "expected": EXPECTED_STATUS,
        "found": queue_status,
        "pass": queue_status == EXPECTED_STATUS,
    }
    print()   # noqa: F405

    # ── Step 1: Writer/Context invariant checks ───────────────────────────
    print(f"STEP 1 — Writer Artifact Invariant Checks")   # noqa: F405
    invariant_errors = []

    # 1a. Job number invariant: writer execution job must match selected job context
    writer_job_num = None
    writer_output_path = None
    writer_sha256 = None
    if _parsed_writer_execution:
        writer_job_num = _parsed_writer_execution.get("job_number")
        writer_output_path = _parsed_writer_execution.get("output_path")
        writer_sha256 = _parsed_writer_execution.get("sha256")

    if writer_job_num and _job_ctx:
        ctx_job_num = _job_ctx.get("job_number")
        if str(writer_job_num) != str(ctx_job_num):
            invariant_errors.append(
                f"BLOCK_JOB_CONTEXT_MISMATCH: writer job {writer_job_num} != context job {ctx_job_num}"
            )
            print(f"  ❌ BLOCK_JOB_CONTEXT_MISMATCH: writer job {writer_job_num} != context job {ctx_job_num}")   # noqa: F405
        else:
            print(f"  ✅ Job number invariant: writer {writer_job_num} == context {ctx_job_num}")   # noqa: F405
    else:
        print(f"  ℹ️  Skipped: writer execution or context missing job number")   # noqa: F405

    # 1b. Draft path invariant: Publisher must use Writer execution output path
    if writer_output_path and draft_path:
        if writer_output_path != draft_path:
            invariant_errors.append(
                f"BLOCK_DRAFT_PATH_MISMATCH: publisher path {draft_path} != writer output {writer_output_path}"
            )
            print(f"  ❌ BLOCK_DRAFT_PATH_MISMATCH: publisher {draft_path} != writer {writer_output_path}")   # noqa: F405
        else:
            print(f"  ✅ Draft path invariant: publisher path == writer output path")   # noqa: F405
    else:
        print(f"  ℹ️  Skipped: writer output path or draft path missing")   # noqa: F405

    # 1c. SHA256 invariant: local draft must not be mutated after Writer execution
    # Deferred to after local draft check (Step 3) when draft_content is available
    sha256_check_passed = None
    sha256_current = None

    results["checks"]["invariant_checks"] = {
        "job_number_match": writer_job_num == _job_ctx.get("job_number") if (writer_job_num and _job_ctx) else None,
        "draft_path_match": writer_output_path == draft_path if (writer_output_path and draft_path) else None,
        "sha256_match": sha256_check_passed,  # filled in after draft is read
        "errors": invariant_errors,
    }
    print()   # noqa: F405

    # Block on invariant errors before proceeding
    if invariant_errors:
        results["decision"] = "BLOCK — " + "; ".join(invariant_errors)
        results["passed"] = False
        if JSON_MODE:
            globals()["print"] = _saved_print
            sys.stdout.write(json.dumps(results, indent=2, default=str))
        return results

    # ── Step 2 (renumbered): Queue status ──────────────────────────────
    print(f"STEP 3 — Local Draft Check")   # noqa: F405
    try:
        draft_content = read_file(draft_path)
        draft_exists = True
        log(f"File exists — {len(draft_content)} bytes")
    except FileNotFoundError:
        draft_exists = False
        draft_content = ""
        log("FILE NOT FOUND")
    results["checks"]["local_draft_exists"] = draft_exists
    print(f"  Local draft exists: {'✅ YES' if draft_exists else '❌ NO'}")   # noqa: F405
    print()   # noqa: F405

    if not draft_exists:
        results["decision"] = "BLOCK — local draft not found"
        results["passed"] = False
        if JSON_MODE:
            globals()["print"] = _saved_print
            sys.stdout.write(json.dumps(results, indent=2, default=str))
        return results

    # Re-check SHA256 after file read (local draft exists)
    if writer_sha256:
        sha256_current = hashlib.sha256(draft_content.encode()).hexdigest()
        sha256_check_passed = sha256_current == writer_sha256
        results["checks"]["invariant_checks"]["sha256_match"] = sha256_check_passed
        if not sha256_check_passed:
            err = f"BLOCK_LOCAL_DRAFT_MUTATED_AFTER_WRITER: current {sha256_current} != writer {writer_sha256}"
            results["decision"] = err
            results["passed"] = False
            if JSON_MODE:
                globals()["print"] = _saved_print
                sys.stdout.write(json.dumps(results, indent=2, default=str))
            return results
        print(f"  ✅ SHA256 invariant: draft not mutated after Writer")   # noqa: F405
        print(f"    SHA256: {writer_sha256}")   # noqa: F405

    print(f"STEP 4 — Queue Status Check")   # noqa: F405
    status_ok = queue_status == EXPECTED_STATUS
    print(f"  Expected: {EXPECTED_STATUS} | Found: {queue_status} | {'✅ PASS' if status_ok else '❌ FAIL'}")   # noqa: F405
    print()   # noqa: F405

    # ── Step 5: Slug verification ──────────────────────────────────────────
    print(f"STEP 5 — Slug Verification")   # noqa: F405
    meta = extract_meta_from_comment(draft_content)
    actual_slug = meta.get("url_slug", "")
    title_from_meta = meta.get("meta_title", "")
    # If no expected slug in job context (new planned job), skip check
    if not EXPECTED_SLUG:
        slug_ok = True
        log("No expected slug in job context — slug verification skipped")
        print(f"  Expected: (none — new planned job, handle not yet known)")
        print(f"  Found:    {actual_slug or '(none)'}")
        print(f"  ℹ️  SKIPPED — new planned job, handle assigned by writer")   # noqa: F405
    else:
        slug_ok = actual_slug == EXPECTED_SLUG
        print(f"  Expected: {EXPECTED_SLUG}")   # noqa: F405
        print(f"  Found:    {actual_slug}")   # noqa: F405
        print(f"  {'✅ MATCH' if slug_ok else '❌ MISMATCH'}")   # noqa: F405
    results["checks"]["slug"] = {
        "expected": EXPECTED_SLUG or "(skipped — new planned job)",
        "found": actual_slug,
        "pass": slug_ok,
    }
    print()   # noqa: F405

    # ── Step 6: LIVE inventory refresh ─────────────────────────────────────
    print(f"STEP 6 — Live Shopify Inventory Refresh")   # noqa: F405
    log("Refreshing live inventory from Shopify API...")
    inventory_refresh = refresh_shopify_inventory()
    inventory = inventory_refresh["inventory"]
    inv_error = inventory_refresh["error"]
    inventory_available = inventory_refresh["inventory_available"]
    if inv_error:
        print(f"  ⚠️  Live fetch unavailable: {inv_error}")
    if inventory_refresh["fallback_used"]:
        print(f"  ⚠️  Using local inventory snapshot")
    if not inventory_available:
        print(f"  ❌ No inventory source available")
    results["checks"]["live_inventory_refresh"] = {
        "attempted": True,
        "live_fetch_success": inventory_refresh["live_fetch_success"],
        "fallback_used": inventory_refresh["fallback_used"],
        "inventory_available": inventory_available,
        "source": inventory_refresh["source"],
        "article_count": len(inventory),
    }
    print(f"  Inventory articles: {len(inventory)}")   # noqa: F405
    print()   # noqa: F405

    # ── Step 5: Conflict analysis (PHASE 2G) ───────────────────────────────
    print(f"STEP 7 — Conflict Analysis (exact handle / exact title / near-handle)")   # noqa: F405
    conflicts = analyse_shopify_conflicts(inventory, actual_slug, title_from_meta, queue_article_id)
    results["checks"]["conflicts"] = {
        "exact_handle_match": {
            "found": conflicts["exact_handle_match"] is not None,
            "article_id": conflicts["exact_handle_match"].get("id") if conflicts["exact_handle_match"] else None,
            "handle": conflicts["exact_handle_match"].get("handle") if conflicts["exact_handle_match"] else None,
        },
        "exact_title_match": {
            "found": conflicts["exact_title_match"] is not None,
            "article_id": conflicts["exact_title_match"].get("id") if conflicts["exact_title_match"] else None,
            "handle": conflicts["exact_title_match"].get("handle") if conflicts["exact_title_match"] else None,
            "title": conflicts["exact_title_match"].get("title") if conflicts["exact_title_match"] else None,
        },
        "near_handle_matches": {
            "count": len(conflicts["near_handle_matches"]),
            "articles": [
                {"id": a.get("id"), "handle": a.get("handle"), "title": a.get("title")}
                for a in conflicts["near_handle_matches"]
            ],
        },
        "near_title_matches": {
            "count": len(conflicts["near_title_matches"]),
        },
        "self_match": conflicts["self_match"],
        "self_match_article_id": conflicts["self_match_article"].get("id") if conflicts["self_match_article"] else None,
    }

    print(f"  Exact handle match: {'YES' if conflicts['exact_handle_match'] else 'NO'}")
    if conflicts["exact_handle_match"]:
        print(f"    → Article ID {conflicts['exact_handle_match'].get('id')} | {conflicts['exact_handle_match'].get('handle')}")
    print(f"  Exact title match (different handle): {'YES ❌ BLOCK' if conflicts['exact_title_match'] else 'NO'}")
    if conflicts["exact_title_match"]:
        print(f"    → Article ID {conflicts['exact_title_match'].get('id')} | {conflicts['exact_title_match'].get('handle')}")
        print(f"    → Title: {conflicts['exact_title_match'].get('title')}")
    print(f"  Near-handle variants: {len(conflicts['near_handle_matches'])}")
    for a in conflicts["near_handle_matches"]:
        print(f"    → {a.get('handle')}")
    print(f"  Near-title overlaps: {len(conflicts['near_title_matches'])}")
    print(f"  Self-match (already created): {'YES ✅' if conflicts['self_match'] else 'NO'}")
    if conflicts["self_match"]:
        print(f"    → Matches queue article ID {conflicts['self_match_article'].get('id')}")
    print()   # noqa: F405

    # ── Step 8: Compliance check ──────────────────────────────────────────
    print(f"STEP 8 — Compliance Check")   # noqa: F405
    compliance_issues = compliance_check(draft_content)

    # Separate blocking (affirmative) from non-blocking (negated/disclaimer/unrelated)
    blocked_issues = []
    allowed_issues = []
    for item in compliance_issues:
        line_no, code, text = item[:3]
        classification = item[3] if len(item) > 3 else "AFFIRMATIVE_PROHIBITED_CLAIM"
        issue_entry = {"line": line_no, "code": code, "text": text, "classification": classification}
        if classification == "AFFIRMATIVE_PROHIBITED_CLAIM":
            blocked_issues.append(issue_entry)
        else:
            allowed_issues.append(issue_entry)
    compliance_pass = len(blocked_issues) == 0
    compliance_has_allowed = len(allowed_issues) > 0
    results["checks"]["compliance"] = {
        "issues_found": len(compliance_issues),
        "blocked_count": len(blocked_issues),
        "allowed_count": len(allowed_issues),
        "pass": compliance_pass,
        "blocked_issues": blocked_issues,
        "allowed_issues": allowed_issues,
    }
    if blocked_issues:
        for issue in blocked_issues:
            print(f"  ❌ BLOCKED Line {issue['line']} [{issue['code']}] ({issue['classification']}): {issue['text']}")   # noqa: F405
    if allowed_issues:
        for issue in allowed_issues:
            print(f"  ⚠️  ALLOWED Line {issue['line']} [{issue['code']}] ({issue['classification']}): {issue['text']}")   # noqa: F405
    if compliance_issues and not blocked_issues:
        print(f"  ℹ️  All flagged language is non-blocking (negated/disclaimer/unrelated)")   # noqa: F405
    if not compliance_issues:
        print(f"  ✅ PASS — no flagged language")   # noqa: F405
    print()   # noqa: F405

    # ── Step 7: HTML quality check ────────────────────────────────────────
    print(f"STEP 9 — HTML Quality Check")   # noqa: F405
    hq_pass, hq_issues, hq_warnings = html_quality_check(draft_content)
    results["checks"]["html_quality"] = {
        "pass": hq_pass,
        "issues": hq_issues,
        "warnings": hq_warnings,
    }
    if hq_issues:
        for issue in hq_issues:
            print(f"  ❌ {issue}")   # noqa: F405
    for w in hq_warnings:
        print(f"  ⚠️  {w}")   # noqa: F405
    if hq_pass and not hq_warnings:
        print(f"  ✅ PASS")   # noqa: F405
    elif hq_pass:
        print(f"  ✅ PASS (warnings above)")   # noqa: F405
    print()   # noqa: F405

    # ── Step 8: Payload preview ────────────────────────────────────────────
    print(f"STEP 10 — Payload Preview")   # noqa: F405
    body_html, body_len = extract_html_body(draft_content)
    payload = {
        "article": {
            "title": title_from_meta or "Best Hoverboard Accessories for Safer Riding UK 2026",
            "author": "Hoverboard Store",
            "handle": actual_slug,
            "published": False,
            "published_at": None,
            "body_html": body_html[:200] + f"\n... [{body_len:,} chars total] ...",
            "body_html_length": body_len,
            "tags": ["hoverboard", "accessories", "safety", "uk"],
            "meta_title": meta.get("meta_title", ""),
            "meta_description": meta.get("meta_description", ""),
        },
        "expected_action": "create_new_shopify_draft",
        "queue_update_after_push": "planned → draft_created",
        "publish_on_push": False,
        "dry_run": True,
    }
    results["payload_preview"] = {
        "title": payload["article"]["title"],
        "handle": payload["article"]["handle"],
        "author": payload["article"]["author"],
        "blog_target": BLOG_TARGET,
        "body_html_length": body_len,
        "tags": payload["article"]["tags"],
        "published": False,
        "published_at": None,
        "expected_action": "create_new_shopify_draft",
        "queue_update_after_push": "planned → draft_created",
        "payload_size_bytes": len(json.dumps(payload["article"])),
    }
    print(f"  Title:       {payload['article']['title']}")   # noqa: F405
    print(f"  Handle:      {payload['article']['handle']}")   # noqa: F405
    print(f"  Body length: {body_len:,} chars")   # noqa: F405
    print()   # noqa: F405

    # ── Step 9: Decision ──────────────────────────────────────────────────
    print(f"STEP 11 — Decision")   # noqa: F405

    # PHASE 2G blocking rules (in priority order)
    # Canonical selected-job decision enum
    BLOCKING_DECISIONS = frozenset([
        "BLOCKED_DUPLICATE_SHOPIFY_TITLE",
        "BLOCKED_NEAR_HANDLE_CONFLICT",
        "BLOCKED_DUPLICATE_SHOPIFY_HANDLE",
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
        "BLOCK_INVENTORY_UNAVAILABLE",
    ])
    PASSING_DECISIONS = frozenset([
        "READY_TO_CREATE_SELECTED_JOB_DRAFT",
        "ALREADY_CREATED_QUEUE_ALREADY_CORRECT",
        "ALREADY_CREATED_QUEUE_RECONCILIATION_REQUIRED",
    ])

    # Determine decision
    if conflicts["self_match"]:
        # Shopify draft exists for this job — check queue status
        if queue_status == "draft_created":
            decision = "ALREADY_CREATED_QUEUE_ALREADY_CORRECT"
            results["message"] = (
                f"Job {job_id}: Shopify article ID {conflicts.get('self_match_article_id')} "
                f"already created. Queue status is 'draft_created' — already correct."
            )
        else:
            decision = "ALREADY_CREATED_QUEUE_RECONCILIATION_REQUIRED"
            results["message"] = (
                f"Job {job_id}: Shopify article ID {conflicts.get('self_match_article_id')} "
                f"already created but queue status is '{queue_status}'. "
                f"Update queue to 'draft_created' to reconcile."
            )
        results["decision"] = decision
        results["passed"] = True  # Not a failure — already done
        print(f"  🟡 {decision}")   # noqa: F405
    elif conflicts["exact_title_match"]:
        decision = "BLOCKED_DUPLICATE_SHOPIFY_TITLE"
        results["decision"] = decision
        results["passed"] = False
        print(f"  ❌ {decision}")   # noqa: F405
    elif conflicts["near_handle_matches"]:
        decision = "BLOCKED_NEAR_HANDLE_CONFLICT"
        results["decision"] = decision
        results["passed"] = False
        print(f"  ❌ {decision}")   # noqa: F405
    elif conflicts["exact_handle_match"]:
        decision = "BLOCKED_DUPLICATE_SHOPIFY_HANDLE"
        results["decision"] = decision
        results["passed"] = False
        print(f"  ❌ {decision}")   # noqa: F405
    elif not status_ok:
        decision = "BLOCK_QUEUE_STATUS_MISMATCH"
        results["decision"] = decision
        results["passed"] = False
        print(f"  ❌ {decision}")   # noqa: F405
    elif not inventory_available:
        decision = "BLOCK_INVENTORY_UNAVAILABLE"
        results["decision"] = decision
        results["passed"] = False
        print(f"  ❌ {decision}")   # noqa: F405
    elif not draft_exists:
        decision = "BLOCK_DRAFT_NOT_FOUND"
        results["decision"] = decision
        results["passed"] = False
        print(f"  ❌ {decision}")   # noqa: F405
    elif not slug_ok:
        decision = "BLOCK_SLUG_MISMATCH"
        results["decision"] = decision
        results["passed"] = False
        print(f"  ❌ {decision}")   # noqa: F405
    elif not compliance_pass:
        decision = "BLOCK_COMPLIANCE"
        results["decision"] = decision
        results["passed"] = False
        print(f"  ❌ {decision}")   # noqa: F405
    elif not hq_pass:
        decision = "BLOCK_HTML_QUALITY"
        results["decision"] = decision
        results["passed"] = False
        print(f"  ❌ {decision}")   # noqa: F405
    else:
        decision = "READY_TO_CREATE_SELECTED_JOB_DRAFT"
        results["decision"] = decision
        results["passed"] = True
        results["message"] = (
            f"Job {job_id} passed Publisher preflight. "
            f"Shopify duplicate check: 0 exact title, 0 exact handle, 0 near-handle. "
            f"Compliance: 0 blockers. "
            f"Eligible for draft creation."
        )
        print(f"  ✅ {decision}")   # noqa: F405

    print()   # noqa: F405
    print(f"{'='*60}")   # noqa: F405
    print(f"PHASE 2G PREFLIGHT: {'✅ ' + decision.split('—')[0].strip() if results['passed'] else '❌ BLOCKED'}")   # noqa: F405
    print(f"DECISION: {decision}")   # noqa: F405
    print(f"{'='*60}")   # noqa: F405

    results["shopify_touched"] = False
    results["queue_touched"] = False
    results["draft_created"] = False

    if JSON_MODE:
        # Restore print before writing JSON so it goes to stdout
        globals()["print"] = _saved_print
        # Use sys.stdout.write to bypass any further print overrides
        sys.stdout.write(json.dumps(results, indent=2, default=str))

    return results

# ─── ENTRY POINT ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    job_id = _parsed_job_number or TARGET_JOB
    draft_path = _parsed_draft_path or (str(BASE_DIR / DRAFT_PATH) if DRAFT_PATH else None)
    results = run_dryrun(job_id, draft_path)
    if not JSON_MODE:
        sys.stdout.write(json.dumps(results, indent=2, default=str))
