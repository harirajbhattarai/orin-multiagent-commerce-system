"""Run a credential-free hidden-draft reconciliation fault drill.

This drill never calls Shopify. It models a remote create that becomes
observable before the runner receives a response, forces the first runner
attempt to time out, and then proves that retry reconciles the same marker
without a second create.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any

from orin_runner.contract import ERROR_PIPELINE_TIMEOUT
from orin_runner.runner import run_client


SHOPIFY_ENV_PREFIXES = (
    "HOVERBOARD_STORE_SHOPIFY_",
    "SHOPIFY_",
)


def _write_private_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    path.chmod(0o600)


def _assert_credential_free() -> None:
    exposed = sorted(
        name
        for name, value in os.environ.items()
        if value and name.startswith(SHOPIFY_ENV_PREFIXES)
    )
    if exposed:
        raise RuntimeError(
            "partial-failure drill refuses to run with Shopify environment variables present: "
            + ", ".join(exposed)
        )


def _assert_network_none() -> list[str]:
    interfaces_root = Path("/sys/class/net")
    if not interfaces_root.is_dir():
        raise RuntimeError("cannot verify container network isolation")
    interfaces = sorted(path.name for path in interfaces_root.iterdir())
    if any(name != "lo" for name in interfaces):
        raise RuntimeError(
            "partial-failure drill requires a network-none container; interfaces found: "
            + ", ".join(interfaces)
        )
    return interfaces


def _simulator_source(*, state_path: Path, preview_path: Path) -> str:
    return f"""\
import json
import os
import pathlib
import time

state_path = pathlib.Path({str(state_path)!r})
preview_path = pathlib.Path({str(preview_path)!r})
marker = "orin-v1:" + os.environ["ORIN_IDEMPOTENCY_KEY"]

if not state_path.exists():
    state_path.write_text(json.dumps({{
        "article_id": "9001",
        "handle": "partial-failure-reconciliation-drill",
        "marker": marker,
        "mutation_count": 1,
        "published": False
    }}))
    time.sleep(30)
else:
    state = json.loads(state_path.read_text())
    if state["marker"] != marker:
        raise SystemExit("marker mismatch")
    preview_path.write_text(json.dumps({{
        "blocked": False,
        "transaction_decision": "DRAFT_CREATED_VERIFICATION_PASSED",
        "effective_mode": "live-draft",
        "shopify_article_id": state["article_id"],
        "shopify_create_count": 1,
        "shopify_write_state": "article_observed",
        "shopify_idempotency_marker": marker,
        "reconciliation_status": "reconciled",
        "replay_disposition": "terminal",
        "queue_touched": False
    }}))
"""


def run_drill(
    *,
    artifact_root: Path,
    repo_root: Path,
    request_id: str,
    timeout_seconds: float = 0.1,
    require_network_none: bool = True,
) -> dict[str, Any]:
    """Execute the three-call timeout, reconcile, and cached-replay sequence."""
    _assert_credential_free()
    interfaces = _assert_network_none() if require_network_none else ["not-enforced"]

    artifact_root = artifact_root.resolve()
    artifact_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    artifact_root.chmod(0o700)

    with tempfile.TemporaryDirectory(prefix="orin-reconciliation-drill-") as raw_workdir:
        workdir = Path(raw_workdir)
        workspace_root = workdir / "workspace"
        workspace_root.mkdir(mode=0o700)
        remote_state_path = workdir / "simulated_remote_state.json"
        preview_path = workdir / "pipeline_preview.json"
        simulator_path = workdir / "timeout_then_reconcile.py"
        simulator_path.write_text(
            _simulator_source(state_path=remote_state_path, preview_path=preview_path),
            encoding="utf-8",
        )
        simulator_path.chmod(0o700)
        pipeline_command = [sys.executable, str(simulator_path)]

        common = {
            "client_id": "hoverboard_store",
            "request_id": request_id,
            "mode": "hidden-draft",
            "workspace_root": workspace_root,
            "artifact_root": artifact_root,
            "repo_root": repo_root,
            "pipeline_command": pipeline_command,
            "pipeline_preview_path": preview_path,
        }
        first = run_client(**common, pipeline_timeout_seconds=timeout_seconds)
        second = run_client(**common, pipeline_timeout_seconds=5)
        third = run_client(**common, pipeline_timeout_seconds=5)
        simulated_remote_state = json.loads(remote_state_path.read_text(encoding="utf-8"))

    expected_marker = f"orin-v1:hoverboard_store:{request_id}"
    checks = {
        "first_attempt_is_unknown_and_reconcilable": (
            first["attempt"] == 1
            and first["status"] == "failed"
            and first["error_code"] == ERROR_PIPELINE_TIMEOUT
            and first["shopify_write_state"] == "unknown"
            and first["reconciliation_status"] == "needs_review"
            and first["replay_disposition"] == "reconcile"
        ),
        "second_attempt_reconciles_one_unpublished_article": (
            second["attempt"] == 2
            and second["status"] == "completed"
            and second["replay_disposition"] == "terminal"
            and second["shopify_write_state"] == "article_observed"
            and second["reconciliation_status"] == "reconciled"
            and second["shopify_create_count"] == 1
            and second["shopify_published"] is False
            and second["queue_changed"] is False
            and second["shopify_idempotency_marker"] == expected_marker
        ),
        "third_call_is_cached_terminal_replay": third == second,
        "simulated_remote_has_exactly_one_create": (
            simulated_remote_state["mutation_count"] == 1
            and simulated_remote_state["published"] is False
            and simulated_remote_state["marker"] == expected_marker
        ),
    }
    summary = {
        "schema": "orin.partial-failure-reconciliation-drill/v1",
        "passed": all(checks.values()),
        "simulation_only": True,
        "network_interfaces": interfaces,
        "request_id": request_id,
        "checks": checks,
        "first_result": first,
        "reconciled_result": second,
        "cached_replay_result": third,
        "simulated_remote_state": simulated_remote_state,
    }
    summary_path = artifact_root / "partial_failure_reconciliation_drill.json"
    _write_private_json(summary_path, summary)
    summary["summary_path"] = str(summary_path)
    if not summary["passed"]:
        raise RuntimeError(f"partial-failure reconciliation drill failed; see {summary_path}")
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--request-id", default=None)
    parser.add_argument("--timeout-seconds", type=float, default=0.1)
    parser.add_argument(
        "--allow-host-network",
        action="store_true",
        help="Development-only override; production evidence must use network-none.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    request_id = args.request_id or str(uuid.uuid4())
    summary = run_drill(
        artifact_root=args.artifact_root,
        repo_root=args.repo_root.resolve(),
        request_id=request_id,
        timeout_seconds=args.timeout_seconds,
        require_network_none=not args.allow_host_network,
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
