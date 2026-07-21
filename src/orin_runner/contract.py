"""Versioned final-result contract and stable runner error codes."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


SCHEMA_VERSION = "orin.final-result/v1"

ERROR_INVALID_REQUEST = "ORIN_INVALID_REQUEST"
ERROR_UNSUPPORTED_CLIENT = "ORIN_UNSUPPORTED_CLIENT"
ERROR_RUNNER_BUSY = "ORIN_RUNNER_BUSY"
ERROR_PIPELINE_BLOCKED = "ORIN_PIPELINE_BLOCKED"
ERROR_PIPELINE_EXIT_NONZERO = "ORIN_PIPELINE_EXIT_NONZERO"
ERROR_PIPELINE_TIMEOUT = "ORIN_PIPELINE_TIMEOUT"
ERROR_PIPELINE_START_FAILED = "ORIN_PIPELINE_START_FAILED"
ERROR_PIPELINE_RESULT_MISSING = "ORIN_PIPELINE_RESULT_MISSING"
ERROR_PIPELINE_RESULT_INVALID = "ORIN_PIPELINE_RESULT_INVALID"
ERROR_RUNNER_INTERNAL = "ORIN_RUNNER_INTERNAL"


@dataclass(frozen=True)
class FinalResult:
    schema: str
    run_id: str
    request_id: str
    client_id: str
    job_id: str | None
    attempt: int
    requested_mode: str
    effective_mode: str
    status: str
    decision: str
    code_version: str
    config_version: str | None
    idempotency_key: str
    shopify_article_id: str | None
    shopify_create_count: int
    shopify_published: bool
    queue_changed: bool
    reconciliation_status: str
    started_at: str
    finished_at: str
    artifact_uri: str
    error_code: str | None
    pipeline_exit_code: int | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
