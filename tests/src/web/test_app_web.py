import os
from typing import Any, Generator

import pytest
import requests_mock
from _pytest.monkeypatch import MonkeyPatch
from flask.testing import FlaskClient
from requests_mock.mocker import Mocker

import src.web.app as web_app_module


@pytest.fixture(autouse=True)
def configure_env(monkeypatch: MonkeyPatch) -> None:
    """
    Override AUTH_SERVICE_URL at both env and module level, enable TESTING.
    """
    test_url = "http://auth:8000"
    monkeypatch.setenv("AUTH_SERVICE_URL", test_url)
    web_app_module.AUTH_SERVICE_URL = test_url
    web_app_module.app.config["TESTING"] = True


@pytest.fixture
def client() -> Generator[FlaskClient, None, None]:
    """Create a Flask test client for web_app."""
    with web_app_module.app.test_client() as c:
        yield c


@pytest.fixture
def mock_api() -> Any:
    """mock_api fixture to mock external API calls."""
    with requests_mock.Mocker() as m:
        yield m


def test_login_renders_auth_url(mock_api: Mocker, client: FlaskClient) -> None:
    """
    When the auth service returns an auth_url, GET /login
    should return 200 and include that auth_url in the response body.
    """
    expected_oauth_url = "https://accounts.google.com/o/oauth2/auth?foo=bar"

    # * stub the external call to /login/google
    mock_api.get(
        f"{os.environ['AUTH_SERVICE_URL']}/login/google",
        json={"auth_url": expected_oauth_url},
        status_code=200,
    )

    response = client.get("/login")
    assert response.status_code == 200

    body = response.get_data(as_text=True)
    assert expected_oauth_url in body


def test_index_not_logged_in_shows_login_link(client: FlaskClient) -> None:
    """
    GET / when no session cookie should render the homepage with a login link.
    """
    response = client.get("/")
    assert response.status_code == 200
    body: str = response.get_data(as_text=True).lower()
    assert "login" in body


def test_index_logged_in_shows_user(mock_api: Mocker, client: FlaskClient) -> None:
    """
    GET / with valid session should show the current user's name and redirect to /dashboard (302).
    """
    # * stub verify endpoint
    user_payload = {"user": '{"name":"TestUser"}'}
    mock_api.post(f"{os.environ['AUTH_SERVICE_URL']}/verify", json=user_payload, status_code=200)

    client.set_cookie("session_id", "dummy-session-id")

    response = client.get("/")
    assert response.status_code == 302
    assert "/dashboard" in response.headers["Location"]


def test_google_login_sets_cookie_and_redirects(client: FlaskClient) -> None:
    """
    GET /google-login?session_id=abc123 should set the cookie and redirect to dashboard.
    """
    response = client.get("/google-login?session_id=abc123")
    assert response.status_code in (301, 302)
    # * location header points to dashboard
    assert "/dashboard" in response.headers["Location"]
    set_cookie: str = response.headers.get("Set-Cookie", "")
    assert "session_id=abc123" in set_cookie


def test_dashboard_redirects_when_not_logged_in(client: FlaskClient) -> None:
    """
    GET /dashboard without session should redirect to /login.
    """
    response = client.get("/dashboard")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_dashboard_success_when_logged_in(mock_api: Mocker, client: FlaskClient) -> None:
    """
    GET /dashboard with valid session should display the user's dashboard.
    """
    mock_api.post(f"{os.environ['AUTH_SERVICE_URL']}/verify", json={"user": '{"name":"Alice"}'}, status_code=200)
    client.set_cookie("session_id", "sess456")

    response = client.get("/dashboard")
    assert response.status_code == 200
    assert "Alice" in response.get_data(as_text=True)


def test_settings_redirects_when_not_logged_in(client: FlaskClient) -> None:
    """
    GET /settings without session should redirect to /login.
    """
    response = client.get("/settings")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_settings_success_when_logged_in(mock_api: Mocker, client: FlaskClient) -> None:
    """
    GET /settings with valid session should display settings page.
    """
    mock_api.post(f"{os.environ['AUTH_SERVICE_URL']}/verify", json={"user": '{"name":"Bob"}'}, status_code=200)
    client.set_cookie("session_id", "sess789")

    response = client.get("/settings")
    assert response.status_code == 200
    body: str = response.get_data(as_text=True)
    assert "settings" in body.lower()
    assert "Bob" in body


def test_logout_clears_cookie_and_redirects(mock_api: Mocker, client: FlaskClient) -> None:
    """
    GET or POST /logout should hit auth logout, clear cookie, and redirect to index.
    """
    mock_api.post(f"{os.environ['AUTH_SERVICE_URL']}/logout", status_code=200)
    client.set_cookie("session_id", "sess000")

    # * test GET
    response_get = client.get("/logout")
    assert response_get.status_code in (301, 302, 200)
    sc_get: str = response_get.headers.get("Set-Cookie", "")
    assert "session_id=;" in sc_get

    # * test POST
    response_post = client.post("/logout")
    assert response_post.status_code in (301, 302, 200)
    sc_post: str = response_post.headers.get("Set-Cookie", "")
    assert "session_id=;" in sc_post
