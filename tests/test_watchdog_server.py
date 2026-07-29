from __future__ import annotations

import json
import os
import socket
import stat
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

import pytest

from orin_watchdog.models import WatchdogResult
from orin_watchdog.server import REQUEST_LINE, Settings, build_server


CLIENT_SCRIPT = Path(
    "deploy/openclaw/orin-watchdog/bin/orin_watchdog_check.py"
)


class FakeCapability:
    def __init__(self, *, fail: bool = False) -> None:
        self.calls = 0
        self.fail = fail

    def check(self) -> WatchdogResult:
        self.calls += 1
        if self.fail:
            raise RuntimeError("sensitive database detail")
        return WatchdogResult(
            status="healthy",
            code="ORIN_SCHEDULED_RUN_OBSERVED",
            client_id="hoverboard_store",
            source_job_key="scheduler:orin-hbstore-prod:2026-07-30",
            observed_at="2026-07-30T10:20:00+00:00",
            expected_at="2026-07-30T11:00:00+01:00",
            deadline_at="2026-07-30T11:15:00+01:00",
            job_id="11111111-1111-4111-8111-111111111111",
            run_id="hb_20260730T100001Z_abcdef12",
            job_status="completed",
            run_status="completed",
        )

    def close(self) -> None:
        return None


def request(socket_path: Path, payload: bytes) -> dict:
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.connect(str(socket_path))
        connection.sendall(payload)
        return json.loads(connection.makefile("rb").readline(8193))


def serve_once(server) -> threading.Thread:
    thread = threading.Thread(target=server.handle_request)
    thread.start()
    return thread


def test_socket_accepts_only_fixed_read_only_check():
    with tempfile.TemporaryDirectory(prefix="orin-watchdog-", dir="/tmp") as directory:
        socket_path = Path(directory) / "watchdog.sock"
        capability = FakeCapability()
        server = build_server(
            socket_path=socket_path,
            socket_directory_mode=0o710,
            socket_mode=0o620,
            allowed_peer_uid=os.getuid(),
            peer_uid_resolver=lambda _: os.getuid(),
            capability=capability,
        )
        try:
            assert stat.S_IMODE(socket_path.parent.stat().st_mode) == 0o710
            assert stat.S_IMODE(socket_path.stat().st_mode) == 0o620

            invalid_thread = serve_once(server)
            invalid = request(socket_path, b"CHECK another-client WATCHDOG V1\n")
            invalid_thread.join(timeout=2)
            assert invalid == {
                "schema": "orin.watchdog/v1",
                "status": "failed",
                "code": "ORIN_WATCHDOG_INVALID_REQUEST",
            }
            assert capability.calls == 0

            valid_thread = serve_once(server)
            healthy = request(socket_path, REQUEST_LINE)
            valid_thread.join(timeout=2)
            assert healthy["status"] == "healthy"
            assert healthy["client_id"] == "hoverboard_store"
            assert healthy["code"] == "ORIN_SCHEDULED_RUN_OBSERVED"
            assert capability.calls == 1
        finally:
            server.server_close()


def test_database_errors_are_redacted_and_fail_closed():
    with tempfile.TemporaryDirectory(prefix="orin-watchdog-", dir="/tmp") as directory:
        socket_path = Path(directory) / "watchdog.sock"
        server = build_server(
            socket_path=socket_path,
            socket_directory_mode=0o710,
            socket_mode=0o620,
            allowed_peer_uid=os.getuid(),
            peer_uid_resolver=lambda _: os.getuid(),
            capability=FakeCapability(fail=True),
        )
        try:
            thread = serve_once(server)
            response = request(socket_path, REQUEST_LINE)
            thread.join(timeout=2)
        finally:
            server.server_close()

        assert response == {
            "schema": "orin.watchdog/v1",
            "status": "failed",
            "code": "ORIN_WATCHDOG_CHECK_FAILED",
        }
        assert "sensitive" not in json.dumps(response)


def test_socket_rejects_unapproved_peer():
    with tempfile.TemporaryDirectory(prefix="orin-watchdog-", dir="/tmp") as directory:
        socket_path = Path(directory) / "watchdog.sock"
        capability = FakeCapability()
        server = build_server(
            socket_path=socket_path,
            socket_directory_mode=0o710,
            socket_mode=0o620,
            allowed_peer_uid=os.getuid() + 1,
            peer_uid_resolver=lambda _: os.getuid(),
            capability=capability,
        )
        try:
            thread = serve_once(server)
            response = request(socket_path, REQUEST_LINE)
            thread.join(timeout=2)
        finally:
            server.server_close()

        assert response["status"] == "failed"
        assert response["code"] == "ORIN_WATCHDOG_UNAUTHORIZED_PEER"
        assert capability.calls == 0


def test_settings_reject_ambiguous_database_sources(tmp_path):
    secret = tmp_path / "database-url"
    secret.write_text(
        "postgresql://orin_watchdog:secret@example.test/postgres\n",
        encoding="utf-8",
    )
    secret.chmod(0o400)

    with pytest.raises(ValueError, match="exactly one"):
        Settings(
            database_url="postgresql://orin_watchdog:secret@example.test/postgres",
            database_url_file=secret,
        )


def test_openclaw_client_refuses_arguments_before_socket_access():
    completed = subprocess.run(
        [sys.executable, str(CLIENT_SCRIPT), "hoverboard_store"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 2
    assert "accepts no arguments" in completed.stderr
