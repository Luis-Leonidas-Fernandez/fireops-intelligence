"""HTTP transport for public registration requests and administrator review."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, Request, status
from pydantic import BaseModel, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import get_settings
from app.infrastructure.database.session import get_database_session
from app.infrastructure.rate_limit.limiter import get_rate_limiter
from app.modules.auth.dependencies import require_authenticated_user
from app.modules.auth.invitations.errors import PublicBaseURLConfigurationError
from app.modules.auth.invitations.mail import delivery_error
from app.modules.auth.invitations.policy import require_admin, require_reissue_admin
from app.modules.auth.invitations.reissue import reissue_registration_invitation
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


class ReissueInvitationPayload(BaseModel):
    idempotency_key: str | None = None
    reason: str | None = None


class ReissueInvitationResponse(BaseModel):
    message: str
    request_id: int
    invitation_id: int
    reissue_count: int
    idempotent_replay: bool


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
    payload: RegistrationRequestPayload,
    request: Request,
    session: DatabaseSession,
) -> MessageResponse:
    limiter = get_rate_limiter()
    should_submit = await limiter.check_registration_request_allowed(
        request, payload.email
    )
    if should_submit:
        await submit_request(session, payload.email, "password")
    return MessageResponse(message=GENERIC_MESSAGE)


@router.get("/registration-requests", response_model=list[PendingRequestResponse])
async def list_requests(
    request: Request, session: DatabaseSession, actor: CurrentUser
) -> list[PendingRequestResponse]:
    await require_admin(session, actor)
    settings = get_settings()
    await get_rate_limiter().check_admin_action_limit(
        request,
        admin_id=actor.id,
        action="list_requests",
        max_requests=settings.admin_rate_limit_list_requests,
        window_seconds=60,
    )
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
    request: Request,
    session: DatabaseSession,
    actor: CurrentUser,
) -> MessageResponse:
    await require_admin(session, actor)
    settings = get_settings()
    await get_rate_limiter().check_admin_action_limit(
        request,
        admin_id=actor.id,
        action="review_registration",
        max_requests=settings.admin_rate_limit_review_requests,
        window_seconds=60,
    )
    if payload.decision == "approved":
        if not settings.outbox_enabled and not settings.gmail_invitation_enabled:
            raise delivery_error()
        if settings.outbox_enabled:
            try:
                from app.infrastructure.outbox.service import OutboxService

                OutboxService.from_settings(settings)
            except Exception as err:
                raise ApplicationError(
                    code="OUTBOX_CONFIGURATION_INVALID",
                    message="La infraestructura de entrega diferida (Outbox) no está correctamente configurada.",
                    status_code=503,
                ) from err
    try:
        await review_registration_request(session, request_id, actor.id, payload.decision)
    except PublicBaseURLConfigurationError as error:
        raise ApplicationError(
            code="PUBLIC_BASE_URL_UNAVAILABLE",
            message="No pudimos preparar el enlace público. Revisá PUBLIC_BASE_URL.",
            status_code=503,
        ) from error
    return MessageResponse(message="Solicitud revisada.")


@router.post(
    "/registration-requests/{request_id}/reissue",
    response_model=ReissueInvitationResponse,
    status_code=status.HTTP_200_OK,
)
async def reissue_invitation(
    request_id: int,
    payload: ReissueInvitationPayload,
    request: Request,
    session: DatabaseSession,
    actor: CurrentUser,
    idempotency_key_header: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> ReissueInvitationResponse:
    idem_key = idempotency_key_header or payload.idempotency_key
    if not idem_key or not idem_key.strip():
        raise ApplicationError(
            code="INVALID_IDEMPOTENCY_KEY",
            message="Se requiere una clave de idempotencia en el header Idempotency-Key o en el cuerpo de la solicitud.",
            status_code=400,
        )

    await require_reissue_admin(session, actor)
    settings = get_settings()
    await get_rate_limiter().check_admin_action_limit(
        request,
        admin_id=actor.id,
        action="reissue_invitation",
        max_requests=settings.admin_rate_limit_reissue_requests,
        window_seconds=60,
    )
    if not settings.outbox_enabled and not settings.gmail_invitation_enabled:
        raise delivery_error()
    if settings.outbox_enabled:
        try:
            from app.infrastructure.outbox.service import OutboxService

            OutboxService.from_settings(settings)
        except Exception as err:
            raise ApplicationError(
                code="OUTBOX_CONFIGURATION_INVALID",
                message="La infraestructura de entrega diferida (Outbox) no está correctamente configurada.",
                status_code=503,
            ) from err
    try:
        result = await reissue_registration_invitation(
            session=session,
            request_id=request_id,
            actor=actor,
            idempotency_key=idem_key,
            reason=payload.reason,
            settings=settings,
        )
        await session.commit()
    except Exception:
        await session.rollback()
        raise

    msg = (
        "Invitación reemitida exitosamente."
        if not result.idempotent_replay
        else "Reemisión previa devuelta de manera idempotente."
    )
    return ReissueInvitationResponse(
        message=msg,
        request_id=result.request_id,
        invitation_id=result.invitation_id,
        reissue_count=result.reissue_count,
        idempotent_replay=result.idempotent_replay,
    )
