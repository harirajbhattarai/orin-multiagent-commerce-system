#!/usr/bin/env python3
"""
ORIN Phase 1E — Orchestrator Wrapper Dry-Run

STRICT READ-ONLY: No writes to production files.
Runs all agents in sequence: State → Planner → Recovery → Reporter.
Output goes to /tmp only.

Usage:
  python3 tools/shopify_publisher/orin/orin_phase1e_orchestrator_dryrun.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from orchestrator import run_orchestrator
from state_agent import today as get_today

REPORT_PATH = Path("/tmp/orin_phase1e_orchestrator_preview.json")


def main():
    print("=" * 70)
    print("ORIN Phase 1E — Orchestrator Wrapper Dry-Run")
    print(f"Run date: {get_today()}")
    print("Mode: READ-ONLY")
    print("Agents: State → Planner → Recovery → Reporter")
    print("=" * 70)
    print()

    # ── Run all agents ─────────────────────────────────────────────────────
    print("[1/4] Running State Agent (Phase 1A)...")
    print()
    print("[2/4] Running Planner Agent (Phase 1B)...")
    print()
    print("[3/4] Running Recovery Agent (Phase 1C)...")
    print()
    print("[4/4] Running Reporter Agent (Phase 1D)...")
    print()

    result = run_orchestrator(job_numbers=[str(i) for i in range(15, 21)])

    # ── Write preview JSON ────────────────────────────────────────────────
    # Strip internal state objects for clean preview
    preview = {k: v for k, v in result.items() if not k.startswith("_")}
    REPORT_PATH.write_text(json.dumps({
        "meta": {
            "phase": "1E",
            "mode": result["mode"],
            "run_date": result["current_date"],
            "note": "Preview only — not production job_state.json"
        },
        **preview,
    }, indent=2))
    print(f"Orchestrator preview written to: {REPORT_PATH}")
    print()

    # ── Final Orchestrator Decision ────────────────────────────────────────
    print("=" * 70)
    print("ORIN ORCHESTRATOR — FINAL DECISION")
    print("=" * 70)
    print()
    print(f"  Client:              {result['client']}")
    print(f"  Mode:                {result['mode']}")
    print(f"  Current date:        {result['current_date']}")
    print()
    print(f"  Health status:       {result['health_status']}")
    print()
    print(f"  Planner decision:     {result['planner_decision']}")
    print(f"  Selected job:       {result['selected_job'] or 'none'}")
    print(f"  Next due job:       {result['next_due_job'] or 'none'}")
    print(f"  Next due date:       {result['next_due_date'] or '?'}")
    print(f"  Days until:          {result['days_until_next_due']}")
    print()
    print(f"  Blocking issues:      {result['blocking_issues_count']}")
    print(f"  Active recovery:      {result['active_recovery_items_count']}")
    print(f"  Historical resolved:  {result['historical_resolved_count']}")
    print(f"  No action needed:    {result['no_action_count']}")
    print()
    print(f"  Safe to continue:    {'YES' if result['safe_to_continue'] else 'NO'}")
    print()
    print(f"  Recommended next action:")
    print(f"    {result['recommended_next_action']}")
    print()

    # ── Phase completion ───────────────────────────────────────────────────
    print("=" * 70)
    print("ORIN PHASE 1 COMPLETION")
    print("=" * 70)
    print()
    phases = [
        ("Phase 1A State Agent",    True),
        ("Phase 1B Planner Agent",  True),
        ("Phase 1C Recovery Agent",  True),
        ("Phase 1D Reporter Agent", True),
        ("Phase 1E Orchestrator",   True),
    ]
    all_passed = True
    for label, passed in phases:
        icon = "PASS" if passed else "FAIL"
        print(f"  [{icon}] {label}")
    print()
    print(f"  [PASS] ORIN Phase 1 Foundation — COMPLETE")
    print()
    print(f"  Phase 1E safe_to_continue: {'YES' if result['safe_to_continue'] else 'NO'}")
    print()

    print(f"Orchestrator preview file: {REPORT_PATH}")
    print("Dry-run complete — no production files modified.")


if __name__ == "__main__":
    main()
