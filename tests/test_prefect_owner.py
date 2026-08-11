from datetime import UTC, datetime
from uuid import UUID

import pytest

from orin_prefect_owner import repository


class FakeCursor:
    def __init__(self, rows):
        self.rows = iter(rows)
        self.queries = []

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return None

    def execute(self, query):
        self.queries.append(query)

    def fetchone(self):
        return next(self.rows)


class FakeConnection:
    def __init__(self, cursor):
        self.value = cursor

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return None

    def cursor(self):
        return self.value


def test_owner_repository_uses_fixed_zero_argument_function(monkeypatch, tmp_path):
    secret = tmp_path / "owner_database_url"
    secret.write_text("postgresql://orin_prefect_scheduler:secret@example/db\n")
    cursor = FakeCursor(
        [
            ("orin_prefect_scheduler",),
            (
                UUID("11111111-1111-5111-8111-111111111111"),
                "hoverboard_store",
                UUID("22222222-2222-5222-8222-222222222222"),
                "dry-run",
                "queued",
                datetime(2026, 8, 11, tzinfo=UTC),
                datetime(2026, 8, 11, tzinfo=UTC),
                False,
            ),
        ]
    )
    monkeypatch.setattr(
        repository.psycopg,
        "connect",
        lambda url, autocommit: FakeConnection(cursor),
    )

    receipt = repository.OwnerRepository(
        secret, expected_role="orin_prefect_scheduler"
    ).enqueue()

    assert receipt.client_id == "hoverboard_store"
    assert receipt.requested_mode == "dry-run"
    assert receipt.replayed is False
    assert "enqueue_hoverboard_prefect_commissioning_job()" in cursor.queries[1]
    assert "%s" not in cursor.queries[1]
    assert receipt.as_json()["job_id"] == "11111111-1111-5111-8111-111111111111"


def test_owner_repository_rejects_the_wrong_database_role(monkeypatch, tmp_path):
    secret = tmp_path / "owner_database_url"
    secret.write_text("postgresql://wrong:secret@example/db\n")
    cursor = FakeCursor([("postgres",)])
    monkeypatch.setattr(
        repository.psycopg,
        "connect",
        lambda url, autocommit: FakeConnection(cursor),
    )

    with pytest.raises(RuntimeError, match="database role mismatch"):
        repository.OwnerRepository(
            secret, expected_role="orin_prefect_scheduler"
        ).enqueue()


def test_owner_repository_rejects_an_empty_secret(tmp_path):
    secret = tmp_path / "owner_database_url"
    secret.write_text("")

    with pytest.raises(RuntimeError, match="empty"):
        repository.OwnerRepository(
            secret, expected_role="orin_prefect_scheduler"
        ).enqueue()


def test_daily_owner_repository_uses_fixed_zero_argument_function(
    monkeypatch, tmp_path
):
    secret = tmp_path / "owner_database_url"
    secret.write_text("postgresql://orin_prefect_scheduler:secret@example/db\n")
    cursor = FakeCursor(
        [
            ("orin_prefect_scheduler",),
            (
                UUID("33333333-3333-5333-8333-333333333333"),
                "hoverboard_store",
                UUID("44444444-4444-5444-8444-444444444444"),
                "dry-run",
                "queued",
                datetime(2026, 8, 12, tzinfo=UTC),
                datetime(2026, 8, 12, tzinfo=UTC),
                False,
            ),
        ]
    )
    monkeypatch.setattr(
        repository.psycopg,
        "connect",
        lambda url, autocommit: FakeConnection(cursor),
    )

    receipt = repository.DailyOwnerRepository(
        secret, expected_role="orin_prefect_scheduler"
    ).enqueue()

    assert receipt.requested_mode == "dry-run"
    assert receipt.replayed is False
    assert "enqueue_hoverboard_prefect_scheduled_job()" in cursor.queries[1]
    assert "commissioning" not in cursor.queries[1]
    assert "%s" not in cursor.queries[1]
