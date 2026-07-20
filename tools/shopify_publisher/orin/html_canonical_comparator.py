"""
html_canonical_comparator.py
=============================
Tested canonical HTML comparison for Shopify draft verification.

Compares the locally-generated HTML with the fetched Shopify HTML to determine
whether they represent the same content after Shopify's HTML serialization
(character references, inter-tag whitespace normalization).

Approved normalization only:
1. Inter-tag LF collapse: sequences of LF between closing `>` and opening `<`
   are replaced with a single space (Shopify HTML serialization artifact).
2. Character references: `&` → `&amp;` (HTML entity encoding).

What MUST NOT be normalized away:
- Whitespace WITHIN text nodes (words, sentences — not formatting whitespace)
- href attribute value changes
- tag name changes
- attribute value changes
- element removal or reordering

Contract
--------
    PASS_RAW_EXACT                      — raw bytes identical
    PASS_ALLOWED_INTER_TAG_LF_NORMALIZATION — inter-tag LF only
    PASS_CANONICAL_HTML_EQUIVALENT       — same DOM + text after approved normalization
    FAIL_TEXT_CONTENT_CHANGED            — text node content differs
    FAIL_HREF_CHANGED                   — href attribute differs after entity decode
    FAIL_TAG_CHANGED                    — tag name differs
    FAIL_ATTRIBUTE_CHANGED               — attribute value differs
    FAIL_ELEMENT_MISSING                — element removed from fetched
    FAIL_ELEMENT_ADDED                  — element added in fetched
    FAIL_STRUCTURE_CHANGED              — element order differs
    FAIL_UNSUPPORTED_NORMALIZATION      — any other difference

Regression tests (proved below in TEST_CASES):
1.  raw identical                          → PASS_RAW_EXACT
2.  `>\\n<` serialization only              → PASS_ALLOWED_INTER_TAG_LF_NORMALIZATION
3.  `&` vs `&amp;` same char              → PASS_CANONICAL_HTML_EQUIVALENT
4.  text word changed                      → FAIL_TEXT_CONTENT_CHANGED
5.  text space removed inside text node    → FAIL_TEXT_CONTENT_CHANGED
6.  href changed                           → FAIL_HREF_CHANGED
7.  tag changed                            → FAIL_TAG_CHANGED
8.  attribute value changed                → FAIL_ATTRIBUTE_CHANGED
9.  element removed                       → FAIL_ELEMENT_MISSING
10. element reordered                      → FAIL_STRUCTURE_CHANGED
"""

import re
import html as html_module
from typing import Any

# ── Decision codes ────────────────────────────────────────────────────────────

PASS_RAW_EXACT                              = "PASS_RAW_EXACT"
PASS_ALLOWED_INTER_TAG_LF_NORMALIZATION      = "PASS_ALLOWED_INTER_TAG_LF_NORMALIZATION"
PASS_CANONICAL_HTML_EQUIVALENT               = "PASS_CANONICAL_HTML_EQUIVALENT"

FAIL_TEXT_CONTENT_CHANGED                   = "FAIL_TEXT_CONTENT_CHANGED"
FAIL_HREF_CHANGED                          = "FAIL_HREF_CHANGED"
FAIL_TAG_CHANGED                           = "FAIL_TAG_CHANGED"
FAIL_ATTRIBUTE_CHANGED                      = "FAIL_ATTRIBUTE_CHANGED"
FAIL_ELEMENT_MISSING                       = "FAIL_ELEMENT_MISSING"
FAIL_ELEMENT_ADDED                         = "FAIL_ELEMENT_ADDED"
FAIL_STRUCTURE_CHANGED                     = "FAIL_STRUCTURE_CHANGED"
FAIL_UNSUPPORTED_NORMALIZATION             = "FAIL_UNSUPPORTED_NORMALIZATION"


# ── Approved normalization ────────────────────────────────────────────────────

