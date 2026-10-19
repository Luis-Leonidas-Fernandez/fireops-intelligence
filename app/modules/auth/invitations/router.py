"""Public registration requests and authenticated administrator review."""

import logging
from typing import Annotated, Literal
from urllib.parse import urlsplit, urlunsplit

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import get_settings
from app.infrastructure.database.session import get_database_session
from app.modules.auth.dependencies import require_authenticated_user
from app.modules.auth.invitations.approval import review_request
from app.modules.auth.invitations.mail import (
    delivery_error,
    send_invitation_email,
    send_registration_notice,
)
from app.modules.auth.invitations.requests import create_registration_request
from app.modules.auth.models import RegistrationRequest, Role, User
from app.modules.auth.validations.credentials import normalize_email
from app.shared.errors.application_error import ApplicationError
from app.shared.errors.authorization_error import AuthorizationError

router = APIRouter()
DatabaseSession = Annotated[AsyncSession, Depends(get_database_session)]
CurrentUser = Annotated[User, Depends(require_authenticated_user)]
GENERIC_MESSAGE = "Si corresponde, recibirás novedades por correo."
logger = logging.getLogger("uvicorn.error")


class RegistrationRequestPayload(BaseModel):
    email: str

    @field_validator("email")
    @classmethod
    def check_email(cls, value: str) -> str:
        return normalize_email(value)


class ReviewPayload(BaseModel):
    decision: Literal["approved", "rejected"]


class MessageResponse(BaseModel):
    message: str


class PendingRequestResponse(BaseModel):
    id: int
    email: str
    source: str
    requested_at: str


def public_origin() -> str:
    callback = urlsplit(get_settings().google_redirect_uri or "")
    if callback.scheme not in {"http", "https"} or not callback.netloc:
        raise delivery_error()
    return urlunsplit((callback.scheme, callback.netloc, "", "", ""))


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


async def submit_request(session: AsyncSession, email: str, source: str) -> None:
    try:
        item = await create_registration_request(session, email, source)
        if item is None:
            await session.rollback()
            return
        # Persist first: a mail outage must not erase a request or disclose existence.
        await session.commit()
    except IntegrityError:
        # Concurrent requests for the same normalized email are also generic.
        await session.rollback()
        return
    except Exception:
        await session.rollback()
        raise

    settings = get_settings()
    if not settings.gmail_invitation_enabled or not settings.registration_admin_email:
        logger.warning("registration_notice_unavailable: sender_not_configured")
        return
    try:
        await send_registration_notice(
            settings.registration_admin_email, f"{public_origin()}/solicitudes"
        )
    except ApplicationError:
        # Do not log email, provider payloads, or credentials.
        logger.warning("registration_notice_unavailable: delivery_failed")


@router.post(
    "/registration-requests",
    response_model=MessageResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def request_registration(
    payload: RegistrationRequestPayload, session: DatabaseSession
) -> MessageResponse:
    await submit_request(session, payload.email, "password")
    return MessageResponse(message=GENERIC_MESSAGE)


@router.get("/registration-requests", response_model=list[PendingRequestResponse])
async def list_requests(
    session: DatabaseSession, actor: CurrentUser
) -> list[PendingRequestResponse]:
    await require_admin(session, actor)
    items = (
        await session.scalars(
            select(RegistrationRequest)
            .where(RegistrationRequest.status == "pending")
            .order_by(RegistrationRequest.requested_at.asc())
            .limit(100)
        )
    ).all()
    return [
        PendingRequestResponse(
            id=item.id,
            email=item.email,
            source=item.source,
            requested_at=item.requested_at.isoformat(),
        )
        for item in items
    ]


@router.post(
    "/registration-requests/{request_id}/review", response_model=MessageResponse
)
async def review_registration(
    request_id: int,
    payload: ReviewPayload,
    session: DatabaseSession,
    actor: CurrentUser,
) -> MessageResponse:
    await require_admin(session, actor)
    settings = get_settings()
    if payload.decision == "approved" and not settings.gmail_invitation_enabled:
        raise delivery_error()
    try:
        item, token = await review_request(
            session, request_id, actor.id, payload.decision
        )
        if token is not None:
            await send_invitation_email(
                item.email, f"{public_origin()}/registro#invite={token}"
            )
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    return MessageResponse(message="Solicitud revisada.")
