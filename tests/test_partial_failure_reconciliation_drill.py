import json
import uuid
from pathlib import Path

import pytest

from tools.shopify_publisher.orin.partial_failure_reconciliation_drill import (
    run_drill,
)


def test_partial_failure_drill_reconciles_and_caches_without_duplicate(tmp_path):
    artifact_root = tmp_path / "evidence"
    summary = run_drill(
        artifact_root=artifact_root,
        repo_root=Path.cwd(),
        request_id=str(uuid.uuid4()),
        timeout_seconds=0.05,
        require_network_none=False,
    )

    assert summary["passed"] is True
    assert all(summary["checks"].values())
    assert summary["first_result"]["replay_disposition"] == "reconcile"
    assert summary["reconciled_result"]["attempt"] == 2
    assert summary["cached_replay_result"] == summary["reconciled_result"]
    assert summary["simulated_remote_state"]["mutation_count"] == 1

    saved = json.loads(
        (artifact_root / "partial_failure_reconciliation_drill.json").read_text()
    )
    assert saved["passed"] is True
    assert saved["simulated_remote_state"]["published"] is False


def test_partial_failure_drill_refuses_shopify_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("HOVERBOARD_STORE_SHOPIFY_ACCESS_TOKEN", "must-not-be-used")

    with pytest.raises(RuntimeError, match="refuses to run"):
        run_drill(
            artifact_root=tmp_path / "evidence",
            repo_root=Path.cwd(),
            request_id=str(uuid.uuid4()),
            require_network_none=False,
        )
