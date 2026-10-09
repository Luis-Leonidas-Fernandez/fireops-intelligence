from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.session import get_database_session
from app.modules.inventory.register_asset.schemas import RegisterAssetResponse
from app.modules.inventory.shared.models import Asset

router = APIRouter(prefix="/inventory/assets", tags=["Inventory"])
DatabaseSession = Annotated[AsyncSession, Depends(get_database_session)]


def asset_response(asset: Asset) -> RegisterAssetResponse:
    return RegisterAssetResponse(
        id=asset.id,
        internal_code=asset.codigo_interno,
        name=asset.nombre,
        category_id=asset.categoria_id,
    )


@router.get("/", response_model=list[RegisterAssetResponse])
async def list_assets(session: DatabaseSession) -> list[RegisterAssetResponse]:
    result = await session.execute(select(Asset).order_by(Asset.id))
    return [asset_response(asset) for asset in result.scalars().all()]


@router.get("/{asset_id}", response_model=RegisterAssetResponse)
async def get_asset(
    asset_id: int, session: DatabaseSession
) -> RegisterAssetResponse:
    asset = await session.get(Asset, asset_id)
    if asset is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Asset not found.",
        )
    return asset_response(asset)
