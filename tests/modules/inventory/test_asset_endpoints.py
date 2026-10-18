from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.inventory.shared.models import Category


async def create_test_category(session: AsyncSession) -> int:
    category = Category(nombre=f"Categoria-test-{uuid4().hex[:8]}")
    session.add(category)
    await session.commit()
    return category.id


@pytest.mark.asyncio
async def test_create_asset(
    inventory_session: AsyncSession, authenticated_inventory_client: AsyncClient
) -> None:
    category_id = await create_test_category(inventory_session)
    internal_code = f"TEST-{uuid4().hex[:8]}"

    client = authenticated_inventory_client
    response = await client.post(
        "/inventory/assets",
        json={
            "internal_code": internal_code,
            "name": "Manguera de prueba",
            "category_id": category_id,
        },
    )

    assert response.status_code == 201

    data = response.json()

    assert isinstance(data["id"], int)
    assert data["internal_code"] == internal_code
    assert data["name"] == "Manguera de prueba"
    assert data["category_id"] == category_id
