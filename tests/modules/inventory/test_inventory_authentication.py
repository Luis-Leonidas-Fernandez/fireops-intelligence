from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import get_settings
from app.main import app
from app.modules.auth.validations.tokens import ACCESS_TOKEN_COOKIE, create_access_token

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
