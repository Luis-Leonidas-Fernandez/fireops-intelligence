"""Administrative invitation reissuance workflow.

Provides secure, auditable, and persistent idempotent reissuance for expired,
revoked, or terminal delivery failed invitations, serialized with row-level locks
and bounded by persistent database constraints (max 3 reissues).
"""

from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import Settings, get_settings
from app.infrastructure.idempotency.service import (
    compute_request_hash,
    get_idempotency_record,
    record_idempotent_operation,
)
from app.infrastructure.outbox.models import OutboxEvent
from app.infrastructure.outbox.service import OutboxService
from app.modules.auth.invitations.links import public_link
from app.modules.auth.invitations.mail import delivery_error, send_invitation_email
from app.modules.auth.invitations.policy import require_reissue_admin
from app.modules.auth.invitations.service import INVITATION_TTL, token_digest
from app.modules.auth.models import Invitation, RegistrationRequest, Role, User
from app.modules.inventory.shared.models import AuditChange
from app.shared.errors.application_error import ApplicationError

logger = logging.getLogger("uvicorn.error")

MAX_REISSUES_PER_REQUEST = 3
IDEMPOTENCY_SCOPE_REISSUE = "invitation.reissue"


@dataclass(frozen=True, slots=True)
class ReissueResult:
    """Safe, non-sensitive result of an administrative invitation reissuance."""

    request_id: int
    invitation_id: int
    reissue_count: int
    idempotent_replay: bool


