import json
import logging
import os
from functools import wraps
from typing import Any, Callable

import requests
from dotenv import load_dotenv
from flask import Flask, g, redirect, render_template, request, url_for
from werkzeug.wrappers import Response as WerkzeugResponse

from . import logging_config  # pylint: disable=import-error

# * configure logging
logging_config.setup_logging(os.getenv("LOG_LEVEL", "WARNING"))
logger = logging.getLogger(__name__)

load_dotenv()

app = Flask(__name__)

# * Configuration variables
AUTH_SERVICE_URL: str = os.environ["AUTH_SERVICE_URL"]
COOKIE_SECURE: bool = os.getenv("COOKIE_SECURE", "false").lower() == "true"
app.config["SECRET_KEY"] = os.environ["SECRET_KEY"]


def verify_session(session_id: str, timeout: int = 3) -> dict[str, Any] | None:
    """
    Call auth_service /verify. On success (200 + valid JSON), return the user dict.
    On any error (HTTP != 200, network, parse), log and return None.
    """
    try:
        resp = requests.post(f"{AUTH_SERVICE_URL}/verify", json={"session_id": session_id}, timeout=timeout)
        resp.raise_for_status()  # automatically raises on 4xx/5xx
        if resp.status_code != 200:
            logger.warning(f"Auth /verify returned HTTP {resp.status_code}")
            return None

        return json.loads(resp.json().get("user"))
    except requests.exceptions.HTTPError as e:
        status = e.response.status_code if e.response else "unknown"
        logger.warning(f"Auth /verify HTTP {status}")
    except requests.exceptions.RequestException as e:
        logger.error(f"Auth /verify network error: {e}")
    except (ValueError, TypeError) as e:
        logger.error(f"Auth /verify JSON error: {e}")
    except Exception as e:
        logger.error(f"Auth /verify unexpected error: {e}")

    return None


def login_required(f: Callable) -> Callable:
    """Decorator: ensure user is logged in and set g.current_user."""

    @wraps(f)
    def wrapper(*args: Any, **kwargs: Any) -> WerkzeugResponse:
        """Check if user is logged in, redirect to login if not."""
        session_id = request.cookies.get("session_id")
        if not session_id:
            return redirect(url_for("login"))

        user = verify_session(session_id)
        if not user:
            return redirect(url_for("login"))

        g.current_user = user
        return f(*args, **kwargs)

    return wrapper


def check_already_logged_in(f: Callable) -> Callable:
    """Decorator: if user is already logged in, redirect to dashboard."""

    @wraps(f)
    def wrapper(*args: Any, **kwargs: Any) -> WerkzeugResponse:
        """Check if user is already logged in, redirect to dashboard if so."""
        session_id = request.cookies.get("session_id")
        if session_id and verify_session(session_id):
            logger.info("User already logged in, redirecting.")
            return redirect(url_for("dashboard"))
        return f(*args, **kwargs)

    return wrapper


@app.route("/login")
@check_already_logged_in
def login() -> tuple[str, int] | str:
    """Render login page (or redirect if already logged in)."""
    try:
        resp = requests.get(f"{AUTH_SERVICE_URL}/login/google", timeout=3)
        resp.raise_for_status()
        auth_url = resp.json().get("auth_url")
        if not auth_url:
            logger.error("Auth service returned empty auth_url field")
            return "Auth service error", 502

        return render_template("login.html", google_oauth_url=auth_url)
    except requests.exceptions.Timeout:
        logger.warning("Timed out fetching Google OAuth URL from auth service")
        return "Auth service timeout", 504
    except requests.exceptions.HTTPError as e:
        # * 4xx/5xx error from the auth service
        status = e.response.status_code if e.response else "unknown"
        logger.error(f"Auth service HTTP error {status}: {e}")
        return f"Auth service error ({status})", status if isinstance(status, int) else 502
    except requests.exceptions.RequestException as e:
        # * DNS failure, connection error, etc.
        logger.error(f"Network error contacting auth service: {e}")
        return "Auth service unavailable", 503
    except ValueError as e:
        # * JSON decode error or our own ValueError
        logger.error(f"Invalid response from auth service: {e}")
        return "Auth service error", 502
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return "Internal server error", 500


@app.route("/")
@check_already_logged_in
def index() -> str:
    """Homepage: show `index.html`, passing `user` if logged in."""
    session_id = request.cookies.get("session_id")
    user = verify_session(session_id) if session_id else None
    if user:
        g.current_user = user
    return render_template("index.html", user=user)


@app.route("/google-login")
def google_login() -> WerkzeugResponse | tuple[str, int]:
    """Callback route after Google OAuth, sets session cookie and redirects to dashboard."""
    session_id = request.args.get("session_id")
    if not session_id:
        return "Missing session ID", 400

    response = redirect(url_for("dashboard"))
    response.set_cookie(
        "session_id",
        session_id,
        httponly=True,
        secure=COOKIE_SECURE,
        domain=request.host,
        path="/",
        max_age=int(os.getenv("SESSION_EXPIRE_TIME_SECONDS", "3600")),
    )
    return response


@app.route("/dashboard", methods=["GET", "POST"])
@login_required
def dashboard() -> str:
    """Protected dashboard view."""
    user = g.current_user
    return (
        f"<h1>Dashboard — {user['name']}</h1>"
        '<form action="/logout" method="post"><button>Logout</button></form>'
        '<form action="/settings" method="post"><button>Settings</button></form>'
    )


@app.route("/settings", methods=["GET", "POST"])
@login_required
def settings() -> str:
    """Protected settings view."""
    user = g.current_user
    return (
        f"<h1>Settings — {user['name']}</h1>"
        '<form action="/logout" method="post"><button>Logout</button></form>'
        '<form action="/dashboard" method="post"><button>Dashboard</button></form>'
    )


@app.route("/logout", methods=["GET", "POST"])
def logout() -> WerkzeugResponse:
    """Logs out the user by deleting session on server and clearing cookie."""
    session_id = request.cookies.get("session_id")

    if session_id:
        try:
            resp = requests.post(f"{AUTH_SERVICE_URL}/logout", json={"session_id": session_id}, timeout=3)
            resp.raise_for_status()  # automatically raises on 4xx/5xx
            logger.info("Successfully notified auth service of logout.")
        except requests.exceptions.HTTPError as e:
            # * 4xx/5xx error from the auth service
            status = e.response.status_code if e.response is not None else "unknown"
            logger.warning(f"Auth logout endpoint returned HTTP {status}: {e}")
        except requests.exceptions.RequestException as e:
            # * network error, timeout, DNS failure, etc.
            logger.error(f"Failed to reach auth service for logout: {e}")
        except Exception as e:
            logger.error(f"Unexpected error during logout: {e}")
    else:
        logger.debug("No session_id cookie present; skipping auth service call.")

    resp_redirect = redirect(url_for("index"))
    resp_redirect.delete_cookie("session_id", path="/")
    return resp_redirect


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT_FLASK", "5000")))
