"""FastAPI application factory for the restricted ORIN control plane."""

from __future__ import annotations

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from pathlib import Path as FilePath
from typing import Literal, Protocol

from fastapi import Depends, FastAPI, HTTPException, Path, Response, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import AnyHttpUrl, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from orin_control.auth import SupabaseJwtVerifier
from orin_control.errors import (
    AuthenticationError,
    ClientAccessDenied,
    InsufficientRole,
    RequestConflict,
    RequestIntakeDisabled,
)
from orin_control.models import Principal, RunRequest, RunRequestResult
from orin_control.repository import (
    JobRecord,
    PostgresRunRequestRepository,
    create_database_engine,
)
from orin_control.secrets import read_private_secret


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ORIN_", extra="ignore")

    database_url: SecretStr | None = None
    database_url_file: FilePath | None = None
    supabase_url: AnyHttpUrl
    jwt_audience: Literal["authenticated"] = "authenticated"
    jwt_algorithm: Literal["ES256"] = "ES256"
    db_pool_size: int = 1
    database_role: str = "orin_api"

    @model_validator(mode="after")
    def require_one_database_url_source(self) -> "Settings":
        if (self.database_url is None) == (self.database_url_file is None):
            raise ValueError("configure exactly one of ORIN_DATABASE_URL or ORIN_DATABASE_URL_FILE")
        return self

    def resolved_database_url(self) -> str:
        if self.database_url is not None:
            return self.database_url.get_secret_value()
        assert self.database_url_file is not None
        return read_private_secret(self.database_url_file, label="database URL")


class Verifier(Protocol):
    def verify(self, token: str) -> Principal: ...


class Repository(Protocol):
    def request_run(self, *, principal: Principal, client_id: str, request: RunRequest) -> JobRecord: ...
    def ping(self) -> None: ...
    def close(self) -> None: ...


def create_app(
    *,
    settings: Settings | None = None,
    repository: Repository | None = None,
    verifier: Verifier | None = None,
) -> FastAPI:
    owns_repository = repository is None
    if repository is None or verifier is None:
        settings = settings or Settings()  # type: ignore[call-arg]
    if repository is None:
        assert settings is not None
        repository = PostgresRunRequestRepository(
            create_database_engine(
                settings.resolved_database_url(),
                pool_size=settings.db_pool_size,
            ),
            expected_role=settings.database_role,
        )
    if verifier is None:
        assert settings is not None
        verifier = SupabaseJwtVerifier(
            supabase_url=str(settings.supabase_url),
            audience=settings.jwt_audience,
            algorithm=settings.jwt_algorithm,
        )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            if owns_repository:
                repository.close()

    app = FastAPI(
        title="ORIN Control API",
        version="0.1.0",
        lifespan=lifespan,
    )
    bearer = HTTPBearer(auto_error=False)

    def authenticated_principal(
        credentials: HTTPAuthorizationCredentials | None = Security(bearer),
    ) -> Principal:
        if credentials is None or credentials.scheme.lower() != "bearer":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="valid bearer token required",
                headers={"WWW-Authenticate": "Bearer"},
            )
        try:
            return verifier.verify(credentials.credentials)
        except AuthenticationError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="valid bearer token required",
                headers={"WWW-Authenticate": "Bearer"},
            ) from exc

    @app.get("/healthz", include_in_schema=False)
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz", include_in_schema=False)
    def ready() -> dict[str, str]:
        try:
            repository.ping()
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="database unavailable") from exc
        return {"status": "ready"}

    @app.post(
        "/v1/clients/{client_id}/run-requests",
        response_model=RunRequestResult,
        status_code=status.HTTP_201_CREATED,
    )
    def request_run(
        response: Response,
        request: RunRequest,
        client_id: str = Path(pattern=r"^[a-z0-9][a-z0-9_]{1,62}$"),
        principal: Principal = Depends(authenticated_principal),
    ) -> RunRequestResult:
        try:
            record = repository.request_run(
                principal=principal,
                client_id=client_id,
                request=request,
            )
        except ClientAccessDenied as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="client not found") from exc
        except InsufficientRole as exc:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="operator role required") from exc
        except RequestIntakeDisabled as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="client request intake is disabled") from exc
        except RequestConflict as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="request ID conflict") from exc

        if record.replayed:
            response.status_code = status.HTTP_200_OK
        return RunRequestResult(
            job_id=record.job_id,
            client_id=record.client_id,
            request_id=record.request_id,
            requested_mode=record.requested_mode,
            status=record.status,
            scheduled_for=record.scheduled_for,
            created_at=record.created_at,
            replayed=record.replayed,
        )

    return app
