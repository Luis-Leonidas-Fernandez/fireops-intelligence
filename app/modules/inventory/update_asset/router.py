from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.session import get_database_session
from app.modules.auth.dependencies import require_authenticated_user
from app.modules.auth.models import User
from app.modules.inventory.register_asset.schemas import RegisterAssetResponse
from app.modules.inventory.update_asset.schemas import UpdateAssetRequest
from app.modules.inventory.update_asset.service import (
    AssetNotFoundError,
    CategoryNotFoundError,
    update_asset,
)

router = APIRouter(
    prefix="/inventory/assets",
    tags=["Inventory"],
    dependencies=[Depends(require_authenticated_user)],
)
DatabaseSession = Annotated[AsyncSession, Depends(get_database_session)]
CurrentUser = Annotated[User, Depends(require_authenticated_user)]


@router.patch("/{asset_id}", response_model=RegisterAssetResponse)
async def edit_asset(
    asset_id: int,
    request: UpdateAssetRequest,
    session: DatabaseSession,
    user: CurrentUser,
) -> RegisterAssetResponse:
    try:
        asset = await update_asset(session, asset_id, request, user.id)
    except AssetNotFoundError as error:
        raise HTTPException(status_code=404, detail="Asset not found.") from error
    except CategoryNotFoundError as error:
        raise HTTPException(status_code=409, detail="Category not found.") from error
    except IntegrityError as error:
        raise HTTPException(
            status_code=409,
            detail="The asset could not be updated. The internal code may already exist.",
        ) from error

    return RegisterAssetResponse(
        id=asset.id,
        internal_code=asset.codigo_interno,
        name=asset.nombre,
        category_id=asset.categoria_id,
        location_id=asset.ubicacion_id,
    )
