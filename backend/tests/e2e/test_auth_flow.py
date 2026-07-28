"""Route-level Administrator authentication tests.

Exercises the real FastAPI router, AuthService, Prisma repositories, password
hashing, JWT validation, session cookie, and Docker PostgreSQL. Upstash is the
only test double, injected by `cod_flow`, so counters are deterministic and no
external REST endpoint is required.
"""

from __future__ import annotations

from app.services.auth_service import LOGIN_RATE_LIMIT_MAX_ATTEMPTS

from tests.conftest import requires_database
from tests.e2e.conftest import CodFlowHarness

pytestmark = requires_database

_CLIENT_IP = "203.0.113.200"


async def test_valid_credentials_issue_cookie_and_hydrate_session(
    cod_flow: CodFlowHarness,
) -> None:
    username, password = await cod_flow.seed_admin()

    login = await cod_flow.client.post(
        "/api/auth/login",
        json={"username": username, "password": password},
        headers={"X-Forwarded-For": _CLIENT_IP},
    )

    assert login.status_code == 200
    assert login.json() == {"authenticated": True, "role": "admin"}
    assert login.cookies.get("session")
    set_cookie = login.headers["set-cookie"].lower()
    assert "httponly" in set_cookie
    assert "samesite=strict" in set_cookie
    assert "secure" not in set_cookie  # localhost development uses HTTP

    session = await cod_flow.client.get("/api/auth/session")
    assert session.status_code == 200
    assert session.json() == {"authenticated": True, "role": "admin"}


async def test_wrong_password_and_unknown_username_return_same_generic_401(
    cod_flow: CodFlowHarness,
) -> None:
    username, _ = await cod_flow.seed_admin()

    wrong_password = await cod_flow.client.post(
        "/api/auth/login",
        json={"username": username, "password": "wrong-password"},
        headers={"X-Forwarded-For": _CLIENT_IP},
    )
    unknown_username = await cod_flow.client.post(
        "/api/auth/login",
        json={"username": f"missing-{username}", "password": "wrong-password"},
        headers={"X-Forwarded-For": _CLIENT_IP},
    )

    assert wrong_password.status_code == 401
    assert unknown_username.status_code == 401
    assert wrong_password.json() == unknown_username.json()
    assert wrong_password.json() == {"detail": "Invalid username or password."}
    assert "session" not in wrong_password.cookies
    assert "session" not in unknown_username.cookies


async def test_login_rate_limit_returns_429_after_the_allowed_attempts(
    cod_flow: CodFlowHarness,
) -> None:
    username, password = await cod_flow.seed_admin()

    for _ in range(LOGIN_RATE_LIMIT_MAX_ATTEMPTS):
        response = await cod_flow.client.post(
            "/api/auth/login",
            json={"username": username, "password": "wrong-password"},
            headers={"X-Forwarded-For": _CLIENT_IP},
        )
        assert response.status_code == 401

    limited = await cod_flow.client.post(
        "/api/auth/login",
        json={"username": username, "password": password},
        headers={"X-Forwarded-For": _CLIENT_IP},
    )

    assert limited.status_code == 429
    assert limited.json() == {"detail": "Too many login attempts. Please try again later."}


async def test_logout_clears_cookie_and_session_becomes_unauthorized(
    cod_flow: CodFlowHarness,
) -> None:
    username, password = await cod_flow.seed_admin()
    login = await cod_flow.client.post(
        "/api/auth/login",
        json={"username": username, "password": password},
        headers={"X-Forwarded-For": _CLIENT_IP},
    )
    assert login.status_code == 200

    logout = await cod_flow.client.post("/api/auth/logout")
    session = await cod_flow.client.get("/api/auth/session")

    assert logout.status_code == 200
    assert logout.json() == {"logged_out": True}
    assert session.status_code == 401
    assert session.json() == {"detail": "Authentication required."}
