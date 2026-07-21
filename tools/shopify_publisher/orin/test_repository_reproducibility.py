"""Regression checks for a self-contained ORIN source checkout."""

import os
import subprocess
import sys
from pathlib import Path


AGENTS_DIR = Path(__file__).resolve().parent


def test_required_writer_planning_modules_are_tracked_source_files():
    for filename in (
        "orin_phase2c_writer_planning_dryrun.py",
        "hcs_phase2c_writer_planning_dryrun.py",
    ):
        assert (AGENTS_DIR / filename).is_file(), filename


def test_runtime_defaults_to_its_own_checkout_not_a_live_workspace():
    for filename in (
        "client_context.py",
        "cron_entrypoint.py",
        "duplicate_decision_agent.py",
        "hcs_cron_entrypoint.py",
        "hcs_phase1a_state_dryrun.py",
        "hcs_phase1b_planner_dryrun.py",
        "hcs_writer_adapter.py",
        "job_context.py",
        "orin_phase2a_post_write_review_dryrun.py",
        "orin_phase2c_writer_planning_dryrun.py",
        "orin_phase2d_writer_dryrun.py",
        "orin_phase2e_publisher_dryrun.py",
        "orin_phase2f_html_validation_dryrun.py",
        "publisher_agent.py",
        "review_agent.py",
        "shopify_draft_transaction.py",
        "state_agent.py",
        "workspace_paths.py",
        "writer_agent.py",
    ):
        source = (AGENTS_DIR / filename).read_text(encoding="utf-8")
        assert 'Path("/data/.openclaw/workspace")' not in source


def test_workspace_root_defaults_to_checkout_and_honours_override(tmp_path):
    script = "from workspace_paths import workspace_root; print(workspace_root())"
    default_result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=AGENTS_DIR,
        capture_output=True,
        text=True,
        check=True,
        env={k: v for k, v in os.environ.items() if k != "ORIN_WORKSPACE_ROOT"},
    )
    assert Path(default_result.stdout.strip()) == AGENTS_DIR.parents[2]

    override_result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=AGENTS_DIR,
        capture_output=True,
        text=True,
        check=True,
        env={**os.environ, "ORIN_WORKSPACE_ROOT": str(tmp_path)},
    )
    assert Path(override_result.stdout.strip()) == tmp_path.resolve()
