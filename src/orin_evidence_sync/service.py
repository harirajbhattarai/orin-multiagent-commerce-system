"""Upload immutable local run evidence to private Supabase Storage."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Protocol


CLIENT_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_]{1,62}$")
RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{5,127}$")
SUPPORTED_FILES = {
    "final_result.json": ("final_result", "application/json"),
    "events.jsonl": ("events", "application/x-ndjson"),
    "stdout.log": ("stdout", "text/plain"),
    "stderr.log": ("stderr", "text/plain"),
    "pipeline_preview.json": ("pipeline_preview", "application/json"),
    "content_plan_snapshot.json": ("other", "application/json"),
    "content_queue_projection.md": ("other", "text/plain"),
}


class EvidenceSyncError(RuntimeError):
    """Raised when local or remote evidence violates the sync contract."""


@dataclass(frozen=True)
class Artifact:
    client_id: str
    run_id: str
    kind: str
    object_path: str
    mime_type: str
    byte_count: int
    sha256: str
    local_path: Path

    def database_record(self) -> dict[str, Any]:
        record = asdict(self)
        record.pop("local_path")
        return record


class EvidenceApi(Protocol):
    def assert_run(self, *, client_id: str, run_id: str) -> None: ...
    def upload_immutable(self, artifact: Artifact) -> bool: ...
    def register_artifact(self, artifact: Artifact) -> bool: ...


def _load_final_result(run_dir: Path) -> dict[str, Any]:
    final_path = run_dir / "final_result.json"
    if not final_path.is_file() or final_path.is_symlink():
        raise EvidenceSyncError(f"regular final_result.json is required: {run_dir.name}")
    try:
        value = json.loads(final_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EvidenceSyncError(f"invalid final_result.json: {run_dir.name}") from exc
    if not isinstance(value, dict) or value.get("schema") != "orin.final-result/v2":
        raise EvidenceSyncError(f"unsupported final-result contract: {run_dir.name}")
    if value.get("status") not in {"completed", "blocked", "failed"}:
        raise EvidenceSyncError(f"run is not terminal: {run_dir.name}")
    return value


def build_artifacts(run_dir: Path) -> list[Artifact]:
    run_dir = run_dir.resolve()
    if not run_dir.is_dir() or run_dir.is_symlink():
        raise EvidenceSyncError("run directory must be a regular directory")
    result = _load_final_result(run_dir)
    client_id = result.get("client_id")
    run_id = result.get("run_id")
    if not isinstance(client_id, str) or not CLIENT_ID_PATTERN.fullmatch(client_id):
        raise EvidenceSyncError("final result has an invalid client_id")
    if not isinstance(run_id, str) or not RUN_ID_PATTERN.fullmatch(run_id):
        raise EvidenceSyncError("final result has an invalid run_id")
    if run_dir.name != run_id:
        raise EvidenceSyncError("run directory does not match final-result run_id")

    artifacts: list[Artifact] = []
    for filename, (kind, mime_type) in SUPPORTED_FILES.items():
        path = run_dir / filename
        if not path.exists():
            continue
        if not path.is_file() or path.is_symlink() or path.parent != run_dir:
            raise EvidenceSyncError(f"unsafe evidence file: {filename}")
        payload = path.read_bytes()
        artifacts.append(
            Artifact(
                client_id=client_id,
                run_id=run_id,
                kind=kind,
                object_path=f"{client_id}/{run_id}/{filename}",
                mime_type=mime_type,
                byte_count=len(payload),
                sha256=hashlib.sha256(payload).hexdigest(),
                local_path=path,
            )
        )
    if not any(item.kind == "final_result" for item in artifacts):
        raise EvidenceSyncError("final_result artifact is missing")
    return artifacts


def sync_run(api: EvidenceApi, run_dir: Path, *, dry_run: bool = False) -> dict[str, Any]:
    artifacts = build_artifacts(run_dir)
    first = artifacts[0]
    if not dry_run:
        api.assert_run(client_id=first.client_id, run_id=first.run_id)

    uploaded = 0
    replayed = 0
    registered = 0
    for artifact in artifacts:
        if dry_run:
            continue
        if api.upload_immutable(artifact):
            uploaded += 1
        else:
            replayed += 1
        if api.register_artifact(artifact):
            registered += 1

    return {
        "status": "validated" if dry_run else "completed",
        "client_id": first.client_id,
        "run_id": first.run_id,
        "artifact_count": len(artifacts),
        "uploaded_count": uploaded,
        "replayed_count": replayed,
        "registered_count": registered,
        "dry_run": dry_run,
    }
