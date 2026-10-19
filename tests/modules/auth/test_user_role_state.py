from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app
from app.modules.auth.models import Role, User


@pytest.mark.asyncio
async def test_seeded_roles_have_expected_metadata(
    auth_session: AsyncSession,
) -> None:
    roles = (
        await auth_session.scalars(
            select(Role)
            .where(Role.nombre.in_(["ADMINISTRADOR", "SUPERVISOR"]))
            .order_by(Role.nombre)
        )
    ).all()

    assert {role.nombre for role in roles} == {
        "ADMINISTRADOR",
        "SUPERVISOR",
    }
    assert all(role.activo and role.created_at and role.updated_at for role in roles)


@pytest.mark.asyncio
async def test_users_keep_nullable_role_and_password_with_active_default(
    auth_session: AsyncSession,
) -> None:
    suffix = uuid4().hex
    rows = (
        (
            await auth_session.execute(
                text(
                    "INSERT INTO usuarios (email, password_hash, google_sub) "
                    "VALUES (:legacy_email, :password_hash, NULL), "
                    "(:google_email, NULL, :google_sub) "
                    "RETURNING id, email, password_hash, google_sub, rol_id, activo"
                ),
                {
                    "legacy_email": f"legacy-{suffix}@example.test",
                    "google_email": f"google-{suffix}@example.test",
                    "password_hash": "legacy-hash",
                    "google_sub": f"google-{suffix}",
                },
            )
        )
        .mappings()
        .all()
    )

    assert len(rows) == 2
    assert {row["password_hash"] for row in rows} == {"legacy-hash", None}
    assert all(row["rol_id"] is None and row["activo"] is True for row in rows)
    users = (
        await auth_session.scalars(
            select(User).where(User.id.in_([row["id"] for row in rows]))
        )
    ).all()
    assert all(user.rol_id is None and user.activo is True for user in users)


@pytest.mark.asyncio
async def test_role_foreign_key_is_enforced(auth_session: AsyncSession) -> None:
    constraints = (
        (
            await auth_session.execute(
                text(
                    "SELECT conname FROM pg_constraint "
                    "WHERE conrelid = 'usuarios'::regclass AND contype = 'f' "
                    "AND pg_get_constraintdef(oid) LIKE '%rol_id%'"
                )
            )
        )
        .scalars()
        .all()
    )

    assert constraints


@pytest.mark.asyncio
async def test_invited_registration_assigns_invited_role(
    auth_session: AsyncSession,
) -> None:
    email = f"new-{uuid4().hex}@example.test"
    from tests.modules.auth.conftest import create_test_invitation
    token = await create_test_invitation(auth_session, email, "SUPERVISOR")
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/auth/register", json={"email": email, "password": "ClaveSegura123", "invitation_token": token}
        )

    assert response.status_code == 201
    user = await auth_session.scalar(select(User).where(User.email == email))
    assert user is not None
    role = await auth_session.scalar(select(Role).where(Role.nombre == "SUPERVISOR"))
    assert role is not None and user.rol_id == role.id
    assert user.activo is True
