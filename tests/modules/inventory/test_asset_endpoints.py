from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.infrastructure.database.session import AsyncSessionLocal
from app.main import app


async def create_test_category() -> int:
    async with AsyncSessionLocal() as session:
        category_name = f"Categoria-test-{uuid4().hex[:8]}"

        result = await session.execute(
            text(
                """
                INSERT INTO categorias (nombre)
                VALUES (:category_name)
                RETURNING id
                """
            ),
            {"category_name": category_name},
        )
        category_id = result.scalar_one()
        await session.commit()

        return int(category_id)


@pytest.mark.asyncio
async def test_create_asset() -> None:
    category_id = await create_test_category()
    internal_code = f"TEST-{uuid4().hex[:8]}"
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
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