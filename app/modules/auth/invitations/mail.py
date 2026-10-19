"""Minimal Gmail API adapter: refresh sender token, send plain-text MIME."""

import base64
from email.message import EmailMessage

import httpx

from app.config.settings import get_settings
from app.shared.errors.application_error import ApplicationError

TOKEN_URL = "https://oauth2.googleapis.com/token"
SEND_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"


def delivery_error() -> ApplicationError:
    return ApplicationError(
        code="INVITATION_DELIVERY_UNAVAILABLE",
        message="No pudimos enviar la invitación. Intentá nuevamente.",
        status_code=503,
    )


async def send_registration_notice(email: str, link: str) -> None:
    await _send_email(
        email,
        "Nueva solicitud de registro",
        f"Hay una nueva solicitud de registro en Fire Control.\n\nRevisala desde la aplicación: {link}\n\nDebés iniciar sesión como administrador para aprobarla o rechazarla.\n",
    )


async def send_invitation_email(email: str, link: str) -> None:
    await _send_email(
        email,
        "Registro aprobado en Fire Control",
        f"Tu solicitud fue aprobada.\n\nCreá tu cuenta desde este enlace (válido por 48 horas):\n{link}\n\nSi no esperabas este mensaje, ignoralo.\n",
    )


async def _send_email(email: str, subject: str, body: str) -> None:
    settings = get_settings()
    if not settings.gmail_invitation_enabled:
        raise delivery_error()
    message = EmailMessage()
    message["From"] = settings.gmail_sender_email
    message["To"] = email
    message["Subject"] = subject
    message.set_content(body)
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            exchange = await client.post(
                TOKEN_URL,
                data={
                    "client_id": settings.google_client_id,
                    "client_secret": settings.google_client_secret,
                    "refresh_token": settings.gmail_refresh_token,
                    "grant_type": "refresh_token",
                },
            )
            exchange.raise_for_status()
            payload = exchange.json()
            token = payload.get("access_token") if isinstance(payload, dict) else None
            if not isinstance(token, str) or not token:
                raise delivery_error()
            delivery = await client.post(
                SEND_URL,
                headers={"Authorization": f"Bearer {token}"},
                json={"raw": raw},
            )
            delivery.raise_for_status()
    except (httpx.HTTPError, ValueError, TypeError) as error:
        raise delivery_error() from error
