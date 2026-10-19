"""Authorization policy for registration-request review."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.models import Role, User
from app.shared.errors.authorization_error import AuthorizationError


async def require_admin(session: AsyncSession, actor: User) -> None:
    role = await session.get(Role, actor.rol_id)
    if (
        not actor.activo
        or role is None
        or not role.activo
        or role.nombre != "ADMINISTRADOR"
    ):
        raise AuthorizationError(
            code="REGISTRATION_REVIEW_DENIED",
            message="Solo un administrador puede revisar solicitudes.",
        )
