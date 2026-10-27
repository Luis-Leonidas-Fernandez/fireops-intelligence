from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.models import User
from app.modules.inventory.shared.models import Asset, Location, Movement
from app.modules.inventory.transfer_asset.schemas import (
    MovementItemResponse,
    TransferAssetRequest,
)


class AssetNotFoundError(Exception):
    """The requested asset does not exist."""


class DestinationUnavailableError(Exception):
    """The requested destination location is missing or inactive."""


class SameLocationError(Exception):
    """The asset is already located at the destination."""


class TransferConstraintViolationError(Exception):
    """The transfer violates inventory location or cycle constraints."""


async def transfer_asset(
    session: AsyncSession,
    asset_id: int,
    payload: TransferAssetRequest,
    actor_id: int,
) -> Movement:
    """
    Transfers an asset to a new destination location atomically.

    Guarantees:
    - Obtains exclusive row-lock on the asset to avoid race conditions.
    - Validates that the destination exists and is active.
    - Rejects transfers where destination equals the current location.
    - Creates a TRASLADO record in the movimientos table.
    - Updates asset.ubicacion_id to the destination location.
    - Commits the transaction, or rolls back completely on any constraint violation.
    """
    asset = await session.scalar(
        select(Asset).where(Asset.id == asset_id).with_for_update()
    )
    if asset is None:
        raise AssetNotFoundError

    destination = await session.get(Location, payload.destination_location_id)
    if destination is None or not destination.activa:
        raise DestinationUnavailableError
    if asset.ubicacion_id == destination.id:
        raise SameLocationError

    movement = Movement(
        bien_id=asset.id,
        usuario_id=actor_id,
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
        return movement
    except IntegrityError as error:
        await session.rollback()
        raise TransferConstraintViolationError from error
    except Exception:
        await session.rollback()
        raise


async def list_asset_transfers(
    session: AsyncSession,
    asset_id: int,
) -> list[Movement]:
    """Lists all transfer movements for a given asset, ordered by timestamp and ID."""
    if await session.get(Asset, asset_id) is None:
        raise AssetNotFoundError
    result = await session.scalars(
        select(Movement)
        .where(Movement.bien_id == asset_id, Movement.tipo_movimiento == "TRASLADO")
        .order_by(Movement.fecha, Movement.id)
    )
    return list(result.all())


async def list_all_movements(
    session: AsyncSession,
) -> list[MovementItemResponse]:
    """Lists all movements across all assets with resolved asset, user, and location names."""
    query = (
        select(
            Movement,
            Asset.codigo_interno.label("asset_code"),
            Asset.nombre.label("asset_name"),
            User.email.label("user_email"),
        )
        .join(Asset, Movement.bien_id == Asset.id)
        .join(User, Movement.usuario_id == User.id)
        .order_by(Movement.fecha.desc(), Movement.id.desc())
    )
    result = await session.execute(query)
    rows = result.all()

    loc_result = await session.scalars(select(Location))
    loc_map = {loc.id: loc.nombre for loc in loc_result.all()}

    items: list[MovementItemResponse] = []
    for movement, asset_code, asset_name, user_email in rows:
        items.append(
            MovementItemResponse(
                id=movement.id,
                asset_id=movement.bien_id,
                asset_code=asset_code,
                asset_name=asset_name,
                user_id=movement.usuario_id,
                user_email=user_email,
                movement_type=movement.tipo_movimiento,
                occurred_at=movement.fecha,
                origin_location_id=movement.ubicacion_origen_id,
                origin_location_name=loc_map.get(movement.ubicacion_origen_id),
                destination_location_id=movement.ubicacion_destino_id,
                destination_location_name=loc_map.get(movement.ubicacion_destino_id),
                reason=movement.motivo,
                observations=movement.observaciones,
            )
        )
    return items
