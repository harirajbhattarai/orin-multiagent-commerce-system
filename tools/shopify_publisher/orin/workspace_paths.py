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


def content_queue_path(*, client_id: str) -> Path:
    """Resolve a database projection in durable mode or the legacy source file."""
    configured = os.environ.get("ORIN_CONTENT_QUEUE_PATH")
    if configured:
        candidate = Path(configured).expanduser()
        if not candidate.is_absolute():
            raise RuntimeError("ORIN_CONTENT_QUEUE_PATH must be absolute")
        resolved = candidate.resolve()
        if os.environ.get("ORIN_DURABLE_DB_MODE") == "1":
            artifact_dir = os.environ.get("ORIN_RUN_ARTIFACT_DIR")
            if not artifact_dir:
                raise RuntimeError("durable queue projection requires ORIN_RUN_ARTIFACT_DIR")
            artifact_root = Path(artifact_dir).expanduser().resolve()
            if not resolved.is_relative_to(artifact_root):
                raise RuntimeError("durable queue projection must be private run evidence")
        return resolved
    return workspace_root() / "clients" / client_id / "content_engine" / "content_queue_3_months.md"


def writable_output_path(
    *,
    artifact_relative_path: str,
    workspace_relative_path: str,
) -> Path:
    """Resolve mutable output into private run evidence when configured."""
    artifact_dir = os.environ.get("ORIN_RUN_ARTIFACT_DIR")
    if artifact_dir:
        artifact_root = Path(artifact_dir).expanduser()
        if not artifact_root.is_absolute():
            raise RuntimeError("ORIN_RUN_ARTIFACT_DIR must be absolute")
        return artifact_root.resolve() / artifact_relative_path
    return workspace_root() / workspace_relative_path


def writable_report_path(*, artifact_name: str, workspace_relative_path: str) -> Path:
    """Keep generated reports out of a read-only runtime workspace."""
    return writable_output_path(
        artifact_relative_path=artifact_name,
        workspace_relative_path=workspace_relative_path,
    )
