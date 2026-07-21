"""Canonical filesystem roots for ORIN source and runtime data."""

from __future__ import annotations

import os
from pathlib import Path


_SOURCE_ROOT = Path(__file__).resolve().parents[3]


def source_root() -> Path:
    """Return the immutable source checkout containing this module."""
    return _SOURCE_ROOT


def workspace_root() -> Path:
    """Return the explicit runtime root, or this repository checkout by default."""
    return Path(os.environ.get("ORIN_WORKSPACE_ROOT", _SOURCE_ROOT)).expanduser().resolve()
