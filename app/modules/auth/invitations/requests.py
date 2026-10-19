"""Registration request persistence, with no account or credential creation."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.models import Invitation, RegistrationRequest, User

REQUEST_COOLDOWN = timedelta(minutes=15)


async def create_registration_request(
    session: AsyncSession, email: str, source: str
) -> RegistrationRequest | None:
    # A unique email row bounds duplicate submissions. Existing accounts remain opaque.
    if await session.scalar(select(User.id).where(User.email == email)) is not None:
        return None
    now = datetime.now(UTC)
    existing = await session.scalar(
        select(RegistrationRequest)
        .where(RegistrationRequest.email == email)
        .with_for_update()
    )
    if existing is not None:
        if now - existing.requested_at < REQUEST_COOLDOWN:
            return None
        if existing.status == "approved":
            active_invitation = await session.scalar(
                select(Invitation.id).where(
                    Invitation.email == email,
                    Invitation.used_at.is_(None),
                    Invitation.expires_at > now,
                )
            )
            if active_invitation is not None:
                return None
        elif existing.status not in {"pending", "rejected"}:
            return None
        existing.status = "pending"
        existing.source = source
        existing.requested_at = now
        existing.reviewed_at = None
        existing.reviewed_by_id = None
        return existing
    item = RegistrationRequest(
        email=email, source=source, requested_at=now, status="pending"
    )
    session.add(item)
    await session.flush()
    return item


async def list_pending_requests(session: AsyncSession) -> list[RegistrationRequest]:
    """Return the bounded review queue in request order."""
    return list(
        (
            await session.scalars(
                select(RegistrationRequest)
                .where(RegistrationRequest.status == "pending")
                .order_by(RegistrationRequest.requested_at.asc())
                .limit(100)
            )
        ).all()
    )