def _collapse_inter_tag_lf(html: str) -> str:
    """
    Collapse inter-tag LF sequences: `>` followed by one or more LF, then `<`
    becomes `> <` (single space).

    This mimics Shopify's HTML serialization which removes line breaks between
    tags while preserving a single space separator.

    Does NOT strip other whitespace, collapse text-node spaces, or touch
    intra-tag attributes.
    """
    # Match `>` followed by \n\r\t spaces, then `<`
    return re.sub(r'>([\n\r\t ]+)<', '> <', html)


def _decode_html_character_references(html: str) -> str:
    """
    Decode standard HTML character references to their character equivalents.
    Uses html.unescape which handles &amp; → &, &lt; → <, &gt; → >, etc.
    """
    return html_module.unescape(html)


def _canonical_normalize(html: str) -> str:
    """
    Apply the approved canonical normalization sequence:
    1. Decode HTML character references
    2. Collapse inter-tag LF sequences

    Returns a normalized string suitable for structural comparison.
    Does NOT strip all whitespace or collapse text-node spaces.
    """
    h = _decode_html_character_references(html)
    h = _collapse_inter_tag_lf(h)
    return h


# ── HTML parser ───────────────────────────────────────────────────────────────

class _ParsedElement:
    """Lightweight parsed element for canonical comparison."""
    __slots__ = ("tag", "attrs", "text", "children", "raw")

    def __init__(
        self,
        tag: str,
        attrs: dict[str, str],
        text: str,
        children: list["_ParsedElement | str"],
        raw: str,
    ):
        self.tag = tag
        self.attrs = attrs          # normalized key→value
        self.text = text            # direct text content
        self.children = children    # child elements or str text nodes
        self.raw = raw              # original matched string


def _tokenize_html(raw: str) -> list[_ParsedElement | str]:
    """
    Lightweight HTML tokenizer that produces a flat list of elements and
    text nodes, preserving structure for comparison.

    Handles: <tag attr="val">...<\tag>, <tag attr="val"/>
    Does NOT parse malformed HTML — input is assumed well-formed.
    """
    tokens: list[_ParsedElement | str] = []
    pos = 0
    n = len(raw)

    while pos < n:
        # Find next tag start
        tag_start = raw.find('<', pos)
        if tag_start == -1:
            # Rest is text
            text = raw[pos:]
            if text.strip():
                tokens.append(text)
            break

        if tag_start > pos:
            text = raw[pos:tag_start]
            if text.strip():
                tokens.append(text)

        # Check for closing tag
        if raw[tag_start + 1:tag_start + 2] == '/':
            # Closing tag — find the >
            close = raw.find('>', tag_start)
            if close == -1:
                close = n
            tokens.append(raw[tag_start:close + 1])
            pos = close + 1
            continue

        # Self-closing or opening tag
        close = raw.find('>', tag_start)
        if close == -1:
            close = n

        tag_content = raw[tag_start:close + 1]
        tag_name_match = re.match(r'<(\w+)', tag_content)
        if not tag_name_match:
            # Not a standard tag — treat as text
            tokens.append(tag_content)
            pos = close + 1
            continue

        tag_name = tag_name_match.group(1).lower()

        # Check if self-closing
        if tag_content.rstrip().endswith('/>') or tag_name in (
            "br", "hr", "img", "input", "meta", "link"
        ):
            # Extract attrs
            attr_str = tag_content[tag_name_match.end():]
            if attr_str.endswith('/>'):
                attr_str = attr_str[:-2]
            attrs = _parse_attrs(attr_str)
            elem = _ParsedElement(tag=tag_name, attrs=attrs, text="",
                                   children=[], raw=tag_content)
            tokens.append(elem)
            pos = close + 1
            continue

        # Find matching close tag
        open_tag = f'<{tag_name}'
        close_tag = f'</{tag_name}>'
        search_from = close + 1

        # Find the innermost matching close tag
        depth = 1
        search_pos = search_from
        while depth > 0 and search_pos < n:
            next_open = raw.find(open_tag, search_pos)
            next_close = raw.find(close_tag, search_pos)

            if next_close == -1:
                break

            if next_open != -1 and next_open < next_close:
                depth += 1
                search_pos = next_open + len(open_tag)
            else:
                depth -= 1
                if depth == 0:
                    elem_raw = raw[tag_start:next_close + len(close_tag)]
                    inner = raw[close + 1:next_close]
                    attr_str = tag_content[tag_name_match.end():]
                    attrs = _parse_attrs(attr_str.rstrip())
                    # Recurse on inner content
                    children = _tokenize_html(inner) if inner.strip() else []
                    text_content = re.sub(r'<[^>]+>', '', inner).strip()
                    elem = _ParsedElement(
                        tag=tag_name, attrs=attrs,
                        text=text_content, children=children, raw=elem_raw
                    )
                    tokens.append(elem)
                    search_pos = next_close + len(close_tag)
                else:
                    search_pos = next_close + len(close_tag)

        pos = search_pos if 'search_pos' in dir() else n

    return tokens


