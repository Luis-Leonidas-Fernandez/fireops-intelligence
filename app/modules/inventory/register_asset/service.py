from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.inventory.register_asset.schemas import RegisterAssetRequest
from app.modules.inventory.shared.models import Asset, Category, Location


class LocationUnavailableError(Exception):
    """The requested location is missing or inactive."""


async def _resolve_category_id(
    session: AsyncSession, request: RegisterAssetRequest
) -> int:
    if request.category_id is not None:
        return request.category_id

    assert request.new_category_name is not None
    name = request.new_category_name
    statement = (
        insert(Category)
        .values(nombre=name)
        .on_conflict_do_nothing(index_elements=[Category.nombre])
        .returning(Category.id)
    )
    new_id = await session.scalar(statement)
    if new_id is not None:
        return new_id

    existing_id = await session.scalar(
        select(Category.id).where(Category.nombre == name)
    )
    if existing_id is None:
        raise RuntimeError("Category conflict resolved without an existing category")
    return existing_id


async def create_asset(session: AsyncSession, request: RegisterAssetRequest) -> Asset:
    try:
        if request.location_id is not None:
            location = await session.get(Location, request.location_id)
            if location is None or not location.activa:
                raise LocationUnavailableError

        category_id = await _resolve_category_id(session, request)
        asset = Asset(
            codigo_interno=request.internal_code,
            nombre=request.name,
            categoria_id=category_id,
            ubicacion_id=request.location_id,
        )
        session.add(asset)
        await session.commit()
        return asset
    except Exception:
        await session.rollback()
        raise
