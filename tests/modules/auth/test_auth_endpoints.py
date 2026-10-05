from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import get_settings
from app.main import app
from app.modules.auth.models import User
from app.modules.auth.validations.passwords import verify_password
from app.modules.auth.validations.tokens import (
    ACCESS_TOKEN_COOKIE,
    validate_access_token,
)


def unique_email() -> str:
    return f"bombero-{uuid4().hex}@example.test"


@pytest.mark.asyncio
async def test_register_persists_hashed_password_and_sets_session(
    auth_session: AsyncSession,
) -> None:
    email = unique_email()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/auth/register",
            json={"email": email.upper(), "password": "ClaveSegura123"},
        )
        dashboard = await client.get("/")

    assert response.status_code == 201
    assert response.json() == {
        "message": "Cuenta creada correctamente.",
        "user": {"id": response.json()["user"]["id"], "email": email, "display_name": None},
    }
    assert dashboard.status_code == 200
    cookie = response.cookies.get(ACCESS_TOKEN_COOKIE)
    assert cookie is not None
    assert (
        validate_access_token(cookie, get_settings().secret_key)
        == response.json()["user"]["id"]
    )
    assert "httponly" in response.headers["set-cookie"].lower()
    assert "samesite=lax" in response.headers["set-cookie"].lower()
    user = await auth_session.scalar(select(User).where(User.email == email))
    assert user is not None
    assert user.password_hash != "ClaveSegura123"
    assert user.password_hash.startswith("$argon2")
    assert verify_password("ClaveSegura123", user.password_hash)


@pytest.mark.asyncio
async def test_register_rejects_invalid_email(auth_session: AsyncSession) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/auth/register",
            json={"email": "no-es-email", "password": "ClaveSegura123"},
        )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert response.json()["error"]["message"]


@pytest.mark.asyncio
async def test_register_rejects_weak_password(auth_session: AsyncSession) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/auth/register", json={"email": unique_email(), "password": "soloLetras"}
        )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_register_rejects_duplicate_email(auth_session: AsyncSession) -> None:
    email = unique_email()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        first = await client.post(
            "/auth/register", json={"email": email, "password": "ClaveSegura123"}
        )
        second = await client.post(
            "/auth/register",
            json={"email": email.upper(), "password": "ClaveSegura123"},
        )
    assert first.status_code == 201
    assert second.status_code == 409
    assert second.json()["error"] == {
        "code": "EMAIL_ALREADY_REGISTERED",
        "message": "Ese correo ya está registrado.",
        "details": {},
    }


@pytest.mark.asyncio
async def test_login_valid_credentials_returns_session(
    auth_session: AsyncSession,
) -> None:
    email = unique_email()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        await client.post(
            "/auth/register", json={"email": email, "password": "ClaveSegura123"}
        )
        response = await client.post(
            "/auth/login", json={"email": email.upper(), "password": "ClaveSegura123"}
        )
    assert response.status_code == 200
    assert response.json()["message"] == "Inicio de sesión correcto."
    assert response.json()["user"]["email"] == email
    assert (
        validate_access_token(
            response.cookies[ACCESS_TOKEN_COOKIE], get_settings().secret_key
        )
        == response.json()["user"]["id"]
    )


@pytest.mark.asyncio
async def test_login_rejects_wrong_password_and_unknown_user(
    auth_session: AsyncSession,
) -> None:
    email = unique_email()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        await client.post(
            "/auth/register", json={"email": email, "password": "ClaveSegura123"}
        )
        wrong = await client.post(
            "/auth/login", json={"email": email, "password": "OtraClave999"}
        )
        unknown = await client.post(
            "/auth/login", json={"email": unique_email(), "password": "OtraClave999"}
        )
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json()["error"] == unknown.json()["error"]
    assert wrong.json()["error"]["code"] == "INVALID_CREDENTIALS"


@pytest.mark.asyncio
async def test_login_rejects_invalid_input(auth_session: AsyncSession) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/auth/login", json={"email": "mal", "password": ""}
        )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_logout_clears_cookie_and_dashboard_access(
    auth_session: AsyncSession,
) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        await client.post(
            "/auth/register",
            json={"email": unique_email(), "password": "ClaveSegura123"},
        )
        logout = await client.post("/auth/logout")
        dashboard = await client.get("/")
    assert logout.status_code == 204
    assert dashboard.status_code == 303
    assert dashboard.headers["location"] == "/iniciar-sesion"


@pytest.mark.asyncio
async def test_profile_uses_session_and_registered_name(
    auth_session: AsyncSession,
) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        anonymous = await client.get("/auth/me")
        assert anonymous.status_code == 401
        registered = await client.post(
            "/auth/register",
            json={
                "email": unique_email(), "password": "ClaveSegura123",
                "display_name": "  María   Fernández  ",
            },
        )
        profile = await client.get("/auth/me")
        assert registered.status_code == 201
        assert registered.json()["user"]["display_name"] == "María Fernández"
        assert profile.status_code == 200
        assert profile.json() == registered.json()["user"]
        await client.post("/auth/logout")
        assert (await client.get("/auth/me")).status_code == 401


@pytest.mark.asyncio
async def test_existing_user_profile_falls_back_to_email(
    auth_session: AsyncSession,
) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        registered = await client.post(
            "/auth/register", json={"email": unique_email(), "password": "ClaveSegura123"}
        )
        profile = await client.get("/auth/me")
    assert registered.status_code == 201
    assert profile.json()["display_name"] is None
    assert profile.json()["email"] == registered.json()["user"]["email"]
