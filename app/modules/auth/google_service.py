"""Local account rules for verified Google identities."""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.google_oauth import GoogleIdentity, GoogleOAuthFailure
from app.modules.auth.models import User


async def sign_in_with_google(session: AsyncSession, identity: GoogleIdentity) -> User:
    linked = await session.scalar(select(User).where(User.google_sub == identity.sub))
    if linked is not None:
        if linked.display_name is None and identity.display_name is not None:
            linked.display_name = identity.display_name
            await session.commit()
        return linked

    existing_email = await session.scalar(select(User).where(User.email == identity.email))
    if existing_email is not None:
        if existing_email.password_hash is None or existing_email.google_sub is not None:
            raise GoogleOAuthFailure("GOOGLE_ACCOUNT_CONFLICT")
        raise GoogleOAuthFailure("GOOGLE_LINK_REQUIRED")

    user = User(
        email=identity.email,
        display_name=identity.display_name,
        password_hash=None,
        google_sub=identity.sub,
    )
    session.add(user)
    try:
        await session.commit()
        await session.refresh(user)
    except IntegrityError as error:
        await session.rollback()
        raise GoogleOAuthFailure("GOOGLE_ACCOUNT_CONFLICT") from error
    return user


async def link_google_identity(
    session: AsyncSession, user_id: int, identity: GoogleIdentity
) -> User:
    user = await session.get(User, user_id)
    if user is None:
        raise GoogleOAuthFailure("GOOGLE_LOGIN_REQUIRED")
    if user.email != identity.email:
        raise GoogleOAuthFailure("GOOGLE_EMAIL_MISMATCH")
    if user.google_sub == identity.sub:
        return user
    if user.google_sub is not None:
        raise GoogleOAuthFailure("GOOGLE_ALREADY_LINKED")
    other = await session.scalar(select(User.id).where(User.google_sub == identity.sub))
    if other is not None:
        raise GoogleOAuthFailure("GOOGLE_ACCOUNT_CONFLICT")

    user.google_sub = identity.sub
    if user.display_name is None:
        user.display_name = identity.display_name
    try:
        await session.commit()
    except IntegrityError as error:
        await session.rollback()
        raise GoogleOAuthFailure("GOOGLE_ACCOUNT_CONFLICT") from error
    return user
