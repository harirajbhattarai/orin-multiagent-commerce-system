"""
Canonical Shopify handle utilities for ORIN.

One source of truth for handle normalisation across all ORIN phases.
Every downstream ORIN module imports from here — no duplicate handle algorithms.

Rules for canonical Shopify handles:
  - lowercase
  - spaces converted to hyphens
  - repeated whitespace collapsed to one hyphen
  - unsupported punctuation removed
  - repeated hyphens collapsed
  - no leading/trailing hyphens
  - ASCII letters and numbers only
"""

import re

# ── Sentinel ─────────────────────────────────────────────────────────────────

BLOCK_INVALID_PLANNED_HANDLE = "BLOCK_INVALID_PLANNED_HANDLE"


# ── Core normalisation ────────────────────────────────────────────────────────

def normalise_shopify_handle(value: str) -> str:
    """
    Convert any input string to a canonical Shopify handle.

    Rules:
      - lowercase
      - trim leading/trailing whitespace
      - convert spaces to hyphens
      - convert repeated whitespace/separators to one hyphen
      - remove unsupported punctuation (keep a-z, 0-9, spaces, hyphens only)
      - collapse repeated hyphens
      - strip leading/trailing hyphens

    Input:  "Hoverkart Compatibility Checklist Before You Buy"
    Output: "hoverkart-compatibility-checklist-before-you-buy"

    Input:  "Best Hoverboard Accessories: UK 2026"
    Output: "best-hoverboard-accessories-uk-2026"

    Input:  " Portable BBQ -- Guide "
    Output: "portable-bbq-guide"
    """
    if not value:
        return ""

    # Step 1: lowercase
    slug = value.lower()

    # Step 2: strip leading/trailing whitespace
    slug = slug.strip()

    # Step 3: keep only ASCII letters, digits, spaces, hyphens
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)

    # Step 4: convert whitespace sequences to single hyphens
    slug = re.sub(r"\s+", "-", slug)

    # Step 5: collapse repeated hyphens
    slug = re.sub(r"-+", "-", slug)

    # Step 6: strip leading/trailing hyphens
    slug = slug.strip("-")

    return slug


# ── Validation ─────────────────────────────────────────────────────────────────

def is_canonical_shopify_handle(value: str) -> bool:
    """
    Validate that a handle is a canonical Shopify handle.

    Canonical handle rules:
      - no spaces
      - all lowercase
      - hyphens as separators (no underscores, no other separators)
      - no repeated hyphens (e.g. no "--" or "---")
      - does not start with hyphen
      - does not end with hyphen
      - contains only a-z, 0-9, hyphens
      - not empty after normalisation
    """
    if not value:
        return False

    # Must have at least one character
    if len(value) == 0:
        return False

    # No spaces
    if " " in value:
        return False

    # All lowercase (a-z only — digits and hyphens are their own case)
    if not value.islower():
        return False

    # No uppercase letters
    if re.search(r"[A-Z]", value):
        return False

    # No repeated hyphens
    if re.search(r"--+", value):
        return False

    # No leading hyphen
    if value.startswith("-"):
        return False

    # No trailing hyphen
    if value.endswith("-"):
        return False

    # Only a-z, 0-9, hyphens
    if not re.fullmatch(r"[a-z0-9-]+", value):
        return False

    # Must not be empty after normalisation (sanity check)
    normalised = normalise_shopify_handle(value)
    if not normalised:
        return False

    return True


# ── Canonical handle invariant ─────────────────────────────────────────────────

def validate_or_raise_canonical_handle(handle: str, job_label: str = "unknown") -> None:
    """
    Validate a handle is canonical.
    Raises ValueError with BLOCK_INVALID_PLANNED_HANDLE if not.
    """
    if not is_canonical_shopify_handle(handle):
        raise ValueError(
            f"{BLOCK_INVALID_PLANNED_HANDLE}: "
            f"handle for {job_label} is not canonical: {repr(handle)}. "
            f"Expected lowercase, hyphen-separated, no spaces, no repeated hyphens, "
            f"no leading/trailing hyphens."
        )
