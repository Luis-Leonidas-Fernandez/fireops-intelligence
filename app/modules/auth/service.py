from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.rate_limit.argon_guard import get_argon2_guard
from app.modules.auth.invitations.service import consume_invitation, lock_invitation
from app.modules.auth.models import User
from app.modules.auth.validations.passwords import (
    DUMMY_ARGON2_HASH,
    hash_password,
    verify_password,
)
from app.shared.errors.authentication_error import AuthenticationError
from app.shared.errors.conflict_error import ConflictError


async def register_user(
    session: AsyncSession, email: str, password: str, display_name: str | None = None,
    invitation_token: str | None = None,
) -> User:
    existing = await session.scalar(select(User.id).where(User.email == email))
    if existing is not None:
        raise ConflictError(
            code="EMAIL_ALREADY_REGISTERED", message="Ese correo ya está registrado."
        )

    invitation = await lock_invitation(session, email, invitation_token)
    password_hash = await get_argon2_guard().run_verified(hash_password, password)
    user = User(email=email, password_hash=password_hash, display_name=display_name, rol_id=invitation.rol_id)
    consume_invitation(invitation)
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
    target_hash = (
        user.password_hash
        if (user is not None and user.password_hash is not None)
        else DUMMY_ARGON2_HASH
    )
    is_valid = await get_argon2_guard().run_verified(
        verify_password, password, target_hash
    )
    if user is None or user.password_hash is None or not is_valid:
        raise AuthenticationError(
            code="INVALID_CREDENTIALS",
            message="El correo o la contraseña son incorrectos.",
        )
    if not user.activo:
        raise AuthenticationError(
            code="INVALID_CREDENTIALS",
            message="El correo o la contraseña son incorrectos.",
        )
    return user
