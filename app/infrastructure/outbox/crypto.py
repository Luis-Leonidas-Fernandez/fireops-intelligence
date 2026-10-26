"""Cryptographic core for Outbox payload authenticated encryption.

Implements AES-256-GCM AEAD encryption with versioned Keyring support,
Additional Authenticated Data (AAD) binding to event metadata,
and strict rejection of tampered payloads.
"""

from __future__ import annotations

import base64
import binascii
import json
import os
from dataclasses import dataclass
from typing import Any

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.shared.errors.application_error import ApplicationError

DEFAULT_FORMAT_VERSION = 3
SUPPORTED_FORMAT_VERSIONS = frozenset({1, 2, 3})
AES_256_KEY_BYTES = 32
GCM_NONCE_BYTES = 12


class OutboxCryptoError(ApplicationError):
    """Base error for all outbox cryptographic operations."""

    def __init__(self, code: str, message: str, status_code: int = 500) -> None:
        super().__init__(code=code, message=message, status_code=status_code)


class OutboxConfigurationError(OutboxCryptoError):
    """Raised when cryptographic configuration or key material is invalid or missing."""

    def __init__(self, message: str) -> None:
        super().__init__(
            code="OUTBOX_CRYPTO_CONFIGURATION_ERROR",
            message=message,
            status_code=500,
        )


class OutboxKeyNotFoundError(OutboxCryptoError):
    """Raised when the payload's key_id is not present in the keyring."""

    def __init__(self, key_id: str) -> None:
        super().__init__(
            code="OUTBOX_CRYPTO_KEY_NOT_FOUND",
            message=f"No cryptographic key found for key_id '{key_id}'",
            status_code=500,
        )


class OutboxTamperedError(OutboxCryptoError):
    """Raised when authentication tag verification fails (ciphertext or AAD modified)."""

    def __init__(self, message: str = "Payload authentication failed: data may be corrupted or tampered") -> None:
        super().__init__(
            code="OUTBOX_PAYLOAD_TAMPERED",
            message=message,
            status_code=500,
        )


@dataclass(frozen=True, slots=True)
class EncryptedPayload:
    """Structured container for encrypted outbox payload components."""

    ciphertext_b64: str
    nonce_b64: str
    format_version: int
    key_id: str


def _decode_key_bytes(raw_b64: str, identifier: str) -> bytes:
    """Decode and validate a 32-byte base64-encoded key without leaking material."""
    try:
        key_bytes = base64.b64decode(raw_b64, validate=True)
    except (binascii.Error, ValueError) as err:
        raise OutboxConfigurationError(
            f"Cryptographic key for '{identifier}' is not valid base64."
        ) from err

    if len(key_bytes) != AES_256_KEY_BYTES:
        raise OutboxConfigurationError(
            f"Cryptographic key for '{identifier}' must be exactly {AES_256_KEY_BYTES} bytes (256 bits), "
            f"got {len(key_bytes)} bytes."
        )
    return key_bytes


