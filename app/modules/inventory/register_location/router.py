from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.session import get_database_session
from app.modules.auth.dependencies import require_authenticated_user
from app.modules.inventory.register_location.schemas import (
    CreateLocationRequest,
    LocationResponse,
    LocationType,
)
from app.modules.inventory.shared.models import Asset, Location

router = APIRouter(
    prefix="/inventory/locations",
    tags=["Inventory"],
    dependencies=[Depends(require_authenticated_user)],
)
DatabaseSession = Annotated[AsyncSession, Depends(get_database_session)]


def location_response(location: Location) -> LocationResponse:
    return LocationResponse(
        id=location.id,
        name=location.nombre,
        location_type=cast(LocationType, location.tipo_ubicacion),
        container_asset_id=location.bien_contenedor_id,
        description=location.descripcion,
        active=location.activa,
        created_at=location.created_at,
        updated_at=location.updated_at,
    )


@router.post("", response_model=LocationResponse, status_code=status.HTTP_201_CREATED)
async def register_location(
    request: CreateLocationRequest, session: DatabaseSession
) -> LocationResponse:
    if request.container_asset_id is not None:
        container = await session.get(Asset, request.container_asset_id)
        if container is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="The container asset does not exist.",
            )

    location = Location(
        nombre=request.name,
        tipo_ubicacion=request.location_type,
        bien_contenedor_id=request.container_asset_id,
        descripcion=request.description,
        activa=request.active,
    )
    session.add(location)
    try:
        await session.commit()
        await session.refresh(location)
    except IntegrityError as error:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The location could not be created. The container asset may already have a location.",
        ) from error
    return location_response(location)


@router.get("", response_model=list[LocationResponse])
async def list_locations(session: DatabaseSession) -> list[LocationResponse]:
    result = await session.execute(select(Location).order_by(Location.id))
    return [location_response(location) for location in result.scalars().all()]


@router.get("/{location_id}", response_model=LocationResponse)
async def get_location(location_id: int, session: DatabaseSession) -> LocationResponse:
    location = await session.get(Location, location_id)
    if location is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Location not found.",
        )
    return location_response(location)
