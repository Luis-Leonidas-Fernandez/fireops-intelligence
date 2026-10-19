"""Administrator-only review transitions."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.invitations.service import create_invitation
from app.modules.auth.models import RegistrationRequest
from app.shared.errors.application_error import ApplicationError


def unavailable_request() -> ApplicationError:
    return ApplicationError(
        code="REGISTRATION_REQUEST_UNAVAILABLE",
        message="La solicitud ya no está pendiente.",
        status_code=409,
    )


async def review_request(
    session: AsyncSession, request_id: int, actor_id: int, decision: str
) -> tuple[RegistrationRequest, str | None]:
    item = await session.scalar(
        select(RegistrationRequest)
        .where(RegistrationRequest.id == request_id)
        .with_for_update()
    )
    if item is None or item.status != "pending":
        raise unavailable_request()
    token = None
    if decision == "approved":
        _, token = await create_invitation(session, item.email, "SUPERVISOR", actor_id)
    item.status = decision
    item.reviewed_at = datetime.now(UTC)
    item.reviewed_by_id = actor_id
    return item, token
