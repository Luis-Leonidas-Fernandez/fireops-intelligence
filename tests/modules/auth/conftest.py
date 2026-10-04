from collections.abc import AsyncIterator

import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.session import engine, get_database_session
from app.main import app


@pytest_asyncio.fixture
async def auth_session() -> AsyncIterator[AsyncSession]:
    async with engine.connect() as connection:
        outer_transaction = await connection.begin()
        database_name = await connection.scalar(text("SELECT current_database()"))
        if database_name != "fireassets_test":
            await outer_transaction.rollback()
            raise RuntimeError("Los tests de autenticación requieren fireassets_test.")

        async with AsyncSession(
            bind=connection,
            join_transaction_mode="create_savepoint",
            expire_on_commit=False,
        ) as session:
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
                await session.close()
                if outer_transaction.is_active:
                    await outer_transaction.rollback()
