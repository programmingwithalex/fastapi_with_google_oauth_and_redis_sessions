import os

import pytest
import redis
import requests
from fastapi import status
from fastapi.testclient import TestClient
from requests.exceptions import RequestException, Timeout

from src.auth import app


@pytest.fixture(autouse=True)
def setup_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Set required environment variables for the auth service.
    """

    env = {
        "REDIS_HOST": os.getenv("REDIS_HOST", "localhost"),
        "REDIS_PORT": os.getenv("REDIS_PORT", "6379"),
        "REDIS_DB": os.getenv("REDIS_DB", "0"),
        "REDIS_SSL": os.getenv("REDIS_SSL", "false"),
        "SESSION_EXPIRE_TIME_SECONDS": os.getenv("SESSION_EXPIRE_TIME_SECONDS", "3600"),
    }
    for key, val in env.items():
        monkeypatch.setenv(key, val)


@pytest.fixture
def client() -> TestClient:
    """Provide a TestClient for the FastAPI app."""
    return TestClient(app.app)


@pytest.mark.parametrize(
    "exception, status_code",
    [
        (Timeout(), status.HTTP_504_GATEWAY_TIMEOUT),
        (RequestException("error"), status.HTTP_502_BAD_GATEWAY),
    ],
)
def test_auth_google_token_errors(
    monkeypatch: pytest.MonkeyPatch, client: TestClient, exception: Exception, status_code: int
) -> None:
    """Errors during token exchange map to appropriate HTTPException codes."""
    monkeypatch.setattr(requests, "post", lambda *args, **kwargs: (_ for _ in ()).throw(exception))
    resp = client.get("/auth/google?code=badcode")
    assert resp.status_code == status_code


def test_auth_google_no_token(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Missing access_token in token response returns 502."""

    class TokenResp:
        """Simulate a token response with no access_token."""

        def raise_for_status(self) -> None:
            """Simulate a successful response."""

        def json(self) -> dict:
            """Simulate a response with no access_token."""
            return {}

    monkeypatch.setattr(requests, "post", lambda *args, **kwargs: TokenResp())
    resp = client.get("/auth/google?code=none")
    assert resp.status_code == status.HTTP_502_BAD_GATEWAY


@pytest.mark.parametrize(
    "exception, status_code",
    [
        (Timeout(), status.HTTP_504_GATEWAY_TIMEOUT),
        (RequestException("error"), status.HTTP_502_BAD_GATEWAY),
    ],
)
def test_auth_google_userinfo_errors(
    monkeypatch: pytest.MonkeyPatch, client: TestClient, exception: Exception, status_code: int
) -> None:
    """Errors during user-info fetch map to appropriate HTTPException codes."""

    class TokenResp:
        """Simulate a token response with no access_token."""

        def raise_for_status(self) -> None:
            """Simulate a successful response."""

        def json(self) -> dict:
            """Simulate a response with an access_token."""
            return {"access_token": "tok"}

    monkeypatch.setattr(requests, "post", lambda *args, **kwargs: TokenResp())
    monkeypatch.setattr(requests, "get", lambda *args, **kwargs: (_ for _ in ()).throw(exception))
    resp = client.get("/auth/google?code=abc")
    assert resp.status_code == status_code


def test_verify_missing_session(client: TestClient) -> None:
    """Missing session_id in /verify returns 400."""
    resp = client.post("/verify", json={})
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    assert resp.json()["detail"] == "Missing session_id"


def test_verify_redis_error(monkeypatch: pytest.MonkeyPatch, client: TestClient) -> None:
    """Redis errors during /verify return 500."""
    monkeypatch.setattr(app.redis_session_store, "get", lambda k: (_ for _ in ()).throw(redis.RedisError("fail")))
    resp = client.post("/verify", json={"session_id": "x"})
    assert resp.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


def test_verify_invalid_session(monkeypatch: pytest.MonkeyPatch, client: TestClient) -> None:
    """Invalid session_id returns 401."""
    monkeypatch.setattr(app.redis_session_store, "get", lambda k: None)
    resp = client.post("/verify", json={"session_id": "x"})
    assert resp.status_code == status.HTTP_401_UNAUTHORIZED


def test_verify_success(monkeypatch: pytest.MonkeyPatch, client: TestClient) -> None:
    """Valid session_id returns 200 and user payload."""
    monkeypatch.setattr(app.redis_session_store, "get", lambda k: b"userdata")
    resp = client.post("/verify", json={"session_id": "x"})
    assert resp.status_code == status.HTTP_200_OK
    assert resp.json() == {"user": "userdata"}


def test_logout_missing_session(client: TestClient) -> None:
    """Missing session_id in /logout returns 400."""
    resp = client.post("/logout", json={})
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    assert resp.json()["detail"] == "Missing session_id"


def test_logout_redis_error(monkeypatch: pytest.MonkeyPatch, client: TestClient) -> None:
    """Redis errors during /logout return 500."""
    monkeypatch.setattr(app.redis_session_store, "delete", lambda k: (_ for _ in ()).throw(redis.RedisError("fail")))
    resp = client.post("/logout", json={"session_id": "x"})
    assert resp.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


def test_logout_success(monkeypatch: pytest.MonkeyPatch, client: TestClient) -> None:
    """Valid logout returns 200 and confirms deletion."""
    called: dict = {}

    def fake_delete(key: str) -> None:
        called['k'] = key

    monkeypatch.setattr(app.redis_session_store, "delete", fake_delete)
    resp = client.post("/logout", json={"session_id": "x"})
    assert resp.status_code == status.HTTP_200_OK
    assert resp.json() == {"message": "Logged out"}
    assert called['k'] == "session:x"
