"""Small server-only client for Supabase Storage and PostgREST."""

from __future__ import annotations

import hashlib
import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from orin_evidence_sync.service import Artifact, EvidenceSyncError


class SupabaseEvidenceApi:
    def __init__(self, *, project_url: str, service_key: str, timeout_seconds: float = 30) -> None:
        self.project_url = project_url.rstrip("/")
        self.service_key = service_key
        self.timeout_seconds = timeout_seconds
        if not self.project_url.startswith("https://"):
            raise ValueError("Supabase project URL must use HTTPS")
        if len(service_key) < 32 or "\n" in service_key or "\r" in service_key:
            raise ValueError("Supabase service key is invalid")

    def _request(
        self,
        method: str,
        path: str,
        *,
        body: bytes | None = None,
        content_type: str = "application/json",
        prefer: str | None = None,
    ) -> tuple[int, bytes]:
        headers = {
            "apikey": self.service_key,
            "Authorization": f"Bearer {self.service_key}",
            "Content-Type": content_type,
        }
        if prefer:
            headers["Prefer"] = prefer
        request = Request(
            f"{self.project_url}{path}",
            data=body,
            headers=headers,
            method=method,
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                return response.status, response.read()
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            raise EvidenceSyncError(f"Supabase API returned {exc.code}: {detail}") from exc
        except (URLError, TimeoutError) as exc:
            raise EvidenceSyncError("Supabase API request failed") from exc

    def _json(self, method: str, path: str, **kwargs: Any) -> tuple[int, Any]:
        status, raw = self._request(method, path, **kwargs)
        try:
            value = json.loads(raw or b"null")
        except json.JSONDecodeError as exc:
            raise EvidenceSyncError("Supabase API returned invalid JSON") from exc
        return status, value

    def assert_run(self, *, client_id: str, run_id: str) -> None:
        query = urlencode(
            {
                "client_id": f"eq.{client_id}",
                "run_id": f"eq.{run_id}",
                "select": "run_id,status",
            }
        )
        _, value = self._json("GET", f"/rest/v1/runs?{query}")
        if not isinstance(value, list) or len(value) != 1:
            raise EvidenceSyncError("durable run record was not found")
        if value[0].get("status") not in {"completed", "blocked", "failed"}:
            raise EvidenceSyncError("durable run record is not terminal")

    def _download(self, object_path: str) -> bytes:
        _, raw = self._request(
            "GET",
            f"/storage/v1/object/orin-evidence/{quote(object_path, safe='/')}",
            content_type="application/octet-stream",
        )
        return raw

    def upload_immutable(self, artifact: Artifact) -> bool:
        payload = artifact.local_path.read_bytes()
        path = f"/storage/v1/object/orin-evidence/{quote(artifact.object_path, safe='/')}"
        try:
            self._request("POST", path, body=payload, content_type=artifact.mime_type)
            return True
        except EvidenceSyncError as exc:
            # Storage uses conflict responses for an existing object. Never
            # overwrite it: accept only byte-for-byte replay.
            if "returned 400" not in str(exc) and "returned 409" not in str(exc):
                raise
        existing = self._download(artifact.object_path)
        if hashlib.sha256(existing).hexdigest() != artifact.sha256:
            raise EvidenceSyncError(f"remote artifact conflicts: {artifact.object_path}")
        return False

    def register_artifact(self, artifact: Artifact) -> bool:
        body = json.dumps(artifact.database_record(), separators=(",", ":")).encode("utf-8")
        _, value = self._json(
            "POST",
            "/rest/v1/run_artifacts?on_conflict=object_path",
            body=body,
            prefer="resolution=ignore-duplicates,return=representation",
        )
        if isinstance(value, list) and len(value) == 1:
            return True

        query = urlencode(
            {
                "object_path": f"eq.{artifact.object_path}",
                "select": "client_id,run_id,kind,object_path,mime_type,byte_count,sha256",
            }
        )
        _, existing = self._json("GET", f"/rest/v1/run_artifacts?{query}")
        expected = artifact.database_record()
        if not isinstance(existing, list) or len(existing) != 1:
            raise EvidenceSyncError("artifact metadata was not registered")
        if any(existing[0].get(key) != expected[key] for key in expected):
            raise EvidenceSyncError(f"artifact metadata conflicts: {artifact.object_path}")
        return False
