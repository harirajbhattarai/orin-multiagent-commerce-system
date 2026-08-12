"""Container-local health check for the persistent Prefect owner worker."""

from __future__ import annotations

import json
import urllib.request


request = urllib.request.Request("http://127.0.0.1:8080/health")
with urllib.request.urlopen(request, timeout=5) as response:
    payload = json.load(response)

if response.status != 200 or payload != {"message": "OK"}:
    raise SystemExit("Prefect owner worker health check failed")
