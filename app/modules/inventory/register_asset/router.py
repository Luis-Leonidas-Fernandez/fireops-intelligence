from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.session import get_database_session
from app.modules.inventory.register_asset.schemas import (
    RegisterAssetRequest,
    RegisterAssetResponse,
)
from app.modules.inventory.shared.models import Asset

router = APIRouter(prefix="/inventory/assets", tags=["Inventory"])

DatabaseSession = Annotated[AsyncSession, Depends(get_database_session)]


@router.post("", response_model=RegisterAssetResponse, status_code=status.HTTP_201_CREATED)
async def register_asset(
    request: RegisterAssetRequest,
    session: DatabaseSession,
) -> RegisterAssetResponse:
    asset = Asset(
        codigo_interno=request.internal_code,
        nombre=request.name,
        categoria_id=request.category_id,
    )

    print("Asset before save:", asset.codigo_interno, asset.nombre, asset.categoria_id)

    try:
        session.add(asset)
        await session.commit()
        await session.refresh(asset)
    except IntegrityError as error:
        await session.rollback()

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "The asset could not be created. "
                "The internal code may already exist or the category may not exist."
            ),
        ) from error

    print("Asset created with ID:", asset.id)

    return RegisterAssetResponse(
        id=asset.id,
        internal_code=asset.codigo_interno,
        name=asset.nombre,
        category_id=asset.categoria_id,
    )