async def reissue_registration_invitation(
    session: AsyncSession,
    *,
    request_id: int,
    actor: User,
    idempotency_key: str,
    reason: str | None = None,
    correlation_id: UUID | None = None,
    settings: Settings | None = None,
) -> ReissueResult:
    """Reissue an invitation under strict administrative control.

    1. Authenticates and authorizes administrator (ADMINISTRADOR role required).
    2. Enforces fail-closed delivery check BEFORE modifying any persistent state.
    3. Validates and canonicalizes idempotency key and computes request hash.
    4. Checks persistent server-side idempotency registry for deterministic replays
       and parameter mismatch conflict detection (HTTP 409).
    5. Serializes reissues per request via SELECT FOR UPDATE on RegistrationRequest.
    6. Re-verifies idempotency under lock to handle concurrent race conditions.
    7. Enforces persistent maximum of 3 reissues per request.
    8. Validates eligibility: prior invitation must be expired or associate with DEAD_LETTER outbox event.
    9. Invalidates prior invitations and securely generates fresh token (hash persisted, raw token ephemeral).
    10. Enqueues authenticated, encrypted OutboxEvent (or legacy mailer if outbox disabled).
    11. Records immutable AuditChange in auditoria_cambios.
    12. Persists executed operation in idempotency_records within the same transaction.
    """
    # 1. Authorize actor
    await require_reissue_admin(session, actor)

    # 2. Fail-closed delivery mechanism verification (P1-A Remediation)
    if settings is None:
        settings = get_settings()
    if not settings.outbox_enabled and not settings.gmail_invitation_enabled:
        raise delivery_error()

    outbox_service: OutboxService | None = None
    if settings.outbox_enabled:
        try:
            outbox_service = OutboxService.from_settings(settings)
        except Exception as err:
            raise ApplicationError(
                code="OUTBOX_CONFIGURATION_INVALID",
                message="La infraestructura de entrega diferida (Outbox) no está correctamente configurada.",
                status_code=503,
            ) from err

    # 3. Validate idempotency key and compute canonical request hash (P1-B Remediation)
    clean_idempotency_key = (idempotency_key or "").strip()
    if not clean_idempotency_key or len(clean_idempotency_key) > 128:
        raise ApplicationError(
            code="INVALID_IDEMPOTENCY_KEY",
            message="Clave de idempotencia inválida (debe tener entre 1 y 128 caracteres).",
            status_code=400,
        )

    scope = IDEMPOTENCY_SCOPE_REISSUE
    agg_id = str(request_id)
    canonical_params = {
        "request_id": request_id,
        "reason": (reason or "").strip(),
    }
    req_hash = compute_request_hash(canonical_params)

    # 4. Check persistent historical idempotency registry (survives restarts, multiple reissues, and replays)
    existing_record = await get_idempotency_record(
        session,
        scope=scope,
        aggregate_id=agg_id,
        idempotency_key=clean_idempotency_key,
        for_update=False,
    )
    if existing_record is not None:
        if existing_record.request_hash != req_hash:
            raise ApplicationError(
                code="IDEMPOTENCY_CONFLICT",
                message="La clave de idempotencia ya fue utilizada previamente con parámetros distintos.",
                status_code=409,
            )
        data = existing_record.response_data
        return ReissueResult(
            request_id=data["request_id"],
            invitation_id=data["invitation_id"],
            reissue_count=data["reissue_count"],
            idempotent_replay=True,
        )

    # 5. Lock RegistrationRequest row to serialize mutations
    request_item = await session.scalar(
        select(RegistrationRequest)
        .where(RegistrationRequest.id == request_id)
        .with_for_update()
    )
    if request_item is None:
        raise ApplicationError(
            code="REGISTRATION_REQUEST_NOT_FOUND",
            message="La solicitud de registro no existe.",
            status_code=404,
        )

    # Verify request status
    if request_item.status != "approved":
        raise ApplicationError(
            code="REGISTRATION_REQUEST_NOT_APPROVED",
            message="Solo se pueden reemitir invitaciones para solicitudes aprobadas.",
            status_code=400,
        )

    # 6. Re-check idempotency under lock to handle concurrent race conditions
    locked_record = await get_idempotency_record(
        session,
        scope=scope,
        aggregate_id=agg_id,
        idempotency_key=clean_idempotency_key,
        for_update=True,
    )
    if locked_record is not None:
        if locked_record.request_hash != req_hash:
            raise ApplicationError(
                code="IDEMPOTENCY_CONFLICT",
                message="La clave de idempotencia ya fue utilizada previamente con parámetros distintos.",
                status_code=409,
            )
        data = locked_record.response_data
        return ReissueResult(
            request_id=data["request_id"],
            invitation_id=data["invitation_id"],
            reissue_count=data["reissue_count"],
            idempotent_replay=True,
        )

    # Legacy request-level idempotency fallback (for records predating idempotency_records)
    if request_item.last_reissue_idempotency_key == clean_idempotency_key:
        inv_id = request_item.current_invitation_id
        if inv_id is None:
            latest = await session.scalar(
                select(Invitation.id)
                .where(Invitation.email == request_item.email)
                .order_by(Invitation.created_at.desc(), Invitation.id.desc())
                .limit(1)
            )
            inv_id = latest or 0
        return ReissueResult(
            request_id=request_item.id,
            invitation_id=inv_id,
            reissue_count=request_item.reissue_count,
            idempotent_replay=True,
        )

    # 7. Check persistent reissue ceiling
    current_reissue_count = request_item.reissue_count or 0
    if current_reissue_count >= MAX_REISSUES_PER_REQUEST:
        raise ApplicationError(
            code="REISSUE_LIMIT_EXCEEDED",
            message=f"Se ha alcanzado el límite máximo de {MAX_REISSUES_PER_REQUEST} reemisiones para esta solicitud.",
            status_code=429,
        )

    # 8. Verify user is not already registered
    existing_user = await session.scalar(
        select(User.id).where(User.email == request_item.email)
    )
    if existing_user is not None:
        raise ApplicationError(
            code="INVITATION_ALREADY_CONSUMED",
            message="El usuario ya completó su registro en el sistema.",
            status_code=409,
        )

    # 9. Lock prior invitations and verify eligibility
    prior_invitations = (
        await session.scalars(
            select(Invitation)
            .where(Invitation.email == request_item.email)
            .order_by(Invitation.created_at.desc(), Invitation.id.desc())
            .with_for_update()
        )
    ).all()

    for inv in prior_invitations:
        if inv.used_at is not None:
            raise ApplicationError(
                code="INVITATION_ALREADY_CONSUMED",
                message="La invitación anterior ya fue consumida.",
                status_code=409,
            )

    now = datetime.now(UTC)
    latest_inv = prior_invitations[0] if prior_invitations else None
    is_expired = latest_inv is None or latest_inv.expires_at <= now
    is_dead_letter = False

    if latest_inv is not None:
        outbox_event = await session.scalar(
            select(OutboxEvent)
            .where(
                OutboxEvent.aggregate_id == str(request_item.id),
                OutboxEvent.recipient_email == request_item.email,
            )
            .order_by(OutboxEvent.created_at.desc(), OutboxEvent.id.desc())
            .limit(1)
        )
        if outbox_event is not None and outbox_event.status == "DEAD_LETTER":
            is_dead_letter = True

    if not is_expired and not is_dead_letter:
        raise ApplicationError(
            code="INVITATION_NOT_ELIGIBLE",
            message="La invitación previa aún no ha expirado ni registra un fallo terminal de entrega.",
            status_code=400,
        )

    # 10. Invalidate all prior invitations (revocation via timestamp ceiling)
    for inv in prior_invitations:
        inv.expires_at = min(inv.expires_at, now)

    # 11. Generate fresh cryptographic token & hash
    role = await session.scalar(
        select(Role).where(Role.nombre == "SUPERVISOR", Role.activo.is_(True))
    )
    if role is None:
        raise ApplicationError(
            code="ROLE_NOT_FOUND",
            message="Rol SUPERVISOR no encontrado o inactivo.",
            status_code=500,
        )

    token = secrets.token_urlsafe(48)
    token_hash = token_digest(token)
    new_expires_at = now + INVITATION_TTL

    new_invitation = Invitation(
        email=request_item.email,
        token_hash=token_hash,
        rol_id=role.id,
        invited_by_id=actor.id,
        expires_at=new_expires_at,
    )
    session.add(new_invitation)
    await session.flush()

    # 12. Update RegistrationRequest
    prior_count = request_item.reissue_count or 0
    request_item.reissue_count = prior_count + 1
    request_item.last_reissue_idempotency_key = clean_idempotency_key
    request_item.current_invitation_id = new_invitation.id

    # 13. Delivery execution (Deterministic policy without double sending)
    if settings.outbox_enabled:
        assert outbox_service is not None
        link = public_link(settings, f"/registro#invite={token}")
        await outbox_service.enqueue_event(
            session=session,
            event_type="auth.invitation.reissued",
            aggregate_type="registration_request",
            aggregate_id=str(request_item.id),
            recipient_email=request_item.email,
            payload={
                "email": request_item.email,
                "link": link,
                "request_id": request_item.id,
                "token_hash": token_hash,
                "expires_at": new_expires_at.isoformat(),
                "reissue_count": request_item.reissue_count,
            },
            idempotency_key=f"invitation:reissue:{request_item.id}:{request_item.reissue_count}:{clean_idempotency_key}",
        )
    else:
        # Legacy direct delivery (settings.gmail_invitation_enabled must be True here)
        await send_invitation_email(
            request_item.email,
            public_link(settings, f"/registro#invite={token}"),
        )

    # 14. Record audit entry in auditoria_cambios
    op_uuid = correlation_id or uuid4()
    audit_entry = AuditChange(
        operacion_id=op_uuid,
        entidad_tipo="USUARIO",
        entidad_id=request_item.id,
        accion="MODIFICACION",
        datos_anteriores={
            "registration_request_id": request_item.id,
            "reissue_count": prior_count,
            "previous_invitation_id": latest_inv.id if latest_inv else None,
            "email": request_item.email,
        },
        datos_nuevos={
            "registration_request_id": request_item.id,
            "reissue_count": request_item.reissue_count,
            "new_invitation_id": new_invitation.id,
            "idempotency_key": clean_idempotency_key,
            "expires_at": new_expires_at.isoformat(),
        },
        motivo=reason or "Reemisión administrativa de invitación",
        realizado_por_usuario_id=actor.id,
    )
    session.add(audit_entry)

    # 15. Persist operation in persistent idempotency registry
    response_payload = {
        "request_id": request_item.id,
        "invitation_id": new_invitation.id,
        "reissue_count": request_item.reissue_count,
    }
    await record_idempotent_operation(
        session,
        scope=scope,
        aggregate_id=agg_id,
        idempotency_key=clean_idempotency_key,
        request_hash=req_hash,
        response_status=200,
        response_data=response_payload,
        expires_at=None,
    )

    return ReissueResult(
        request_id=request_item.id,
        invitation_id=new_invitation.id,
        reissue_count=request_item.reissue_count,
        idempotent_replay=False,
    )
