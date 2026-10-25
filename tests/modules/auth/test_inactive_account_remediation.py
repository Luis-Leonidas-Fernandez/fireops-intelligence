"""tests/modules/auth/test_inactive_account_remediation.py.

Deterministic test suite for remediation of finding M-06:
Inactive accounts (activo = False) must not obtain new sessions nor access authenticated resources.
Operates on an isolated ephemeral PostgreSQL database to ensure zero writes to protected databases.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator

import asyncpg  # type: ignore[import-untyped]
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

from app.config.settings import get_settings
from app.infrastructure.database.base import Base
from app.infrastructure.database.session import get_database_session
from app.main import app
from app.modules.auth.google_oauth import GoogleIdentity, GoogleOAuthFailure
from app.modules.auth.google_service import link_google_identity, sign_in_with_google
from app.modules.auth.models import Role, User
from app.modules.auth.validations.google_flow import GOOGLE_FLOW_COOKIE
from app.modules.auth.validations.passwords import hash_password
from app.modules.auth.validations.tokens import (
    ACCESS_TOKEN_COOKIE,
    create_access_token,
    validate_access_token,
)

FORBIDDEN_DATABASES: set[str] = {
    "fireassets",
    "fireassets_test",
    "fireassets_concurrency_test",
    "postgres",
    "afterlook",
    "template0",
    "template1",
}


@pytest_asyncio.fixture(scope="module")
async def m06_isolated_engine() -> AsyncIterator[AsyncEngine]:
    """Provision a 100% isolated ephemeral PostgreSQL database."""
    db_name = f"fireassets_m06_drill_{uuid.uuid4().hex[:12]}"
    assert db_name.startswith("fireassets_m06_drill_")
    assert db_name not in FORBIDDEN_DATABASES

    admin_conn = await asyncpg.connect(
        database="postgres",
        host="localhost",
        port=5432,
        user=os.getenv("USER", "postgres"),
    )
    try:
        await admin_conn.execute(f'CREATE DATABASE "{db_name}"')
    finally:
        await admin_conn.close()

    engine = create_async_engine(
        f"postgresql+asyncpg://{os.getenv('USER', 'postgres')}@localhost:5432/{db_name}"
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Seed required roles
    async with AsyncSession(engine) as session:
        admin_role = Role(nombre="ADMINISTRADOR", descripcion="Admin", activo=True)
        supervisor_role = Role(nombre="SUPERVISOR", descripcion="Supervisor", activo=True)
        session.add_all([admin_role, supervisor_role])
        await session.commit()

    yield engine

    await engine.dispose()
    admin_conn = await asyncpg.connect(
        database="postgres",
        host="localhost",
        port=5432,
        user=os.getenv("USER", "postgres"),
    )
    try:
        await admin_conn.execute(f'DROP DATABASE "{db_name}" WITH (FORCE)')
    finally:
        await admin_conn.close()


@pytest_asyncio.fixture
async def m06_session(
    m06_isolated_engine: AsyncEngine,
) -> AsyncIterator[AsyncSession]:
    """Yield an isolated transaction per test."""
    async with m06_isolated_engine.connect() as connection:
        outer_tx = await connection.begin()
        async with AsyncSession(
            bind=connection,
            join_transaction_mode="create_savepoint",
            expire_on_commit=False,
        ) as session:
            previous = app.dependency_overrides.get(get_database_session)

            async def override_get_db() -> AsyncIterator[AsyncSession]:
                yield session

            app.dependency_overrides[get_database_session] = override_get_db
            try:
                yield session
            finally:
                if previous is None:
                    app.dependency_overrides.pop(get_database_session, None)
                else:
                    app.dependency_overrides[get_database_session] = previous
                await session.close()
                if outer_tx.is_active:
                    await outer_tx.rollback()


@pytest_asyncio.fixture
async def m06_client(m06_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    """Client wired to the ephemeral test session."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client


# --- 1. Usuario activo con contraseña correcta ---
@pytest.mark.asyncio
async def test_01_active_user_valid_password_logs_in(
    m06_session: AsyncSession, m06_client: AsyncClient
) -> None:
    role = await m06_session.scalar(select(Role).where(Role.nombre == "SUPERVISOR"))
    assert role is not None
    user = User(
        email="active_user@example.test",
        password_hash=hash_password("Valida12345"),
        activo=True,
        rol_id=role.id,
    )
    m06_session.add(user)
    await m06_session.commit()

    response = await m06_client.post(
        "/auth/login",
        json={"email": "active_user@example.test", "password": "Valida12345"},
    )
    assert response.status_code == 200
    assert response.json()["message"] == "Inicio de sesión correcto."
    cookie = response.cookies.get(ACCESS_TOKEN_COOKIE)
    assert cookie is not None
    assert validate_access_token(cookie, get_settings().secret_key) == user.id


