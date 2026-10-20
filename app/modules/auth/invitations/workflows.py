"""Registration request use cases shared by password and Google entry points."""

import logging

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import get_settings
from app.modules.auth.invitations.approval import review_request
from app.modules.auth.invitations.errors import PublicBaseURLConfigurationError
from app.modules.auth.invitations.links import public_link
from app.modules.auth.invitations.mail import (
    send_invitation_email,
    send_registration_notice,
)
from app.modules.auth.invitations.requests import create_registration_request
from app.shared.errors.application_error import ApplicationError

logger = logging.getLogger("uvicorn.error")


async def submit_request(session: AsyncSession, email: str, source: str) -> None:
    try:
        item = await create_registration_request(session, email, source)
        if item is None:
            await session.rollback()
            return
        # Existing ordering: persist before the optional administrator notice.
        await session.commit()
    except IntegrityError:
        await session.rollback()
        return
    except Exception:
        await session.rollback()
        raise

    settings = get_settings()
    recipient = settings.registration_admin_email
    if not recipient:
        logger.error("registration_notice_unavailable: recipient_configuration_invalid")
        return
    if not settings.gmail_invitation_enabled:
        logger.error("registration_notice_unavailable: sender_not_configured")
        return
    try:
        await send_registration_notice(
            recipient,
            public_link(settings, "/solicitudes"),
        )
    except (ApplicationError, PublicBaseURLConfigurationError):
        # Keep the public response generic and the committed request intact.
        logger.error("registration_notice_unavailable: delivery_failed")


async def review_registration_request(
    session: AsyncSession, request_id: int, actor_id: int, decision: str
) -> None:
    settings = get_settings()
    try:
        item, token = await review_request(session, request_id, actor_id, decision)
        if token is not None:
            # Existing ordering: send before commit; rollback on delivery failure.
            await send_invitation_email(
                item.email,
                public_link(settings, f"/registro#invite={token}"),
            )
        await session.commit()
    except Exception:
        await session.rollback()
        raise
