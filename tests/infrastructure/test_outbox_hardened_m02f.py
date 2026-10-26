"""Hardened security and adversarial verification tests for Transactional Outbox (Stage M-02F1).

Covers:
1. Missing encryption key recovery:
   - Key temporarily unavailable -> RETRY with KEY_UNAVAILABLE code.
   - Ciphertext preserved intact (no shredding of recoverable data).
   - Attempt count unconsumed (quota protected).
   - Successful delivery once keyring is restored.
2. Cryptographic authentication failure:
   - Tampered ciphertext / invalid tag -> DEAD_LETTER with CRYPTO_AUTH_FAILED.
   - Ciphertext preserved for forensic analysis without leaking secrets.
3. Adversarial recipient redirection defense:
   - Direct database tampering of recipient_email column.
   - AAD AEAD tag mismatch blocks delivery.
   - Zero emails sent to adversary address; zero tokens leaked.
4. Real worker subprocess crash & recovery:
   - Subprocess killed with SIGKILL while holding lease.
   - LeaseReaper recovers abandoned event to RETRY.
   - Second worker claims and delivers recovered event.
5. Production runner isolation guards:
   - Strict rejection of production database in non-production environments.
   - Rejection unless explicit --allow-production-db is configured.
"""

from __future__ import annotations

import base64
import subprocess
import sys
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config.settings import Settings, get_settings
from app.infrastructure.outbox.adapter import (
    FakeEmailDeliveryAdapter,
)
from app.infrastructure.outbox.crypto import (
    DEFAULT_FORMAT_VERSION,
    Keyring,
    encrypt_outbox_payload,
)
from app.infrastructure.outbox.dispatcher import OutboxDispatcher
from app.infrastructure.outbox.isolation import (
    EnvironmentProtectionError,
    validate_target_database,
)
from app.infrastructure.outbox.models import OutboxEvent
from app.infrastructure.outbox.reaper import LeaseReaper
from app.infrastructure.outbox.service import OutboxService

EPHEMERAL_DB_URL = (
    "postgresql+asyncpg://ephemeral_m02f_user:ephemeral_m02f_pass@127.0.0.1:55432/fireassets_ephemeral_m02f"
)

KEY_CURR_B64 = base64.b64encode(b"\x11" * 32).decode("ascii")
KEY_HIST_B64 = base64.b64encode(b"\x22" * 32).decode("ascii")


@pytest_asyncio.fixture(scope="module")
async def ephemeral_engine() -> AsyncIterator[AsyncEngine]:
    validate_target_database(EPHEMERAL_DB_URL, require_ephemeral=True)
    engine = create_async_engine(
        EPHEMERAL_DB_URL,
        pool_size=10,
        max_overflow=10,
        pool_pre_ping=True,
    )
    yield engine
    await engine.dispose()


