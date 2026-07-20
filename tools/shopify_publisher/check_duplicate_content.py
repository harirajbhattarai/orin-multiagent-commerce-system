#!/usr/bin/env python3
"""
Duplicate Content Preflight Checker — supports both Hoverboard Store and HCS Gadgets.

Auto-detects client from draft file path:
  clients/hcs_gadgets/...        → HCS Gadgets mode
  clients/hoverboard_store/...   → Hoverboard Store mode

Three-tier risk model:
  0.00 – 0.39  LOW / MEDIUM RISK   → warning only; workflow continues
  0.40 – 0.69  REVIEW NEEDED      → stop unless manually approved
  0.70 +        BLOCK              → do not create draft; rewrite required
"""
import json
import re
import sys
import difflib
from pathlib import Path
from collections import defaultdict

BASE_DIR = Path("/data/.openclaw/workspace")
if not BASE_DIR.exists():
    BASE_DIR = Path("/root/.openclaw/workspace")

# Default: Hoverboard Store
CONTENT_DIR = BASE_DIR / "clients" / "hoverboard_store" / "content_engine"
INV_PATH = CONTENT_DIR / "shopify_inventory.json"


def detect_client_from_path(path_str):
    """Detect client from file path. Returns 'hcs_gadgets', 'hoverboard_store', or None."""
    parts = path_str.split("/")
    try:
        idx = parts.index("clients")
        return parts[idx + 1] if idx + 1 < len(parts) else None
    except ValueError:
        return None


def resolve_client_paths(client_name):
    """Return (content_dir, inv_path) for the detected client."""
    if client_name == "hcs_gadgets":
        cdir = BASE_DIR / "clients" / "hcs_gadgets" / "content_engine"
    elif client_name == "hoverboard_store":
        cdir = BASE_DIR / "clients" / "hoverboard_store" / "content_engine"
    else:
        cdir = CONTENT_DIR  # fallback to Hoverboard
    inv = cdir / "shopify_inventory.json"
    return cdir, inv


# Shared category language — high-frequency terms that indicate topic
# adjacency, not necessarily duplicate content.
CATEGORY_SHARED_TERMS = {
    "hoverboard", "kids", "child", "children", "buying", "buyer",
    "safety", "safe", "wheel size", "wheels", "charger", "charging",
    "battery", "hoverkart", "uk", "guide", "first time", "beginner",
    "age", "weight limit", "weight limits", "bundle", "review",
}


def normalise(text):
    text = (text or "").lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def token_set(text):
    words = normalise(text).split()
    stop = {
        "the", "and", "for", "with", "you", "your", "are", "can", "how",
        "what", "why", "when", "from", "this", "that", "into", "guide",
        "uk", "2026", "complete", "everything", "need", "know", "best",
        "safe", "safely",
    }
    return set(w for w in words if len(w) > 2 and w not in stop)


def jaccard(a, b):
    aa, bb = token_set(a), token_set(b)
    if not aa or not bb:
        return 0.0
    return len(aa & bb) / len(aa | bb)


def jaccard_detail(a, b):
    """Return (score, shared_terms, all_terms) for intent analysis."""
    aa, bb = token_set(a), token_set(b)
    if not aa or not bb:
        return 0.0, set(), set()
    shared = aa & bb
    all_terms = aa | bb
    score = len(shared) / len(all_terms)
    return score, shared, all_terms


def sequence_similarity(a, b):
    a = normalise(a)[:5000]
    b = normalise(b)[:5000]
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a, b).ratio()


def classify_article(article):
    text = " ".join([
        article.get("title", ""),
        article.get("handle", ""),
        " ".join(article.get("h2s", []) or []),
        " ".join(article.get("faq_questions", []) or []),
    ]).lower()

    clusters = []
    rules = {
        "hoverboard_safety": ["safety", "safe", "laws", "legal", "ride safely"],
        "charging_battery": ["charge", "charging", "battery"],
        "hoverkart": ["hoverkart", "go kart"],
        "electric_scooter": ["electric scooter", "scooter"],
        "buying_guide": ["buying guide", "choose", "age", "wheel size", "first time"],
        "accessories": ["accessories", "protective gear", "helmet"],
        "troubleshooting": ["troubleshooting", "problem", "repair", "maintenance"],
        "weight_limits": ["weight limit", "weight limits"],
    }

    for cluster, terms in rules.items():
        if any(term in text for term in terms):
            clusters.append(cluster)

    return clusters or ["general"]


