from typing import Annotated, Literal, cast

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.session import get_database_session
from app.modules.auth.dependencies import require_authenticated_user
from app.modules.auth.models import User
from app.modules.inventory.shared.models import Movement
from app.modules.inventory.transfer_asset.schemas import (
    MovementItemResponse,
    TransferAssetRequest,
    TransferAssetResponse,
)
from app.modules.inventory.transfer_asset.service import (
    AssetNotFoundError,
    DestinationUnavailableError,
    SameLocationError,
    TransferConstraintViolationError,
)
from app.modules.inventory.transfer_asset.service import (
    list_all_movements as list_all_movements_service,
)
from app.modules.inventory.transfer_asset.service import (
    list_asset_transfers as get_transfers_service,
)
from app.modules.inventory.transfer_asset.service import (
    transfer_asset as transfer_asset_service,
)

router = APIRouter(
    prefix="/inventory/assets",
    tags=["Inventory"],
    dependencies=[Depends(require_authenticated_user)],
)

router_movements = APIRouter(
    prefix="/inventory/movements",
    tags=["Inventory"],
    dependencies=[Depends(require_authenticated_user)],
)
DatabaseSession = Annotated[AsyncSession, Depends(get_database_session)]
CurrentUser = Annotated[User, Depends(require_authenticated_user)]


def transfer_response(movement: Movement) -> TransferAssetResponse:
    return TransferAssetResponse(
        id=movement.id,
        asset_id=movement.bien_id,
        user_id=movement.usuario_id,
        movement_type=cast(Literal["TRASLADO"], movement.tipo_movimiento),
        occurred_at=movement.fecha,
        origin_location_id=movement.ubicacion_origen_id,
        destination_location_id=cast(int, movement.ubicacion_destino_id),
        reason=movement.motivo,
        observations=movement.observaciones,
    )


@router.post(
    "/{asset_id}/transfers",
    response_model=TransferAssetResponse,
    status_code=status.HTTP_201_CREATED,
)
async def transfer_asset(
    asset_id: int,
    payload: TransferAssetRequest,
    session: DatabaseSession,
    user: CurrentUser,
) -> TransferAssetResponse:
    try:
        movement = await transfer_asset_service(
            session=session,
            asset_id=asset_id,
            payload=payload,
            actor_id=user.id,
        )
    except AssetNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Asset not found.",
        ) from error
    except DestinationUnavailableError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The destination is unavailable.",
        ) from error
    except SameLocationError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The asset is already there.",
        ) from error
    except TransferConstraintViolationError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The transfer violates inventory location constraints.",
        ) from error

    return transfer_response(movement)


@router.get("/{asset_id}/transfers", response_model=list[TransferAssetResponse])
async def list_asset_transfers(
    asset_id: int, session: DatabaseSession
) -> list[TransferAssetResponse]:
    try:
        movements = await get_transfers_service(session=session, asset_id=asset_id)
    except AssetNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Asset not found.",
        ) from error

    return [transfer_response(movement) for movement in movements]


@router_movements.get("", response_model=list[MovementItemResponse])
async def list_movements(
    session: DatabaseSession,
) -> list[MovementItemResponse]:
    return await list_all_movements_service(session)
