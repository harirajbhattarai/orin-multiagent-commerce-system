from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from orin_control.app import Settings, create_app
from orin_control.errors import (
    AuthenticationError,
    ClientAccessDenied,
    InsufficientRole,
    RequestConflict,
    RequestIntakeDisabled,
)
from orin_control.models import Principal, RunRequest
from orin_control.repository import JobRecord, PostgresRunRequestRepository, normalize_database_url


USER_ID = UUID("11111111-1111-4111-8111-111111111111")
REQUEST_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
JOB_ID = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")


class FakeVerifier:
    def verify(self, token: str) -> Principal:
        if token != "valid-user-token":
            raise AuthenticationError("invalid")
        return Principal(user_id=USER_ID)


class FakeRepository:
    def __init__(self) -> None:
        self.error: Exception | None = None
        self.replayed = False
        self.calls: list[tuple[Principal, str, RunRequest]] = []
        self.ready = True

    def request_run(self, *, principal: Principal, client_id: str, request: RunRequest) -> JobRecord:
        self.calls.append((principal, client_id, request))
        if self.error is not None:
            raise self.error
        now = datetime.now(timezone.utc)
        return JobRecord(
            job_id=JOB_ID,
            client_id=client_id,
            request_id=request.request_id,
            requested_mode="dry-run",
            status="queued",
            scheduled_for=now,
            created_at=now,
            replayed=self.replayed,
        )

    def ping(self) -> None:
        if not self.ready:
            raise RuntimeError("offline")

    def close(self) -> None:
        pass


@pytest.fixture
def api():
    repository = FakeRepository()
    app = create_app(repository=repository, verifier=FakeVerifier())
    with TestClient(app) as client:
        yield client, repository


def headers(token: str = "valid-user-token") -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_health_and_database_readiness_are_separate(api):
    client, repository = api

    assert client.get("/healthz").json() == {"status": "ok"}
    assert client.get("/readyz").json() == {"status": "ready"}

    repository.ready = False
    assert client.get("/readyz").status_code == 503
    assert client.get("/healthz").status_code == 200


def test_missing_or_invalid_bearer_token_fails_closed(api):
    client, repository = api
    path = "/v1/clients/hoverboard_store/run-requests"
    body = {"request_id": str(REQUEST_ID), "mode": "dry-run"}

    missing = client.post(path, json=body)
    invalid = client.post(path, json=body, headers=headers("invalid"))

    assert missing.status_code == 401
    assert invalid.status_code == 401
    assert missing.headers["www-authenticate"] == "Bearer"
    assert repository.calls == []


def test_new_request_returns_201_and_tenant_scoped_job(api):
    client, repository = api

    response = client.post(
        "/v1/clients/hoverboard_store/run-requests",
        json={"request_id": str(REQUEST_ID), "mode": "dry-run"},
        headers=headers(),
    )

    assert response.status_code == 201
    assert response.json()["job_id"] == str(JOB_ID)
    assert response.json()["client_id"] == "hoverboard_store"
    assert response.json()["request_id"] == str(REQUEST_ID)
    assert response.json()["replayed"] is False
    principal, client_id, request = repository.calls[0]
    assert principal.user_id == USER_ID
    assert client_id == "hoverboard_store"
    assert request.mode == "dry-run"


def test_idempotent_replay_returns_200(api):
    client, repository = api
    repository.replayed = True

    response = client.post(
        "/v1/clients/hoverboard_store/run-requests",
        json={"request_id": str(REQUEST_ID)},
        headers=headers(),
    )

    assert response.status_code == 200
    assert response.json()["replayed"] is True


@pytest.mark.parametrize(
    ("error", "expected_status", "expected_detail"),
    [
        (ClientAccessDenied("denied"), 404, "client not found"),
        (InsufficientRole("viewer"), 403, "operator role required"),
        (RequestIntakeDisabled("maintenance"), 409, "client request intake is disabled"),
        (RequestConflict("different input"), 409, "request ID conflict"),
    ],
)
def test_expected_repository_failures_have_stable_safe_responses(
    api, error, expected_status, expected_detail
):
    client, repository = api
    repository.error = error

    response = client.post(
        "/v1/clients/hoverboard_store/run-requests",
        json={"request_id": str(REQUEST_ID)},
        headers=headers(),
    )

    assert response.status_code == expected_status
    assert response.json() == {"detail": expected_detail}


def test_hidden_draft_and_extra_fields_are_not_in_the_api_contract(api):
    client, repository = api
    path = "/v1/clients/hoverboard_store/run-requests"

    hidden_draft = client.post(
        path,
        json={"request_id": str(REQUEST_ID), "mode": "hidden-draft"},
        headers=headers(),
    )
    extra_payload = client.post(
        path,
        json={"request_id": str(REQUEST_ID), "payload": {"command": "anything"}},
        headers=headers(),
    )

    assert hidden_draft.status_code == 422
    assert extra_payload.status_code == 422
    assert repository.calls == []


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("postgres://user:pass@example/db", "postgresql+psycopg://user:pass@example/db"),
        ("postgresql://user:pass@example/db", "postgresql+psycopg://user:pass@example/db"),
        ("postgresql+psycopg://user:pass@example/db", "postgresql+psycopg://user:pass@example/db"),
    ],
)
def test_database_url_normalization_uses_psycopg3(value, expected):
    assert normalize_database_url(value) == expected


