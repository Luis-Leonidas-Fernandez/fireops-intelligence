from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.inventory.shared.models import Asset, AuditChange, Category, Movement
from app.modules.inventory.update_asset.schemas import UpdateAssetRequest
from app.modules.inventory.update_asset.service import update_asset


async def create_category(session: AsyncSession) -> Category:
    category = Category(nombre=f"Categoria-{uuid4().hex}")
    session.add(category)
    await session.commit()
    return category


async def create_asset(client: AsyncClient, category_id: int) -> dict:
    response = await client.post(
        "/inventory/assets",
        json={
            "internal_code": f"EDIT-{uuid4().hex[:20]}",
            "name": "Casco original",
            "category_id": category_id,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.asyncio
async def test_edit_asset_persists_partial_fields_and_audit(
    inventory_session: AsyncSession, authenticated_inventory_client: AsyncClient
) -> None:
    original_category = await create_category(inventory_session)
    new_category = await create_category(inventory_session)
    original = await create_asset(authenticated_inventory_client, original_category.id)
    new_code = f"EDIT-{uuid4().hex[:20]}"

    response = await authenticated_inventory_client.patch(
        f"/inventory/assets/{original['id']}",
        json={
            "internal_code": new_code,
            "name": "Casco corregido",
            "category_id": new_category.id,
            "reason": "Corrección de inventario",
        },
    )

    assert response.status_code == 200, response.text
    expected = {
        **original,
        "internal_code": new_code,
        "name": "Casco corregido",
        "category_id": new_category.id,
    }
    assert response.json() == expected
    assert (
        await authenticated_inventory_client.get(f"/inventory/assets/{original['id']}")
    ).json() == expected
    audits = (
        await inventory_session.scalars(
            select(AuditChange).where(AuditChange.entidad_id == original["id"])
        )
    ).all()
    assert len(audits) == 1
    audit = audits[0]
    assert audit.operacion_id is not None
    assert audit.entidad_tipo == "BIEN"
    assert audit.accion == "CORRECCION"
    assert audit.datos_anteriores == original
    assert audit.datos_nuevos == expected
    assert audit.motivo == "Corrección de inventario"
    assert audit.realizado_por_usuario_id > 0
    assert audit.fecha is not None
    assert (
        await inventory_session.scalar(select(func.count()).select_from(Movement)) == 0
    )


@pytest.mark.asyncio
async def test_edit_asset_requires_existing_asset(
    inventory_session: AsyncSession, authenticated_inventory_client: AsyncClient
) -> None:
    missing_id = int(
        await inventory_session.scalar(
            text("SELECT COALESCE(MAX(id), 0) + 1 FROM bienes")
        )
    )
    response = await authenticated_inventory_client.patch(
        f"/inventory/assets/{missing_id}",
        json={"name": "New name", "reason": "Fix typo"},
    )
    assert response.status_code == 404, response.text
    assert (
        await inventory_session.scalar(select(func.count()).select_from(AuditChange))
        == 0
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body",
    (
        {"name": "New name"},
        {"reason": "Fix typo"},
        {"name": "New name", "reason": " "},
        {"name": None, "reason": "Fix typo"},
        {"category_id": None, "reason": "Fix typo"},
        {"location_id": 1, "reason": "Fix typo"},
        {"name": "New name", "unexpected": 1, "reason": "Fix typo"},
    ),
)
async def test_edit_asset_rejects_invalid_payload(
    inventory_session: AsyncSession,
    authenticated_inventory_client: AsyncClient,
    body: dict,
) -> None:
    category = await create_category(inventory_session)
    original = await create_asset(authenticated_inventory_client, category.id)
    response = await authenticated_inventory_client.patch(
        f"/inventory/assets/{original['id']}", json=body
    )
    assert response.status_code == 422, response.text
    assert (
        await authenticated_inventory_client.get(f"/inventory/assets/{original['id']}")
    ).json() == original
    assert (
        await inventory_session.scalar(select(func.count()).select_from(AuditChange))
        == 0
    )


@pytest.mark.asyncio
async def test_edit_asset_rejects_duplicate_code_and_rolls_back(
    inventory_session: AsyncSession, authenticated_inventory_client: AsyncClient
) -> None:
    category = await create_category(inventory_session)
    first = await create_asset(authenticated_inventory_client, category.id)
    second = await create_asset(authenticated_inventory_client, category.id)
    response = await authenticated_inventory_client.patch(
        f"/inventory/assets/{first['id']}",
        json={
            "internal_code": second["internal_code"],
            "name": "Incorrect",
            "reason": "Correction",
        },
    )
    assert response.status_code == 409, response.text
    assert (
        await authenticated_inventory_client.get(f"/inventory/assets/{first['id']}")
    ).json() == first
    assert (
        await inventory_session.scalar(select(func.count()).select_from(AuditChange))
        == 0
    )


@pytest.mark.asyncio
async def test_edit_asset_rejects_missing_category_and_rolls_back(
    inventory_session: AsyncSession, authenticated_inventory_client: AsyncClient
) -> None:
    category = await create_category(inventory_session)
    original = await create_asset(authenticated_inventory_client, category.id)
    missing_id = int(
        await inventory_session.scalar(
            text("SELECT COALESCE(MAX(id), 0) + 1 FROM categorias")
        )
    )
    response = await authenticated_inventory_client.patch(
        f"/inventory/assets/{original['id']}",
        json={"category_id": missing_id, "name": "Incorrect", "reason": "Correction"},
    )
    assert response.status_code == 409, response.text
    assert (
        await authenticated_inventory_client.get(f"/inventory/assets/{original['id']}")
    ).json() == original
    assert (
        await inventory_session.scalar(select(func.count()).select_from(AuditChange))
        == 0
    )


@pytest.mark.asyncio
async def test_edit_asset_preserves_location_and_movement_history(
    inventory_session: AsyncSession, authenticated_inventory_client: AsyncClient
) -> None:
    category = await create_category(inventory_session)
    asset = await create_asset(authenticated_inventory_client, category.id)
    location = await authenticated_inventory_client.post(
        "/inventory/locations", json={"name": "Main depot", "location_type": "FISICA"}
    )
    assert location.status_code == 201, location.text
    transfer = await authenticated_inventory_client.post(
        f"/inventory/assets/{asset['id']}/transfers",
        json={"destination_location_id": location.json()["id"], "reason": "Assignment"},
    )
    assert transfer.status_code == 201, transfer.text
    movement_count = await inventory_session.scalar(
        select(func.count()).select_from(Movement)
    )
    response = await authenticated_inventory_client.patch(
        f"/inventory/assets/{asset['id']}", json={"name": "Corrected", "reason": "Typo"}
    )
    assert response.status_code == 200, response.text
    assert response.json()["location_id"] == location.json()["id"]
    assert (
        await inventory_session.scalar(select(func.count()).select_from(Movement))
        == movement_count
    )
    persisted = await inventory_session.get(Asset, asset["id"])
    assert persisted is not None and persisted.ubicacion_id == location.json()["id"]


@pytest.mark.asyncio
async def test_audit_failure_rolls_back_asset_change(
    inventory_session: AsyncSession, authenticated_inventory_client: AsyncClient
) -> None:
    category = await create_category(inventory_session)
    original = await create_asset(authenticated_inventory_client, category.id)
    nonexistent_actor = int(
        await inventory_session.scalar(
            text("SELECT COALESCE(MAX(id), 0) + 1 FROM usuarios")
        )
    )

    with pytest.raises(IntegrityError):
        await update_asset(
            inventory_session,
            original["id"],
            UpdateAssetRequest(name="Uncommitted edit", reason="Fault injection"),
            nonexistent_actor,
        )

    assert (
        await authenticated_inventory_client.get(f"/inventory/assets/{original['id']}")
    ).json() == original
    assert (
        await inventory_session.scalar(select(func.count()).select_from(AuditChange))
        == 0
    )
