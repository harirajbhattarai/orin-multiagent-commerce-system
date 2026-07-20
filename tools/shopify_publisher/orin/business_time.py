#!/usr/bin/env python3
"""
ORIN Business Time Utility — Canonical Date Source

Single source of truth for ORIN's business date in Europe/London.

Timezone: Europe/London (handles GMT/BST automatically via ZoneInfo)

Production default: current date in Europe/London
Deterministic override: --as-of-date YYYY-MM-DD argument (for testing/dry-runs)

Usage:
  from business_time import get_business_today

  # Production — uses current Europe/London date
  today = get_business_today()

  # Deterministic override — for testing and dry-runs
  today = get_business_today(as_of_date="2026-07-04")

  # Via CLI string (e.g. from sys.argv)
  today = get_business_today_from_args(["--as-of-date", "2026-07-04"])
"""

import os
import re
import sys
from datetime import date, datetime
from pathlib import Path

try:
    from zoneinfo import ZoneInfo
except ImportError:
    # Python < 3.9 fallback — not recommended, but handles older installs
    from backports.zoneinfo import ZoneInfo  # noqa: F401

# Canonical business timezone
BUSINESS_TZ = ZoneInfo("Europe/London")

# YYYY-MM-DD validation regex
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# Store for the resolved business date (set once per process lifecycle)
_resolved_business_date: date | None = None


def _parse_date(date_str: str, param_name: str = "as_of_date") -> date:
    """
    Parse a YYYY-MM-DD string to a date object.
    Raises ValueError with a clear message on invalid input.
    """
    if not _DATE_RE.match(date_str):
        raise ValueError(
            f"Invalid {param_name} format: '{date_str}'. "
            f"Expected YYYY-MM-DD (e.g. 2026-07-04)."
        )
    try:
        return date.fromisoformat(date_str)
    except ValueError as e:
        raise ValueError(
            f"Impossible date '{date_str}' ({e}). "
            f"Please check the {param_name} value."
        ) from e


def get_business_today(as_of_date: str | None = None) -> date:
    """
    Return the ORIN business date.

    Priority order:
      1. Explicit as_of_date argument (highest)
      2. ORIN_BUSINESS_DATE env var (for subprocess propagation)
      3. sys.argv --as-of-date flag (for direct CLI use)
      4. Current Europe/London date (production default)

    Args:
        as_of_date: Optional YYYY-MM-DD string for deterministic override.
                    When None, checks ORIN_BUSINESS_DATE env var, then sys.argv.

    Returns:
        date in Europe/London timezone.

    Raises:
        ValueError: if as_of_date is malformed or impossible.

    Does NOT silently fall back to any other date.
    """
    # 1. Explicit argument
    if as_of_date is not None:
        d = _parse_date(as_of_date, "as_of_date")
        return d

    # 2. Environment variable (set by parent cron entrypoint for subprocesses)
    env_date = os.environ.get("ORIN_BUSINESS_DATE", "").strip()
    if env_date:
        return _parse_date(env_date, "ORIN_BUSINESS_DATE env var")

    # 3. sys.argv --as-of-date (for direct CLI use)
    argv_date = os.environ.get("ORIN_ARGV_DATE", "").strip()
    if not argv_date:
        # Construct from sys.argv --as-of-date if present
        for i, arg in enumerate(sys.argv):
            if arg == "--as-of-date" and i + 1 < len(sys.argv):
                argv_date = sys.argv[i + 1]
                break
            m = re.match(r"^--as-of-date=(.+)$", arg)
            if m:
                argv_date = m.group(1)
                break
    if argv_date:
        return _parse_date(argv_date, "--as-of-date")

    # 4. Production default: current date in Europe/London
    return datetime.now(BUSINESS_TZ).date()


def get_business_today_from_args(argv: list[str]) -> date:
    """
    Parse --as-of-date from a sys.argv-style list and return the business date.

    If --as-of-date is present, uses that value.
    If --as-of-date is missing, falls back to current Europe/London date.

    Raises:
        ValueError: if --as-of-date is present but has an invalid value.

    Does NOT silently fall back if --as-of-date is provided but malformed.
    """
    as_of = None
    for i, arg in enumerate(argv):
        if arg == "--as-of-date" and i + 1 < len(argv):
            as_of = argv[i + 1]
            break
        m = re.match(r"^--as-of-date=(.+)$", arg)
        if m:
            as_of = m.group(1)
            break

    return get_business_today(as_of)


# ─── CLI test harness ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    """
    Direct CLI test:
      python3 tools/shopify_publisher/orin/business_time.py
      python3 tools/shopify_publisher/orin/business_time.py --as-of-date 2026-07-04
      python3 tools/shopify_publisher/orin/business_time.py --as-of-date 2026-02-30   # fails
      python3 tools/shopify_publisher/orin/business_time.py --as-of-date 04-07-2026   # fails
    """
    today = get_business_today_from_args(sys.argv[1:])
    print(f"business_date={today.isoformat()}")
