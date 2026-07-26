#!/usr/bin/env python3
"""Fixed-input OpenClaw client for the HBStore scheduler trigger socket."""

from __future__ import annotations

import json
import socket
import sys


SOCKET_PATH = "/data/.openclaw/run/orin/orin-hbstore-trigger.sock"
REQUEST_LINE = b"TRIGGER ORIN-HBSTORE V1\n"
MAX_RESPONSE_BYTES = 8192


def main() -> int:
    if len(sys.argv) != 1:
        print("orin_hbstore_trigger accepts no arguments", file=sys.stderr)
        return 2

    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.settimeout(15)
        connection.connect(SOCKET_PATH)
        connection.sendall(REQUEST_LINE)
        connection.shutdown(socket.SHUT_WR)
        response_bytes = connection.makefile("rb").readline(MAX_RESPONSE_BYTES + 1)

    if not response_bytes or len(response_bytes) > MAX_RESPONSE_BYTES:
        print("invalid scheduler trigger response", file=sys.stderr)
        return 3
    try:
        response = json.loads(response_bytes)
    except json.JSONDecodeError:
        print("invalid scheduler trigger response", file=sys.stderr)
        return 3
    if response.get("schema") != "orin.scheduler-trigger/v1":
        print("invalid scheduler trigger response", file=sys.stderr)
        return 3

    print(json.dumps(response, separators=(",", ":"), sort_keys=True))
    return 0 if response.get("status") == "accepted" else 4


if __name__ == "__main__":
    raise SystemExit(main())
