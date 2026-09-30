from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


def unique_category_name() -> str:
    return f"Categoria-{uuid4().hex[:8]}"


@pytest.mark.asyncio
async def test_create_category() -> None:
    category_name = unique_category_name()
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/inventory/categories",
            json={"name": category_name},
        )

    assert response.status_code == 201

    data = response.json()

    assert isinstance(data["id"], int)
    assert data["name"] == category_name


@pytest.mark.asyncio
async def test_list_categories() -> None:
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/inventory/categories")

    assert response.status_code == 200
    assert isinstance(response.json(), list)


@pytest.mark.asyncio
async def test_create_category_with_invalid_name() -> None:
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/inventory/categories",
            json={"name": "AB"},
        )

    assert response.status_code == 422