#!/usr/bin/env python3
"""Fixed-input OpenClaw client for the read-only HCS watchdog."""

from __future__ import annotations

import json
import socket
import sys


SOCKET_PATH = "/data/.openclaw/run/orin/hcs-watchdog/orin-hcs-watchdog.sock"
REQUEST_LINE = b"CHECK ORIN-HCS WATCHDOG V1\n"
MAX_RESPONSE_BYTES = 8192


def main() -> int:
    if len(sys.argv) != 1:
        print("orin_hcs_watchdog_check accepts no arguments", file=sys.stderr)
        return 2

    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.settimeout(15)
        connection.connect(SOCKET_PATH)
        connection.sendall(REQUEST_LINE)
        response_bytes = connection.makefile("rb").readline(MAX_RESPONSE_BYTES + 1)

    if not response_bytes or len(response_bytes) > MAX_RESPONSE_BYTES:
        print("invalid watchdog response", file=sys.stderr)
        return 3
    try:
        response = json.loads(response_bytes)
    except json.JSONDecodeError:
        print("invalid watchdog response", file=sys.stderr)
        return 3
    if response.get("schema") != "orin.watchdog/v1":
        print("invalid watchdog response", file=sys.stderr)
        return 3
    if response.get("client_id") not in {None, "hcs_gadgets"}:
        print("invalid watchdog tenant", file=sys.stderr)
        return 3

    print(json.dumps(response, separators=(",", ":"), sort_keys=True))
    status = response.get("status")
    if status in {"healthy", "pending"}:
        return 0
    if status == "alert":
        return 4
    return 5


if __name__ == "__main__":
    raise SystemExit(main())
