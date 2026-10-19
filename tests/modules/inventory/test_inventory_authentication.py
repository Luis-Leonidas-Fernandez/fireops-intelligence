from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import get_settings
from app.main import app
from app.modules.auth.models import Role, User
from app.modules.auth.validations.tokens import (
    ACCESS_TOKEN_COOKIE,
    create_access_token,
    validate_access_token,
)

INVENTORY_REQUESTS = (
    (
        "post",
        "/inventory/assets",
        {"internal_code": "SEC-001", "name": "Helmet", "new_category_name": "Helmets"},
    ),
    ("get", "/inventory/assets/", None),
    ("get", "/inventory/assets/1", None),
    ("patch", "/inventory/assets/1", {"name": "Changed", "reason": "Correction"}),
    ("post", "/inventory/categories", {"name": "Helmets"}),
    ("get", "/inventory/categories", None),
    ("post", "/inventory/locations", {"name": "Depot", "location_type": "FISICA"}),
    ("get", "/inventory/locations", None),
    ("get", "/inventory/locations/1", None),
    ("post", "/inventory/assets/1/transfers", {"destination_location_id": 1}),
    ("get", "/inventory/assets/1/transfers", None),
)


@pytest.mark.asyncio
@pytest.mark.parametrize("method,path,payload", INVENTORY_REQUESTS)
async def test_inventory_requires_a_session(
    inventory_session: AsyncSession,
    method: str,
    path: str,
    payload: dict[str, object] | None,
) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.request(method, path, json=payload)
    assert response.status_code == 401, response.text
    assert response.json()["error"]["code"] == "AUTH_REQUIRED"


@pytest.mark.asyncio
@pytest.mark.parametrize("method,path,payload", INVENTORY_REQUESTS)
@pytest.mark.parametrize("token_kind", ("invalid", "expired"))
async def test_inventory_rejects_invalid_or_expired_cookie(
    inventory_session: AsyncSession,
    method: str,
    path: str,
    payload: dict[str, object] | None,
    token_kind: str,
) -> None:
    token = (
        "invalid-token"
        if token_kind == "invalid"
        else create_access_token(
            1,
            get_settings().secret_key,
            now=datetime.now(UTC) - timedelta(hours=1),
        )
    )
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        client.cookies.set(ACCESS_TOKEN_COOKIE, token)
        response = await client.request(method, path, json=payload)
    assert response.status_code == 401, response.text
    assert response.json()["error"]["code"] == "AUTH_REQUIRED"


@pytest.mark.asyncio
@pytest.mark.parametrize("method,path,payload", INVENTORY_REQUESTS)
async def test_inventory_rejects_cookie_for_deleted_user(
    inventory_session: AsyncSession,
    method: str,
    path: str,
    payload: dict[str, object] | None,
) -> None:
    absent_id = await inventory_session.scalar(
        text("SELECT COALESCE(MAX(id), 0) + 1 FROM usuarios")
    )
    token = create_access_token(int(absent_id), get_settings().secret_key)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        client.cookies.set(ACCESS_TOKEN_COOKIE, token)
        response = await client.request(method, path, json=payload)
    assert response.status_code == 401, response.text
    assert response.json()["error"]["code"] == "AUTH_REQUIRED"


@pytest.mark.asyncio
@pytest.mark.parametrize("method,path,payload", INVENTORY_REQUESTS)
@pytest.mark.parametrize(
    "restriction", ("no_role", "inactive_user", "inactive_role", "unapproved_role")
)
async def test_inventory_rejects_authenticated_user_without_active_allowed_role(
    inventory_session: AsyncSession,
    method: str,
    path: str,
    payload: dict[str, object] | None,
    restriction: str,
) -> None:
    role = await inventory_session.scalar(
        select(Role).where(Role.nombre == "SUPERVISOR")
    )
    assert role is not None
    if restriction == "unapproved_role":
        role = Role(nombre=f"VISITANTE-{uuid4().hex}", activo=True)
        inventory_session.add(role)
        await inventory_session.flush()
    user = User(
        email=f"restricted-{uuid4().hex}@example.test",
        password_hash="test-only",
        rol_id=None if restriction == "no_role" else role.id,
        activo=restriction != "inactive_user",
    )
    inventory_session.add(user)
    if restriction == "inactive_role":
        role.activo = False
    await inventory_session.commit()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        client.cookies.set(
            ACCESS_TOKEN_COOKIE,
            create_access_token(user.id, get_settings().secret_key),
        )
        response = await client.request(method, path, json=payload)
    assert response.status_code == 403, response.text
    assert response.json()["error"]["code"] == "INVENTORY_ACCESS_DENIED"


@pytest.mark.asyncio
@pytest.mark.parametrize("role_name", ("ADMINISTRADOR", "SUPERVISOR"))
@pytest.mark.parametrize("method,path,payload", INVENTORY_REQUESTS)
async def test_inventory_allows_both_active_roles_on_every_endpoint(
    inventory_session: AsyncSession,
    authenticated_inventory_client: AsyncClient,
    role_name: str,
    method: str,
    path: str,
    payload: dict[str, object] | None,
) -> None:
    role = await inventory_session.scalar(select(Role).where(Role.nombre == role_name))
    assert role is not None and role.activo
    token = authenticated_inventory_client.cookies.get(ACCESS_TOKEN_COOKIE)
    assert token is not None
    user_id = validate_access_token(token, get_settings().secret_key)
    user = await inventory_session.get(User, user_id)
    assert user is not None
    user.rol_id = role.id
    await inventory_session.commit()
    response = await authenticated_inventory_client.request(method, path, json=payload)
    assert response.status_code not in {401, 403}, response.text
    assert response.status_code < 500, response.text
