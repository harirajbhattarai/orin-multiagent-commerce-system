"""Verify Supabase user JWTs without accepting secret or service-role tokens."""

from __future__ import annotations

from typing import Any, Protocol
from uuid import UUID

import jwt
from jwt import PyJWKClient
from jwt.exceptions import InvalidTokenError, PyJWKClientError

from orin_control.errors import AuthenticationError
from orin_control.models import Principal


class SigningKey(Protocol):
    key: Any


class SigningKeyClient(Protocol):
    def get_signing_key_from_jwt(self, token: str) -> SigningKey: ...


class SupabaseJwtVerifier:
    """Validate signature, issuer, audience, expiry, role, and subject."""

    def __init__(
        self,
        *,
        supabase_url: str,
        audience: str = "authenticated",
        algorithm: str = "ES256",
        signing_key_client: SigningKeyClient | None = None,
    ) -> None:
        base_url = supabase_url.rstrip("/")
        if not base_url.startswith("https://"):
            raise ValueError("Supabase URL must use HTTPS")
        self.issuer = f"{base_url}/auth/v1"
        self.audience = audience
        self.algorithm = algorithm
        self.signing_key_client = signing_key_client or PyJWKClient(
            f"{self.issuer}/.well-known/jwks.json",
            cache_keys=True,
            max_cached_keys=16,
            cache_jwk_set=True,
            lifespan=300,
            timeout=5,
        )

    def verify(self, token: str) -> Principal:
        try:
            header = jwt.get_unverified_header(token)
            if header.get("alg") != self.algorithm:
                raise AuthenticationError("unexpected JWT algorithm")
            signing_key = self.signing_key_client.get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=[self.algorithm],
                audience=self.audience,
                issuer=self.issuer,
                options={
                    "require": ["iss", "sub", "aud", "exp", "iat", "role"],
                },
            )
        except AuthenticationError:
            raise
        except (InvalidTokenError, PyJWKClientError, KeyError, TypeError, ValueError) as exc:
            raise AuthenticationError("invalid bearer token") from exc

        if claims.get("role") != "authenticated" or claims.get("is_anonymous") is True:
            raise AuthenticationError("a non-anonymous authenticated user token is required")
        try:
            user_id = UUID(str(claims["sub"]))
        except (KeyError, TypeError, ValueError) as exc:
            raise AuthenticationError("invalid JWT subject") from exc
        return Principal(user_id=user_id)
