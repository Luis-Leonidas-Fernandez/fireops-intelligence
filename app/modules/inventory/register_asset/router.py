from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.session import get_database_session
from app.modules.auth.dependencies import require_authenticated_user
from app.modules.inventory.register_asset.schemas import (
    RegisterAssetRequest,
    RegisterAssetResponse,
)
from app.modules.inventory.register_asset.service import (
    LocationUnavailableError,
    create_asset,
)

router = APIRouter(
    prefix="/inventory/assets",
    tags=["Inventory"],
    dependencies=[Depends(require_authenticated_user)],
)

DatabaseSession = Annotated[AsyncSession, Depends(get_database_session)]


@router.post(
    "", response_model=RegisterAssetResponse, status_code=status.HTTP_201_CREATED
)
async def register_asset(
    request: RegisterAssetRequest,
    session: DatabaseSession,
) -> RegisterAssetResponse:
    try:
        asset = await create_asset(session, request)
    except LocationUnavailableError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="La ubicación seleccionada no existe o se encuentra inactiva.",
        ) from error
    except IntegrityError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "El código interno ingresado ya existe en el inventario o la categoría es inválida."
            ),
        ) from error

    return RegisterAssetResponse(
        id=asset.id,
        internal_code=asset.codigo_interno,
        name=asset.nombre,
        category_id=asset.categoria_id,
        location_id=asset.ubicacion_id,
    )
