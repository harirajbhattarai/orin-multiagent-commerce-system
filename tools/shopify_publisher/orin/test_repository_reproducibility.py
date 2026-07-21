"""Regression checks for a self-contained ORIN source checkout."""

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
        "cron_entrypoint.py",
        "orin_phase2c_writer_planning_dryrun.py",
    ):
        source = (AGENTS_DIR / filename).read_text(encoding="utf-8")
        assert 'Path("/data/.openclaw/workspace")' not in source
        assert "ORIN_WORKSPACE_ROOT" in source