class Keyring:
    """Versioned cryptographic keyring holding an active key and authorized historical keys."""

    def __init__(self, primary_key_id: str, keys: dict[str, bytes]) -> None:
        if not primary_key_id:
            raise OutboxConfigurationError("primary_key_id must not be empty.")
        if primary_key_id not in keys:
            raise OutboxConfigurationError(
                f"primary_key_id '{primary_key_id}' must exist in the keys dictionary."
            )
        for k_id, k_bytes in keys.items():
            if not isinstance(k_bytes, (bytes, bytearray)) or len(k_bytes) != AES_256_KEY_BYTES:
                raise OutboxConfigurationError(
                    f"Key '{k_id}' in keyring must be exactly {AES_256_KEY_BYTES} bytes."
                )

        self._primary_key_id = primary_key_id
        self._keys = dict(keys)

    @property
    def primary_key_id(self) -> str:
        return self._primary_key_id

    @property
    def primary_key(self) -> bytes:
        return self._keys[self._primary_key_id]

    def get_key(self, key_id: str) -> bytes | None:
        return self._keys.get(key_id)

    @property
    def key_ids(self) -> list[str]:
        return sorted(self._keys.keys())

    def __repr__(self) -> str:
        return f"<Keyring active_key_id={self._primary_key_id!r} available_keys={self.key_ids!r}>"

    @classmethod
    def from_raw(
        cls,
        primary_key_b64: str,
        primary_key_id: str = "v1",
        secondary_keys: dict[str, str] | str | None = None,
    ) -> Keyring:
        """Construct Keyring from base64 strings."""
        if not primary_key_b64:
            raise OutboxConfigurationError("Primary encryption key must not be empty.")

        primary_bytes = _decode_key_bytes(primary_key_b64, primary_key_id)
        keys_dict: dict[str, bytes] = {primary_key_id: primary_bytes}

        if secondary_keys:
            if isinstance(secondary_keys, str):
                # Format: either JSON {"v0": "b64..."} or comma-separated "v0:b64...,v-pre:b64..."
                secondary_keys = secondary_keys.strip()
                if secondary_keys.startswith("{"):
                    try:
                        parsed = json.loads(secondary_keys)
                        if not isinstance(parsed, dict):
                            raise TypeError("Secondary keys JSON must be an object")
                        secondary_dict = {str(k): str(v) for k, v in parsed.items()}
                    except Exception as err:
                        raise OutboxConfigurationError(
                            "Failed to parse secondary encryption keys JSON."
                        ) from err
                else:
                    secondary_dict = {}
                    for item in secondary_keys.split(","):
                        item = item.strip()
                        if not item:
                            continue
                        if ":" not in item:
                            raise OutboxConfigurationError(
                                "Secondary keys must be in 'key_id:base64_key' format."
                            )
                        kid, b64_val = item.split(":", 1)
                        secondary_dict[kid.strip()] = b64_val.strip()
            elif isinstance(secondary_keys, dict):
                secondary_dict = {str(k): str(v) for k, v in secondary_keys.items()}
            else:
                raise OutboxConfigurationError(
                    "Secondary encryption keys must be a dict or string."
                )

            for kid, b64_val in secondary_dict.items():
                if kid not in keys_dict:
                    keys_dict[kid] = _decode_key_bytes(b64_val, kid)

        return cls(primary_key_id=primary_key_id, keys=keys_dict)


def build_aad(
    format_version: int,
    key_id: str,
    event_type: str,
    aggregate_id: str,
    idempotency_key: str,
    recipient_email: str | None = None,
) -> bytes:
    """Build canonical Additional Authenticated Data binding payload to event identity.

    Version 1 binds: format_version:key_id:event_type:aggregate_id:idempotency_key
    Version 2 binds: format_version:key_id:event_type:aggregate_id:idempotency_key:recipient_email
    Version 3 binds: 3:structured_fields with explicit lengths preventing delimiter injection.
    """
    if format_version == 1:
        return f"{format_version}:{key_id}:{event_type}:{aggregate_id}:{idempotency_key}".encode()
    elif format_version == 2:
        norm_recipient = (recipient_email or "").strip().lower()
        return (
            f"{format_version}:{key_id}:{event_type}:{aggregate_id}:{idempotency_key}:{norm_recipient}".encode()
        )
    elif format_version == 3:
        norm_recipient = (recipient_email or "").strip().lower()
        fields = [
            ("key_id", key_id),
            ("event_type", event_type),
            ("aggregate_id", aggregate_id),
            ("idempotency_key", idempotency_key),
            ("recipient_email", norm_recipient),
        ]
        parts: list[bytes] = [b"3", str(len(fields)).encode("ascii")]
        for name, val in fields:
            name_b = name.encode("utf-8")
            val_b = str(val).encode("utf-8")
            parts.extend([
                str(len(name_b)).encode("ascii"),
                name_b,
                str(len(val_b)).encode("ascii"),
                val_b,
            ])
        return b":".join(parts)
    raise OutboxCryptoError(
        code="OUTBOX_UNSUPPORTED_VERSION",
        message=f"Unsupported payload format version: {format_version}",
    )