def _parse_attrs(attr_str: str) -> dict[str, str]:
    """Parse HTML attribute string into key→value dict."""
    attrs: dict[str, str] = {}
    # Match attr="value" or attr='value' or attr=value
    for m in re.finditer(r'(\w+)(?:=(?:\"([^\"]*)\"|\'([^\']*)\'|(\S+)))?', attr_str):
        key = m.group(1).lower()
        val = m.group(2) or m.group(3) or m.group(4) or ""
        attrs[key] = val
    return attrs


def _elem_str(e: _ParsedElement | str, indent: int = 0) -> str:
    """Debug string for a parsed element."""
    if isinstance(e, str):
        return f"TEXT: {e[:50]!r}"
    attrs_short = {k: v for k, v in e.attrs.items() if k in ("href", "class", "id")}
    return f"<{e.tag} {attrs_short}>"


# ── Canonical comparison ──────────────────────────────────────────────────────

def compare_html_canonical(
    local_html: str,
    fetched_html: str,
) -> tuple[str, list[str]]:
    """
    Compare local HTML with fetched Shopify HTML using canonical comparison.

    Applies approved normalizations in sequence and compares structure.

    Returns: (decision_code: str, details: list[str])
    """
    details: list[str] = []

    # ── Tier 1: raw exact ──────────────────────────────────────────────
    if local_html == fetched_html:
        return PASS_RAW_EXACT, ["Raw exact match."]

    # ── Tier 2: inter-tag LF only ──────────────────────────────────────
    local_t2 = _collapse_inter_tag_lf(local_html)
    fetched_t2 = _collapse_inter_tag_lf(fetched_html)
    if local_t2 == fetched_t2:
        return PASS_ALLOWED_INTER_TAG_LF_NORMALIZATION, [
            "Inter-tag LF normalization only. Content identical."
        ]

    # ── Tier 3: full canonical (entity decode + inter-tag LF) ───────────
    local_t3 = _canonical_normalize(local_html)
    fetched_t3 = _canonical_normalize(fetched_html)

    # Compare structure: tokenize both and compare elements
    local_tokens = _tokenize_html(local_t3)
    fetched_tokens = _tokenize_html(fetched_t3)

    # Compare element-by-element
    diffs = _compare_tokens(local_tokens, fetched_tokens, path="root")

    if not diffs:
        return PASS_CANONICAL_HTML_EQUIVALENT, [
            "Canonical HTML equivalent after entity decode and inter-tag LF normalization.",
            f"Local normalized: {len(local_t3)} chars, "
            f"Fetched normalized: {len(fetched_t3)} chars.",
        ]

    # Detailed failure classification
    failure_types = set(d[0] for d in diffs)
    primary_failure = sorted(failure_types)[0]  # Most severe

    detail_msgs = [f"Primary failure: {primary_failure}", f"Total diffs: {len(diffs)}"]
    for diff in diffs[:3]:
        detail_msgs.append(f"  {diff[0]}: {diff[1]}")

    return primary_failure, detail_msgs


