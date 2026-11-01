import unicodedata

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.inventory.shared.models import Asset, Category, Location


class VehicleAssetNotFoundError(Exception):
    """The specified vehicle asset does not exist."""


class IneligibleVehicleAssetError(Exception):
    """The specified asset is not eligible to act as a vehicle container."""


class VehicleLocationInactiveError(Exception):
    """The vehicle's mobile location exists but is currently inactive."""


def is_exact_vehicle_category_name(name: str | None) -> bool:
    if not name:
        return False
    normalized = "".join(
        ch
        for ch in unicodedata.normalize("NFD", name)
        if unicodedata.category(ch) != "Mn"
    )
    cleaned = normalized.strip().lower()
    return cleaned in {"vehiculo", "vehiculos"}


async def resolve_or_create_vehicle_location(
    session: AsyncSession,
    vehicle_asset_id: int,
) -> Location:
    """
    Resolves the mobile Location (tipo_ubicacion='VEHICULO') for a given vehicle asset,
    or creates it within the current transaction if the asset is an eligible vehicle
    without a mobile location yet.

    Does NOT commit the transaction so the caller can atomically commit or roll back
    together with the asset creation or transfer movement.
    Does NOT modify vehicle_asset.ubicacion_id (preserves its parking location).
    """
    vehicle_asset = await session.scalar(
        select(Asset).where(Asset.id == vehicle_asset_id).with_for_update()
    )
    if vehicle_asset is None:
        raise VehicleAssetNotFoundError

    existing_location = await session.scalar(
        select(Location).where(Location.bien_contenedor_id == vehicle_asset_id)
    )
    if existing_location is not None:
        if not existing_location.activa:
            raise VehicleLocationInactiveError
        return existing_location

    category = await session.get(Category, vehicle_asset.categoria_id)
    if category is None or not is_exact_vehicle_category_name(category.nombre):
        raise IneligibleVehicleAssetError

    stmt = (
        insert(Location)
        .values(
            nombre=vehicle_asset.nombre,
            tipo_ubicacion="VEHICULO",
            bien_contenedor_id=vehicle_asset.id,
            descripcion=f"Unidad móvil ({vehicle_asset.codigo_interno})",
            activa=True,
        )
        .on_conflict_do_nothing(
            index_elements=[Location.bien_contenedor_id],
            index_where=text("bien_contenedor_id IS NOT NULL"),
        )
        .returning(Location.id)
    )
    created_id = await session.scalar(stmt)
    if created_id is not None:
        created_loc = await session.get(Location, created_id)
        if created_loc is not None:
            return created_loc

    # Concurrent transaction created the location first; fetch and validate it
    resolved_loc = await session.scalar(
        select(Location).where(Location.bien_contenedor_id == vehicle_asset_id)
    )
    if resolved_loc is None:
        raise RuntimeError("Vehicle location conflict resolved without an existing location")
    if not resolved_loc.activa:
        raise VehicleLocationInactiveError
    return resolved_loc
