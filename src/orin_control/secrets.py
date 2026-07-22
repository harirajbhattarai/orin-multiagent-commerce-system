"""Read runtime secrets from tightly permissioned files."""

from __future__ import annotations

import os
import stat
from pathlib import Path


def read_private_secret(path: Path, *, label: str) -> str:
    if not path.is_absolute():
        raise ValueError(f"{label} file path must be absolute")
    if path.is_symlink():
        raise ValueError(f"{label} path must not be a symbolic link")
    metadata = path.stat()
    if not stat.S_ISREG(metadata.st_mode):
        raise ValueError(f"{label} path must be a regular file")
    if stat.S_IMODE(metadata.st_mode) & 0o077:
        raise ValueError(f"{label} file must not be accessible by group or others")
    if metadata.st_uid != os.geteuid():
        raise ValueError(f"{label} file must be owned by the service user")
    if metadata.st_size > 8192:
        raise ValueError(f"{label} file is unexpectedly large")

    raw = path.read_text(encoding="utf-8")
    value = raw.rstrip("\r\n")
    if not value or "\n" in value or "\r" in value:
        raise ValueError(f"{label} file must contain exactly one non-empty line")
    return value
