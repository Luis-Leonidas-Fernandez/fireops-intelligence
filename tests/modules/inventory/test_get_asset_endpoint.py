from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.inventory.shared.models import Asset, Category


async def create_category(session: AsyncSession, kind: str) -> Category:
    category = Category(nombre=f"{kind}-{uuid4().hex}")
    session.add(category)
    await session.commit()
    await session.refresh(category)
    return category


async def create_asset(
    client: AsyncClient, category_id: int, name: str
) -> dict[str, object]:
    response = await client.post(
        "/inventory/assets",
        json={
            "internal_code": f"TEST-{uuid4().hex[:20]}",
            "name": name,
            "category_id": category_id,
        },
    )
    assert response.status_code == 201
    return response.json()


@pytest.mark.asyncio
async def test_list_assets_empty(
    inventory_session: AsyncSession, authenticated_inventory_client: AsyncClient
) -> None:
    client = authenticated_inventory_client
    response = await client.get("/inventory/assets/")

    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_list_assets_ordered(
    inventory_session: AsyncSession, authenticated_inventory_client: AsyncClient
) -> None:
    hose_category = await create_category(inventory_session, "Mangueras")
    helmet_category = await create_category(inventory_session, "Cascos")
    client = authenticated_inventory_client
    hose = await create_asset(client, hose_category.id, "Manguera de prueba")
    helmet = await create_asset(client, helmet_category.id, "Casco de prueba")
    response = await client.get("/inventory/assets/")

    assert response.status_code == 200
    items = response.json()
    assert len(items) == 2
    assert [item["id"] for item in items] == sorted([hose["id"], helmet["id"]])
    assert {item["id"] for item in items} == {hose["id"], helmet["id"]}
    assert all(
        set(item) == {"id", "internal_code", "name", "category_id", "location_id"}
        for item in items
    )
    assert all(item["location_id"] is None for item in items)
    assert {item["category_id"] for item in items} == {
        hose_category.id,
        helmet_category.id,
    }


@pytest.mark.asyncio
async def test_get_asset_existing(
    inventory_session: AsyncSession, authenticated_inventory_client: AsyncClient
) -> None:
    category = await create_category(inventory_session, "Mangueras")
    client = authenticated_inventory_client
    created = await create_asset(client, category.id, "Manguera de prueba")
    response = await client.get(f"/inventory/assets/{created['id']}")

    assert response.status_code == 200
    assert response.json() == created
    assert set(response.json()) == {
        "id",
        "internal_code",
        "name",
        "category_id",
        "location_id",
    }
    assert response.json()["location_id"] is None


@pytest.mark.asyncio
async def test_get_asset_missing(
    inventory_session: AsyncSession, authenticated_inventory_client: AsyncClient
) -> None:
    category = await create_category(inventory_session, "Cascos")
    client = authenticated_inventory_client
    created = await create_asset(client, category.id, "Casco de prueba")
    missing_id = int(created["id"]) + 1
    assert (
        await inventory_session.scalar(select(Asset.id).where(Asset.id == missing_id))
        is None
    )
    response = await client.get(f"/inventory/assets/{missing_id}")

    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "HTTP_404",
            "message": "Asset not found.",
            "details": {},
        }
    }


@pytest.mark.asyncio
async def test_get_asset_invalid_id(
    inventory_session: AsyncSession, authenticated_inventory_client: AsyncClient
) -> None:
    client = authenticated_inventory_client
    response = await client.get("/inventory/assets/not-an-id")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
