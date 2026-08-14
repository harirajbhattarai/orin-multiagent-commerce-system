#!/usr/bin/env python3
"""
UK Compliance Checker for E-Commerce Article Content

Checks for risky public-use wording, legal claims, and compliance issues.
Supports PASS WITH WARNING for safe-negative FAQ contexts.
"""

import sys
import re
from pathlib import Path

# Phrases that should NEVER appear, even in negative context (hard fails)
BLOCKED_PHRASES = [
    "road legal",
    "pavement legal",
    "legal on uk roads",
    "public road use",
    "ride to work",
    "ride to school",
    "school commute",
    "work commute",
    "daily commute",
    "daily commuter",
    "city commuting",
    "street use",
    "allowed on cycle lanes",
    "ride anywhere",
    "suitable for commuting",
    "legal to ride on pavements",
    "can ride on public roads",
]

# Sensitive terms that are flagged but may be acceptable in safe-negative contexts
SENSITIVE_PHRASES = [
    "public roads",
    "public road",
    "pavements",
    "pavement",
    "cycle lanes",
    "cycle lane",
    "public land",
    "commuting",
    "commute",
]

# Words that indicate safe / negative / restrictive context
SAFE_CONTEXT_INDICATORS = [
    "no",
    "not",
    "not permitted",
    "not allowed",
    "should not",
    "do not",
    "don't",
    "avoid",
    "restricted",
    "private space",
    "suitable private space",
    "follow current guidance",
    "check current guidance",
    "manufacturer guidance",
    "cannot",
    "can not",
    "must not",
    "private land",
    "with landowner permission",
    "check local rules",
    "check current uk rules",
    "legal restrictions",
    "not for",
    "only on private",
    "never on",
    "prohibited",
]

# Words that indicate risky permission or encouragement (override safe context)
PERMISSION_CLAIM_INDICATORS = [
    "can ride",
    "legal to",
    "allowed to",
    "permitted to",
    "road legal",
    "street legal",
    "uk road legal",
    "pavement legal",
    "suitable for commuting",
    "commute on",
    "ride to work",
    "ride to school",
    "use on roads",
    "use on pavements",
    "use on public land",
    "use on cycle lanes",
    "use on the road",
    "fine to ride",
    "ok to ride",
    "you can ride",
]


def remove_html_comments(html):
    return re.sub(r"<!--.*?-->", "", html, flags=re.DOTALL)


def normalise(text):
    return re.sub(r"\s+", " ", text.lower()).strip()


def extract_faq_blocks(html):
    hs_faq_pattern = re.compile(
        r'<div class="hs-faq-item">.*?'
        r'<div class="hs-faq-q">(.*?)</div>.*?'
        r'<div class="hs-faq-a">(.*?)</div>.*?'
        r'</div>',
        re.DOTALL | re.IGNORECASE,
    )
    blocks = []
    for m in hs_faq_pattern.finditer(html):
        q = normalise(re.sub(r"<[^>]+>", "", m.group(1)))
        a = normalise(re.sub(r"<[^>]+>", "", m.group(2)))
        blocks.append((q, a))

    hcs_faq_pattern = re.compile(
        r'<div\b[^>]*class=["\'][^"\']*\bhcs-faq-item\b[^"\']*["\'][^>]*>.*?'
        r'<h3\b[^>]*>(.*?)</h3>.*?'
        r'<p\b[^>]*>(.*?)</p>.*?'
        r'</div>',
        re.DOTALL | re.IGNORECASE,
    )
    for m in hcs_faq_pattern.finditer(html):
        q = normalise(re.sub(r"<[^>]+>", "", m.group(1)))
        a = normalise(re.sub(r"<[^>]+>", "", m.group(2)))
        blocks.append((q, a))
    return blocks


def get_context(text, phrase, window=250):
    idx = text.lower().find(phrase.lower())
    if idx == -1:
        return ""
    start = max(0, idx - window)
    end = min(len(text), idx + len(phrase) + window)
    return text[start:end]


def has_safe_context(context):
    c = context.lower()
    return any(indicator in c for indicator in SAFE_CONTEXT_INDICATORS)


def has_permission_claim(context, phrase):
    """
    Return True if context contains a risky permission/encouragement phrase
    AND does NOT contain a negation word before the sensitive term.
    This prevents false positives on phrases like 'not suitable for use on pavements'.
    """
    c = context.lower()
    negation_words = (
        "not", "no", "never", "avoid", "restricted", "prohibited",
        "do not", "don't", "should not", "must not", "cannot",
    )

    # Permission language is relevant only when it occurs in the same sentence
    # as the sensitive phrase. A broad character window can otherwise join a
    # safe sentence such as "not on public roads" to a later sentence such as
    # "check where you can ride" and produce a false positive.
    for sentence in re.split(r"(?<=[.!?])\s+|[;\n]+", c):
        if phrase.lower() not in sentence:
            continue
        phrase_idx = sentence.find(phrase.lower())
        negation_zone = sentence[max(0, phrase_idx - 80):phrase_idx]
        if any(neg in negation_zone for neg in negation_words):
            continue
        if any(indicator in sentence for indicator in PERMISSION_CLAIM_INDICATORS):
            return True
    return False


