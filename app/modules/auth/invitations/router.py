"""HTTP transport for public registration requests and administrator review."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import get_settings
from app.infrastructure.database.session import get_database_session
from app.modules.auth.dependencies import require_authenticated_user
from app.modules.auth.invitations.errors import PublicBaseURLConfigurationError
from app.modules.auth.invitations.mail import delivery_error
from app.modules.auth.invitations.policy import require_admin
from app.modules.auth.invitations.requests import list_pending_requests
from app.modules.auth.invitations.workflows import (
    review_registration_request,
    submit_request,
)
from app.modules.auth.models import User
from app.modules.auth.validations.credentials import normalize_email
from app.shared.errors.application_error import ApplicationError

router = APIRouter()
DatabaseSession = Annotated[AsyncSession, Depends(get_database_session)]
CurrentUser = Annotated[User, Depends(require_authenticated_user)]
GENERIC_MESSAGE = "Si corresponde, recibirás novedades por correo."


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
    items = await list_pending_requests(session)
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
    if payload.decision == "approved" and not get_settings().gmail_invitation_enabled:
        raise delivery_error()
    try:
        await review_registration_request(session, request_id, actor.id, payload.decision)
    except PublicBaseURLConfigurationError as error:
        raise ApplicationError(
            code="PUBLIC_BASE_URL_UNAVAILABLE",
            message="No pudimos preparar el enlace público. Revisá PUBLIC_BASE_URL.",
            status_code=503,
        ) from error
    return MessageResponse(message="Solicitud revisada.")
