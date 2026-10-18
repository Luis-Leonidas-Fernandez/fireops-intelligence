from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.inventory.shared.models import Asset, Category


def asset_payload(**changes: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "internal_code": f"ATOMIC-{uuid4().hex[:20]}",
        "name": "Fire helmet",
        "new_category_name": f"Helmets-{uuid4().hex}",
    }
    payload.update(changes)
    return payload


@pytest.mark.asyncio
async def test_creates_category_and_asset_together(
    inventory_session: AsyncSession,
    authenticated_inventory_client: AsyncClient,
) -> None:
    payload = asset_payload()
    client = authenticated_inventory_client
    response = await client.post("/inventory/assets", json=payload)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["category_id"] > 0
    assert body["internal_code"] == payload["internal_code"]
    category = await inventory_session.get(Category, body["category_id"])
    assert category is not None
    assert category.nombre == payload["new_category_name"]
    assert await inventory_session.get(Asset, body["id"]) is not None


@pytest.mark.asyncio
async def test_reuses_existing_category_by_name(
    inventory_session: AsyncSession,
    authenticated_inventory_client: AsyncClient,
) -> None:
    name = f"Helmets-{uuid4().hex}"
    category = Category(nombre=name)
    inventory_session.add(category)
    await inventory_session.commit()
    client = authenticated_inventory_client
    response = await client.post(
        "/inventory/assets", json=asset_payload(new_category_name=name)
    )
    assert response.status_code == 201, response.text
    assert response.json()["category_id"] == category.id
    names = await inventory_session.scalars(
        select(Category.id).where(Category.nombre == name)
    )
    assert list(names) == [category.id]


@pytest.mark.asyncio
async def test_existing_category_id_still_works(
    inventory_session: AsyncSession,
    authenticated_inventory_client: AsyncClient,
) -> None:
    category = Category(nombre=f"Equipment-{uuid4().hex}")
    inventory_session.add(category)
    await inventory_session.commit()
    payload = asset_payload(category_id=category.id)
    payload.pop("new_category_name")
    client = authenticated_inventory_client
    response = await client.post("/inventory/assets", json=payload)
    assert response.status_code == 201, response.text
    assert response.json()["category_id"] == category.id


@pytest.mark.asyncio
async def test_exactly_one_category_source_is_required(
    inventory_session: AsyncSession,
    authenticated_inventory_client: AsyncClient,
) -> None:
    client = authenticated_inventory_client
    neither = asset_payload()
    neither.pop("new_category_name")
    both = asset_payload(category_id=1)
    for payload in (neither, both, asset_payload(new_category_name="ab")):
        response = await client.post("/inventory/assets", json=payload)
        assert response.status_code == 422, response.text


@pytest.mark.asyncio
async def test_asset_failure_rolls_back_new_category(
    inventory_session: AsyncSession,
    authenticated_inventory_client: AsyncClient,
) -> None:
    code = f"ATOMIC-{uuid4().hex[:20]}"
    first = asset_payload(internal_code=code)
    rejected = asset_payload(internal_code=code)
    client = authenticated_inventory_client
    assert (await client.post("/inventory/assets", json=first)).status_code == 201
    response = await client.post("/inventory/assets", json=rejected)
    assert response.status_code == 409, response.text
    count = await inventory_session.scalar(
        select(Category.id).where(Category.nombre == rejected["new_category_name"])
    )
    assert count is None


@pytest.mark.asyncio
async def test_invalid_location_does_not_create_category(
    inventory_session: AsyncSession,
    authenticated_inventory_client: AsyncClient,
) -> None:
    missing_location = int(
        await inventory_session.scalar(
            text("SELECT COALESCE(MAX(id), 0) + 1 FROM ubicaciones")
        )
    )
    payload = asset_payload(location_id=missing_location)
    client = authenticated_inventory_client
    response = await client.post("/inventory/assets", json=payload)
    assert response.status_code == 409, response.text
    assert (
        await inventory_session.scalar(
            select(Category.id).where(Category.nombre == payload["new_category_name"])
        )
        is None
    )
