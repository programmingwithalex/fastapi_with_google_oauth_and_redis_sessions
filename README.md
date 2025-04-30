<a id="readme-top"></a>

[![Contributors][contributors-shield]][contributors-url]
[![Forks][forks-shield]][forks-url]
[![Stargazers][stars-shield]][stars-url]
[![Issues][issues-shield]][issues-url]
[![BSD-3-Clause License][license-shield]][license-url]

---

<br/>
<div align="center">

© 2025 [GitHub@programmingwithalex](https://github.com/programmingwithalex)

### FastAPI with Google OAuth2 and Redis session storage

Example of how to deploy a `Flask` frontend with a `FastAPI` auth service using `Google OAuth2` and `Redis` as the session storage.

[Report Bug](https://github.com/programmingwithalex/fastapi_with_google_oauth_and_redis_sessions/issues/new?labels=bug&template=bug-report---.md) · [Request Feature](https://github.com/programmingwithalex/fastapi_with_google_oauth_and_redis_sessions/issues/new?labels=enhancement&template=feature-request---.md)

</div>
<br/>

# Project Overview

This repository contains two components:

1. **auth_service** (`FastAPI`):
   - Handles Google OAuth2 authentication
   - Manages user sessions in Redis
   - Exposes `/login/google`, `/auth/google`, `/verify`, and `/logout` endpoints

2. **web_frontend** (`Flask`):
   - Renders frontend templates (login, dashboard, settings)
   - Delegates auth logic to **auth_service**
   - Sets and clears session cookies

---

## Prerequisites

- `Python` 3.12+
- `Docker` & [`Docker Compose`](https://www.docker.com/products/docker-desktop/)
- `Redis` (can run locally or via Docker)

---

## Environment Variables

Create a `.env` file in each service directory with the following keys:

### auth_service (`src/auth/.env`)<a href="#appendix">¹</a>

```ini
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
REDIS_SSL=false
GOOGLE_OAUTH_CLIENT_ID=<your-google-client-id>
GOOGLE_OAUTH_CLIENT_SECRET=<your-google-client-secret>
GOOGLE_REDIRECT_URI=http://localhost:8000/auth/google
WEB_FRONTEND_URL=http://localhost:5000
SESSION_EXPIRE_TIME_SECONDS=3600
LOG_LEVEL=INFO
```

### web_service (`src/web/.env`)

```ini
AUTH_SERVICE_URL=http://localhost:8000
SECRET_KEY=<your-flask-secret-key>
COOKIE_SECURE=false
LOG_LEVEL=INFO
PORT_FLASK=5000
```

---

## Running Locally with Docker Compose

At the project root, you can spin up the `auth_service`, `web_frontend`, and `Redis`:

```bash
docker-compose up --build
```

- `web_service` available on `http://localhost:5000`
- `auth_service` available on `http://localhost:8000`
- `Redis` on port `6379`

## Testing

Run at top-level directory.

```bash
python -m pytest -v
```

## Linting & Formatting

Use pre-commit hooks at the repo root:

```bash
pre-commit install
pre-commit run --all-files
```

Will also run on each commit to GitHub repo.

---

## Appendix

### ¹Google OAuth Setup

1. Have to setup on [Google Cloud Console](https://console.cloud.google.com)
2. Create project to authenticate with OAuth2.0 on [Google Cloud Console](https://console.cloud.google.com/auth/overview)
3. After creating project:
   1. Clients > Application Type > Web Application
   2. Authorized redirect URIs:
      1. `http://localhost:8000/auth/google`
   3. Copy Google secret variables:
      1. `Client ID`
      2. `Client secret`

## References

[FastApi OAuth2 Scopes](https://fastapi.tiangolo.com/advanced/security/oauth2-scopes/)

[contributors-shield]: https://img.shields.io/github/contributors/programmingwithalex/fastapi_with_google_oauth_and_redis_sessions?style=for-the-badge
[contributors-url]: https://github.com/programmingwithalex/fastapi_with_google_oauth_and_redis_sessions/graphs/contributors
[forks-shield]: https://img.shields.io/github/forks/programmingwithalex/fastapi_with_google_oauth_and_redis_sessions?style=for-the-badge
[forks-url]: https://github.com/programmingwithalex/fastapi_with_google_oauth_and_redis_sessions/network/members
[stars-shield]: https://img.shields.io/github/stars/programmingwithalex/fastapi_with_google_oauth_and_redis_sessions?style=for-the-badge
[stars-url]: https://github.com/programmingwithalex/fastapi_with_google_oauth_and_redis_sessions/stargazers
[issues-shield]: https://img.shields.io/github/issues/programmingwithalex/fastapi_with_google_oauth_and_redis_sessions?style=for-the-badge
[issues-url]: https://github.com/programmingwithalex/fastapi_with_google_oauth_and_redis_sessions/issues
[license-shield]: https://img.shields.io/github/license/programmingwithalex/fastapi_with_google_oauth_and_redis_sessions.svg?style=for-the-badge
[license-url]: https://github.com/programmingwithalex/fastapi_with_google_oauth_and_redis_sessions/blob/main/LICENSE
