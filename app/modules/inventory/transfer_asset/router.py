from typing import Annotated, Literal, cast

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.session import get_database_session
from app.modules.auth.dependencies import require_authenticated_user
from app.modules.auth.models import User
from app.modules.inventory.shared.models import Asset, Location, Movement
from app.modules.inventory.transfer_asset.schemas import (
    TransferAssetRequest,
    TransferAssetResponse,
)

router = APIRouter(
    prefix="/inventory/assets",
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
    asset = await session.scalar(
        select(Asset).where(Asset.id == asset_id).with_for_update()
    )
    if asset is None:
        raise HTTPException(status_code=404, detail="Asset not found.")

    destination = await session.get(Location, payload.destination_location_id)
    if destination is None or not destination.activa:
        raise HTTPException(status_code=409, detail="The destination is unavailable.")
    if asset.ubicacion_id == destination.id:
        raise HTTPException(status_code=409, detail="The asset is already there.")

    movement = Movement(
        bien_id=asset.id,
        usuario_id=user.id,
        tipo_movimiento="TRASLADO",
        ubicacion_origen_id=asset.ubicacion_id,
        ubicacion_destino_id=destination.id,
        motivo=payload.reason,
        observaciones=payload.observations,
    )
    asset.ubicacion_id = destination.id
    session.add(movement)
    try:
        await session.commit()
        await session.refresh(movement)
    except IntegrityError as error:
        await session.rollback()
        raise HTTPException(
            status_code=409,
            detail="The transfer violates inventory location constraints.",
        ) from error
    return transfer_response(movement)


@router.get("/{asset_id}/transfers", response_model=list[TransferAssetResponse])
async def list_asset_transfers(
    asset_id: int, session: DatabaseSession
) -> list[TransferAssetResponse]:
    if await session.get(Asset, asset_id) is None:
        raise HTTPException(status_code=404, detail="Asset not found.")
    result = await session.scalars(
        select(Movement)
        .where(Movement.bien_id == asset_id, Movement.tipo_movimiento == "TRASLADO")
        .order_by(Movement.fecha, Movement.id)
    )
    return [transfer_response(movement) for movement in result.all()]