def test_non_postgresql_database_url_is_rejected():
    with pytest.raises(ValueError):
        normalize_database_url("sqlite:///unsafe.db")


def test_control_api_reads_database_url_from_private_file(tmp_path):
    secret = tmp_path / "database_url"
    secret.write_text("postgresql://orin_api:secret@example.test/postgres\n")
    secret.chmod(0o400)
    settings = Settings(
        database_url_file=secret,
        supabase_url="https://example.supabase.co",
    )

    assert settings.resolved_database_url() == "postgresql://orin_api:secret@example.test/postgres"


def test_control_api_rejects_ambiguous_or_overexposed_secret_sources(tmp_path):
    secret = tmp_path / "database_url"
    secret.write_text("postgresql://orin_api:secret@example.test/postgres\n")
    secret.chmod(0o644)

    with pytest.raises(ValueError, match="exactly one"):
        Settings(
            database_url="postgresql://orin_api:secret@example.test/postgres",
            database_url_file=secret,
            supabase_url="https://example.supabase.co",
        )
    settings = Settings(
        database_url_file=secret,
        supabase_url="https://example.supabase.co",
    )
    with pytest.raises(ValueError, match="group or others"):
        settings.resolved_database_url()


def test_control_api_rejects_a_symlinked_secret_file(tmp_path):
    target = tmp_path / "database_url_target"
    target.write_text("postgresql://orin_api:secret@example.test/postgres\n")
    target.chmod(0o400)
    link = tmp_path / "database_url"
    link.symlink_to(target)
    settings = Settings(
        database_url_file=link,
        supabase_url="https://example.supabase.co",
    )

    with pytest.raises(ValueError, match="symbolic link"):
        settings.resolved_database_url()


class ScalarResult:
    def __init__(self, value: object) -> None:
        self.value = value

    def scalar_one(self) -> object:
        return self.value

    def first(self) -> object:
        return self.value


class RoleConnection:
    def __init__(self, role: str) -> None:
        self.role = role

    def __enter__(self):
        return self

    def __exit__(self, *_: object) -> None:
        pass

    def execute(self, statement: object) -> ScalarResult:
        if str(statement) == "select current_user":
            return ScalarResult(self.role)
        return ScalarResult(1)


class RoleEngine:
    def __init__(self, role: str) -> None:
        self.connection = RoleConnection(role)

    def connect(self) -> RoleConnection:
        return self.connection

    def begin(self) -> RoleConnection:
        return self.connection

    def dispose(self) -> None:
        pass


def test_repository_readiness_rejects_an_overprivileged_database_role():
    repository = PostgresRunRequestRepository(RoleEngine("postgres"))  # type: ignore[arg-type]

    with pytest.raises(RuntimeError, match="required=orin_api, received=postgres"):
        repository.ping()


def test_repository_readiness_accepts_only_the_narrow_api_role():
    repository = PostgresRunRequestRepository(RoleEngine("orin_api"))  # type: ignore[arg-type]

    repository.ping()


class AuthorizationConnection(RoleConnection):
    def __init__(self, *, access_row: object | None, existing_row: object | None) -> None:
        super().__init__("orin_api")
        self.access_row = access_row
        self.existing_row = existing_row
        self.job_lookup_attempted = False

    def execute(self, statement: object) -> ScalarResult:
        sql = str(statement)
        if sql == "select current_user":
            return ScalarResult("orin_api")
        if "FROM public.clients JOIN public.client_members" in sql:
            return ScalarResult(self.access_row)
        if "FROM public.content_jobs" in sql:
            self.job_lookup_attempted = True
            return ScalarResult(self.existing_row)
        raise AssertionError(f"unexpected SQL: {sql}")


class AuthorizationEngine(RoleEngine):
    def __init__(self, connection: AuthorizationConnection) -> None:
        self.connection = connection


def test_repository_authorizes_tenant_before_existing_request_lookup():
    connection = AuthorizationConnection(access_row=None, existing_row=object())
    repository = PostgresRunRequestRepository(AuthorizationEngine(connection))  # type: ignore[arg-type]

    with pytest.raises(ClientAccessDenied):
        repository.request_run(
            principal=Principal(user_id=USER_ID),
            client_id="hoverboard_store",
            request=RunRequest(request_id=REQUEST_ID),
        )

    assert connection.job_lookup_attempted is False


def test_authorized_replay_survives_a_later_maintenance_gate():
    now = datetime.now(timezone.utc)
    access = SimpleNamespace(
        role="operator",
        client_status="maintenance",
        request_intake_enabled=False,
        allowed_mode="dry-run",
    )
    existing = SimpleNamespace(
        _mapping={
            "job_id": JOB_ID,
            "client_id": "hoverboard_store",
            "request_id": REQUEST_ID,
            "requested_mode": "dry-run",
            "status": "queued",
            "scheduled_for": now,
            "created_at": now,
            "source_job_key": f"api:{REQUEST_ID}",
        }
    )
    connection = AuthorizationConnection(access_row=access, existing_row=existing)
    repository = PostgresRunRequestRepository(AuthorizationEngine(connection))  # type: ignore[arg-type]

    result = repository.request_run(
        principal=Principal(user_id=USER_ID),
        client_id="hoverboard_store",
        request=RunRequest(request_id=REQUEST_ID),
    )

    assert result.replayed is True
    assert result.job_id == JOB_ID
