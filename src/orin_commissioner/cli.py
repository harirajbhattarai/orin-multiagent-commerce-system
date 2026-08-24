"""CLI for the trusted no-code commissioning worker."""

from __future__ import annotations

import argparse
import json
import os
import signal
import socket
import threading
import uuid
from pathlib import Path

from orin_commissioner.repository import PostgresCommissioningRepository
from orin_commissioner.service import commission_once
from orin_control.repository import create_database_engine
from orin_control.secrets import read_private_secret


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="orin-commissioner")
    subparsers = parser.add_subparsers(dest="command", required=True)
    once = subparsers.add_parser("once", help="commission at most one queued client")
    serve = subparsers.add_parser("serve", help="continuously consume commissioning requests")
    ping = subparsers.add_parser("ping", help="verify the isolated database role")
    for command in (once, serve):
        command.add_argument("--worker-id")
        command.add_argument("--lease-seconds", type=int, default=300)
    serve.add_argument("--poll-seconds", type=float, default=15)
    serve.add_argument("--error-backoff-seconds", type=float, default=60)
    return parser


def database_url_from_environment() -> str:
    direct = os.environ.get("ORIN_COMMISSIONER_DATABASE_URL")
    secret_file = os.environ.get("ORIN_COMMISSIONER_DATABASE_URL_FILE")
    if bool(direct) == bool(secret_file):
        raise ValueError("configure exactly one commissioner database URL source")
    if direct:
        return direct
    assert secret_file is not None
    return read_private_secret(Path(secret_file), label="commissioner database URL")


def _worker_id(configured: str | None) -> str:
    if configured:
        return configured
    return f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        database_url = database_url_from_environment()
        repository = PostgresCommissioningRepository(
            create_database_engine(database_url, pool_size=1),
            expected_role=os.environ.get("ORIN_COMMISSIONER_DATABASE_ROLE", "orin_commissioner"),
        )
    except (OSError, ValueError):
        print(json.dumps({"status": "failed", "error_code": "ORIN_COMMISSIONER_CONFIG_MISSING"}))
        return 2

    try:
        if args.command == "ping":
            repository.ping()
            print(json.dumps({"status": "healthy", "role": "orin_commissioner"}))
            return 0

        worker_id = _worker_id(args.worker_id)
        if args.command == "once":
            outcome = commission_once(
                repository, worker_id=worker_id, lease_seconds=args.lease_seconds
            )
            print(json.dumps(outcome.to_dict(), sort_keys=True))
            return 0 if outcome.status in {"no_request", "succeeded"} else 1

        if args.poll_seconds <= 0 or args.error_backoff_seconds <= 0:
            raise ValueError("commissioner timing values must be positive")
        stop_event = threading.Event()
        signal.signal(signal.SIGTERM, lambda *_: stop_event.set())
        signal.signal(signal.SIGINT, lambda *_: stop_event.set())
        print(json.dumps({"event": "commissioner_started", "worker_id": worker_id}), flush=True)
        while not stop_event.is_set():
            try:
                outcome = commission_once(
                    repository, worker_id=worker_id, lease_seconds=args.lease_seconds
                )
                print(json.dumps({"event": "commissioning_outcome", **outcome.to_dict()}), flush=True)
                delay = args.poll_seconds
            except Exception as exc:
                print(
                    json.dumps(
                        {
                            "event": "commissioner_error",
                            "error_code": "ORIN_COMMISSIONER_FAILED",
                            "failure_type": type(exc).__name__,
                        }
                    ),
                    flush=True,
                )
                delay = args.error_backoff_seconds
            stop_event.wait(delay)
        print(json.dumps({"event": "commissioner_stopped", "worker_id": worker_id}), flush=True)
        return 0
    finally:
        repository.close()