# --- 2. Usuario inactivo con contraseña correcta ---
@pytest.mark.asyncio
async def test_02_inactive_user_valid_password_rejected(
    m06_session: AsyncSession, m06_client: AsyncClient
) -> None:
    role = await m06_session.scalar(select(Role).where(Role.nombre == "SUPERVISOR"))
    assert role is not None
    user = User(
        email="inactive_user@example.test",
        password_hash=hash_password("Valida12345"),
        activo=False,
        rol_id=role.id,
    )
    m06_session.add(user)
    await m06_session.commit()

    response = await m06_client.post(
        "/auth/login",
        json={"email": "inactive_user@example.test", "password": "Valida12345"},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_CREDENTIALS"
    assert response.json()["error"]["message"] == "El correo o la contraseña son incorrectos."
    assert ACCESS_TOKEN_COOKIE not in response.cookies


# --- 3. Usuario inactivo con contraseña incorrecta ---
@pytest.mark.asyncio
async def test_03_inactive_user_wrong_password_rejected_identically(
    m06_session: AsyncSession, m06_client: AsyncClient
) -> None:
    role = await m06_session.scalar(select(Role).where(Role.nombre == "SUPERVISOR"))
    assert role is not None
    user = User(
        email="inactive_wrong_pw@example.test",
        password_hash=hash_password("Valida12345"),
        activo=False,
        rol_id=role.id,
    )
    m06_session.add(user)
    await m06_session.commit()

    response = await m06_client.post(
        "/auth/login",
        json={"email": "inactive_wrong_pw@example.test", "password": "Incorrecta999"},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_CREDENTIALS"
    assert response.json()["error"]["message"] == "El correo o la contraseña son incorrectos."
    assert ACCESS_TOKEN_COOKIE not in response.cookies


# --- 4. Usuario inactivo autenticándose mediante Google OAuth ---
@pytest.mark.asyncio
async def test_04_inactive_user_google_oauth_rejected(
    m06_session: AsyncSession,
) -> None:
    role = await m06_session.scalar(select(Role).where(Role.nombre == "SUPERVISOR"))
    assert role is not None
    user = User(
        email="inactive_google@example.test",
        google_sub="google_sub_inactive_001",
        display_name="Nombre Original",
        activo=False,
        rol_id=role.id,
    )
    m06_session.add(user)
    await m06_session.commit()

    identity = GoogleIdentity(
        sub="google_sub_inactive_001",
        email="inactive_google@example.test",
        display_name="Intento de Cambio",
    )

    with pytest.raises(GoogleOAuthFailure) as exc_info:
        await sign_in_with_google(m06_session, identity)

    assert exc_info.value.code == "GOOGLE_ACCOUNT_CONFLICT"

    # Verify no side-effect mutation on display_name
    await m06_session.refresh(user)
    assert user.display_name == "Nombre Original"


# --- 5. Usuario inactivo intentando acceder a /auth/me ---
@pytest.mark.asyncio
async def test_05_inactive_user_auth_me_denied(
    m06_session: AsyncSession, m06_client: AsyncClient
) -> None:
    role = await m06_session.scalar(select(Role).where(Role.nombre == "SUPERVISOR"))
    assert role is not None
    user = User(
        email="inactive_me@example.test",
        activo=False,
        rol_id=role.id,
    )
    m06_session.add(user)
    await m06_session.commit()

    token = create_access_token(user.id, get_settings().secret_key)
    m06_client.cookies.set(ACCESS_TOKEN_COOKIE, token)

    response = await m06_client.get("/auth/me")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_REQUIRED"


# --- 6. Usuario inactivo intentando acceder al dashboard GET / ---
@pytest.mark.asyncio
async def test_06_inactive_user_dashboard_redirects_and_deletes_cookie(
    m06_session: AsyncSession, m06_client: AsyncClient
) -> None:
    role = await m06_session.scalar(select(Role).where(Role.nombre == "SUPERVISOR"))
    assert role is not None
    user = User(
        email="inactive_dash@example.test",
        activo=False,
        rol_id=role.id,
    )
    m06_session.add(user)
    await m06_session.commit()

    token = create_access_token(user.id, get_settings().secret_key)
    m06_client.cookies.set(ACCESS_TOKEN_COOKIE, token)

    response = await m06_client.get("/")
    assert response.status_code == 303
    assert response.headers["location"] == "/iniciar-sesion"
    set_cookie = response.headers.get("set-cookie", "")
    assert ACCESS_TOKEN_COOKIE in set_cookie
    assert "max-age=0" in set_cookie.lower() or "expires=" in set_cookie.lower()


# --- 7. JWT emitido antes de desactivar una cuenta (Sesiones preexistentes) ---
@pytest.mark.asyncio
async def test_07_preexisting_jwt_revoked_upon_deactivation(
    m06_session: AsyncSession, m06_client: AsyncClient
) -> None:
    role = await m06_session.scalar(select(Role).where(Role.nombre == "ADMINISTRADOR"))
    assert role is not None
    user = User(
        email="deactivated_later@example.test",
        password_hash=hash_password("Valida12345"),
        activo=True,
        rol_id=role.id,
    )
    m06_session.add(user)
    await m06_session.commit()

    # Step 1: Login when active
    login_res = await m06_client.post(
        "/auth/login",
        json={"email": "deactivated_later@example.test", "password": "Valida12345"},
    )
    assert login_res.status_code == 200
    token = login_res.cookies.get(ACCESS_TOKEN_COOKIE)
    assert token is not None

    # Verify access while active
    dash_res = await m06_client.get("/")
    assert dash_res.status_code == 200
    me_res = await m06_client.get("/auth/me")
    assert me_res.status_code == 200

    # Step 2: Administrator deactivates user in DB
    user.activo = False
    await m06_session.commit()

    # Step 3: With same pre-existing JWT, verify immediate revocation across all endpoints
    dash_res2 = await m06_client.get("/")
    assert dash_res2.status_code == 303
    assert dash_res2.headers["location"] == "/iniciar-sesion"

    # Reset cookie to the pre-existing token to test /auth/me and inventory
    m06_client.cookies.set(ACCESS_TOKEN_COOKIE, token)
    me_res2 = await m06_client.get("/auth/me")
    assert me_res2.status_code == 401
    assert me_res2.json()["error"]["code"] == "AUTH_REQUIRED"

    m06_client.cookies.set(ACCESS_TOKEN_COOKIE, token)
    inv_res = await m06_client.get("/inventory/categories")
    assert inv_res.status_code == 403
    assert inv_res.json()["error"]["code"] == "INVENTORY_ACCESS_DENIED"


# --- 8. Usuario inactivo intentando acceder a inventario ---
@pytest.mark.asyncio
async def test_08_inactive_user_inventory_forbidden(
    m06_session: AsyncSession, m06_client: AsyncClient
) -> None:
    role = await m06_session.scalar(select(Role).where(Role.nombre == "SUPERVISOR"))
    assert role is not None
    user = User(
        email="inactive_inv@example.test",
        activo=False,
        rol_id=role.id,
    )
    m06_session.add(user)
    await m06_session.commit()

    m06_client.cookies.set(
        ACCESS_TOKEN_COOKIE, create_access_token(user.id, get_settings().secret_key)
    )

    response = await m06_client.get("/inventory/categories")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "INVENTORY_ACCESS_DENIED"


# --- 9. Usuario inactivo intentando acceder a endpoints administrativos ---
@pytest.mark.asyncio
async def test_09_inactive_user_admin_endpoints_forbidden(
    m06_session: AsyncSession, m06_client: AsyncClient
) -> None:
    role = await m06_session.scalar(select(Role).where(Role.nombre == "ADMINISTRADOR"))
    assert role is not None
    user = User(
        email="inactive_admin@example.test",
        activo=False,
        rol_id=role.id,
    )
    m06_session.add(user)
    await m06_session.commit()

    m06_client.cookies.set(
        ACCESS_TOKEN_COOKIE, create_access_token(user.id, get_settings().secret_key)
    )

    response = await m06_client.get("/auth/registration-requests")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "INVENTORY_ACCESS_DENIED"


# --- 10. Usuario activo con rol válido conservando su acceso ---
@pytest.mark.asyncio
async def test_10_active_user_preserves_full_access(
    m06_session: AsyncSession, m06_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    reviewer_sub = "test_reviewer_sub_10"
    settings = get_settings().model_copy(
        update={"registration_reviewer_google_sub": reviewer_sub}
    )
    monkeypatch.setattr("app.modules.auth.invitations.policy.get_settings", lambda: settings)

    role = await m06_session.scalar(select(Role).where(Role.nombre == "ADMINISTRADOR"))
    assert role is not None
    user = User(
        email="active_admin@example.test",
        google_sub=reviewer_sub,
        activo=True,
        rol_id=role.id,
    )
    m06_session.add(user)
    await m06_session.commit()

    m06_client.cookies.set(
        ACCESS_TOKEN_COOKIE, create_access_token(user.id, get_settings().secret_key)
    )

    me_res = await m06_client.get("/auth/me")
    assert me_res.status_code == 200
    assert me_res.json()["email"] == "active_admin@example.test"

    dash_res = await m06_client.get("/")
    assert dash_res.status_code == 200

    categories_res = await m06_client.get("/inventory/categories")
    assert categories_res.status_code == 200

    admin_res = await m06_client.get("/auth/registration-requests")
    assert admin_res.status_code == 200


# --- 11. Usuario inactivo intentando vincular o actualizar su identidad Google ---
@pytest.mark.asyncio
async def test_11_inactive_user_google_link_rejected(
    m06_session: AsyncSession, m06_client: AsyncClient
) -> None:
    user = User(
        email="inactive_linker@example.test",
        activo=False,
    )
    m06_session.add(user)
    await m06_session.commit()

    # Direct service call
    identity = GoogleIdentity(
        sub="google_sub_link_999",
        email="inactive_linker@example.test",
    )
    with pytest.raises(GoogleOAuthFailure) as exc_info:
        await link_google_identity(m06_session, user.id, identity)
    assert exc_info.value.code == "GOOGLE_LOGIN_REQUIRED"

    # HTTP endpoint start flow
    m06_client.cookies.set(
        ACCESS_TOKEN_COOKIE, create_access_token(user.id, get_settings().secret_key)
    )
    start_res = await m06_client.get("/auth/google/start?flow=link")
    assert start_res.status_code == 303
    assert start_res.headers["location"] == "/iniciar-sesion?auth_error=GOOGLE_LOGIN_REQUIRED"


# --- 12. Regresiones de PKCE, state, nonce y redirecciones OAuth ---
@pytest.mark.asyncio
async def test_12_oauth_pkce_state_nonce_flow_preserved(
    m06_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = get_settings().model_copy(
        update={
            "google_client_id": "test-client-id",
            "google_client_secret": "test-secret",
            "google_redirect_uri": "http://127.0.0.1:8000/auth/google/callback",
        }
    )
    monkeypatch.setattr("app.modules.auth.router.get_settings", lambda: settings)

    response = await m06_client.get("/auth/google/start?flow=signin&source=login")
    assert response.status_code == 303
    location = response.headers["location"]
    assert "accounts.google.com" in location
    assert "response_type=code" in location
    assert "code_challenge=" in location
    assert "code_challenge_method=S256" in location
    assert "state=" in location
    assert "nonce=" in location
    assert GOOGLE_FLOW_COOKIE in response.cookies


# --- 13. Respuestas públicas sin filtración innecesaria del estado de cuenta ---
@pytest.mark.asyncio
async def test_13_no_account_enumeration_in_errors(
    m06_session: AsyncSession, m06_client: AsyncClient
) -> None:
    user = User(
        email="enumeration_target@example.test",
        password_hash=hash_password("Valida12345"),
        activo=False,
    )
    m06_session.add(user)
    await m06_session.commit()

    # Existing inactive user
    res1 = await m06_client.post(
        "/auth/login",
        json={"email": "enumeration_target@example.test", "password": "Valida12345"},
    )
    # Non-existent user
    res2 = await m06_client.post(
        "/auth/login",
        json={"email": "non_existent_target@example.test", "password": "Valida12345"},
    )

    assert res1.status_code == res2.status_code == 401
    assert res1.json() == res2.json() == {
        "error": {
            "code": "INVALID_CREDENTIALS",
            "message": "El correo o la contraseña son incorrectos.",
            "details": {},
        }
    }


# --- 14. Ausencia de cookies de sesión en autenticaciones rechazadas ---
@pytest.mark.asyncio
async def test_14_rejected_auth_never_emits_session_cookie(
    m06_session: AsyncSession, m06_client: AsyncClient
) -> None:
    user = User(
        email="no_cookie@example.test",
        password_hash=hash_password("Valida12345"),
        activo=False,
    )
    m06_session.add(user)
    await m06_session.commit()

    res = await m06_client.post(
        "/auth/login",
        json={"email": "no_cookie@example.test", "password": "Valida12345"},
    )
    assert res.status_code == 401
    assert ACCESS_TOKEN_COOKIE not in res.cookies