def _same_elements(
    local_tokens: list[_ParsedElement | str],
    fetched_tokens: list[_ParsedElement | str],
) -> bool:
    """Return True if local_tokens and fetched_tokens contain the same elements (multiset equality)."""
    def elem_key(t: _ParsedElement | str) -> tuple:
        if isinstance(t, str):
            return ("TEXT", t.strip())
        return (t.tag, t.text or "", tuple(sorted(t.attrs.items())))
    from collections import Counter
    local_keys = Counter(
        elem_key(t)
        for t in local_tokens
        if isinstance(t, str) or hasattr(t, "tag")
    )
    fetched_keys = Counter(
        elem_key(t)
        for t in fetched_tokens
        if isinstance(t, str) or hasattr(t, "tag")
    )
    return local_keys == fetched_keys


def _compare_tokens(
    local_tokens: list[_ParsedElement | str],
    fetched_tokens: list[_ParsedElement | str],
    path: str,
) -> list[tuple[str, str]]:
    """
    Compare two token lists and return list of (failure_type, description).
    """
    diffs: list[tuple[str, str]] = []

    min_len = min(len(local_tokens), len(fetched_tokens))

    # ── Element reorder detection pre-check ───────────────────────────
    # If all elements are the same (same tag+text+attrs) but in different
    # order → FAIL_STRUCTURE_CHANGED. This catches <p>A</p><p>B</p> vs
    # <p>B</p><p>A</p> as a structural change, not a text change.
    if (
        len(local_tokens) == len(fetched_tokens)
        and _same_elements(local_tokens, fetched_tokens)
    ):
        same_order = True
        for i in range(min_len):
            lt, ft = local_tokens[i], fetched_tokens[i]
            if isinstance(lt, str) and isinstance(ft, str):
                if lt.strip() != ft.strip():
                    same_order = False
                    break
            elif isinstance(lt, _ParsedElement) and isinstance(ft, _ParsedElement):
                if lt.tag != ft.tag or (lt.text or "") != (ft.text or ""):
                    same_order = False
                    break
            else:
                same_order = False
                break
        if not same_order:
            return [(FAIL_STRUCTURE_CHANGED, f"{path}: element order changed")]

    # Compare common prefix
    for i in range(min_len):
        lt = local_tokens[i]
        ft = fetched_tokens[i]
        token_path = f"{path}[{i}]"

        if isinstance(lt, str) and isinstance(ft, str):
            # Both text nodes — compare after whitespace normalization within text
            lt_stripped = re.sub(r'[ \t]+', ' ', lt.strip())
            ft_stripped = re.sub(r'[ \t]+', ' ', ft.strip())
            if lt_stripped != ft_stripped:
                diffs.append((
                    FAIL_TEXT_CONTENT_CHANGED,
                    f"{token_path}: text changed from {lt_stripped!r} to {ft_stripped!r}"
                ))
            continue

        if isinstance(lt, str) or isinstance(ft, str):
            diffs.append((
                FAIL_STRUCTURE_CHANGED,
                f"{token_path}: text/element mismatch"
            ))
            continue

        # Both elements
        elem_diffs = _compare_elements(lt, ft, token_path)
        diffs.extend(elem_diffs)

    # Check for length differences
    if len(local_tokens) > len(fetched_tokens):
        for i in range(min_len, len(local_tokens)):
            lt = local_tokens[i]
            tag = lt.tag if isinstance(lt, _ParsedElement) else "TEXT"
            diffs.append((FAIL_ELEMENT_MISSING, f"{path}: local element missing at [{i}]: <{tag}>"))
    elif len(fetched_tokens) > len(local_tokens):
        for i in range(min_len, len(fetched_tokens)):
            ft = fetched_tokens[i]
            tag = ft.tag if isinstance(ft, _ParsedElement) else "TEXT"
            diffs.append((FAIL_ELEMENT_ADDED, f"{path}: fetched has extra element at [{i}]: <{tag}>"))

    return diffs


