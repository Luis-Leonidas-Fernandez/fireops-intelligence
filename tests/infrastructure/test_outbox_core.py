"""Unit tests for M-02A: Outbox Cryptographic Core and Model Specifications.

Zero database connections, zero external network calls, zero file mutations.
"""

import base64
import os

import pytest
from sqlalchemy import String, Table

from app.config.settings import get_settings
from app.infrastructure.outbox.crypto import (
    AES_256_KEY_BYTES,
    DEFAULT_FORMAT_VERSION,
    Keyring,
    OutboxConfigurationError,
    OutboxKeyNotFoundError,
    OutboxTamperedError,
    decrypt_outbox_payload,
    encrypt_outbox_payload,
)
from app.infrastructure.outbox.models import OutboxEvent, OutboxStatus


def generate_valid_key_b64() -> str:
    """Generate a random 32-byte base64-encoded key."""
    return base64.b64encode(os.urandom(AES_256_KEY_BYTES)).decode("ascii")


class TestOutboxCryptography:
    def test_encrypt_decrypt_roundtrip(self) -> None:
        key_b64 = generate_valid_key_b64()
        keyring = Keyring.from_raw(primary_key_b64=key_b64, primary_key_id="v1")

        payload = {
            "email": "bombero@ejemplo.test",
            "link": "https://control.bomberos.test/registro#invite=test-token-12345",
            "role": "SUPERVISOR",
        }

        encrypted = encrypt_outbox_payload(
            keyring=keyring,
            payload=payload,
            event_type="INVITATION_EMAIL",
            aggregate_id="invitation:42",
            idempotency_key="invitation:42:approval",
        )

        assert encrypted.format_version == DEFAULT_FORMAT_VERSION
        assert encrypted.key_id == "v1"
        assert encrypted.ciphertext_b64 != ""
        assert encrypted.nonce_b64 != ""

        decrypted = decrypt_outbox_payload(
            keyring=keyring,
            ciphertext_b64=encrypted.ciphertext_b64,
            nonce_b64=encrypted.nonce_b64,
            format_version=encrypted.format_version,
            key_id=encrypted.key_id,
            event_type="INVITATION_EMAIL",
            aggregate_id="invitation:42",
            idempotency_key="invitation:42:approval",
        )

        assert decrypted == payload

    def test_nonce_uniqueness_across_invocations(self) -> None:
        key_b64 = generate_valid_key_b64()
        keyring = Keyring.from_raw(primary_key_b64=key_b64)
        payload = {"data": "test"}

        nonces = set()
        for i in range(100):
            encrypted = encrypt_outbox_payload(
                keyring=keyring,
                payload=payload,
                event_type="INVITATION_EMAIL",
                aggregate_id=f"invitation:{i}",
                idempotency_key=f"invitation:{i}:approval",
            )
            nonces.add(encrypted.nonce_b64)

        assert len(nonces) == 100

    def test_tampered_ciphertext_rejected(self) -> None:
        key_b64 = generate_valid_key_b64()
        keyring = Keyring.from_raw(primary_key_b64=key_b64)
        payload = {"secret": "sensitive-token"}

        encrypted = encrypt_outbox_payload(
            keyring=keyring,
            payload=payload,
            event_type="INVITATION_EMAIL",
            aggregate_id="invitation:1",
            idempotency_key="invitation:1:approval",
        )

        raw_ct = bytearray(base64.b64decode(encrypted.ciphertext_b64))
        raw_ct[0] ^= 0xFF
        tampered_ct_b64 = base64.b64encode(raw_ct).decode("ascii")

        with pytest.raises(OutboxTamperedError):
            decrypt_outbox_payload(
                keyring=keyring,
                ciphertext_b64=tampered_ct_b64,
                nonce_b64=encrypted.nonce_b64,
                format_version=encrypted.format_version,
                key_id=encrypted.key_id,
                event_type="INVITATION_EMAIL",
                aggregate_id="invitation:1",
                idempotency_key="invitation:1:approval",
            )

    def test_tampered_aad_rejected(self) -> None:
        key_b64 = generate_valid_key_b64()
        keyring = Keyring.from_raw(primary_key_b64=key_b64)
        payload = {"secret": "sensitive-token"}

        encrypted = encrypt_outbox_payload(
            keyring=keyring,
            payload=payload,
            event_type="INVITATION_EMAIL",
            aggregate_id="invitation:1",
            idempotency_key="invitation:1:approval",
        )

        # Attempt to decrypt with different aggregate_id in AAD
        with pytest.raises(OutboxTamperedError):
            decrypt_outbox_payload(
                keyring=keyring,
                ciphertext_b64=encrypted.ciphertext_b64,
                nonce_b64=encrypted.nonce_b64,
                format_version=encrypted.format_version,
                key_id=encrypted.key_id,
                event_type="INVITATION_EMAIL",
                aggregate_id="invitation:2",  # Tampered!
                idempotency_key="invitation:1:approval",
            )

        # Attempt to decrypt with different event_type in AAD
        with pytest.raises(OutboxTamperedError):
            decrypt_outbox_payload(
                keyring=keyring,
                ciphertext_b64=encrypted.ciphertext_b64,
                nonce_b64=encrypted.nonce_b64,
                format_version=encrypted.format_version,
                key_id=encrypted.key_id,
                event_type="OTHER_EVENT",  # Tampered!
                aggregate_id="invitation:1",
                idempotency_key="invitation:1:approval",
            )

    def test_unknown_key_id_raises_outbox_key_not_found(self) -> None:
        key_b64 = generate_valid_key_b64()
        keyring = Keyring.from_raw(primary_key_b64=key_b64, primary_key_id="v1")
        payload = {"data": "test"}

        encrypted = encrypt_outbox_payload(
            keyring=keyring,
            payload=payload,
            event_type="INVITATION_EMAIL",
            aggregate_id="invitation:1",
            idempotency_key="invitation:1:approval",
        )

        with pytest.raises(OutboxKeyNotFoundError) as exc_info:
            decrypt_outbox_payload(
                keyring=keyring,
                ciphertext_b64=encrypted.ciphertext_b64,
                nonce_b64=encrypted.nonce_b64,
                format_version=encrypted.format_version,
                key_id="v99",  # Not in keyring
                event_type="INVITATION_EMAIL",
                aggregate_id="invitation:1",
                idempotency_key="invitation:1:approval",
            )
        assert exc_info.value.code == "OUTBOX_CRYPTO_KEY_NOT_FOUND"

    def test_invalid_key_length_rejected(self) -> None:
        short_key = base64.b64encode(b"short-16-bytes!").decode("ascii")
        with pytest.raises(OutboxConfigurationError, match="must be exactly 32 bytes"):
            Keyring.from_raw(primary_key_b64=short_key)

    def test_invalid_base64_key_rejected(self) -> None:
        with pytest.raises(OutboxConfigurationError, match="not valid base64"):
            Keyring.from_raw(primary_key_b64="not-valid-base64!@#$")

    def test_key_rotation_multi_keyring(self) -> None:
        k1_b64 = generate_valid_key_b64()
        k2_b64 = generate_valid_key_b64()

        # Step 1: Encrypt with old key v1
        keyring_v1 = Keyring.from_raw(primary_key_b64=k1_b64, primary_key_id="v1")
        payload = {"token": "secret-invitation-token-123"}
        encrypted_v1 = encrypt_outbox_payload(
            keyring=keyring_v1,
            payload=payload,
            event_type="INVITATION_EMAIL",
            aggregate_id="invitation:1",
            idempotency_key="invitation:1:approval",
        )

        # Step 2: Key rotation happens -> v2 is primary, v1 is secondary
        keyring_v2 = Keyring.from_raw(
            primary_key_b64=k2_b64,
            primary_key_id="v2",
            secondary_keys={"v1": k1_b64},
        )

        # Decrypt event created with v1 using keyring_v2
        decrypted_old = decrypt_outbox_payload(
            keyring=keyring_v2,
            ciphertext_b64=encrypted_v1.ciphertext_b64,
            nonce_b64=encrypted_v1.nonce_b64,
            format_version=encrypted_v1.format_version,
            key_id=encrypted_v1.key_id,
            event_type="INVITATION_EMAIL",
            aggregate_id="invitation:1",
            idempotency_key="invitation:1:approval",
        )
        assert decrypted_old == payload

        # Encrypt new event with keyring_v2 -> should use v2 as key_id
        encrypted_v2 = encrypt_outbox_payload(
            keyring=keyring_v2,
            payload={"token": "new-token-456"},
            event_type="INVITATION_EMAIL",
            aggregate_id="invitation:2",
            idempotency_key="invitation:2:approval",
        )
        assert encrypted_v2.key_id == "v2"

        # Step 3: Retire v1
        keyring_v3_retired = Keyring.from_raw(primary_key_b64=k2_b64, primary_key_id="v2")
        with pytest.raises(OutboxKeyNotFoundError):
            decrypt_outbox_payload(
                keyring=keyring_v3_retired,
                ciphertext_b64=encrypted_v1.ciphertext_b64,
                nonce_b64=encrypted_v1.nonce_b64,
                format_version=encrypted_v1.format_version,
                key_id=encrypted_v1.key_id,
                event_type="INVITATION_EMAIL",
                aggregate_id="invitation:1",
                idempotency_key="invitation:1:approval",
            )

    def test_keyring_repr_does_not_leak_key_material(self) -> None:
        key_b64 = generate_valid_key_b64()
        keyring = Keyring.from_raw(primary_key_b64=key_b64, primary_key_id="v1")
        repr_str = repr(keyring)

        assert key_b64 not in repr_str
        assert "active_key_id='v1'" in repr_str
        assert "available_keys=['v1']" in repr_str


