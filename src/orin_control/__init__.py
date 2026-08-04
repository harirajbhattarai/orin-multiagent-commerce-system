"""Narrow authenticated control plane for ORIN run requests."""

from __future__ import annotations

from typing import Any


def __getattr__(name: str) -> Any:
    """Keep non-web helpers usable in minimal worker/runner images."""
    if name == "create_app":
        from orin_control.app import create_app

        return create_app
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = ["create_app"]