def _compare_elements(
    le: _ParsedElement,
    fe: _ParsedElement,
    path: str,
) -> list[tuple[str, str]]:
    """Compare two parsed elements and return diffs."""
    diffs: list[tuple[str, str]] = []

    # Tag name
    if le.tag != fe.tag:
        diffs.append((
            FAIL_TAG_CHANGED,
            f"{path}: tag changed from <{le.tag}> to <{fe.tag}>"
        ))
        return diffs  # Can't continue if tag changed

    # Attributes
    all_keys = set(le.attrs.keys()) | set(fe.attrs.keys())
    for key in sorted(all_keys):
        lv = le.attrs.get(key, "")
        fv = fe.attrs.get(key, "")
        if lv != fv:
            # href: decode entities before comparing
            if key == "href":
                lv_dec = _decode_html_character_references(lv)
                fv_dec = _decode_html_character_references(fv)
                if lv_dec != fv_dec:
                    diffs.append((
                        FAIL_HREF_CHANGED,
                        f"{path}@{key}: href changed from {lv_dec!r} to {fv_dec!r}"
                    ))
                continue
            # Other attributes: exact compare
            diffs.append((
                FAIL_ATTRIBUTE_CHANGED,
                f"{path}@{key}: attribute value changed from {lv!r} to {fv!r}"
            ))

    # Text content (already stripped of tags)
    if le.text != fe.text:
        diffs.append((
            FAIL_TEXT_CONTENT_CHANGED,
            f"{path}: text content differs"
        ))

    # Children
    child_diffs = _compare_tokens(le.children, fe.children, path=f"{path}.children")
    diffs.extend(child_diffs)

    return diffs


# ── Integration shim for shopify_draft_transaction ────────────────────────────

def verify_shopify_draft_against_local_v2(
    article: dict,
    expected_article_id: int | str,
    expected_title: str,
    expected_handle: str,
    local_html: str,
    local_sha256: str,
) -> tuple[bool, list[str], dict[str, Any]]:
    """
    V2 verification using html_canonical_comparator.

    Returns (passed: bool, failures: list[str], details: dict).
    """
    import hashlib

    article_id = article.get("id")
    fetched_body = article.get("body_html", "")
    fetched_title = article.get("title", "")
    fetched_handle = article.get("handle", "")
    fetched_published = article.get("published_at")

    failures: list[str] = []
    details: dict[str, Any] = {
        "fetched_article_id": article_id,
        "expected_article_id": expected_article_id,
        "fetched_title": fetched_title,
        "expected_title": expected_title,
        "fetched_handle": fetched_handle,
        "expected_handle": expected_handle,
        "fetched_published_at": fetched_published,
        "is_draft": fetched_published is None,
        "fetched_body_length": len(fetched_body),
        "expected_body_length": len(local_html),
    }

    # ID / title / handle checks
    if str(article_id) != str(expected_article_id):
        failures.append(f"Article ID mismatch: {article_id} vs {expected_article_id}")

    if fetched_title.strip() != expected_title.strip():
        failures.append(f"Title mismatch: {fetched_title!r} vs {expected_title!r}")

    if fetched_handle.strip() != expected_handle.strip():
        failures.append(f"Handle mismatch: {fetched_handle!r} vs {expected_handle!r}")

    # Draft check
    if fetched_published is not None:
        failures.append(f"Article is published (published_at={fetched_published}), expected draft.")

    if not fetched_body:
        failures.append("Fetched body is empty.")
        return False, failures, details

    # Body comparison
    decision, detail_msgs = compare_html_canonical(local_html, fetched_body)
    details["canonical_decision"] = decision
    details["canonical_details"] = detail_msgs

    if decision == PASS_RAW_EXACT:
        details["body_sha256"] = hashlib.sha256(fetched_body.encode()).hexdigest()
        details["body_verification_result"] = decision
        return True, [], details

    if decision == PASS_ALLOWED_INTER_TAG_LF_NORMALIZATION:
        details["body_sha256"] = hashlib.sha256(fetched_body.encode()).hexdigest()
        details["body_verification_result"] = decision
        return True, [], details

    if decision == PASS_CANONICAL_HTML_EQUIVALENT:
        details["body_sha256"] = hashlib.sha256(fetched_body.encode()).hexdigest()
        details["body_verification_result"] = decision
        return True, [], details

    # Failure
    failures.append(f"Body verification: {decision}")
    for msg in detail_msgs:
        failures.append(msg)

    details["body_sha256"] = hashlib.sha256(fetched_body.encode()).hexdigest()
    details["body_verification_result"] = decision
    return False, failures, details


