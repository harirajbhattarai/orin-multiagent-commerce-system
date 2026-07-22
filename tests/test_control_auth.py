from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import UUID

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec

from orin_control.auth import SupabaseJwtVerifier
from orin_control.errors import AuthenticationError


ISSUER = "https://example.supabase.co/auth/v1"
USER_ID = UUID("11111111-1111-4111-8111-111111111111")


class StaticSigningKeyClient:
    def __init__(self, key: object) -> None:
        self.key = key

    def get_signing_key_from_jwt(self, _: str) -> SimpleNamespace:
        return SimpleNamespace(key=self.key)


@pytest.fixture
def signing_keys():
    private_key = ec.generate_private_key(ec.SECP256R1())
    return private_key, private_key.public_key()


def token(private_key: object, **overrides: object) -> str:
    now = datetime.now(timezone.utc)
    claims: dict[str, object] = {
        "iss": ISSUER,
        "sub": str(USER_ID),
        "aud": "authenticated",
        "exp": now + timedelta(minutes=5),
        "iat": now,
        "role": "authenticated",
        "is_anonymous": False,
    }
    claims.update(overrides)
    return jwt.encode(claims, private_key, algorithm="ES256", headers={"kid": "test-key"})


def verifier(public_key: object) -> SupabaseJwtVerifier:
    return SupabaseJwtVerifier(
        supabase_url="https://example.supabase.co",
        signing_key_client=StaticSigningKeyClient(public_key),
    )


def test_non_https_supabase_url_is_rejected(signing_keys):
    _, public_key = signing_keys

    with pytest.raises(ValueError, match="must use HTTPS"):
        SupabaseJwtVerifier(
            supabase_url="http://example.supabase.co",
            signing_key_client=StaticSigningKeyClient(public_key),
        )


def test_valid_supabase_user_token_is_accepted(signing_keys):
    private_key, public_key = signing_keys

    principal = verifier(public_key).verify(token(private_key))

    assert principal.user_id == USER_ID


@pytest.mark.parametrize(
    "claim_overrides",
    [
        {"aud": "anon"},
        {"iss": "https://attacker.invalid/auth/v1"},
        {"role": "service_role"},
        {"is_anonymous": True},
        {"sub": "not-a-uuid"},
    ],
)
def test_invalid_or_non_user_claims_are_rejected(signing_keys, claim_overrides):
    private_key, public_key = signing_keys

    with pytest.raises(AuthenticationError):
        verifier(public_key).verify(token(private_key, **claim_overrides))


def test_unexpected_signing_algorithm_is_rejected_before_key_use(signing_keys):
    _, public_key = signing_keys
    now = datetime.now(timezone.utc)
    encoded = jwt.encode(
        {
            "iss": ISSUER,
            "sub": str(USER_ID),
            "aud": "authenticated",
            "exp": now + timedelta(minutes=5),
            "iat": now,
            "role": "authenticated",
        },
        "not-a-real-secret-that-is-at-least-32-bytes",
        algorithm="HS256",
    )

    with pytest.raises(AuthenticationError, match="unexpected JWT algorithm"):
        verifier(public_key).verify(encoded)
