"""One-shot CLI for the disconnected ORIN worker."""

from __future__ import annotations

import argparse
import json
import os
import signal
import socket
import sys
import threading
import uuid
from datetime import date
from pathlib import Path

from orin_control.repository import create_database_engine
from orin_control.secrets import read_private_secret
from orin_runner.runner import configured_repo_root, run_client
from orin_worker.models import ClaimedJob
from orin_worker.repository import PostgresWorkerRepository
from orin_worker.service import WorkOutcome, work_forever, work_once


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="orin-worker")
    subparsers = parser.add_subparsers(dest="command", required=True)
    once = subparsers.add_parser("once", help="claim and execute at most one gated due job")
    _add_execution_arguments(once)
    once.add_argument(
        "--as-of-date",
        type=_as_of_date,
        help="manual test-only business date override in YYYY-MM-DD form",
    )
    once.add_argument(
        "--job-number",
        type=_job_number,
        help="manual test-only queue job pin; scheduled workers must omit it",
    )
    serve = subparsers.add_parser(
        "serve",
        help="continuously claim gated jobs using fixed production arguments",
    )
    _add_execution_arguments(serve)
    serve.add_argument("--poll-seconds", type=float, default=15)
    serve.add_argument("--error-backoff-seconds", type=float, default=60)
    return parser


def _add_execution_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--workspace-root", type=Path)
    parser.add_argument("--artifact-root", type=Path)
    parser.add_argument("--worker-id")
    parser.add_argument("--lease-seconds", type=int, default=1200)
    parser.add_argument("--heartbeat-seconds", type=float, default=60)


def _as_of_date(value: str) -> str:
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError as exc:
        raise argparse.ArgumentTypeError("as-of-date must use YYYY-MM-DD") from exc


def _job_number(value: str) -> str:
    if not value.isascii() or not value.isdecimal() or int(value) < 1:
        raise argparse.ArgumentTypeError("job-number must be a positive integer")
    return str(int(value))


def _worker_id(configured: str | None) -> str:
    if configured:
        return configured
    host = socket.gethostname().replace(" ", "_")
    return f"{host}:{os.getpid()}:{uuid.uuid4().hex[:8]}"


def database_url_from_environment() -> str:
    direct = os.environ.get("ORIN_WORKER_DATABASE_URL")
    secret_file = os.environ.get("ORIN_WORKER_DATABASE_URL_FILE")
    if bool(direct) == bool(secret_file):
        raise ValueError(
            "configure exactly one of ORIN_WORKER_DATABASE_URL or ORIN_WORKER_DATABASE_URL_FILE"
        )
    if direct:
        return direct
    assert secret_file is not None
    return read_private_secret(Path(secret_file), label="worker database URL")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        database_url = database_url_from_environment()
        repo_root = configured_repo_root()
    except (OSError, ValueError):
        print(json.dumps({"status": "failed", "error_code": "ORIN_WORKER_CONFIG_MISSING"}))
        return 2

    workspace_root = (args.workspace_root or Path(os.environ.get("ORIN_WORKSPACE_ROOT", repo_root))).resolve()
    artifact_root = (
        args.artifact_root
        or workspace_root / "clients" / "hoverboard_store" / "content_engine" / "automation_state" / "runs"
    ).resolve()
    worker_id = _worker_id(args.worker_id)
    repository = PostgresWorkerRepository(
        create_database_engine(database_url, pool_size=1),
        expected_role=os.environ.get("ORIN_WORKER_DATABASE_ROLE", "orin_worker"),
    )

    def execute(job: ClaimedJob) -> dict[str, object]:
        content_plan_snapshot = repository.get_content_plan_snapshot(
            job_id=job.job_id,
            worker_id=worker_id,
        )
        return run_client(
            client_id=job.client_id,
            request_id=str(job.request_id),
            mode=job.requested_mode,
            workspace_root=workspace_root,
            artifact_root=artifact_root,
            repo_root=repo_root,
            as_of_date=getattr(args, "as_of_date", None),
            job_number=getattr(args, "job_number", None),
            durable_db_mode=True,
            content_plan_snapshot=content_plan_snapshot,
        )

    try:
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

        if args.poll_seconds <= 0 or args.error_backoff_seconds <= 0:
            raise ValueError("worker timing values must be positive")
        stop_event = threading.Event()

        def stop_worker(_signum: int, _frame: object) -> None:
            stop_event.set()

        signal.signal(signal.SIGTERM, stop_worker)
        signal.signal(signal.SIGINT, stop_worker)

        def emit_outcome(outcome: WorkOutcome) -> None:
            print(
                json.dumps(
                    {"event": "work_outcome", **outcome.to_dict()},
                    sort_keys=True,
                ),
                flush=True,
            )

        def emit_error(exc: Exception) -> None:
            print(
                json.dumps(
                    {
                        "event": "worker_error",
                        "status": "failed",
                        "error_code": "ORIN_WORKER_FAILED",
                        "detail": type(exc).__name__,
                    },
                    sort_keys=True,
                ),
                flush=True,
            )

        print(
            json.dumps(
                {
                    "event": "worker_started",
                    "worker_id": worker_id,
                    "poll_seconds": args.poll_seconds,
                },
                sort_keys=True,
            ),
            flush=True,
        )
        work_forever(
            repository,
            worker_id=worker_id,
            execute=execute,
            stop_event=stop_event,
            poll_interval_seconds=args.poll_seconds,
            error_backoff_seconds=args.error_backoff_seconds,
            lease_seconds=args.lease_seconds,
            heartbeat_interval_seconds=args.heartbeat_seconds,
            on_outcome=emit_outcome,
            on_error=emit_error,
        )
        print(
            json.dumps(
                {"event": "worker_stopped", "worker_id": worker_id},
                sort_keys=True,
            ),
            flush=True,
        )
        return 0
    except Exception as exc:
        print(
            json.dumps(
                {
                    "status": "failed",
                    "error_code": "ORIN_WORKER_FAILED",
                    "detail": type(exc).__name__,
                },
                sort_keys=True,
            )
        )
        return 1
    finally:
        repository.close()


if __name__ == "__main__":
    raise SystemExit(main())