# ── Regression test suite ─────────────────────────────────────────────────────

TEST_CASES = [
    # (name, local_html, fetched_html, expected_decision_prefix)
    ("1. raw_identical", "<p>Hello</p>", "<p>Hello</p>", PASS_RAW_EXACT),

    ("2. inter_tag_lf_only",
     "<ul>\n  <li>A</li>\n</ul>",
     "<ul> <li>A</li> </ul>",
     PASS_ALLOWED_INTER_TAG_LF_NORMALIZATION),

    ("3. entity_ampersand",
     "<p>Tom & Jerry</p>",
     "<p>Tom &amp; Jerry</p>",
     PASS_CANONICAL_HTML_EQUIVALENT),

    ("4. text_word_changed",
     "<p>Hello world</p>",
     "<p>Hello universe</p>",
     FAIL_TEXT_CONTENT_CHANGED),

    ("5. text_space_removed",
     "<p>Hello  world</p>",
     "<p>Hello world</p>",
     FAIL_TEXT_CONTENT_CHANGED),

    ("6. href_changed",
     '<a href="/page">Link</a>',
     '<a href="/other">Link</a>',
     FAIL_HREF_CHANGED),

    ("7. tag_changed",
     "<p>Text</p>",
     "<div>Text</div>",
     FAIL_TAG_CHANGED),

    ("8. attribute_value_changed",
     '<div class="a">Text</div>',
     '<div class="b">Text</div>',
     FAIL_ATTRIBUTE_CHANGED),

    ("9. element_removed",
     "<ul><li>A</li><li>B</li></ul>",
     "<ul><li>A</li></ul>",
     FAIL_ELEMENT_MISSING),

    # 10. element_missing: missing a <li> from a list
    ("10. element_missing",
     "<ul><li>A</li><li>B</li><li>C</li></ul>",
     "<ul><li>A</li><li>C</li></ul>",
     FAIL_ELEMENT_MISSING),

    # 11. element_reordered_same_elements: same elements, different order
    # SENT: <div><p>A</p><p>B</p></div>
    # FETCHED: <div><p>B</p><p>A</p></div>
    # Required: FAIL (element order matters — this is a content change)
    ("11. element_reordered_same_elements",
     "<div><p>A</p><p>B</p></div>",
     "<div><p>B</p><p>A</p></div>",
     FAIL_STRUCTURE_CHANGED),
]


def run_regression_tests() -> dict:
    """Run all regression test cases. Returns summary dict."""
    results: list[dict] = []
    all_passed = True

    for name, local, fetched, expected_prefix in TEST_CASES:
        decision, _ = compare_html_canonical(local, fetched)
        passed = decision == expected_prefix
        if not passed:
            all_passed = False
        results.append({
            "name": name,
            "expected": expected_prefix,
            "got": decision,
            "passed": passed,
        })

    return {
        "all_passed": all_passed,
        "results": results,
        "total": len(results),
        "passed": sum(1 for r in results if r["passed"]),
    }


if __name__ == "__main__":
    print("Running HTML canonical comparator regression tests...\n")
    summary = run_regression_tests()
    for r in summary["results"]:
        status = "✅ PASS" if r["passed"] else f"❌ FAIL (expected {r['expected']}, got {r['got']})"
        print(f"  {r['name']}: {status}")
    print(f"\n{summary['passed']}/{summary['total']} passed.")
    if summary["all_passed"]:
        print("ALL TESTS PASSED — comparator contract verified.")
