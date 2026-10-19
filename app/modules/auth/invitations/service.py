"""Invitation lifecycle independent of HTTP and mail delivery."""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.models import Invitation, Role, User
from app.shared.errors.application_error import ApplicationError
from app.shared.errors.conflict_error import ConflictError

INVITATION_TTL = timedelta(hours=48)
ALLOWED_ROLES = frozenset({"SUPERVISOR"})


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def invitation_error() -> ApplicationError:
    return ApplicationError(
        code="INVITATION_INVALID",
        message="La invitación no es válida o ya venció.",
        status_code=403,
    )


async def create_invitation(
    session: AsyncSession, email: str, role_name: str, actor_id: int
) -> tuple[Invitation, str]:
    role = await session.scalar(
        select(Role).where(Role.nombre == role_name, Role.activo.is_(True))
    )
    if role is None or role_name not in ALLOWED_ROLES:
        raise invitation_error()
    if await session.scalar(select(User.id).where(User.email == email)) is not None:
        raise ConflictError(
            code="EMAIL_ALREADY_REGISTERED", message="Ese correo ya está registrado."
        )
    token = secrets.token_urlsafe(48)
    invitation = Invitation(
        email=email,
        token_hash=token_digest(token),
        rol_id=role.id,
        invited_by_id=actor_id,
        expires_at=datetime.now(UTC) + INVITATION_TTL,
    )
    session.add(invitation)
    await session.flush()
    return invitation, token


async def lock_invitation(
    session: AsyncSession, email: str, token: str | None
) -> Invitation:
    if not token or len(token) > 256:
        raise invitation_error()
    return await lock_invitation_digest(session, email, token_digest(token))


async def lock_invitation_digest(
    session: AsyncSession, email: str, digest: str | None
) -> Invitation:
    if not digest or len(digest) != 64:
        raise invitation_error()
    invitation = await session.scalar(
        select(Invitation).where(Invitation.token_hash == digest).with_for_update()
    )
    now = datetime.now(UTC)
    if (
        invitation is None
        or invitation.email != email
        or invitation.used_at is not None
        or invitation.expires_at <= now
    ):
        raise invitation_error()
    role = await session.get(Role, invitation.rol_id)
    if role is None or not role.activo or role.nombre not in ALLOWED_ROLES:
        raise invitation_error()
    return invitation


def consume_invitation(invitation: Invitation) -> None:
    invitation.used_at = datetime.now(UTC)
