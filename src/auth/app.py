import json
import logging
import os
import uuid
from typing import Any, Dict

import redis
import requests
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from requests.exceptions import RequestException, Timeout

from . import logging_config  # pylint: disable=import-error

# * configure logging
logging_config.setup_logging(os.getenv("LOG_LEVEL", "WARNING"))
logger = logging.getLogger(__name__)

load_dotenv()

# * load required environment variables
try:
    REDIS_HOST: str = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT: int = int(os.getenv("REDIS_PORT", "6379"))
    REDIS_DB: int = int(os.getenv("REDIS_DB", "0"))
    REDIS_SSL: bool = os.getenv("REDIS_SSL", "false").lower() == "true"

    GOOGLE_OAUTH_TOKEN_URL: str = os.environ["GOOGLE_OAUTH_TOKEN_URL"]
    GOOGLE_OAUTH_USERINFO_URL: str = os.environ["GOOGLE_OAUTH_USERINFO_URL"]
    GOOGLE_CLIENT_ID: str = os.environ["GOOGLE_OAUTH_CLIENT_ID"]
    GOOGLE_CLIENT_SECRET: str = os.environ["GOOGLE_OAUTH_CLIENT_SECRET"]
    GOOGLE_REDIRECT_URI: str = "http://localhost:8000/auth/google"

    WEB_FRONTEND_URL: str = os.environ["WEB_FRONTEND_URL"]
except KeyError as e:
    logger.critical(f"Missing required environment variable: {e}")
    raise
except ValueError as e:
    logger.critical(f"Invalid integer in environment: {e}")
    raise

app = FastAPI()

# * connect to redis
try:
    redis_session_store = redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        db=REDIS_DB,
        ssl=REDIS_SSL,
        decode_responses=False,
    )
except redis.RedisError as e:
    logger.critical(f"Redis connection failed: {e}")
    raise
except Exception as e:
    logger.critical(f"Redis connection failed (unknown exception): {e}")
    raise


@app.get("/login/google")
async def login_google() -> Dict[str, str]:
    """Returns a Google OAuth login URL."""
    url = (
        "https://accounts.google.com/o/oauth2/auth"
        f"?response_type=code"
        f"&client_id={GOOGLE_CLIENT_ID}"
        f"&redirect_uri={GOOGLE_REDIRECT_URI}"
        f"&scope=openid%20profile%20email"
    )
    return {"auth_url": url}


@app.get("/auth/google")
async def auth_google(code: str) -> RedirectResponse:
    """
    Handles Google OAuth callback, stores session in Redis,
    and redirects to the web frontend.
    """
    token_data = {
        "code": code,
        "client_id": GOOGLE_CLIENT_ID,
        "client_secret": GOOGLE_CLIENT_SECRET,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "grant_type": "authorization_code",
    }

    # * exchange code for token
    try:
        token_resp = requests.post(GOOGLE_OAUTH_TOKEN_URL, data=token_data, timeout=5)
        token_resp.raise_for_status()
        token_response = token_resp.json()
    except Timeout:
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail="Token endpoint request timed out")
    except RequestException as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Token endpoint error: {e}")
    except ValueError:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Invalid JSON from token endpoint")

    access_token = token_response.get("access_token")
    if not access_token:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="No access token returned from provider")

    try:
        user_resp = requests.get(GOOGLE_OAUTH_USERINFO_URL, headers={"Authorization": f"Bearer {access_token}"}, timeout=5)
        user_resp.raise_for_status()
        user_info = user_resp.json()
    except Timeout:
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail="User-info request timed out")
    except RequestException as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"User-info endpoint error: {e}")
    except ValueError:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Invalid JSON from user-info endpoint")

    # Build session
    session_id = str(uuid.uuid4())
    session_data = {
        "email": user_info.get("email"),
        "name": user_info.get("name"),
        "source": "google",
    }

    try:
        redis_session_store.setex(
            f"session:{session_id}",
            int(os.getenv("SESSION_EXPIRE_TIME_SECONDS", "3600")),
            json.dumps(session_data),
        )
    except redis.RedisError as e:
        logger.error(f"Failed to write session to Redis: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Session storage error")

    return RedirectResponse(f"{WEB_FRONTEND_URL}/google-login?session_id={session_id}")


@app.post("/verify")
async def verify(request: Request) -> Dict[str, Any]:
    """Verifies a session ID and returns user info if valid."""
    try:
        data = await request.json()
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Malformed JSON payload")

    session_id = data.get("session_id")
    if not session_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing session_id")

    try:
        user = redis_session_store.get(f"session:{session_id}")
    except redis.RedisError as e:
        logger.error(f"Redis error on verify: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal error")

    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session")
    return {"user": user}


@app.post("/logout")
async def logout(request: Request) -> Dict[str, str]:
    """Deletes a session from Redis to log out the user."""
    try:
        data = await request.json()
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Malformed JSON payload")

    session_id = data.get("session_id")
    if not session_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing session_id")

    try:
        redis_session_store.delete(f"session:{session_id}")
    except redis.RedisError as e:
        logger.error(f"Redis error on logout: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal error")

    return {"message": "Logged out"}
