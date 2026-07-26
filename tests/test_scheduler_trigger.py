import json
import socket
import stat
import subprocess
import sys
import tempfile
import threading
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest

from orin_scheduler_trigger.repository import ScheduledJob
from orin_scheduler_trigger.server import (
    REQUEST_LINE,
    Settings,
    build_server,
)


CLIENT_SCRIPT = Path(
    "deploy/openclaw/orin-hbstore-prod/bin/orin_hbstore_trigger.py"
)


class FakeCapability:
    def __init__(self, *, fail: bool = False) -> None:
        self.calls = 0
        self.fail = fail

    def trigger(self) -> ScheduledJob:
        self.calls += 1
        if self.fail:
            raise RuntimeError("sensitive database detail")
        return ScheduledJob(
            job_id=UUID("11111111-1111-4111-8111-111111111111"),
            client_id="hoverboard_store",
            request_id=UUID("22222222-2222-4222-8222-222222222222"),
            requested_mode="dry-run",
            job_status="queued",
            scheduled_for=datetime(2026, 7, 26, 11, tzinfo=UTC),
            created_at=datetime(2026, 7, 26, 11, tzinfo=UTC),
            replayed=False,
        )


def request(socket_path: Path, payload: bytes) -> dict:
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.connect(str(socket_path))
        connection.sendall(payload)
        connection.shutdown(socket.SHUT_WR)
        return json.loads(connection.makefile("rb").readline(8193))


def serve_once(server) -> threading.Thread:
    thread = threading.Thread(target=server.handle_request)
    thread.start()
    return thread


def test_socket_accepts_only_the_fixed_parameter_free_request():
    with tempfile.TemporaryDirectory(prefix="orin-trigger-", dir="/tmp") as directory:
        socket_path = Path(directory) / "trigger.sock"
        capability = FakeCapability()
        server = build_server(
            socket_path=socket_path,
            socket_mode=0o600,
            capability=capability,
        )
        try:
            assert stat.S_IMODE(socket_path.stat().st_mode) == 0o600

            invalid_thread = serve_once(server)
            invalid = request(socket_path, b"TRIGGER other-client hidden-draft\n")
            invalid_thread.join(timeout=2)
            assert invalid == {
                "schema": "orin.scheduler-trigger/v1",
                "status": "blocked",
                "error_code": "ORIN_TRIGGER_INVALID_REQUEST",
            }
            assert capability.calls == 0

            valid_thread = serve_once(server)
            accepted = request(socket_path, REQUEST_LINE)
            valid_thread.join(timeout=2)
            assert accepted["status"] == "accepted"
            assert accepted["client_id"] == "hoverboard_store"
            assert accepted["requested_mode"] == "dry-run"
            assert accepted["replayed"] is False
            assert capability.calls == 1
        finally:
            server.server_close()


def test_database_errors_are_redacted_and_fail_closed():
    with tempfile.TemporaryDirectory(prefix="orin-trigger-", dir="/tmp") as directory:
        socket_path = Path(directory) / "trigger.sock"
        server = build_server(
            socket_path=socket_path,
            socket_mode=0o600,
            capability=FakeCapability(fail=True),
        )
        try:
            thread = serve_once(server)
            response = request(socket_path, REQUEST_LINE)
            thread.join(timeout=2)
        finally:
            server.server_close()

        assert response == {
            "schema": "orin.scheduler-trigger/v1",
            "status": "blocked",
            "error_code": "ORIN_SCHEDULER_TRIGGER_BLOCKED",
        }
        assert "sensitive" not in json.dumps(response)


def test_settings_reject_ambiguous_database_sources(tmp_path):
    secret = tmp_path / "database-url"
    secret.write_text(
        "postgresql://orin_scheduler:secret@example.test/postgres\n",
        encoding="utf-8",
    )
    secret.chmod(0o400)

    with pytest.raises(ValueError, match="exactly one"):
        Settings(
            database_url="postgresql://orin_scheduler:secret@example.test/postgres",
            database_url_file=secret,
        )


def test_openclaw_client_refuses_arguments_before_socket_access():
    completed = subprocess.run(
        [sys.executable, str(CLIENT_SCRIPT), "hidden-draft"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 2
    assert "accepts no arguments" in completed.stderr
