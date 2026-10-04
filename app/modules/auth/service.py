from fastapi.concurrency import run_in_threadpool
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.models import User
from app.modules.auth.validations.passwords import hash_password, verify_password
from app.shared.errors.authentication_error import AuthenticationError
from app.shared.errors.conflict_error import ConflictError


async def register_user(session: AsyncSession, email: str, password: str) -> User:
    existing = await session.scalar(select(User.id).where(User.email == email))
    if existing is not None:
        raise ConflictError(
            code="EMAIL_ALREADY_REGISTERED", message="Ese correo ya está registrado."
        )

    password_hash = await run_in_threadpool(hash_password, password)
    user = User(email=email, password_hash=password_hash)
    session.add(user)
    try:
        await session.commit()
        await session.refresh(user)
    except IntegrityError as error:
        await session.rollback()
        raise ConflictError(
            code="EMAIL_ALREADY_REGISTERED", message="Ese correo ya está registrado."
        ) from error
    return user


async def authenticate_user(session: AsyncSession, email: str, password: str) -> User:
    user = await session.scalar(select(User).where(User.email == email))
    if user is None or not await run_in_threadpool(
        verify_password, password, user.password_hash
    ):
        raise AuthenticationError(
            code="INVALID_CREDENTIALS",
            message="El correo o la contraseña son incorrectos.",
        )
    return user