class TestOutboxModel:
    def test_model_columns_and_constraints(self) -> None:
        table = OutboxEvent.__table__
        assert isinstance(table, Table)

        assert table.name == "outbox_events"
        assert "id" in table.c
        assert "idempotency_key" in table.c
        assert table.c.idempotency_key.unique is True

        # Check recipient_email is 320 characters
        assert isinstance(table.c.recipient_email.type, String)
        assert table.c.recipient_email.type.length == 320
        assert table.c.recipient_email.nullable is False

        # Check cryptographic envelope columns
        assert "payload_ciphertext" in table.c
        assert "payload_nonce" in table.c
        assert "payload_key_id" in table.c
        assert "payload_format_version" in table.c
        assert "payload_redacted" in table.c

        # Check state machine and lease columns
        assert "status" in table.c
        assert "attempt_count" in table.c
        assert "max_attempts" in table.c
        assert "lease_worker_id" in table.c
        assert "lease_token" in table.c
        assert "lease_expires_at" in table.c
        assert "provider_accepted_at" in table.c

        # Verify check constraint name and presence
        constraint_names = [c.name for c in table.constraints if hasattr(c, "name")]
        assert "ck_outbox_events_status" in constraint_names

        # Verify indexes
        index_names = [idx.name for idx in table.indexes]
        assert "ix_outbox_events_poll" in index_names
        assert "ix_outbox_events_lease_reap" in index_names
        assert "ix_outbox_events_aggregate" in index_names

    def test_outbox_status_enum_values(self) -> None:
        expected = {"PENDING", "PROCESSING", "RETRY", "DELIVERED", "DEAD_LETTER"}
        assert {s.value for s in OutboxStatus} == expected


class TestSettingsCompatibility:
    def test_settings_boot_without_outbox_key_by_default(self) -> None:
        settings = get_settings()
        # Default settings should load without raising
        assert settings.outbox_encryption_key_id == "v1"

    def test_settings_repr_hides_encryption_keys(self) -> None:
        settings = get_settings().model_copy(
            update={
                "outbox_encryption_key": "top-secret-key-material-do-not-leak",
                "outbox_secondary_encryption_keys": "secondary-secret-material",
            }
        )
        repr_str = repr(settings)
        assert "top-secret-key-material-do-not-leak" not in repr_str
        assert "secondary-secret-material" not in repr_str
