from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.session import engine, get_database_session
from app.main import app
from app.modules.inventory.shared.models import Asset, Category

_MISSING = object()


@pytest_asyncio.fixture
async def isolated_asset_session() -> AsyncIterator[AsyncSession]:
    async with engine.connect() as connection:
        outer_transaction = await connection.begin()
        try:
            database_name = await connection.scalar(text("SELECT current_database()"))
            if database_name != "fireassets_test":
                raise RuntimeError("Task 06 tests require fireassets_test")

            async with AsyncSession(
                bind=connection,
                join_transaction_mode="create_savepoint",
                expire_on_commit=False,
            ) as session:
                await session.execute(delete(Asset))
                await session.commit()  # Confirma el SAVEPOINT, no la transacción externa.

                previous = app.dependency_overrides.get(get_database_session, _MISSING)

                async def override_database_session() -> AsyncIterator[AsyncSession]:
                    yield session

                app.dependency_overrides[get_database_session] = override_database_session
                try:
                    yield session
                finally:
                    if previous is _MISSING:
                        app.dependency_overrides.pop(get_database_session, None)
                    else:
                        app.dependency_overrides[get_database_session] = previous
        finally:
            if outer_transaction.is_active:
                await outer_transaction.rollback()


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
async def test_list_assets_empty(isolated_asset_session: AsyncSession) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/inventory/assets/")

    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_list_assets_ordered(isolated_asset_session: AsyncSession) -> None:
    hose_category = await create_category(isolated_asset_session, "Mangueras")
    helmet_category = await create_category(isolated_asset_session, "Cascos")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        hose = await create_asset(client, hose_category.id, "Manguera de prueba")
        helmet = await create_asset(client, helmet_category.id, "Casco de prueba")
        response = await client.get("/inventory/assets/")

    assert response.status_code == 200
    items = response.json()
    assert len(items) == 2
    assert [item["id"] for item in items] == sorted([hose["id"], helmet["id"]])
    assert {item["id"] for item in items} == {hose["id"], helmet["id"]}
    assert all(
        set(item) == {"id", "internal_code", "name", "category_id"}
        for item in items
    )
    assert {item["category_id"] for item in items} == {
        hose_category.id, helmet_category.id
    }


@pytest.mark.asyncio
async def test_get_asset_existing(isolated_asset_session: AsyncSession) -> None:
    category = await create_category(isolated_asset_session, "Mangueras")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        created = await create_asset(client, category.id, "Manguera de prueba")
        response = await client.get(f"/inventory/assets/{created['id']}")

    assert response.status_code == 200
    assert response.json() == created
    assert set(response.json()) == {"id", "internal_code", "name", "category_id"}


@pytest.mark.asyncio
async def test_get_asset_missing(isolated_asset_session: AsyncSession) -> None:
    category = await create_category(isolated_asset_session, "Cascos")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        created = await create_asset(client, category.id, "Casco de prueba")
        missing_id = int(created["id"]) + 1
        assert await isolated_asset_session.scalar(
            select(Asset.id).where(Asset.id == missing_id)
        ) is None
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
async def test_get_asset_invalid_id(isolated_asset_session: AsyncSession) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/inventory/assets/not-an-id")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
