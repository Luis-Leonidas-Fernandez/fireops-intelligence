"""Authorization policy for registration-request review."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import get_settings
from app.modules.auth.models import Role, User
from app.shared.errors.authorization_error import AuthorizationError


async def require_admin(session: AsyncSession, actor: User) -> None:
    settings = get_settings()
    role = await session.get(Role, actor.rol_id) if actor.rol_id is not None else None
    if (
        not actor.activo
        or not settings.registration_reviewer_google_sub
        or actor.google_sub != settings.registration_reviewer_google_sub
        or role is None
        or not role.activo
        or role.nombre != "ADMINISTRADOR"
    ):
        raise AuthorizationError(
            code="REGISTRATION_REVIEW_DENIED",
            message="No tenés permiso para revisar solicitudes.",
        )


async def require_reissue_admin(session: AsyncSession, actor: User) -> None:
    settings = get_settings()
    role = await session.get(Role, actor.rol_id) if actor.rol_id is not None else None
    if (
        not actor.activo
        or role is None
        or not role.activo
        or role.nombre != "ADMINISTRADOR"
    ):
        raise AuthorizationError(
            code="REISSUE_PERMISSION_DENIED",
            message="Solo un usuario con rol ADMINISTRADOR activo puede reemitir invitaciones.",
        )
    if (
        settings.registration_reviewer_google_sub
        and actor.google_sub != settings.registration_reviewer_google_sub
    ):
        raise AuthorizationError(
            code="REISSUE_PERMISSION_DENIED",
            message="No tenés autorización específica para reemitir invitaciones.",
        )
