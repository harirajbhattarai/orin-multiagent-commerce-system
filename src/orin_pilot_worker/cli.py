"""CLI for the shared, sequential generic OAuth pilot worker."""

from __future__ import annotations

import argparse
import json
import os
import signal
import socket
import threading
import uuid
from pathlib import Path

from orin_control.repository import create_database_engine
from orin_control.secrets import read_private_secret
from orin_pilot_worker.repository import PostgresPilotRepository
from orin_pilot_worker.runner import execute_generic_pilot
from orin_worker.models import ClaimedJob
from orin_worker.service import WorkOutcome, work_forever, work_once


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="orin-pilot-worker")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("once", "serve"):
        command = subparsers.add_parser(name)
        command.add_argument("--artifact-root", type=Path, default=Path("/evidence"))
        command.add_argument("--worker-id")
        command.add_argument("--lease-seconds", type=int, default=1200)
        command.add_argument("--heartbeat-seconds", type=float, default=60)
        if name == "serve":
            command.add_argument("--poll-seconds", type=float, default=15)
            command.add_argument("--error-backoff-seconds", type=float, default=60)
    subparsers.add_parser("ping")
    return parser


def _database_url() -> str:
    direct = os.environ.get("ORIN_PILOT_DATABASE_URL")
    secret_file = os.environ.get("ORIN_PILOT_DATABASE_URL_FILE")
    if bool(direct) == bool(secret_file):
        raise ValueError("configure exactly one pilot database URL source")
    if direct:
        return direct
    assert secret_file is not None
    return read_private_secret(Path(secret_file), label="pilot worker database URL")


def _worker_id(value: str | None) -> str:
    if value:
        return value
    return f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        repository = PostgresPilotRepository(
            create_database_engine(_database_url(), pool_size=1),
            expected_role=os.environ.get("ORIN_PILOT_DATABASE_ROLE", "orin_pilot_worker"),
        )
    except Exception:
        print(json.dumps({"status": "failed", "error_code": "ORIN_PILOT_CONFIG_MISSING"}))
        return 2
    try:
        if args.command == "ping":
            repository.ping()
            print(json.dumps({"status": "ok"}))
            return 0
        worker_id = _worker_id(args.worker_id)

        def execute(job: ClaimedJob) -> dict[str, object]:
            context = repository.get_context(job_id=job.job_id, worker_id=worker_id)
            return execute_generic_pilot(
                job, context=context, artifact_root=args.artifact_root.resolve()
            )

        if args.command == "once":
            outcome = work_once(
                repository,
                worker_id=worker_id,
                execute=execute,
                lease_seconds=args.lease_seconds,
                heartbeat_interval_seconds=args.heartbeat_seconds,
            )
            print(json.dumps(outcome.to_dict(), sort_keys=True))
            return 0

        stop = threading.Event()
        signal.signal(signal.SIGTERM, lambda *_: stop.set())
        signal.signal(signal.SIGINT, lambda *_: stop.set())
        work_forever(
            repository,
            worker_id=worker_id,
            execute=execute,
            stop_event=stop,
            poll_interval_seconds=args.poll_seconds,
            error_backoff_seconds=args.error_backoff_seconds,
            lease_seconds=args.lease_seconds,
            heartbeat_interval_seconds=args.heartbeat_seconds,
            on_outcome=lambda outcome: print(
                json.dumps({"event": "work_outcome", **outcome.to_dict()}, sort_keys=True),
                flush=True,
            ),
            on_error=lambda error: print(
                json.dumps(
                    {
                        "event": "worker_error",
                        "error_code": "ORIN_PILOT_WORKER_FAILED",
                        "detail": type(error).__name__,
                    },
                    sort_keys=True,
                ),
                flush=True,
            ),
        )
        return 0
    finally:
        repository.close()
