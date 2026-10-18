from collections.abc import AsyncIterator
from uuid import uuid4

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import get_settings
from app.infrastructure.database.session import engine, get_database_session
from app.main import app
from app.modules.auth.models import User
from app.modules.auth.validations.tokens import ACCESS_TOKEN_COOKIE, create_access_token
from app.modules.inventory.shared.models import Asset, AuditChange, Location, Movement


@pytest_asyncio.fixture
async def inventory_session() -> AsyncIterator[AsyncSession]:
    async with engine.connect() as connection:
        transaction = await connection.begin()
        try:
            name = await connection.scalar(text("SELECT current_database()"))
            if name != "fireassets_test":
                raise RuntimeError("Inventory tests require fireassets_test")

            async with AsyncSession(
                bind=connection,
                join_transaction_mode="create_savepoint",
                expire_on_commit=False,
            ) as session:
                await session.execute(delete(AuditChange))
                await session.execute(delete(Movement))
                await session.execute(update(Asset).values(ubicacion_id=None))
                await session.execute(delete(Location))
                await session.execute(delete(Asset))
                await session.commit()

                previous = app.dependency_overrides.get(get_database_session)

                async def override_session() -> AsyncIterator[AsyncSession]:
                    yield session

                app.dependency_overrides[get_database_session] = override_session
                try:
                    yield session
                finally:
                    if previous is None:
                        app.dependency_overrides.pop(get_database_session, None)
                    else:
                        app.dependency_overrides[get_database_session] = previous
        finally:
            if transaction.is_active:
                await transaction.rollback()


@pytest_asyncio.fixture
async def authenticated_inventory_client(
    inventory_session: AsyncSession,
) -> AsyncIterator[AsyncClient]:
    user = User(
        email=f"inventory-{uuid4().hex}@example.test", password_hash="test-only"
    )
    inventory_session.add(user)
    await inventory_session.commit()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        client.cookies.set(
            ACCESS_TOKEN_COOKIE,
            create_access_token(user.id, get_settings().secret_key),
        )
        yield client