def check_faq_block(q_text, a_text, sensitive_phrase):
    q_has = sensitive_phrase in q_text.lower()
    a_has = sensitive_phrase in a_text.lower()

    if not q_has and not a_has:
        return "ok"

    # Question mentions the sensitive term; answer does not —
    # verify the answer is still safe-negative (contains a safe indicator).
    # This covers cases like Q='Can I use my hoverboard on public land?'
    # A='No. Only use on private land with landowner permission.'
    if q_has and not a_has:
        if has_safe_context(a_text):
            return "pass_warn"
        return "ok"  # silent pass if no safe context detected but not mentioned either

    if a_has:
        context = get_context(a_text, sensitive_phrase, window=250)
        if has_permission_claim(context, sensitive_phrase):
            return "fail"
        if has_safe_context(context):
            return "pass_warn"
        # No safe indicator — check if answer starts with a denial word
        stripped = a_text.lstrip().lower()
        denial_prefixes = (
            "no", "not", "never", "do not", "don't", "should not",
            "must not", "avoid", "restricted", "prohibited"
        )
        if any(stripped.startswith(p) for p in denial_prefixes):
            return "pass_warn"
        return "fail"

    return "ok"


def check_non_faq_content(text, sensitive_phrase, label="Sensitive phrase"):
    if sensitive_phrase.lower() not in text.lower():
        return "ok", None

    context = get_context(text, sensitive_phrase, window=250)

    if has_permission_claim(context, sensitive_phrase):
        return "fail", f"{label} '{sensitive_phrase}' appears with permission/encouragement language"

    if has_safe_context(context):
        return "pass_warn", f"{label} '{sensitive_phrase}' found in safe-negative context"

    return "fail", f"{label} '{sensitive_phrase}' found without safe context"


def analyze_html(raw_html):
    """Return deterministic UK-compliance failures and warnings for HTML."""
    html = remove_html_comments(raw_html)
    visible = normalise(html)

    fails = []
    warnings = []

    # BLOCKED_PHRASES — always fail regardless of context
    for phrase in BLOCKED_PHRASES:
        if phrase in visible:
            ctx = get_context(visible, phrase, window=250)
            fails.append(
                f"Blocked phrase (never allowed): '{phrase}' — context: ...{ctx}..."
            )

    # Check SENSITIVE_PHRASES inside FAQ blocks
    faq_blocks = extract_faq_blocks(raw_html)
    for phrase in SENSITIVE_PHRASES:
        for q_text, a_text in faq_blocks:
            result = check_faq_block(q_text, a_text, phrase)
            if result == "fail":
                fails.append(
                    f"FAQ answer unsafe: '{phrase}' without safe-negative context — "
                    f"Q='{q_text[:80]}...'"
                )
            elif result == "pass_warn":
                warnings.append(
                    f"FAQ safe-negative context (pass with warning): '{phrase}' — "
                    f"Q='{q_text[:80]}...'"
                )

    # Check SENSITIVE_PHRASES in non-FAQ content
    content_without_faqs = re.sub(
        r'<div\b[^>]*class=["\'][^"\']*\b(?:hs|hcs)-faq-item\b[^"\']*["\'][^>]*>.*?</div>\s*</div>',
        "",
        html,
        flags=re.DOTALL | re.IGNORECASE,
    )
    content_visible = normalise(content_without_faqs)

    for phrase in SENSITIVE_PHRASES:
        status, detail = check_non_faq_content(content_visible, phrase)
        if status == "fail":
            fails.append(detail)
        elif status == "pass_warn":
            warnings.append(detail)

    return fails, warnings


def main():
    if len(sys.argv) < 2:
        raise SystemExit("Usage: python3 compliance_check.py path/to/article.html")

    path = Path(sys.argv[1])
    if not path.exists():
        raise SystemExit(f"File not found: {path}")

    raw_html = path.read_text()
    fails, warnings = analyze_html(raw_html)

    print("UK Compliance Check")
    print("-------------------")
    print(f"File: {path}")
    print(f"Fails: {len(fails)}")
    print(f"Warnings: {len(warnings)}")
    print()

    if fails:
        print("STATUS: FAIL — COMPLIANCE REVIEW REQUIRED")
        for issue in fails:
            print(f"  - {issue}")
        if warnings:
            print()
            print("Warnings:")
            for w in warnings:
                print(f"  - {w}")
        sys.exit(2)

    if warnings:
        print("STATUS: PASS WITH WARNINGS — REVIEW BEFORE PUBLISHING")
        for w in warnings:
            print(f"  - {w}")
        sys.exit(0)

    print("STATUS: PASS — No compliance issues detected")
    sys.exit(0)


if __name__ == "__main__":
    main()