@pytest.fixture(scope="module")
def session_factory(ephemeral_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(bind=ephemeral_engine, expire_on_commit=False)


@pytest.fixture
def hardened_settings() -> Settings:
    return get_settings().model_copy(
        update={
            "environment": "test",
            "database_url": EPHEMERAL_DB_URL,
            "outbox_enabled": True,
            "outbox_encryption_key": KEY_CURR_B64,
            "outbox_encryption_key_id": "v_curr",
            "outbox_secondary_encryption_keys": f'{{"v_hist": "{KEY_HIST_B64}"}}',
        }
    )


@pytest_asyncio.fixture(autouse=True)
async def clean_outbox_table(session_factory: async_sessionmaker[AsyncSession]) -> AsyncIterator[None]:
    async with session_factory() as session:
        await session.execute(text("TRUNCATE TABLE outbox_events CASCADE;"))
        await session.commit()
    yield
    async with session_factory() as session:
        await session.execute(text("TRUNCATE TABLE outbox_events CASCADE;"))
        await session.commit()


# =====================================================================
# 1. RECUPERACIÓN ANTE CLAVE CRIPTOGRÁFICA AUSENTE (Sección 1)
# =====================================================================


@pytest.mark.asyncio
async def test_missing_key_recovery_preserves_ciphertext_and_delivers_after_keyring_update(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Proves that a missing historic key leaves ciphertext intact in RETRY state and recovers upon key restoration."""
    # 1. Enqueue event encrypted with historic key 'v_hist'
    keyring_hist = Keyring.from_raw(KEY_HIST_B64, "v_hist")
    encrypted = encrypt_outbox_payload(
        keyring=keyring_hist,
        payload={"email": "applicant@fireops.test", "link": "http://127.0.0.1/invite=xyz"},
        event_type="auth.invitation.created",
        aggregate_id="hist-42",
        idempotency_key="idemp:hist:42",
        recipient_email="applicant@fireops.test",
        format_version=DEFAULT_FORMAT_VERSION,
    )

    async with session_factory() as session:
        event = OutboxEvent(
            event_type="auth.invitation.created",
            aggregate_type="registration_request",
            aggregate_id="hist-42",
            idempotency_key="idemp:hist:42",
            recipient_email="applicant@fireops.test",
            payload_ciphertext=encrypted.ciphertext_b64,
            payload_nonce=encrypted.nonce_b64,
            payload_key_id="v_hist",
            payload_format_version=encrypted.format_version,
            payload_redacted=False,
            status="PENDING",
            attempt_count=0,
            max_attempts=5,
            next_attempt_at=datetime.now(UTC) - timedelta(seconds=1),
        )
        session.add(event)
        await session.commit()
        event_id = event.id

    # 2. Dispatcher boots with ONLY key 'v_curr' (missing 'v_hist')
    keyring_curr_only = Keyring.from_raw(KEY_CURR_B64, "v_curr")
    adapter = FakeEmailDeliveryAdapter()
    dispatcher_curr = OutboxDispatcher(
        session_factory=session_factory,
        keyring=keyring_curr_only,
        adapter=adapter,
        worker_id="w-curr",
    )

    # Dispatch attempt must handle missing key gracefully
    dispatched = await dispatcher_curr.dispatch_next_event()
    assert dispatched is True

    # Invariants: Zero emails sent; event in RETRY; ciphertext intact; attempts unconsumed
    assert len(adapter.calls) == 0
    async with session_factory() as session:
        stored = await session.get(OutboxEvent, event_id)
        assert stored is not None
        assert stored.status == "RETRY"
        assert stored.last_error_code == "KEY_UNAVAILABLE"
        assert stored.payload_ciphertext == encrypted.ciphertext_b64  # NOT shredded!
        assert stored.payload_redacted is False
        assert stored.attempt_count == 0  # Unconsumed retry budget
        assert stored.lease_worker_id is None
        assert stored.lease_token is None

    # 3. Administrator / deployment updates keyring to include 'v_hist'
    keyring_full = Keyring.from_raw(
        primary_key_b64=KEY_CURR_B64,
        primary_key_id="v_curr",
        secondary_keys={"v_hist": KEY_HIST_B64},
    )
    dispatcher_recovered = OutboxDispatcher(
        session_factory=session_factory,
        keyring=keyring_full,
        adapter=adapter,
        worker_id="w-recovered",
    )

    # Simulate arrival of next retry window
    async with session_factory() as session:
        ev = await session.get(OutboxEvent, event_id)
        assert ev is not None
        ev.next_attempt_at = datetime.now(UTC) - timedelta(seconds=1)
        await session.commit()

    # Next dispatch successfully decrypts and delivers
    assert await dispatcher_recovered.dispatch_next_event() is True
    assert len(adapter.calls) == 1
    assert adapter.calls[0]["recipient_email"] == "applicant@fireops.test"

    # Invariants: DELIVERED, shredded, marked redacted
    async with session_factory() as session:
        delivered = await session.get(OutboxEvent, event_id)
        assert delivered is not None
        assert delivered.status == "DELIVERED"
        assert delivered.payload_ciphertext == ""
        assert delivered.payload_redacted is True


# =====================================================================
# 2. FALLO DE AUTENTICACIÓN CRIPTOGRÁFICA (Sección 1)
# =====================================================================


@pytest.mark.asyncio
async def test_crypto_auth_tampering_quarantines_to_dead_letter_and_preserves_forensic_ciphertext(
    session_factory: async_sessionmaker[AsyncSession],
    hardened_settings: Settings,
) -> None:
    """Proves that cryptographic authentication failure (tampered ciphertext) marks DEAD_LETTER without wiping ciphertext."""
    keyring = Keyring.from_raw(KEY_CURR_B64, "v_curr")
    encrypted = encrypt_outbox_payload(
        keyring=keyring,
        payload={"email": "tampered@example.test", "link": "http://127.0.0.1/link"},
        event_type="test.tamper",
        aggregate_id="t-1",
        idempotency_key="tamper:1",
        recipient_email="tampered@example.test",
    )

    # Tamper the ciphertext bytes
    raw_ct = bytearray(base64.b64decode(encrypted.ciphertext_b64))
    raw_ct[5] ^= 0xFF
    tampered_b64 = base64.b64encode(raw_ct).decode("ascii")

    async with session_factory() as session:
        event = OutboxEvent(
            event_type="test.tamper",
            aggregate_type="test",
            aggregate_id="t-1",
            idempotency_key="tamper:1",
            recipient_email="tampered@example.test",
            payload_ciphertext=tampered_b64,
            payload_nonce=encrypted.nonce_b64,
            payload_key_id="v_curr",
            payload_format_version=encrypted.format_version,
            payload_redacted=False,
            status="PENDING",
            attempt_count=0,
            max_attempts=5,
            next_attempt_at=datetime.now(UTC) - timedelta(seconds=1),
        )
        session.add(event)
        await session.commit()
        ev_id = event.id

    adapter = FakeEmailDeliveryAdapter()
    dispatcher = OutboxDispatcher(session_factory=session_factory, keyring=keyring, adapter=adapter)

    assert await dispatcher.dispatch_next_event() is True

    # Invariants:
    # 1. Zero emails sent
    assert len(adapter.calls) == 0
    # 2. Marked DEAD_LETTER with CRYPTO_AUTH_FAILED
    async with session_factory() as session:
        stored = await session.get(OutboxEvent, ev_id)
        assert stored is not None
        assert stored.status == "DEAD_LETTER"
        assert stored.last_error_code == "CRYPTO_AUTH_FAILED"
        # 3. Forensic preservation: ciphertext remains available for audit
        assert stored.payload_ciphertext == tampered_b64
        assert stored.payload_redacted is False


# =====================================================================
# 3. VINCULACIÓN CRIPTOGRÁFICA DEL DESTINATARIO (Sección 3)
# =====================================================================


@pytest.mark.asyncio
async def test_adversarial_recipient_redirection_blocked_by_aad_binding(
    session_factory: async_sessionmaker[AsyncSession],
    hardened_settings: Settings,
) -> None:
    """Adversarial test: Modifying recipient_email column in DB must fail AEAD authentication and send ZERO emails."""
    service = OutboxService.from_settings(hardened_settings)

    # 1. Create valid event intended for Alice
    async with session_factory() as session:
        ev = await service.enqueue_event(
            session=session,
            event_type="auth.invitation.created",
            aggregate_type="registration_request",
            aggregate_id="req-alice",
            recipient_email="alice@fireops.test",
            payload={
                "email": "alice@fireops.test",
                "link": "http://127.0.0.1:8000/registro#invite=alice-secret-token",
                "request_id": 1001,
            },
            idempotency_key="alice:invite:1001",
        )
        await session.commit()
        ev_id = ev.id

    # 2. Adversary executes SQL directly altering recipient_email to Mallory
    async with session_factory() as session:
        await session.execute(
            text("UPDATE outbox_events SET recipient_email = 'mallory@evil.test' WHERE id = :id"),
            {"id": ev_id},
        )
        await session.commit()

    # 3. Dispatcher attempts delivery
    keyring = Keyring.from_raw(KEY_CURR_B64, "v_curr")
    adapter = FakeEmailDeliveryAdapter()
    dispatcher = OutboxDispatcher(session_factory=session_factory, keyring=keyring, adapter=adapter)

    assert await dispatcher.dispatch_next_event() is True

    # 4. Critical security guarantees:
    # - ZERO emails sent to Mallory or anyone else
    assert len(adapter.calls) == 0
    # - Token never leaked
    for call in adapter.calls:
        assert "mallory@evil.test" not in call["recipient_email"]

    # - Event dead-lettered due to cryptographic AAD authentication failure
    async with session_factory() as session:
        stored = await session.get(OutboxEvent, ev_id)
        assert stored is not None
        assert stored.status == "DEAD_LETTER"
        assert stored.last_error_code == "CRYPTO_AUTH_FAILED"


# =====================================================================
# 4. RECUPERACIÓN TRAS CAÍDA REAL DEL WORKER SUBPROCESO (Sección 7)
# =====================================================================


WORKER_CHILD_SCRIPT = """
import asyncio
import os
import signal
import sys
from datetime import datetime, UTC, timedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.infrastructure.outbox.models import OutboxEvent

DB_URL = sys.argv[1]
EVENT_ID = int(sys.argv[2])

async def main():
    engine = create_async_engine(DB_URL)
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    async with session_factory() as session:
        stmt = (
            select(OutboxEvent)
            .where(OutboxEvent.id == EVENT_ID, OutboxEvent.status == "PENDING")
            .with_for_update()
        )
        ev = await session.scalar(stmt)
        if ev is None:
            sys.exit(1)
        ev.status = "PROCESSING"
        ev.lease_worker_id = "crashed-worker-proc"
        ev.lease_token = "fencing-token-crashed"
        ev.lease_expires_at = datetime.now(UTC) + timedelta(seconds=45)
        ev.attempt_count += 1
        await session.commit()

    # Notify parent via stdout that lease was claimed
    print("CLAIMED", flush=True)

    # Simulate work by sleeping until killed
    while True:
        await asyncio.sleep(1)

if __name__ == "__main__":
    asyncio.run(main())
"""


@pytest.mark.asyncio
async def test_real_worker_process_crash_and_lease_reaper_recovery(
    session_factory: async_sessionmaker[AsyncSession],
    hardened_settings: Settings,
    tmp_path: Any,
) -> None:
    """Proves that if an external worker process crashes (SIGKILL) while holding a lease, LeaseReaper recovers it cleanly."""
    service = OutboxService.from_settings(hardened_settings)

    # 1. Enqueue event in PostgreSQL
    async with session_factory() as session:
        ev = await service.enqueue_event(
            session=session,
            event_type="auth.invitation.created",
            aggregate_type="registration_request",
            aggregate_id="crash-77",
            recipient_email="crash_victim@example.test",
            payload={
                "email": "crash_victim@example.test",
                "link": "http://127.0.0.1/invite=crash77",
                "request_id": 77,
            },
            idempotency_key="idemp:crash:77",
        )
        await session.commit()
        ev_id = ev.id

    # 2. Write worker script to temp path
    worker_script_path = str(tmp_path / "worker_child.py")
    Path(worker_script_path).write_text(WORKER_CHILD_SCRIPT, encoding="utf-8")

    # 3. Launch independent worker process
    proc = subprocess.Popen(  # noqa: ASYNC220
        [sys.executable, worker_script_path, EPHEMERAL_DB_URL, str(ev_id)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    try:
        # Wait until child confirms event claim
        claimed_line = proc.stdout.readline().strip() if proc.stdout else ""
        assert claimed_line == "CLAIMED"

        # Verify DB shows event is locked by crashed-worker-proc
        async with session_factory() as session:
            ev_claimed = await session.get(OutboxEvent, ev_id)
            assert ev_claimed is not None
            assert ev_claimed.status == "PROCESSING"
            assert ev_claimed.lease_worker_id == "crashed-worker-proc"

        # 4. FORCIBLY TERMINATE (SIGKILL) worker process
        proc.kill()
        proc.wait(timeout=5)
        assert proc.poll() is not None

        # 5. Verify lease remains abandoned
        async with session_factory() as session:
            ev_abandoned = await session.get(OutboxEvent, ev_id)
            assert ev_abandoned is not None
            assert ev_abandoned.status == "PROCESSING"
            assert ev_abandoned.lease_worker_id == "crashed-worker-proc"
            # Simulate lease expiration without waiting 45 wall-clock seconds
            ev_abandoned.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
            await session.commit()

        # 6. Run LeaseReaper
        reaper = LeaseReaper(session_factory=session_factory)
        reaped_count = await reaper.reap_expired_leases()
        assert reaped_count == 1

        # 7. Verify event recovered to RETRY
        async with session_factory() as session:
            ev_reaped = await session.get(OutboxEvent, ev_id)
            assert ev_reaped is not None
            assert ev_reaped.status == "RETRY"
            assert ev_reaped.lease_worker_id is None
            assert ev_reaped.lease_token is None
            # Prepare for immediate pickup
            ev_reaped.next_attempt_at = datetime.now(UTC) - timedelta(seconds=1)
            await session.commit()

        # 8. Start fresh worker (dispatcher 2) to complete delivery
        keyring = Keyring.from_raw(KEY_CURR_B64, "v_curr")
        adapter = FakeEmailDeliveryAdapter()
        dispatcher2 = OutboxDispatcher(
            session_factory=session_factory,
            keyring=keyring,
            adapter=adapter,
            worker_id="worker-survivor",
        )

        assert await dispatcher2.dispatch_next_event() is True
        assert len(adapter.calls) == 1
        assert adapter.calls[0]["recipient_email"] == "crash_victim@example.test"

        # 9. Invariant: Delivered cleanly without corruption
        async with session_factory() as session:
            ev_final = await session.get(OutboxEvent, ev_id)
            assert ev_final is not None
            assert ev_final.status == "DELIVERED"
            assert ev_final.payload_ciphertext == ""
            assert ev_final.payload_redacted is True
    finally:
        if proc.poll() is None:
            proc.kill()


# =====================================================================
# 5. SEGURIDAD DEL RUNNER EN PRODUCCIÓN (Sección 5)
# =====================================================================


def test_runner_production_isolation_guards() -> None:
    """Verifies separation of test policy and operational policy for production databases."""
    prod_url = "postgresql+asyncpg://app_user:secret@localhost:5432/fireassets"
    test_db_url = "postgresql+asyncpg://app_user:secret@localhost:5432/fireassets_test"

    # In test environment, targeting fireassets fails closed
    with pytest.raises(EnvironmentProtectionError, match="is protected"):
        validate_target_database(prod_url, allow_production=False, environment="test")

    # In test environment, even if allow_production=True, environment must match 'production'
    with pytest.raises(EnvironmentProtectionError, match="requires environment='production'"):
        validate_target_database(prod_url, allow_production=True, environment="test")

    # In production environment with allow_production=True, fireassets is permitted
    assert (
        validate_target_database(prod_url, allow_production=True, environment="production")
        == "fireassets"
    )

    # fireassets_test is ALWAYS rejected for runners regardless of settings
    with pytest.raises(EnvironmentProtectionError, match="is protected"):
        validate_target_database(test_db_url, allow_production=True, environment="production")
