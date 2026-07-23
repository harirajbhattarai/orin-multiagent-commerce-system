"""One-shot CLI for the disconnected ORIN worker."""

from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import uuid
from datetime import date
from pathlib import Path

from orin_control.repository import create_database_engine
from orin_control.secrets import read_private_secret
from orin_runner.runner import configured_repo_root, run_client
from orin_worker.models import ClaimedJob
from orin_worker.repository import PostgresWorkerRepository
from orin_worker.service import work_once


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="orin-worker")
    subparsers = parser.add_subparsers(dest="command", required=True)
    once = subparsers.add_parser("once", help="claim and execute at most one gated due job")
    once.add_argument("--workspace-root", type=Path)
    once.add_argument("--artifact-root", type=Path)
    once.add_argument("--worker-id")
    once.add_argument("--lease-seconds", type=int, default=1200)
    once.add_argument("--heartbeat-seconds", type=float, default=60)
    once.add_argument(
        "--as-of-date",
        type=_as_of_date,
        help="manual test-only business date override in YYYY-MM-DD form",
    )
    return parser


def _as_of_date(value: str) -> str:
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError as exc:
        raise argparse.ArgumentTypeError("as-of-date must use YYYY-MM-DD") from exc


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
        return run_client(
            client_id=job.client_id,
            request_id=str(job.request_id),
            mode=job.requested_mode,
            workspace_root=workspace_root,
            artifact_root=artifact_root,
            repo_root=repo_root,
            as_of_date=args.as_of_date,
            durable_db_mode=True,
        )

    try:
        outcome = work_once(
            repository,
            worker_id=worker_id,
            execute=execute,
            lease_seconds=args.lease_seconds,
            heartbeat_interval_seconds=args.heartbeat_seconds,
        )
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

    print(json.dumps(outcome.to_dict(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
