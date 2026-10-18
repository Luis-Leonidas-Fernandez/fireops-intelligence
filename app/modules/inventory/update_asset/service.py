from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.inventory.shared.models import Asset, AuditChange, Category
from app.modules.inventory.update_asset.schemas import UpdateAssetRequest


class AssetNotFoundError(Exception):
    """The requested asset does not exist."""


class CategoryNotFoundError(Exception):
    """The requested category does not exist."""


def _snapshot(asset: Asset) -> dict[str, str | int | None]:
    return {
        "id": asset.id,
        "internal_code": asset.codigo_interno,
        "name": asset.nombre,
        "category_id": asset.categoria_id,
        "location_id": asset.ubicacion_id,
    }


async def update_asset(
    session: AsyncSession,
    asset_id: int,
    request: UpdateAssetRequest,
    actor_id: int,
) -> Asset:
    try:
        asset = await session.scalar(
            select(Asset).where(Asset.id == asset_id).with_for_update()
        )
        if asset is None:
            raise AssetNotFoundError

        if "category_id" in request.model_fields_set:
            category_id = request.category_id
            assert category_id is not None
            if (
                await session.scalar(
                    select(Category.id).where(Category.id == category_id)
                )
                is None
            ):
                raise CategoryNotFoundError

        previous = _snapshot(asset)
        if "internal_code" in request.model_fields_set:
            assert request.internal_code is not None
            asset.codigo_interno = request.internal_code
        if "name" in request.model_fields_set:
            assert request.name is not None
            asset.nombre = request.name
        if "category_id" in request.model_fields_set:
            assert request.category_id is not None
            asset.categoria_id = request.category_id

        session.add(
            AuditChange(
                operacion_id=uuid4(),
                entidad_tipo="BIEN",
                entidad_id=asset.id,
                accion="CORRECCION",
                datos_anteriores=previous,
                datos_nuevos=_snapshot(asset),
                motivo=request.reason,
                realizado_por_usuario_id=actor_id,
            )
        )
        await session.commit()
        return asset
    except Exception:
        await session.rollback()
        raise
