"""Fixed-input Unix-socket server for the read-only HBStore watchdog."""

from __future__ import annotations

import json
import os
import signal
import socket
import socketserver
import stat
import struct
import sys
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from orin_control.repository import create_database_engine
from orin_control.secrets import read_private_secret
from orin_watchdog.models import WatchdogResult
from orin_watchdog.repository import WatchdogRepository
from orin_watchdog.service import CLIENT_ID, evaluate, source_job_key


REQUEST_LINE = b"CHECK ORIN-HBSTORE WATCHDOG V1\n"
RESPONSE_SCHEMA = "orin.watchdog/v1"


class WatchdogCapability(Protocol):
    def check(self) -> WatchdogResult: ...

    def close(self) -> None: ...


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ORIN_WATCHDOG_", extra="ignore")

    database_url: SecretStr | None = None
    database_url_file: Path | None = None
    database_role: str = "orin_watchdog"
    socket_path: Path = Path("/run/orin/orin-hbstore-watchdog.sock")
    socket_directory_mode: int = 0o710
    socket_mode: int = 0o620
    allowed_peer_uid: int = 1000

    @model_validator(mode="after")
    def require_one_database_url_source(self) -> "Settings":
        if (self.database_url is None) == (self.database_url_file is None):
            raise ValueError(
                "configure exactly one of ORIN_WATCHDOG_DATABASE_URL "
                "or ORIN_WATCHDOG_DATABASE_URL_FILE"
            )
        return self

    def resolved_database_url(self) -> str:
        if self.database_url is not None:
            return self.database_url.get_secret_value()
        assert self.database_url_file is not None
        return read_private_secret(self.database_url_file, label="watchdog database URL")


class DatabaseWatchdog:
    def __init__(
        self,
        repository: WatchdogRepository,
        *,
        now_provider: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.repository = repository
        self.now_provider = now_provider

    def check(self) -> WatchdogResult:
        now = self.now_provider()
        snapshot = self.repository.snapshot(
            client_id=CLIENT_ID,
            source_job_key=source_job_key(now),
        )
        return evaluate(snapshot, now=now)

    def close(self) -> None:
        self.repository.close()


def result_response(result: WatchdogResult) -> dict[str, object]:
    return {"schema": RESPONSE_SCHEMA, **result.to_dict()}


def failed_response(error_code: str) -> dict[str, object]:
    return {
        "schema": RESPONSE_SCHEMA,
        "status": "failed",
        "code": error_code,
    }


class WatchdogHandler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        try:
            peer_uid = self.server.peer_uid_resolver(self.connection)  # type: ignore[attr-defined]
        except OSError:
            response = failed_response("ORIN_WATCHDOG_PEER_CREDENTIALS_UNAVAILABLE")
        else:
            if peer_uid != self.server.allowed_peer_uid:  # type: ignore[attr-defined]
                response = failed_response("ORIN_WATCHDOG_UNAUTHORIZED_PEER")
            else:
                response = self._handle_authorized_peer()
        encoded = (
            json.dumps(response, separators=(",", ":"), sort_keys=True).encode("utf-8")
            + b"\n"
        )
        print(encoded.decode("utf-8").rstrip(), flush=True)
        self.wfile.write(encoded)

    def _handle_authorized_peer(self) -> dict[str, object]:
        line = self.rfile.readline(128)
        if line != REQUEST_LINE:
            return failed_response("ORIN_WATCHDOG_INVALID_REQUEST")
        try:
            return result_response(self.server.capability.check())  # type: ignore[attr-defined]
        except Exception as exc:
            print(f"watchdog check failed: {type(exc).__name__}", file=sys.stderr)
            return failed_response("ORIN_WATCHDOG_CHECK_FAILED")


class WatchdogServer(socketserver.UnixStreamServer):
    allow_reuse_address = False

    def __init__(
        self,
        socket_path: Path,
        capability: WatchdogCapability,
        allowed_peer_uid: int,
        peer_uid_resolver: Callable[[socket.socket], int],
    ) -> None:
        self.capability = capability
        self.allowed_peer_uid = allowed_peer_uid
        self.peer_uid_resolver = peer_uid_resolver
        super().__init__(str(socket_path), WatchdogHandler)


def _connected_peer_uid(connection: socket.socket) -> int:
    if hasattr(socket, "SO_PEERCRED"):
        credentials = connection.getsockopt(
            socket.SOL_SOCKET,
            socket.SO_PEERCRED,
            struct.calcsize("3i"),
        )
        _, uid, _ = struct.unpack("3i", credentials)
        return uid
    if hasattr(connection, "getpeereid"):
        uid, _ = connection.getpeereid()  # type: ignore[attr-defined]
        return uid
    raise OSError("Unix peer credentials are unavailable")


def _prepare_socket_path(socket_path: Path, directory_mode: int) -> None:
    socket_path.parent.mkdir(parents=True, exist_ok=True, mode=directory_mode)
    os.chown(socket_path.parent, -1, os.getegid())
    socket_path.parent.chmod(directory_mode)
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
    socket_directory_mode: int,
    socket_mode: int,
    allowed_peer_uid: int,
    capability: WatchdogCapability,
    peer_uid_resolver: Callable[[socket.socket], int] = _connected_peer_uid,
) -> WatchdogServer:
    if socket_directory_mode != 0o710:
        raise ValueError("watchdog socket directory mode must be 0710")
    if socket_mode != 0o620:
        raise ValueError("watchdog socket mode must be 0620")
    if allowed_peer_uid < 1:
        raise ValueError("watchdog peer UID must be a non-root account")
    _prepare_socket_path(socket_path, socket_directory_mode)
    server = WatchdogServer(
        socket_path,
        capability,
        allowed_peer_uid,
        peer_uid_resolver,
    )
    os.chmod(socket_path, socket_mode)
    return server


def main() -> int:
    settings = Settings()  # type: ignore[call-arg]
    engine = create_database_engine(settings.resolved_database_url(), pool_size=1)
    repository = WatchdogRepository(engine, expected_role=settings.database_role)
    repository.ping()
    capability = DatabaseWatchdog(repository)
    server = build_server(
        socket_path=settings.socket_path,
        socket_directory_mode=settings.socket_directory_mode,
        socket_mode=settings.socket_mode,
        allowed_peer_uid=settings.allowed_peer_uid,
        capability=capability,
    )

    def stop(_: int, __: object) -> None:
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        server.serve_forever(poll_interval=0.5)
    finally:
        server.server_close()
        capability.close()
        try:
            if settings.socket_path.is_socket():
                settings.socket_path.unlink()
        except FileNotFoundError:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
