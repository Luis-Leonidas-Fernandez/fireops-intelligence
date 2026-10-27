from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.models import Role, User
from app.modules.inventory.shared.models import Asset, Category, Location
from app.modules.inventory.transfer_asset.schemas import TransferAssetRequest
from app.modules.inventory.transfer_asset.service import (
    AssetNotFoundError,
    DestinationUnavailableError,
    SameLocationError,
    list_all_movements,
    list_asset_transfers,
    transfer_asset,
)


async def create_test_user(session: AsyncSession) -> User:
    role = await session.scalar(
        select(Role).where(Role.nombre == "SUPERVISOR", Role.activo.is_(True))
    )
    assert role is not None
    user = User(
        email=f"transfer-{uuid4().hex}@example.test",
        password_hash="test-only",
        rol_id=role.id,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


@pytest.mark.asyncio
async def test_transfer_asset_service_success(
    inventory_session: AsyncSession,
) -> None:
    user = await create_test_user(inventory_session)
    category = Category(nombre="Herramientas")
    inventory_session.add(category)
    await inventory_session.flush()

    loc1 = Location(nombre="Estante A", tipo_ubicacion="FISICA", activa=True)
    loc2 = Location(nombre="Móvil 10", tipo_ubicacion="FISICA", activa=True)
    inventory_session.add_all([loc1, loc2])
    await inventory_session.flush()

    asset = Asset(
        codigo_interno="HER-100",
        nombre="Hacha",
        categoria_id=category.id,
        ubicacion_id=loc1.id,
    )
    inventory_session.add(asset)
    await inventory_session.flush()

    payload = TransferAssetRequest(
        destination_location_id=loc2.id,
        reason="Operativo",
        observations="En cabina",
    )
    movement = await transfer_asset(
        session=inventory_session,
        asset_id=asset.id,
        payload=payload,
        actor_id=user.id,
    )

    assert movement.bien_id == asset.id
    assert movement.usuario_id == user.id
    assert movement.ubicacion_origen_id == loc1.id
    assert movement.ubicacion_destino_id == loc2.id
    assert movement.motivo == "Operativo"
    assert movement.observaciones == "En cabina"
    assert asset.ubicacion_id == loc2.id

    history = await list_asset_transfers(inventory_session, asset.id)
    assert len(history) == 1
    assert history[0].id == movement.id


@pytest.mark.asyncio
async def test_transfer_asset_service_missing_asset(
    inventory_session: AsyncSession,
) -> None:
    user = await create_test_user(inventory_session)
    payload = TransferAssetRequest(destination_location_id=1)
    with pytest.raises(AssetNotFoundError):
        await transfer_asset(
            inventory_session, asset_id=999999, payload=payload, actor_id=user.id
        )


@pytest.mark.asyncio
async def test_transfer_asset_service_same_location(
    inventory_session: AsyncSession,
) -> None:
    user = await create_test_user(inventory_session)
    category = Category(nombre="Comunicaciones")
    inventory_session.add(category)
    await inventory_session.flush()

    loc = Location(nombre="Base Central", tipo_ubicacion="FISICA", activa=True)
    inventory_session.add(loc)
    await inventory_session.flush()

    asset = Asset(
        codigo_interno="RAD-01",
        nombre="Handie VHF",
        categoria_id=category.id,
        ubicacion_id=loc.id,
    )
    inventory_session.add(asset)
    await inventory_session.flush()

    payload = TransferAssetRequest(destination_location_id=loc.id)
    with pytest.raises(SameLocationError):
        await transfer_asset(inventory_session, asset.id, payload, actor_id=user.id)


@pytest.mark.asyncio
async def test_transfer_asset_service_inactive_destination(
    inventory_session: AsyncSession,
) -> None:
    user = await create_test_user(inventory_session)
    category = Category(nombre="Equipos")
    inventory_session.add(category)
    await inventory_session.flush()

    loc_active = Location(nombre="Activa", tipo_ubicacion="FISICA", activa=True)
    loc_inactive = Location(nombre="Inactiva", tipo_ubicacion="FISICA", activa=False)
    inventory_session.add_all([loc_active, loc_inactive])
    await inventory_session.flush()

    asset = Asset(
        codigo_interno="EQ-01",
        nombre="Generador",
        categoria_id=category.id,
        ubicacion_id=loc_active.id,
    )
    inventory_session.add(asset)
    await inventory_session.flush()

    payload = TransferAssetRequest(destination_location_id=loc_inactive.id)
    with pytest.raises(DestinationUnavailableError):
        await transfer_asset(inventory_session, asset.id, payload, actor_id=user.id)


@pytest.mark.asyncio
async def test_list_all_movements_service(
    inventory_session: AsyncSession,
) -> None:
    user = await create_test_user(inventory_session)
    category = Category(nombre="Protección")
    inventory_session.add(category)
    await inventory_session.flush()

    loc1 = Location(nombre="Almacén Alpha", tipo_ubicacion="FISICA", activa=True)
    loc2 = Location(nombre="Móvil 01", tipo_ubicacion="FISICA", activa=True)
    inventory_session.add_all([loc1, loc2])
    await inventory_session.flush()

    asset = Asset(
        codigo_interno="EPP-001",
        nombre="Casco F1",
        categoria_id=category.id,
        ubicacion_id=loc1.id,
    )
    inventory_session.add(asset)
    await inventory_session.flush()

    payload = TransferAssetRequest(
        destination_location_id=loc2.id,
        reason="Asignación inicial",
        observations="Nuevo",
    )
    await transfer_asset(
        session=inventory_session,
        asset_id=asset.id,
        payload=payload,
        actor_id=user.id,
    )

    all_movements = await list_all_movements(inventory_session)
    assert len(all_movements) >= 1
    target = next((m for m in all_movements if m.asset_id == asset.id), None)
    assert target is not None
    assert target.asset_code == "EPP-001"
    assert target.asset_name == "Casco F1"
    assert target.origin_location_name == "Almacén Alpha"
    assert target.destination_location_name == "Móvil 01"
    assert target.user_email == user.email
    assert target.reason == "Asignación inicial"
