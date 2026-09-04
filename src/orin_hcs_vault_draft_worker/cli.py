"""Persistent worker for exact HCS Vault-backed Shopify draft approvals."""

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
from orin_hcs_vault_draft_worker.repository import PostgresHCSVaultDraftRepository
from orin_runner.runner import configured_repo_root, run_client
from orin_shopify import ShopifyRuntimeConfig
from orin_worker.models import ClaimedJob
from orin_worker.service import work_forever, work_once


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="orin-hcs-vault-draft-worker")
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
    direct = os.environ.get("ORIN_HCS_VAULT_DRAFT_DATABASE_URL")
    secret_file = os.environ.get("ORIN_HCS_VAULT_DRAFT_DATABASE_URL_FILE")
    if bool(direct) == bool(secret_file):
        raise ValueError("configure exactly one HCS Vault draft database URL source")
    if direct:
        return direct
    assert secret_file is not None
    return read_private_secret(Path(secret_file), label="HCS Vault draft worker database URL")


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
        repository = PostgresHCSVaultDraftRepository(
            create_database_engine(_database_url(), pool_size=1)
        )
        repo_root = configured_repo_root()
    except Exception:
        print(json.dumps({"status": "failed", "error_code": "ORIN_HCS_VAULT_DRAFT_CONFIG_MISSING"}))
        return 2
    try:
        if args.command == "ping":
            repository.ping()
            print(json.dumps({"status": "ok"}))
            return 0
        worker_id = _worker_id(args.worker_id)

        def execute(job: ClaimedJob) -> dict[str, object]:
            if job.client_id != "hcs_gadgets":
                raise RuntimeError("claimed job crossed the HCS client boundary")
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
