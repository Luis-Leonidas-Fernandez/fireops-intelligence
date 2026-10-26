"""Transactional Outbox infrastructure module."""

from app.infrastructure.outbox.adapter import (
    DeliveryResult,
    DeliveryStatus,
    EmailDeliveryAdapter,
    FakeEmailDeliveryAdapter,
    GmailApiAdapter,
)
from app.infrastructure.outbox.backoff import (
    compute_next_attempt_at,
    sanitize_error_detail,
)
from app.infrastructure.outbox.crypto import (
    EncryptedPayload,
    Keyring,
    OutboxConfigurationError,
    OutboxCryptoError,
    OutboxKeyNotFoundError,
    OutboxTamperedError,
    decrypt_outbox_payload,
    encrypt_outbox_payload,
)
from app.infrastructure.outbox.dispatcher import OutboxDispatcher
from app.infrastructure.outbox.isolation import (
    EnvironmentProtectionError,
    extract_database_name,
    redact_database_url,
    validate_target_database,
)
from app.infrastructure.outbox.metrics import OutboxMetrics, QueueGauges
from app.infrastructure.outbox.models import OutboxEvent, OutboxStatus
from app.infrastructure.outbox.reaper import LeaseReaper
from app.infrastructure.outbox.service import OutboxService, get_outbox_service

__all__ = [
    "DeliveryResult",
    "DeliveryStatus",
    "EmailDeliveryAdapter",
    "EncryptedPayload",
    "EnvironmentProtectionError",
    "FakeEmailDeliveryAdapter",
    "GmailApiAdapter",
    "Keyring",
    "LeaseReaper",
    "OutboxConfigurationError",
    "OutboxCryptoError",
    "OutboxDispatcher",
    "OutboxEvent",
    "OutboxKeyNotFoundError",
    "OutboxMetrics",
    "OutboxService",
    "OutboxStatus",
    "OutboxTamperedError",
    "QueueGauges",
    "compute_next_attempt_at",
    "decrypt_outbox_payload",
    "encrypt_outbox_payload",
    "extract_database_name",
    "get_outbox_service",
    "redact_database_url",
    "sanitize_error_detail",
    "validate_target_database",
]