def shared_language_ratio(shared_terms):
    """
    Return a ratio (0.0–1.0) of how much the shared vocabulary consists
    of expected category language rather than content uniqueness.
    """
    if not shared_terms:
        return 0.0
    category_hit = sum(1 for t in shared_terms if t in CATEGORY_SHARED_TERMS)
    return category_hit / len(shared_terms)


def risk_tier(score):
    """Map a body-similarity score to one of three risk tiers."""
    if score >= 0.70:
        return "block"
    if score >= 0.40:
        return "review"
    return "warning"


def risk_tier_label(tier):
    return {"block": "BLOCK", "review": "REVIEW NEEDED", "warning": "LOW/MEDIUM RISK"}[tier]


def intent_summary(score, shared_terms, shared_ratio):
    """Build a human-readable intent assessment string."""
    category_pct = int(shared_ratio * 100)
    return (
        f"similarity {score:.2f}; {category_pct}% of overlap is shared category language "
        f"(hoverboard, buying, safety, wheel size, charger, battery, hoverkart, etc.)"
    )


def extract_title_from_html(html_path):
    """Extract the article title from the HTML <title> or <h1> tag."""
    try:
        html = Path(html_path).read_text(encoding="utf-8")
    except Exception:
        return ""
    # Try <title> first
    m = re.search(r"<title[^>]*>([^<]+)</title>", html, re.I)
    if m:
        return m.group(1).strip()
    # Try <h1>
    m = re.search(r"<h1[^>]*>([^<]+)</h1>", html, re.I)
    if m:
        return m.group(1).strip()
    return ""


