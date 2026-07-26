"""Unix-socket server exposing one parameter-free HBStore trigger operation."""

from __future__ import annotations

import json
import os
import signal
import socket
import socketserver
import stat
import sys
import threading
from pathlib import Path
from typing import Protocol

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from orin_control.repository import create_database_engine
from orin_control.secrets import read_private_secret
from orin_scheduler_trigger.repository import ScheduledJob, SchedulerRepository


REQUEST_LINE = b"TRIGGER ORIN-HBSTORE V1\n"
RESPONSE_SCHEMA = "orin.scheduler-trigger/v1"


class TriggerCapability(Protocol):
    def trigger(self) -> ScheduledJob: ...


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ORIN_SCHEDULER_", extra="ignore")

    database_url: SecretStr | None = None
    database_url_file: Path | None = None
    database_role: str = "orin_scheduler"
    socket_path: Path = Path("/run/orin/orin-hbstore-trigger.sock")
    socket_mode: int = 0o600

    @model_validator(mode="after")
    def require_one_database_url_source(self) -> "Settings":
        if (self.database_url is None) == (self.database_url_file is None):
            raise ValueError(
                "configure exactly one of ORIN_SCHEDULER_DATABASE_URL "
                "or ORIN_SCHEDULER_DATABASE_URL_FILE"
            )
        return self

    def resolved_database_url(self) -> str:
        if self.database_url is not None:
            return self.database_url.get_secret_value()
        assert self.database_url_file is not None
        return read_private_secret(self.database_url_file, label="scheduler database URL")


def accepted_response(job: ScheduledJob) -> dict[str, object]:
    return {
        "schema": RESPONSE_SCHEMA,
        "status": "accepted",
        "client_id": job.client_id,
        "job_id": str(job.job_id),
        "request_id": str(job.request_id),
        "requested_mode": job.requested_mode,
        "job_status": job.job_status,
        "scheduled_for": job.scheduled_for.isoformat(),
        "created_at": job.created_at.isoformat(),
        "replayed": job.replayed,
    }


def blocked_response(error_code: str) -> dict[str, object]:
    return {
        "schema": RESPONSE_SCHEMA,
        "status": "blocked",
        "error_code": error_code,
    }


class TriggerHandler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        line = self.rfile.readline(128)
        if line != REQUEST_LINE:
            response = blocked_response("ORIN_TRIGGER_INVALID_REQUEST")
        else:
            try:
                response = accepted_response(self.server.capability.trigger())  # type: ignore[attr-defined]
            except Exception as exc:
                print(f"scheduler trigger blocked: {type(exc).__name__}", file=sys.stderr)
                response = blocked_response("ORIN_SCHEDULER_TRIGGER_BLOCKED")
        self.wfile.write(
            json.dumps(response, separators=(",", ":"), sort_keys=True).encode("utf-8")
            + b"\n"
        )


class TriggerServer(socketserver.UnixStreamServer):
    allow_reuse_address = False

    def __init__(self, socket_path: Path, capability: TriggerCapability) -> None:
        self.capability = capability
        super().__init__(str(socket_path), TriggerHandler)


def _prepare_socket_path(socket_path: Path) -> None:
    socket_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    socket_path.parent.chmod(0o700)
    try:
        metadata = socket_path.lstat()
    except FileNotFoundError:
        return
    if not stat.S_ISSOCK(metadata.st_mode):
        raise RuntimeError(f"refusing to replace non-socket path: {socket_path}")
    socket_path.unlink()


def build_server(
    *,
    socket_path: Path,
    socket_mode: int,
    capability: TriggerCapability,
) -> TriggerServer:
    if socket_mode & 0o077:
        raise ValueError("scheduler trigger socket may not grant group or other access")
    _prepare_socket_path(socket_path)
    server = TriggerServer(socket_path, capability)
    os.chmod(socket_path, socket_mode)
    return server


def main() -> int:
    settings = Settings()  # type: ignore[call-arg]
    engine = create_database_engine(settings.resolved_database_url(), pool_size=1)
    repository = SchedulerRepository(engine, expected_role=settings.database_role)
    repository.ping()
    server = build_server(
        socket_path=settings.socket_path,
        socket_mode=settings.socket_mode,
        capability=repository,
    )

    def stop(_: int, __: object) -> None:
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        server.serve_forever(poll_interval=0.5)
    finally:
        server.server_close()
        repository.close()
        try:
            if settings.socket_path.is_socket():
                settings.socket_path.unlink()
        except FileNotFoundError:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
