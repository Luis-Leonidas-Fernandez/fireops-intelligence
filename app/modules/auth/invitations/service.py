"""Invitation lifecycle independent of HTTP and mail delivery."""

import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.outbox.models import OutboxEvent
from app.modules.auth.models import Invitation, RegistrationRequest, Role, User
from app.shared.errors.application_error import ApplicationError
from app.shared.errors.conflict_error import ConflictError

INVITATION_TTL = timedelta(hours=48)
ALLOWED_ROLES = frozenset({"SUPERVISOR"})
MAX_REISSUES_PER_REQUEST = 3
InvitationStatus = Literal["active", "consumed", "expired", "revoked"]


@dataclass(frozen=True, slots=True)
class IssuedInvitationItem:
    id: int
    email: str
    role: str
    created_at: datetime
    expires_at: datetime
    used_at: datetime | None
    status: InvitationStatus
    registration_request_id: int | None
    reissue_count: int
    can_reissue: bool


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def invitation_error() -> ApplicationError:
    return ApplicationError(
        code="INVITATION_INVALID",
        message="La invitación no es válida o ya venció.",
        status_code=403,
    )


async def create_invitation(
    session: AsyncSession, email: str, role_name: str, actor_id: int
) -> tuple[Invitation, str]:
    role = await session.scalar(
        select(Role).where(Role.nombre == role_name, Role.activo.is_(True))
    )
    if role is None or role_name not in ALLOWED_ROLES:
        raise invitation_error()
    if await session.scalar(select(User.id).where(User.email == email)) is not None:
        raise ConflictError(
            code="EMAIL_ALREADY_REGISTERED", message="Ese correo ya está registrado."
        )
    token = secrets.token_urlsafe(48)
    invitation = Invitation(
        email=email,
        token_hash=token_digest(token),
        rol_id=role.id,
        invited_by_id=actor_id,
        expires_at=datetime.now(UTC) + INVITATION_TTL,
    )
    session.add(invitation)
    await session.flush()
    return invitation, token


async def lock_invitation(
    session: AsyncSession, email: str, token: str | None
) -> Invitation:
    if not token or len(token) > 256:
        raise invitation_error()
    return await lock_invitation_digest(session, email, token_digest(token))


async def lock_invitation_digest(
    session: AsyncSession, email: str, digest: str | None
) -> Invitation:
    if not digest or len(digest) != 64:
        raise invitation_error()
    invitation = await session.scalar(
        select(Invitation).where(Invitation.token_hash == digest).with_for_update()
    )
    now = datetime.now(UTC)
    if (
        invitation is None
        or invitation.email != email
        or invitation.used_at is not None
        or invitation.expires_at <= now
    ):
        raise invitation_error()
    role = await session.get(Role, invitation.rol_id)
    if role is None or not role.activo or role.nombre not in ALLOWED_ROLES:
        raise invitation_error()
    return invitation


def consume_invitation(invitation: Invitation) -> None:
    invitation.used_at = datetime.now(UTC)


async def list_issued_invitations(
    session: AsyncSession,
) -> list[IssuedInvitationItem]:
    """Return bounded list of issued invitations with deterministic lifecycle status."""
    rows = (
        await session.execute(
            select(Invitation, Role.nombre)
            .join(Role, Role.id == Invitation.rol_id)
            .order_by(Invitation.created_at.desc(), Invitation.id.desc())
            .limit(100)
        )
    ).all()
    if not rows:
        return []

    emails = {inv.email for inv, _ in rows}
    requests_by_email: dict[str, RegistrationRequest] = {
        req.email: req
        for req in (
            await session.scalars(
                select(RegistrationRequest).where(
                    RegistrationRequest.email.in_(emails)
                )
            )
        ).all()
    }
    registered_emails: set[str] = set(
        (
            await session.scalars(
                select(User.email).where(User.email.in_(emails))
            )
        ).all()
    )

    approved_request_ids = [
        str(req.id)
        for req in requests_by_email.values()
        if req.status == "approved"
    ]
    dead_letter_request_ids: set[int] = set()
    if approved_request_ids:
        outbox_events = (
            await session.scalars(
                select(OutboxEvent)
                .where(OutboxEvent.aggregate_id.in_(approved_request_ids))
                .order_by(OutboxEvent.created_at.desc(), OutboxEvent.id.desc())
            )
        ).all()
        seen_aggregates: set[tuple[str, str]] = set()
        for ev in outbox_events:
            key = (ev.aggregate_id, ev.recipient_email)
            if key not in seen_aggregates:
                seen_aggregates.add(key)
                req_obj = requests_by_email.get(ev.recipient_email)
                if (
                    req_obj is not None
                    and str(req_obj.id) == ev.aggregate_id
                    and ev.status == "DEAD_LETTER"
                ):
                    dead_letter_request_ids.add(req_obj.id)

    now = datetime.now(UTC)
    legacy_matched_emails: set[str] = set()
    result: list[IssuedInvitationItem] = []

    for inv, role_name in rows:
        rr = requests_by_email.get(inv.email)
        is_current_invitation = False
        if rr is not None and rr.status == "approved":
            if rr.current_invitation_id is not None:
                is_current_invitation = inv.id == rr.current_invitation_id
            elif inv.email not in legacy_matched_emails and (
                rr.reviewed_at is None or inv.created_at >= rr.reviewed_at
            ):
                is_current_invitation = True
                legacy_matched_emails.add(inv.email)

        if inv.used_at is not None:
            inv_status: InvitationStatus = "consumed"
        elif not is_current_invitation:
            inv_status = "revoked"
        elif inv.expires_at > now:
            inv_status = "active"
        else:
            inv_status = "expired"

        reissue_count = (rr.reissue_count or 0) if rr is not None else 0
        is_expired = inv.expires_at <= now
        is_dead_letter = rr is not None and rr.id in dead_letter_request_ids
        can_reissue = bool(
            is_current_invitation
            and rr is not None
            and rr.status == "approved"
            and inv.used_at is None
            and inv.email not in registered_emails
            and (is_expired or is_dead_letter)
            and reissue_count < MAX_REISSUES_PER_REQUEST
        )

        result.append(
            IssuedInvitationItem(
                id=inv.id,
                email=inv.email,
                role=role_name,
                created_at=inv.created_at,
                expires_at=inv.expires_at,
                used_at=inv.used_at,
                status=inv_status,
                registration_request_id=rr.id if rr is not None else None,
                reissue_count=reissue_count,
                can_reissue=can_reissue,
            )
        )

    return result
