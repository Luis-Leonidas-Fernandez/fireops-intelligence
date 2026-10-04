from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import get_settings
from app.infrastructure.database.session import get_database_session
from app.modules.auth.schemas import (
    AuthResponse,
    LoginRequest,
    RegisterRequest,
    UserResponse,
)
from app.modules.auth.service import authenticate_user, register_user
from app.modules.auth.validations.tokens import (
    ACCESS_TOKEN_COOKIE,
    ACCESS_TOKEN_TTL,
    create_access_token,
)

router = APIRouter(prefix="/auth", tags=["Authentication"])
DatabaseSession = Annotated[AsyncSession, Depends(get_database_session)]


def set_auth_cookie(response: Response, user_id: int) -> None:
    settings = get_settings()
    response.set_cookie(
        key=ACCESS_TOKEN_COOKIE,
        value=create_access_token(user_id, settings.secret_key),
        max_age=int(ACCESS_TOKEN_TTL.total_seconds()),
        httponly=True,
        secure=settings.environment == "production",
        samesite="lax",
        path="/",
    )


@router.post(
    "/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED
)
async def register(
    request: RegisterRequest, response: Response, session: DatabaseSession
) -> AuthResponse:
    user = await register_user(session, request.email, request.password)
    set_auth_cookie(response, user.id)
    return AuthResponse(
        message="Cuenta creada correctamente.", user=UserResponse.model_validate(user)
    )


@router.post("/login", response_model=AuthResponse)
async def login(
    request: LoginRequest, response: Response, session: DatabaseSession
) -> AuthResponse:
    user = await authenticate_user(session, request.email, request.password)
    set_auth_cookie(response, user.id)
    return AuthResponse(
        message="Inicio de sesión correcto.", user=UserResponse.model_validate(user)
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(response: Response) -> None:
    response.delete_cookie(ACCESS_TOKEN_COOKIE, path="/", samesite="lax")
