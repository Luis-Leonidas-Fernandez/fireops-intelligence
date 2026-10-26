"""Email delivery adapter abstraction for Transactional Outbox.

Provides:
- DeliveryStatus and DeliveryResult data structures.
- EmailDeliveryAdapter protocol.
- FakeEmailDeliveryAdapter for deterministic unit and concurrency testing.
- GmailApiAdapter for real-world production delivery (not invoked during test/audit).
"""

from __future__ import annotations

import base64
import enum
import logging
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Any, Protocol

import httpx

from app.config.settings import Settings, get_settings

logger = logging.getLogger("uvicorn.error")

TOKEN_URL = "https://oauth2.googleapis.com/token"
SEND_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"


class DeliveryStatus(str, enum.Enum):
    """Categorized status outcome of an email delivery attempt."""

    ACCEPTED = "ACCEPTED"
    TRANSIENT_ERROR = "TRANSIENT_ERROR"
    RATE_LIMITED = "RATE_LIMITED"
    PERMANENT_ERROR = "PERMANENT_ERROR"
    TIMEOUT = "TIMEOUT"
    AMBIGUOUS = "AMBIGUOUS"
    KEY_UNAVAILABLE = "KEY_UNAVAILABLE"


@dataclass(frozen=True, slots=True)
class DeliveryResult:
    """Standardized delivery result across all email providers."""

    status: DeliveryStatus
    provider_message_id: str | None = None
    error_code: str | None = None
    error_detail: str | None = None
    retry_after_seconds: float | None = None

    @classmethod
    def accepted(cls, message_id: str = "msg-ok") -> DeliveryResult:
        return cls(status=DeliveryStatus.ACCEPTED, provider_message_id=message_id)

    @classmethod
    def transient_error(cls, code: str, detail: str) -> DeliveryResult:
        return cls(status=DeliveryStatus.TRANSIENT_ERROR, error_code=code, error_detail=detail)

    @classmethod
    def rate_limited(cls, retry_after: float = 60.0, detail: str = "Rate limit exceeded") -> DeliveryResult:
        return cls(
            status=DeliveryStatus.RATE_LIMITED,
            error_code="RATE_LIMITED",
            error_detail=detail,
            retry_after_seconds=retry_after,
        )

    @classmethod
    def permanent_error(cls, code: str, detail: str) -> DeliveryResult:
        return cls(status=DeliveryStatus.PERMANENT_ERROR, error_code=code, error_detail=detail)

    @classmethod
    def timeout(cls, detail: str = "Request timed out") -> DeliveryResult:
        return cls(status=DeliveryStatus.TIMEOUT, error_code="TIMEOUT", error_detail=detail)

    @classmethod
    def key_unavailable(cls, key_id: str, detail: str = "") -> DeliveryResult:
        return cls(
            status=DeliveryStatus.KEY_UNAVAILABLE,
            error_code="KEY_UNAVAILABLE",
            error_detail=f"Decryption key '{key_id}' unavailable: {detail}".strip(),
            retry_after_seconds=60.0,
        )


class EmailDeliveryAdapter(Protocol):
    """Protocol defining provider-agnostic email delivery contract."""

    async def send_email(
        self,
        *,
        recipient_email: str,
        subject: str,
        body: str,
        idempotency_key: str,
    ) -> DeliveryResult:
        """Deliver an email or return a categorized DeliveryResult."""
        ...


