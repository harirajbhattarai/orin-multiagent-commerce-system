"""One-client worker for approved OAuth-backed Shopify drafts."""

from __future__ import annotations

import argparse
import json
import os
import re
import signal
import socket
import threading
import uuid
from pathlib import Path

from orin_control.repository import create_database_engine
from orin_control.secrets import read_private_secret
from orin_oauth_draft_worker.repository import PostgresOAuthDraftRepository
from orin_runner.runner import configured_repo_root, run_client
from orin_shopify import ShopifyRuntimeConfig
from orin_worker.models import ClaimedJob
from orin_worker.service import WorkOutcome, work_forever, work_once


def _client_id(value: str) -> str:
    if not re.fullmatch(r"[a-z0-9][a-z0-9_]{1,62}", value):
        raise argparse.ArgumentTypeError("client ID is invalid")
    if value in {"hoverboard_store", "hcs_gadgets"}:
        raise argparse.ArgumentTypeError("dedicated clients cannot use the OAuth draft worker")
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="orin-oauth-draft-worker")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("once", "serve"):
        command = subparsers.add_parser(name)
        command.add_argument("--client-id", required=True, type=_client_id)
        command.add_argument("--artifact-root", type=Path, default=Path("/evidence"))
        command.add_argument("--worker-id")
        command.add_argument("--lease-seconds", type=int, default=1200)
        command.add_argument("--heartbeat-seconds", type=float, default=60)
        if name == "serve":
            command.add_argument("--poll-seconds", type=float, default=15)
            command.add_argument("--error-backoff-seconds", type=float, default=60)
    ping = subparsers.add_parser("ping")
    ping.add_argument("--client-id", required=True, type=_client_id)
    return parser


def _database_url() -> str:
    direct = os.environ.get("ORIN_OAUTH_DRAFT_DATABASE_URL")
    secret_file = os.environ.get("ORIN_OAUTH_DRAFT_DATABASE_URL_FILE")
    if bool(direct) == bool(secret_file):
        raise ValueError("configure exactly one OAuth draft database URL source")
    if direct:
        return direct
    assert secret_file is not None
    return read_private_secret(Path(secret_file), label="OAuth draft worker database URL")


def _worker_id(value: str | None) -> str:
    return value or f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"


def _runtime_config(context: dict[str, object]) -> ShopifyRuntimeConfig:
    shopify = context.get("shopify")
    if not isinstance(shopify, dict):
        raise RuntimeError("Shopify runtime context is missing")
    return ShopifyRuntimeConfig(
        store_domain=str(shopify.get("store_domain") or ""),
        access_token=str(shopify.get("access_token") or ""),
        api_version=str(shopify.get("api_version") or ""),
        blog_id=str(shopify.get("blog_id") or ""),
        author_name=str(shopify.get("author_name") or ""),
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        repository = PostgresOAuthDraftRepository(
            create_database_engine(_database_url(), pool_size=1), client_id=args.client_id
        )
        repo_root = configured_repo_root()
    except Exception:
        print(json.dumps({"status": "failed", "error_code": "ORIN_OAUTH_DRAFT_CONFIG_MISSING"}))
        return 2
    try:
        if args.command == "ping":
            repository.ping()
            print(json.dumps({"status": "ok"}))
            return 0
        worker_id = _worker_id(args.worker_id)

        def execute(job: ClaimedJob) -> dict[str, object]:
            if job.client_id != args.client_id:
                raise RuntimeError("claimed job crossed the configured client boundary")
            context = repository.get_context(job_id=job.job_id, worker_id=worker_id)
            snapshot = context.get("snapshot")
            if not isinstance(snapshot, dict):
                raise RuntimeError("approved draft snapshot is missing")
            return run_client(
                client_id=job.client_id,
                request_id=str(job.request_id),
                mode=job.requested_mode,
                workspace_root=repo_root,
                artifact_root=args.artifact_root.resolve(),
                repo_root=repo_root,
                durable_db_mode=True,
                content_plan_snapshot=snapshot,
                claim_attempt=job.attempt_count,
                shopify_runtime_config=_runtime_config(context),
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
                json.dumps({"event": "work_outcome", **outcome.to_dict()}, sort_keys=True), flush=True
            ),
            on_error=lambda error: print(
                json.dumps({"event": "worker_error", "error": type(error).__name__}), flush=True
            ),
        )
        return 0
    finally:
        repository.close()
