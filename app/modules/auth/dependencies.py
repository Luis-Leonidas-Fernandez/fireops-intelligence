from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import get_settings
from app.infrastructure.database.session import get_database_session
from app.modules.auth.models import User
from app.modules.auth.validations.tokens import (
    ACCESS_TOKEN_COOKIE,
    validate_access_token,
)
from app.shared.errors.authentication_error import AuthenticationError

DatabaseSession = Annotated[AsyncSession, Depends(get_database_session)]


def current_user_id(request: Request) -> int | None:
    token = request.cookies.get(ACCESS_TOKEN_COOKIE)
    if not token:
        return None
    try:
        return validate_access_token(token, get_settings().secret_key)
    except AuthenticationError:
        return None


async def require_authenticated_user(
    request: Request, session: DatabaseSession
) -> User:
    user_id = current_user_id(request)
    user = await session.get(User, user_id) if user_id is not None else None
    if user is None:
        raise AuthenticationError(
            code="AUTH_REQUIRED", message="Iniciá sesión para usar el inventario."
        )
    return user