class FakeEmailDeliveryAdapter:
    """Test fake adapter allowing deterministic control over delivery responses."""

    def __init__(self, default_status: DeliveryStatus = DeliveryStatus.ACCEPTED) -> None:
        self.default_status = default_status
        self.calls: list[dict[str, Any]] = []
        self._custom_responses: dict[str, DeliveryResult] = {}
        self._next_results: list[DeliveryResult] = []

    def queue_next_result(self, result: DeliveryResult) -> None:
        """Queue a specific result to return on the next call."""
        self._next_results.append(result)

    def set_result_for_recipient(self, recipient: str, result: DeliveryResult) -> None:
        self._custom_responses[recipient] = result

    async def send_email(
        self,
        *,
        recipient_email: str,
        subject: str,
        body: str,
        idempotency_key: str,
    ) -> DeliveryResult:
        call_record = {
            "recipient_email": recipient_email,
            "subject": subject,
            "body": body,
            "idempotency_key": idempotency_key,
        }
        self.calls.append(call_record)

        if self._next_results:
            return self._next_results.pop(0)

        if recipient_email in self._custom_responses:
            return self._custom_responses[recipient_email]

        if self.default_status == DeliveryStatus.ACCEPTED:
            return DeliveryResult.accepted(f"fake-msg-{len(self.calls)}")
        if self.default_status == DeliveryStatus.TIMEOUT:
            return DeliveryResult.timeout("Simulated WAN timeout")
        if self.default_status == DeliveryStatus.RATE_LIMITED:
            return DeliveryResult.rate_limited(retry_after=45.0)
        if self.default_status == DeliveryStatus.PERMANENT_ERROR:
            return DeliveryResult.permanent_error("RECIPIENT_REJECTED", "Simulated permanent reject")
        return DeliveryResult.transient_error("HTTP_503", "Simulated temporary outage")


class GmailApiAdapter:
    """Production Gmail API adapter with OAuth2 refresh and error classification.

    Preserves separation: not invoked during tests unless explicitly provided real tokens.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    async def send_email(
        self,
        *,
        recipient_email: str,
        subject: str,
        body: str,
        idempotency_key: str,
    ) -> DeliveryResult:
        settings = self._settings
        if not settings.gmail_invitation_enabled:
            return DeliveryResult.permanent_error(
                "SENDER_NOT_CONFIGURED", "Gmail integration is not configured or disabled"
            )

        message = EmailMessage()
        message["From"] = settings.gmail_sender_email
        message["To"] = recipient_email
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
                if exchange.status_code in {400, 401, 403}:
                    return DeliveryResult.permanent_error(
                        f"AUTH_{exchange.status_code}", "OAuth token exchange rejected"
                    )
                exchange.raise_for_status()
                payload = exchange.json()
                token = payload.get("access_token") if isinstance(payload, dict) else None
                if not isinstance(token, str) or not token:
                    return DeliveryResult.permanent_error(
                        "INVALID_TOKEN_RESPONSE", "Access token missing from Google response"
                    )

                delivery = await client.post(
                    SEND_URL,
                    headers={"Authorization": f"Bearer {token}"},
                    json={"raw": raw},
                )

                if delivery.status_code == 200:
                    data = delivery.json()
                    msg_id = data.get("id", "gmail-ok") if isinstance(data, dict) else "gmail-ok"
                    return DeliveryResult.accepted(str(msg_id))

                if delivery.status_code == 429:
                    retry_header = delivery.headers.get("Retry-After")
                    retry_val = float(retry_header) if retry_header and retry_header.isdigit() else 60.0
                    return DeliveryResult.rate_limited(retry_after=retry_val)

                if delivery.status_code in {400, 403, 404}:
                    return DeliveryResult.permanent_error(
                        f"GMAIL_{delivery.status_code}", "Gmail API rejected recipient or payload"
                    )

                if delivery.status_code >= 500:
                    return DeliveryResult.transient_error(
                        f"GMAIL_{delivery.status_code}", "Google server error"
                    )

                return DeliveryResult.transient_error(
                    f"HTTP_{delivery.status_code}", f"Unexpected HTTP status {delivery.status_code}"
                )

        except (httpx.ConnectTimeout, httpx.ReadTimeout) as err:
            return DeliveryResult.timeout(f"Timeout contacting Google: {err}")
        except (httpx.ConnectError, httpx.NetworkError) as err:
            return DeliveryResult.transient_error("NETWORK_ERROR", f"Network connectivity failure: {err}")
        except Exception as err:  # noqa: BLE001
            return DeliveryResult.transient_error("UNEXPECTED_DELIVERY_ERROR", str(err))
