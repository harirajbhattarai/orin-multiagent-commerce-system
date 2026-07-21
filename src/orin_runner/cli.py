"""Command-line interface for the deterministic ORIN runner."""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from pathlib import Path

from orin_runner.contract import (
    ERROR_IDEMPOTENCY_CONFLICT,
    ERROR_INVALID_REQUEST,
    ERROR_RUNNER_BUSY,
    ERROR_UNSUPPORTED_CLIENT,
    ERROR_UNSUPPORTED_MODE,
)
from orin_runner.runner import (
    IdempotencyConflictError,
    RunnerBusyError,
    SUPPORTED_CLIENTS,
    SUPPORTED_MODES,
    run_client,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="orin-runner")
    subparsers = parser.add_subparsers(dest="command", required=True)
    run_parser = subparsers.add_parser("run", help="execute one client workflow request")
    run_parser.add_argument("--client-id", required=True)
    run_parser.add_argument("--request-id", required=True)
    run_parser.add_argument("--mode", required=True)
    run_parser.add_argument("--workspace-root", type=Path, default=None)
    run_parser.add_argument("--artifact-root", type=Path, default=None)
    run_parser.add_argument("--as-of-date")
    return parser


def _error_payload(error_code: str, detail: str) -> dict[str, str]:
    return {"schema": "orin.cli-error/v1", "status": "failed", "error_code": error_code, "detail": detail}


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.client_id not in SUPPORTED_CLIENTS:
        print(json.dumps(_error_payload(ERROR_UNSUPPORTED_CLIENT, args.client_id), sort_keys=True))
        return 2
    if args.mode not in SUPPORTED_MODES:
        print(json.dumps(_error_payload(ERROR_UNSUPPORTED_MODE, args.mode), sort_keys=True))
        return 2
    try:
        uuid.UUID(args.request_id)
    except ValueError:
        print(json.dumps(_error_payload(ERROR_INVALID_REQUEST, "request-id must be a UUID"), sort_keys=True))
        return 2

    repo_root = Path(__file__).resolve().parents[2]
    workspace_root = (args.workspace_root or Path(os.environ.get("ORIN_WORKSPACE_ROOT", repo_root))).resolve()
    artifact_root = (
        args.artifact_root
        or workspace_root / "clients" / args.client_id / "content_engine" / "automation_state" / "runs"
    ).resolve()

    try:
        result = run_client(
            client_id=args.client_id,
            request_id=args.request_id,
            mode=args.mode,
            workspace_root=workspace_root,
            artifact_root=artifact_root,
            repo_root=repo_root,
            as_of_date=args.as_of_date,
        )
    except RunnerBusyError:
        print(json.dumps(_error_payload(ERROR_RUNNER_BUSY, "another local ORIN run is active"), sort_keys=True))
        return 75
    except IdempotencyConflictError as exc:
        print(json.dumps(_error_payload(ERROR_IDEMPOTENCY_CONFLICT, str(exc)), sort_keys=True))
        return 2

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] in {"completed", "blocked"} else 1
