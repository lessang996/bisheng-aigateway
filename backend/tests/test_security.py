import base64

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from starlette.requests import Request

from app.apis.deps import extract_token
from app.core.config import Settings, get_settings
from app.core.security import create_token, decode_token
from app.exceptions.errors import AuthenticationError
from app.utils.http_client import _safe_url
from app.utils.safety_guard import SafetyGuard, SafetyGuardError


@pytest.fixture(autouse=True)
def secure_jwt_settings(monkeypatch):
    secret = base64.b64encode(b"test-only-secret-with-at-least-32-bytes").decode()
    monkeypatch.setenv("JWT_ALGORITHM", "HS256")
    monkeypatch.setenv("JWT_SECRET_KEY", secret)
    monkeypatch.setenv("JWT_ISSUER", "bisheng-gateway")
    monkeypatch.setenv("JWT_AUDIENCE", "bisheng-client")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _request(*, authorization: str = "", query_string: bytes = b"") -> Request:
    headers = []
    if authorization:
        headers.append((b"authorization", authorization.encode()))
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": headers,
            "query_string": query_string,
        }
    )


def test_access_token_round_trip_validates_required_claims():
    token = create_token("42", "alice", "access")

    payload = decode_token(token, "access")

    assert payload["sub"] == "42"
    assert payload["type"] == "access"
    assert payload["iss"] == "bisheng-gateway"
    assert payload["aud"] == "bisheng-client"


def test_refresh_token_cannot_be_used_as_access_token():
    token = create_token("42", "alice", "refresh")

    with pytest.raises(AuthenticationError, match="Invalid token type"):
        decode_token(token, "access")


def test_rs256_uses_private_key_for_signing_and_public_key_for_verification(monkeypatch):
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    public_pem = private_key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    monkeypatch.setenv("JWT_ALGORITHM", "RS256")
    monkeypatch.setenv("JWT_PRIVATE_KEY", private_pem)
    monkeypatch.setenv("JWT_PUBLIC_KEY", public_pem)
    get_settings.cache_clear()

    token = create_token("42", "alice", "access")

    assert decode_token(token, "access")["sub"] == "42"


def test_hs256_rejects_missing_or_weak_secret(monkeypatch):
    monkeypatch.setenv("JWT_SECRET_KEY", "")
    get_settings.cache_clear()
    with pytest.raises(ValueError, match="JWT_SECRET_KEY is required"):
        create_token("42")

    monkeypatch.setenv("JWT_SECRET_KEY", base64.b64encode(b"too-short").decode())
    get_settings.cache_clear()
    with pytest.raises(ValueError, match="at least 32 bytes"):
        create_token("42")


def test_extract_token_only_accepts_bearer_header():
    assert extract_token(_request(authorization="Bearer header-token")) == "header-token"
    assert extract_token(_request(authorization="raw-token")) is None
    assert extract_token(_request(query_string=b"token=query-token")) is None


def test_safe_url_removes_query_parameters_and_fragment():
    assert _safe_url("https://example.test/path?appkey=secret#part") == (
        "https://example.test/path"
    )


@pytest.mark.asyncio
async def test_safety_guard_fails_closed_when_configuration_is_incomplete():
    settings = Settings(
        safety_filter_enabled=True,
        safety_base_url="",
        safety_appkey="",
        safety_secret_key="",
        safety_template_id="",
    )
    guard = SafetyGuard(settings)
    try:
        with pytest.raises(SafetyGuardError, match="配置不完整"):
            await guard.analyze_input("test")
    finally:
        await guard.client.aclose()
