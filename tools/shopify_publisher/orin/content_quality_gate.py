#!/usr/bin/env python3
"""Deterministic, fail-closed SEO content quality gate for ORIN articles.

The gate evaluates the rendered article text rather than raw HTML tokens. It is
designed to run after writer execution and before any Shopify transaction.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from html.parser import HTMLParser
from urllib.parse import urlparse


CONTRACT_VERSION = "phase3.5-blog-v1"
DEFAULT_CONTRACT = {
    "min_visible_words": 1500,
    "min_seo_title_chars": 30,
    "max_seo_title_chars": 60,
    "min_meta_description_chars": 120,
    "max_meta_description_chars": 160,
    "min_h2_count": 5,
    "min_paragraph_count": 10,
    "min_faq_items": 3,
    "min_internal_links": 5,
    "min_substantive_sections": 4,
    "min_words_per_substantive_section": 100,
    "min_target_keyword_occurrences": 2,
    "max_target_keyword_occurrences": 12,
}

_WORD_RE = re.compile(r"\b[\w]+(?:[’'-][\w]+)*\b", re.UNICODE)
_PLACEHOLDER_RE = re.compile(
    r"\b(?:TBD|TODO|FIXME|XXX)\b|\[(?:INSERT|PLACEHOLDER|YOUR TEXT HERE)[^\]]*\]",
    re.IGNORECASE,
)
_NON_SUBSTANTIVE_H2 = {
    "frequently asked questions",
    "highlights",
    "related guides",
    "quick answer",
    "introduction",
}


def _words(value: str) -> list[str]:
    return _WORD_RE.findall(value)


def _normalise_space(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _normalise_paragraph(value: str) -> str:
    return " ".join(word.lower() for word in _words(value))


def _classes(attributes: list[tuple[str, str | None]]) -> set[str]:
    for name, value in attributes:
        if name.lower() == "class" and value:
            return set(value.split())
    return set()


def _attribute(
    attributes: list[tuple[str, str | None]],
    target: str,
) -> str:
    for name, value in attributes:
        if name.lower() == target:
            return value or ""
    return ""


@dataclass
class ParsedArticle:
    visible_chunks: list[str] = field(default_factory=list)
    comments: list[str] = field(default_factory=list)
    h1_chunks: list[str] = field(default_factory=list)
    h2s: list[str] = field(default_factory=list)
    paragraphs: list[str] = field(default_factory=list)
    hrefs: list[str] = field(default_factory=list)
    faq_items: int = 0
    quick_answer_present: bool = False
    cta_present: bool = False
    section_text: dict[str, list[str]] = field(default_factory=dict)

    @property
    def visible_text(self) -> str:
        return _normalise_space(" ".join(self.visible_chunks))


class _ArticleParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.article = ParsedArticle()
        self._stack: list[tuple[str, set[str], bool]] = []
        self._skip_depth = 0
        self._current_h1: list[str] | None = None
        self._current_h2: list[str] | None = None
        self._current_paragraph: list[str] | None = None
        self._active_section: str | None = None

    def handle_starttag(
        self,
        tag: str,
        attributes: list[tuple[str, str | None]],
    ) -> None:
        tag = tag.lower()
        classes = _classes(attributes)
        parent_hidden = self._stack[-1][2] if self._stack else False
        style = (_attribute(attributes, "style") or "").replace(" ", "").lower()
        hidden = parent_hidden or any(
            name.lower() == "hidden"
            or (name.lower() == "aria-hidden" and (value or "").lower() == "true")
            for name, value in attributes
        ) or "display:none" in style or "visibility:hidden" in style
        self._stack.append((tag, classes, hidden))
        if tag in {"script", "style", "noscript", "template"}:
            self._skip_depth += 1
            return
        if self._skip_depth or hidden:
            return
        if "hs-faq-item" in classes:
            self.article.faq_items += 1
        if "hs-quick-answer" in classes:
            self.article.quick_answer_present = True
        if "hs-cta" in classes:
            self.article.cta_present = True
        if tag == "a":
            self.article.hrefs.append(_attribute(attributes, "href"))
        elif tag == "h1":
            self._current_h1 = []
        elif tag == "h2":
            self._current_h2 = []
        elif tag == "p":
            self._current_paragraph = []

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"script", "style", "noscript", "template"}:
            self._skip_depth = max(0, self._skip_depth - 1)
        elif not self._skip_depth:
            if tag == "h1" and self._current_h1 is not None:
                self.article.h1_chunks.append(
                    _normalise_space(" ".join(self._current_h1))
                )
                self._current_h1 = None
            elif tag == "h2" and self._current_h2 is not None:
                heading = _normalise_space(" ".join(self._current_h2))
                if heading:
                    self.article.h2s.append(heading)
                    self._active_section = heading
                    self.article.section_text.setdefault(heading, [])
                self._current_h2 = None
            elif tag == "p" and self._current_paragraph is not None:
                paragraph = _normalise_space(" ".join(self._current_paragraph))
                if paragraph:
                    self.article.paragraphs.append(paragraph)
                self._current_paragraph = None
        for index in range(len(self._stack) - 1, -1, -1):
            if self._stack[index][0] == tag:
                del self._stack[index:]
                break

    def handle_data(self, data: str) -> None:
        if self._skip_depth or (self._stack and self._stack[-1][2]):
            return
        text = _normalise_space(data)
        if not text:
            return
        self.article.visible_chunks.append(text)
        if self._current_h1 is not None:
            self._current_h1.append(text)
        if self._current_h2 is not None:
            self._current_h2.append(text)
        elif self._active_section:
            self.article.section_text.setdefault(self._active_section, []).append(text)
        if self._current_paragraph is not None:
            self._current_paragraph.append(text)

    def handle_comment(self, data: str) -> None:
        self.article.comments.append(data)


def parse_article(html: str) -> ParsedArticle:
    parser = _ArticleParser()
    parser.feed(html)
    parser.close()
    return parser.article


def _metadata(comments: list[str]) -> dict[str, str]:
    metadata: dict[str, str] = {}
    labels = {
        "SEO Title": "seo_title",
        "Meta Title": "meta_title",
        "Meta Description": "meta_description",
        "URL Slug": "url_slug",
        "Target Keyword": "target_keyword",
    }
    for comment in comments:
        for line in comment.splitlines():
            if ":" not in line:
                continue
            label, value = line.split(":", 1)
            key = labels.get(label.strip())
            if key and key not in metadata:
                metadata[key] = value.strip()
    return metadata


def _internal_links(hrefs: list[str], site_url: str) -> list[str]:
    site_host = (urlparse(site_url).hostname or "").lower()
    accepted_hosts = {site_host, f"www.{site_host}"} if site_host else set()
    result = []
    for href in hrefs:
        parsed = urlparse(href)
        if href.startswith("/") and not href.startswith("//"):
            result.append(href)
        elif parsed.scheme in {"http", "https"} and (
            parsed.hostname or ""
        ).lower() in accepted_hosts:
            result.append(href)
    return result


def _block(
    blockers: list[dict],
    code: str,
    message: str,
    actual: object,
    expected: object,
) -> None:
    blockers.append(
        {
            "code": code,
            "message": message,
            "actual": actual,
            "expected": expected,
        }
    )


def evaluate_article_quality(
    html: str,
    *,
    target_keyword: str,
    site_url: str,
) -> dict:
    """Return a machine-readable Phase 3.5 content-quality receipt."""
    parsed = parse_article(html)
    metadata = _metadata(parsed.comments)
    visible_text = parsed.visible_text
    visible_words = _words(visible_text)
    visible_word_count = len(visible_words)
    h1 = parsed.h1_chunks[0] if parsed.h1_chunks else ""
    seo_title = metadata.get("meta_title") or metadata.get("seo_title", "")
    meta_description = metadata.get("meta_description", "")
    internal_links = _internal_links(parsed.hrefs, site_url)

    keyword = _normalise_space(target_keyword).lower()
    visible_lower = visible_text.lower()
    keyword_occurrences = visible_lower.count(keyword) if keyword else 0
    first_150_words = " ".join(visible_words[:150]).lower()
    keyword_in_opening = bool(keyword and keyword in first_150_words)
    keyword_in_h1 = bool(keyword and keyword in h1.lower())

    paragraph_norms = [
        _normalise_paragraph(paragraph)
        for paragraph in parsed.paragraphs
        if len(_words(paragraph)) >= 30
    ]
    paragraph_counts = Counter(paragraph_norms)
    repeated_paragraphs = sorted(
        paragraph for paragraph, count in paragraph_counts.items() if count > 1
    )

    substantive_sections = []
    shallow_sections = []
    for heading, chunks in parsed.section_text.items():
        heading_lower = heading.lower().strip()
        if (
            heading_lower in _NON_SUBSTANTIVE_H2
            or heading_lower.startswith("shop ")
            or heading_lower.startswith("find ")
        ):
            continue
        words = len(_words(" ".join(chunks)))
        substantive_sections.append({"heading": heading, "word_count": words})
        if words < DEFAULT_CONTRACT["min_words_per_substantive_section"]:
            shallow_sections.append({"heading": heading, "word_count": words})

    metrics = {
        "visible_word_count": visible_word_count,
        "seo_title": seo_title,
        "seo_title_chars": len(seo_title),
        "meta_description": meta_description,
        "meta_description_chars": len(meta_description),
        "h1": h1,
        "h2_count": len(parsed.h2s),
        "paragraph_count": len(parsed.paragraphs),
        "faq_item_count": parsed.faq_items,
        "quick_answer_present": parsed.quick_answer_present,
        "cta_present": parsed.cta_present,
        "internal_link_count": len(internal_links),
        "internal_links": internal_links,
        "target_keyword": target_keyword,
        "target_keyword_occurrences": keyword_occurrences,
        "target_keyword_in_h1": keyword_in_h1,
        "target_keyword_in_opening": keyword_in_opening,
        "substantive_sections": substantive_sections,
        "substantive_section_count": len(substantive_sections),
        "shallow_sections": shallow_sections,
        "repeated_paragraph_count": len(repeated_paragraphs),
        "placeholder_content_found": bool(_PLACEHOLDER_RE.search(visible_text)),
    }
    c = DEFAULT_CONTRACT
    blockers: list[dict] = []
    if visible_word_count < c["min_visible_words"]:
        _block(
            blockers,
            "CQ_VISIBLE_WORD_COUNT_LOW",
            "Article is too thin for an in-depth blog post.",
            visible_word_count,
            f">={c['min_visible_words']}",
        )
    if not (c["min_seo_title_chars"] <= len(seo_title) <= c["max_seo_title_chars"]):
        _block(
            blockers,
            "CQ_SEO_TITLE_LENGTH",
            "SEO title length is outside the approved range.",
            len(seo_title),
            f"{c['min_seo_title_chars']}-{c['max_seo_title_chars']}",
        )
    if not (
        c["min_meta_description_chars"]
        <= len(meta_description)
        <= c["max_meta_description_chars"]
    ):
        _block(
            blockers,
            "CQ_META_DESCRIPTION_LENGTH",
            "Meta description length is outside the approved range.",
            len(meta_description),
            (
                f"{c['min_meta_description_chars']}-"
                f"{c['max_meta_description_chars']}"
            ),
        )
    if len(parsed.h2s) < c["min_h2_count"]:
        _block(
            blockers,
            "CQ_H2_COUNT_LOW",
            "Article does not have enough structured sections.",
            len(parsed.h2s),
            f">={c['min_h2_count']}",
        )
    if len(parsed.paragraphs) < c["min_paragraph_count"]:
        _block(
            blockers,
            "CQ_PARAGRAPH_COUNT_LOW",
            "Article does not contain enough developed paragraphs.",
            len(parsed.paragraphs),
            f">={c['min_paragraph_count']}",
        )
    if parsed.faq_items < c["min_faq_items"]:
        _block(
            blockers,
            "CQ_FAQ_COUNT_LOW",
            "Article does not answer enough reader questions.",
            parsed.faq_items,
            f">={c['min_faq_items']}",
        )
    if len(internal_links) < c["min_internal_links"]:
        _block(
            blockers,
            "CQ_INTERNAL_LINK_COUNT_LOW",
            "Article does not provide enough relevant internal paths.",
            len(internal_links),
            f">={c['min_internal_links']}",
        )
    if len(substantive_sections) < c["min_substantive_sections"]:
        _block(
            blockers,
            "CQ_SUBSTANTIVE_SECTION_COUNT_LOW",
            "Article does not contain enough substantive sections.",
            len(substantive_sections),
            f">={c['min_substantive_sections']}",
        )
    if shallow_sections:
        _block(
            blockers,
            "CQ_SHALLOW_SECTIONS",
            "One or more substantive sections are underdeveloped.",
            shallow_sections,
            f">={c['min_words_per_substantive_section']} words each",
        )
    if not keyword_in_h1:
        _block(
            blockers,
            "CQ_KEYWORD_MISSING_FROM_H1",
            "Target keyword is not present in the H1.",
            h1,
            target_keyword,
        )
    if not keyword_in_opening:
        _block(
            blockers,
            "CQ_KEYWORD_MISSING_FROM_OPENING",
            "Target keyword is not present naturally near the beginning.",
            False,
            True,
        )
    if not (
        c["min_target_keyword_occurrences"]
        <= keyword_occurrences
        <= c["max_target_keyword_occurrences"]
    ):
        _block(
            blockers,
            "CQ_KEYWORD_USAGE_OUT_OF_RANGE",
            "Target keyword usage is missing or excessive.",
            keyword_occurrences,
            (
                f"{c['min_target_keyword_occurrences']}-"
                f"{c['max_target_keyword_occurrences']}"
            ),
        )
    if repeated_paragraphs:
        _block(
            blockers,
            "CQ_REPEATED_PARAGRAPHS",
            "Article repeats one or more substantive paragraphs.",
            len(repeated_paragraphs),
            0,
        )
    if metrics["placeholder_content_found"]:
        _block(
            blockers,
            "CQ_PLACEHOLDER_CONTENT",
            "Article contains placeholder or unfinished content.",
            True,
            False,
        )
    if not parsed.quick_answer_present:
        _block(
            blockers,
            "CQ_QUICK_ANSWER_MISSING",
            "Article is missing a concise quick-answer block.",
            False,
            True,
        )
    if not parsed.cta_present:
        _block(
            blockers,
            "CQ_CTA_MISSING",
            "Article is missing a clear next-step block.",
            False,
            True,
        )

    return {
        "contract_version": CONTRACT_VERSION,
        "page_type": "blog_post",
        "passed": not blockers,
        "blockers": blockers,
        "metrics": metrics,
        "thresholds": dict(DEFAULT_CONTRACT),
    }
