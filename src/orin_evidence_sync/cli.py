"""Command-line entry point for one-shot evidence synchronization."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from orin_control.secrets import read_private_secret
from orin_evidence_sync.api import SupabaseEvidenceApi
from orin_evidence_sync.service import EvidenceSyncError, sync_run


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Sync immutable ORIN evidence to Supabase")
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--run-id")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def _run_directories(root: Path, run_id: str | None) -> list[Path]:
    root = root.resolve()
    if not root.is_dir() or root.is_symlink():
        raise EvidenceSyncError("artifact root must be a regular directory")
    if run_id:
        candidate = (root / run_id).resolve()
        if candidate.parent != root:
            raise EvidenceSyncError("run_id escapes the artifact root")
        return [candidate]
    return sorted(
        path for path in root.iterdir()
        if path.is_dir() and not path.is_symlink() and (path / "final_result.json").is_file()
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        directories = _run_directories(args.artifact_root, args.run_id)
        if args.dry_run:
            api = None
        else:
            project_url = os.environ.get("ORIN_SUPABASE_URL", "")
            secret_path = os.environ.get("ORIN_EVIDENCE_SERVICE_KEY_FILE", "")
            if not project_url or not secret_path:
                raise EvidenceSyncError("evidence sync credentials are not configured")
            service_key = read_private_secret(
                Path(secret_path), label="evidence service key"
            )
            api = SupabaseEvidenceApi(project_url=project_url, service_key=service_key)

        results = [
            sync_run(api, directory, dry_run=args.dry_run)  # type: ignore[arg-type]
            for directory in directories
        ]
    except (OSError, ValueError, EvidenceSyncError) as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, sort_keys=True))
        return 1

    print(
        json.dumps(
            {
                "status": "validated" if args.dry_run else "completed",
                "run_count": len(results),
                "results": results,
            },
            sort_keys=True,
        )
    )
    return 0
