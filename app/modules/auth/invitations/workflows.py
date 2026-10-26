"""Registration request use cases shared by password and Google entry points."""

import logging
from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import get_settings
from app.infrastructure.outbox.service import OutboxService
from app.modules.auth.invitations.approval import review_request
from app.modules.auth.invitations.errors import PublicBaseURLConfigurationError
from app.modules.auth.invitations.links import public_link
from app.modules.auth.invitations.mail import (
    send_invitation_email,
    send_registration_notice,
)
from app.modules.auth.invitations.requests import create_registration_request
from app.modules.auth.invitations.service import INVITATION_TTL, token_digest
from app.shared.errors.application_error import ApplicationError

logger = logging.getLogger("uvicorn.error")


async def submit_request(session: AsyncSession, email: str, source: str) -> None:
    settings = get_settings()
    if settings.outbox_enabled:
        try:
            item = await create_registration_request(session, email, source)
            if item is None:
                await session.rollback()
                return

            recipient_config = settings.registration_admin_email
            if recipient_config and settings.gmail_invitation_enabled:
                try:
                    link = public_link(settings, "/solicitudes")
                    outbox_service = OutboxService.from_settings(settings)
                    recipients = [
                        r.strip() for r in recipient_config.split(",") if r.strip()
                    ]
                    for recipient in recipients:
                        await outbox_service.enqueue_event(
                            session=session,
                            event_type="auth.registration_notice",
                            aggregate_type="registration_request",
                            aggregate_id=str(item.id),
                            recipient_email=recipient,
                            payload={
                                "email": recipient,
                                "link": link,
                                "request_id": item.id,
                                "applicant_email": item.email,
                            },
                            idempotency_key=f"registration_notice:{item.id}:{recipient}",
                        )
                except PublicBaseURLConfigurationError:
                    # In public submission, failure of public link format is logged
                    # while preserving generic public response and clean rollback.
                    logger.error("registration_notice_unavailable: delivery_failed")
                except Exception:
                    logger.error("registration_notice_unavailable: outbox_enqueue_failed")
                    raise

            await session.commit()
        except IntegrityError:
            await session.rollback()
            return
        except Exception:
            await session.rollback()
            raise
    else:
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

        admin_recipient = settings.registration_admin_email
        if not admin_recipient:
            logger.error("registration_notice_unavailable: recipient_configuration_invalid")
            return
        if not settings.gmail_invitation_enabled:
            logger.error("registration_notice_unavailable: sender_not_configured")
            return
        try:
            await send_registration_notice(
                admin_recipient,
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
            if settings.outbox_enabled:
                link = public_link(settings, f"/registro#invite={token}")
                outbox_service = OutboxService.from_settings(settings)
                token_hash = token_digest(token)
                expires_at = (datetime.now(UTC) + INVITATION_TTL).isoformat()
                await outbox_service.enqueue_event(
                    session=session,
                    event_type="auth.invitation.created",
                    aggregate_type="registration_request",
                    aggregate_id=str(item.id),
                    recipient_email=item.email,
                    payload={
                        "email": item.email,
                        "link": link,
                        "request_id": item.id,
                        "token_hash": token_hash,
                        "expires_at": expires_at,
                    },
                    idempotency_key=f"invitation:request:{item.id}",
                )
            else:
                # Existing ordering: send before commit; rollback on delivery failure.
                await send_invitation_email(
                    item.email,
                    public_link(settings, f"/registro#invite={token}"),
                )
        await session.commit()
    except Exception:
        await session.rollback()
        raise
