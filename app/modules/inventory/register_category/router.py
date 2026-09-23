from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.session import get_database_session
from app.modules.inventory.register_category.schemas import (
    CategoryResponse,
    CreateCategoryRequest,
)
from app.modules.inventory.shared.models import Category

router = APIRouter(prefix="/inventory/categories", tags=["Inventory"])
DatabaseSession = Annotated[AsyncSession, Depends(get_database_session)]


@router.post("", response_model=CategoryResponse, status_code=status.HTTP_201_CREATED)
async def register_category(
    request: CreateCategoryRequest,
    session: DatabaseSession,
) -> CategoryResponse:
    category = Category(nombre=request.name)
    session.add(category)

    try:
        await session.commit()
        await session.refresh(category)
    except IntegrityError as error:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The category already exists.",
        ) from error

    return CategoryResponse(id=category.id, name=category.nombre)


@router.get("", response_model=list[CategoryResponse])
async def list_categories(
    session: DatabaseSession,
) -> list[CategoryResponse]:
    result = await session.execute(select(Category).order_by(Category.id))
    categories = result.scalars().all()

    return [
        CategoryResponse(id=category.id, name=category.nombre)
        for category in categories
    ]