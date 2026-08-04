"""Authenticated health probe for the loopback-only Prefect API."""

from __future__ import annotations

import base64
from pathlib import Path
from urllib.request import Request, urlopen


auth = Path("/run/secrets/prefect_api_auth").read_text(encoding="utf-8").strip()
header = base64.b64encode(auth.encode("utf-8")).decode("ascii")
request = Request(
    "http://127.0.0.1:4200/api/health",
    headers={"Authorization": f"Basic {header}"},
)
with urlopen(request, timeout=5) as response:  # noqa: S310 - fixed loopback URL
    if response.status != 200:
        raise SystemExit(f"unexpected Prefect health status: {response.status}")