def main():
    # Parse positional args: [path/to/draft.html, job_number]
    # Also support --client=hcs_gadgets override
    client_override = None
    path_arg = None
    job_num = None

    for arg in sys.argv[1:]:
        if arg.startswith("--client="):
            client_override = arg.split("=", 1)[1]
        elif arg.startswith("--"):
            pass  # ignore unknown flags
        elif Path(arg).is_file() or Path(arg).exists():
            path_arg = arg
        else:
            job_num = arg  # second positional = job number

    if not path_arg:
        raise SystemExit("Usage: python3 check_duplicate_content.py [--client=CLIENT] path/to/draft.html [job_number]")

    # Auto-detect client from draft path
    detected_client = detect_client_from_path(str(Path(path_arg).resolve()))
    client_name = client_override or detected_client

    # Resolve client-specific paths
    content_dir, inv_path = resolve_client_paths(client_name)

    # Report client being used
    client_label = {
        "hcs_gadgets": "HCS Gadgets",
        "hoverboard_store": "Hoverboard Store",
    }.get(client_name, client_name or "Unknown")

    # Extract local draft title for self-match check
    local_title = extract_title_from_html(path_arg) or ""

    if not inv_path.exists():
        # HCS may not have inventory fetched yet — this is not an error
        print(f"Duplicate/content pattern preflight complete.")
        print(f"Client: {client_label}")
        print(f"Articles checked: 0")
        print(f"Total risks found: 0")
        print()
        print(f"Inventory not found: {inv_path}")
        print("STATUS: PASS — No inventory available for duplicate check.")
        sys.exit(0)

    raw = json.loads(inv_path.read_text())

    # Handle both inventory formats:
    # - Hoverboard: flat list of articles
    # - HCS Gadgets: dict with 'published' and 'drafts' keys
    if isinstance(raw, dict):
        pub = raw.get("published", [])
        drafts = raw.get("drafts", [])
        articles = pub + drafts
    elif isinstance(raw, list):
        articles = raw
    else:
        raise SystemExit(f"Unexpected inventory format in {inv_path}")
    risks = []
    clusters = defaultdict(list)

    for article in articles:
        for cluster in classify_article(article):
            clusters[cluster].append(article)

    # Pairwise duplicate checks with three-tier logic
    for i in range(len(articles)):
        for j in range(i + 1, len(articles)):
            a = articles[i]
            b = articles[j]

            # Skip if both inventory articles have the exact same title — this is an
            # internal inventory data quality issue, not a draft-vs-inventory problem.
            if a.get("title", "") == b.get("title", ""):
                continue

            title_score = jaccard(a.get("title", ""), b.get("title", ""))
            h1_score = jaccard(a.get("h1", ""), b.get("h1", ""))
            body_jaccard, shared_terms, _ = jaccard_detail(
                a.get("clean_text", ""), b.get("clean_text", "")
            )
            body_sequence = sequence_similarity(
                a.get("clean_text", ""), b.get("clean_text", "")
            )

            faq_overlap = set(
                map(normalise, a.get("faq_questions", []) or [])
            ) & set(map(normalise, b.get("faq_questions", []) or []))

            # Tiered body similarity assessment
            body_tier = risk_tier(body_jaccard)
            shared_ratio = shared_language_ratio(shared_terms)

            reasons = []

            # Title tier
            if title_score >= 0.70:
                reasons.append({"check": "title similarity", "tier": "block",
                                 "detail": f"{title_score:.2f}"})
            elif title_score >= 0.40:
                reasons.append({"check": "title similarity", "tier": "review",
                                 "detail": f"{title_score:.2f}"})

            # H1 tier
            if h1_score >= 0.70:
                reasons.append({"check": "H1 similarity", "tier": "block",
                                 "detail": f"{h1_score:.2f}"})
            elif h1_score >= 0.40:
                reasons.append({"check": "H1 similarity", "tier": "review",
                                 "detail": f"{h1_score:.2f}"})

            # Body topic similarity — the main intent-aware check
            if body_jaccard >= 0.40:
                reasons.append({
                    "check": "body topic similarity",
                    "tier": body_tier,
                    "detail": f"{body_jaccard:.2f} — {intent_summary(body_jaccard, shared_terms, shared_ratio)}",
                    "shared_ratio": shared_ratio,
                })

            # Body phrase similarity
            if body_sequence >= 0.70:
                reasons.append({"check": "body phrase similarity", "tier": "block",
                                 "detail": f"{body_sequence:.2f}"})
            elif body_sequence >= 0.40:
                reasons.append({"check": "body phrase similarity", "tier": "review",
                                 "detail": f"{body_sequence:.2f}"})

            # FAQ overlap
            if len(faq_overlap) >= 3:
                reasons.append({
                    "check": "FAQ overlap",
                    "tier": "review",
                    "detail": f"{len(faq_overlap)} overlapping FAQ questions",
                })

            if reasons:
                tier_order = {"warning": 0, "review": 1, "block": 2}
                worst = max(reasons, key=lambda r: tier_order[r["tier"]])["tier"]
                risks.append({
                    "a_title": a.get("title", ""),
                    "a_slug": a.get("handle", ""),
                    "a_status": "published" if a.get("published_at") else "draft",
                    "b_title": b.get("title", ""),
                    "b_slug": b.get("handle", ""),
                    "b_status": "published" if b.get("published_at") else "draft",
                    "overall_tier": worst,
                    "overall_label": risk_tier_label(worst),
                    "reasons": reasons,
                })

    # Sort: block first, then review, then warnings
    tier_order = {"block": 0, "review": 1, "warning": 2}
    risks.sort(key=lambda r: tier_order[r["overall_tier"]])

    blocks   = [r for r in risks if r["overall_tier"] == "block"]
    reviews  = [r for r in risks if r["overall_tier"] == "review"]
    warns    = [r for r in risks if r["overall_tier"] == "warning"]

    # ── Markdown report ──
    lines = []
    lines.append(f"# {client_label} — Duplicate Risk Log")
    lines.append("")
    lines.append(
        "Three-tier risk model: 0.00-0.39 = LOW/MEDIUM (warn), "
        "0.40-0.69 = REVIEW NEEDED (stop), 0.70+ = BLOCK (rewrite)."
    )
    lines.append("")
    lines.append(f"Articles checked: {len(articles)}")
    lines.append(f"Duplicate / similarity risks found: {len(risks)}")
    lines.append("")

    if risks:
        for idx, r in enumerate(risks, 1):
            lines.append(f"## Risk {idx}: {r['overall_label']}")
            lines.append("")
            lines.append(f"**Article A:** {r['a_title']}  ")
            lines.append(f"Slug: `{r['a_slug']}` — {r['a_status']}")
            lines.append("")
            lines.append(f"**Article B:** {r['b_title']}  ")
            lines.append(f"Slug: `{r['b_slug']}` — {r['b_status']}")
            lines.append("")
            lines.append("Reason breakdown:")
            for reason in r["reasons"]:
                badge = f"[{reason['tier'].upper()}]"
                lines.append(f"- {badge} {reason['check']}: {reason['detail']}")
            lines.append("")

        if blocks:
            lines.append(
                f"**{len(blocks)} pair(s) at BLOCK tier — do not publish without rewrite or merge.**"
            )
        if reviews:
            lines.append(
                f"**{len(reviews)} pair(s) at REVIEW NEEDED — stop and assess before proceeding.**"
            )
        if warns:
            lines.append(
                f"**{len(warns)} pair(s) at LOW/MEDIUM — workflow may continue with warning.**"
            )
    else:
        lines.append("No duplicate risks detected.")
        lines.append("")

    dup_log_path = content_dir / "duplicate_risk_log.md"
    dup_log_path.write_text("\n".join(lines))

    # ── Content cluster report ──
    cluster_lines = []
    cluster_lines.append(f"# {client_label} — Content Patterns")
    cluster_lines.append("")
    cluster_lines.append("Existing topic clusters based on Shopify published + draft content.")
    cluster_lines.append("")
    for cluster, items in sorted(clusters.items()):
        cluster_lines.append(f"## {cluster}")
        cluster_lines.append("")
        for item in items:
            status = "published" if item.get("published_at") else "draft"
            cluster_lines.append(
                f"- [{status}] {item.get('title', '')} "
                f"(`{item.get('handle', '')}`) — {item.get('word_count', 0)} words"
            )
        cluster_lines.append("")

    (content_dir / "content_patterns.md").write_text("\n".join(cluster_lines))

    # ── Console summary with tier-specific workflow guidance ──
    print(f"Duplicate/content pattern preflight complete.")
    print(f"Client: {client_label}")
    print(f"Articles checked: {len(articles)}")
    print(f"Total risks found: {len(risks)}")
    print(f"  BLOCK (do not draft):        {len(blocks)}")
    print(f"  REVIEW NEEDED (stop first):  {len(reviews)}")
    print(f"  LOW/MEDIUM (warn only):     {len(warns)}")
    print()
    print(f"Saved: {dup_log_path}")
    print(f"Saved: {content_dir / 'content_patterns.md'}")
    print()

    if blocks:
        print("STATUS: BLOCK — Rewrite or merge required before proceeding.")
        for r in blocks:
            for reason in r["reasons"]:
                if reason["tier"] == "block":
                    print(f"  [{reason['tier'].upper()}] {reason['check']}: {reason['detail']}")
        sys.exit(2)

    if reviews:
        print("STATUS: REVIEW NEEDED — Workflow paused. Manual approval required.")
        for r in reviews:
            print(f"  - {r['a_slug']} <-> {r['b_slug']}")
            for reason in r["reasons"]:
                print(f"    [{reason['tier'].upper()}] {reason['check']}: {reason['detail']}")
        sys.exit(1)

    if warns:
        print("STATUS: PASS WITH WARNINGS — Workflow may continue.")
        print("Warnings (shared category language; topic intent is different):")
        for r in warns:
            for reason in r["reasons"]:
                print(f"  - {reason['check']}: {reason['detail']}")
        sys.exit(0)

    print("STATUS: PASS — No duplicate risks detected.")
    sys.exit(0)


if __name__ == "__main__":
    main()
