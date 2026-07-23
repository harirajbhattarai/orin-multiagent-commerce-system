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


def writable_report_path(*, artifact_name: str, workspace_relative_path: str) -> Path:
    """Keep generated reports out of a read-only runtime workspace."""
    artifact_dir = os.environ.get("ORIN_RUN_ARTIFACT_DIR")
    if artifact_dir:
        artifact_root = Path(artifact_dir).expanduser()
        if not artifact_root.is_absolute():
            raise RuntimeError("ORIN_RUN_ARTIFACT_DIR must be absolute")
        return artifact_root.resolve() / artifact_name
    return workspace_root() / workspace_relative_path