def encrypt_outbox_payload(
    keyring: Keyring,
    payload: dict[str, Any],
    event_type: str,
    aggregate_id: str,
    idempotency_key: str,
    recipient_email: str | None = None,
    format_version: int = DEFAULT_FORMAT_VERSION,
) -> EncryptedPayload:
    """Encrypt a dictionary payload using AES-256-GCM authenticated with AAD."""
    if format_version not in SUPPORTED_FORMAT_VERSIONS:
        raise OutboxConfigurationError(f"Unsupported format_version {format_version}")

    try:
        plaintext = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    except (TypeError, ValueError) as err:
        raise OutboxCryptoError(
            code="OUTBOX_PAYLOAD_SERIALIZATION_ERROR",
            message="Payload could not be serialized to JSON",
        ) from err

    nonce = os.urandom(GCM_NONCE_BYTES)
    aad = build_aad(
        format_version=format_version,
        key_id=keyring.primary_key_id,
        event_type=event_type,
        aggregate_id=aggregate_id,
        idempotency_key=idempotency_key,
        recipient_email=recipient_email,
    )

    aesgcm = AESGCM(keyring.primary_key)
    ciphertext_and_tag = aesgcm.encrypt(nonce, plaintext, aad)

    return EncryptedPayload(
        ciphertext_b64=base64.b64encode(ciphertext_and_tag).decode("ascii"),
        nonce_b64=base64.b64encode(nonce).decode("ascii"),
        format_version=format_version,
        key_id=keyring.primary_key_id,
    )


def decrypt_outbox_payload(
    keyring: Keyring,
    ciphertext_b64: str,
    nonce_b64: str,
    format_version: int,
    key_id: str,
    event_type: str,
    aggregate_id: str,
    idempotency_key: str,
    recipient_email: str | None = None,
) -> dict[str, Any]:
    """Decrypt and verify an outbox payload using the versioned keyring and AAD."""
    key = keyring.get_key(key_id)
    if key is None:
        raise OutboxKeyNotFoundError(key_id)

    if format_version not in SUPPORTED_FORMAT_VERSIONS:
        raise OutboxCryptoError(
            code="OUTBOX_UNSUPPORTED_VERSION",
            message=f"Unsupported payload format version: {format_version}",
        )

    try:
        nonce = base64.b64decode(nonce_b64, validate=True)
    except Exception as err:
        raise OutboxTamperedError("Invalid nonce encoding") from err

    if len(nonce) != GCM_NONCE_BYTES:
        raise OutboxTamperedError(
            f"Invalid nonce length: expected {GCM_NONCE_BYTES} bytes, got {len(nonce)}"
        )

    try:
        ciphertext_and_tag = base64.b64decode(ciphertext_b64, validate=True)
    except Exception as err:
        raise OutboxTamperedError("Invalid ciphertext encoding") from err

    if len(ciphertext_and_tag) < 16:
        raise OutboxTamperedError("Ciphertext length too short to contain authentication tag")

    aad = build_aad(
        format_version=format_version,
        key_id=key_id,
        event_type=event_type,
        aggregate_id=aggregate_id,
        idempotency_key=idempotency_key,
        recipient_email=recipient_email,
    )

    aesgcm = AESGCM(key)
    try:
        plaintext = aesgcm.decrypt(nonce, ciphertext_and_tag, aad)
    except InvalidTag as err:
        raise OutboxTamperedError() from err

    try:
        result = json.loads(plaintext.decode("utf-8"))
        if not isinstance(result, dict):
            raise TypeError("Decrypted payload is not a dict")
    except Exception as err:
        raise OutboxCryptoError(
            code="OUTBOX_PAYLOAD_DESERIALIZATION_ERROR",
            message="Decrypted payload is not valid JSON dictionary",
        ) from err

    # Cryptographic & integrity defense: cross-check recipient inside payload with recipient_email
    payload_recipient = result.get("email") or result.get("recipient_email")
    if payload_recipient is not None and recipient_email is not None:
        norm_payload = str(payload_recipient).strip().lower()
        norm_expected = str(recipient_email).strip().lower()
        if norm_payload != norm_expected:
            raise OutboxTamperedError(
                "Recipient email in authenticated payload does not match target recipient."
            )

    return result
