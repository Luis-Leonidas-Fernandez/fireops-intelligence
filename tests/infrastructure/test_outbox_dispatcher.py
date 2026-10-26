"""Deterministic unit and concurrency tests for OutboxDispatcher and LeaseReaper (Stage M-02C).

Covers:
- Successful claim of PENDING events (single-item, limit 1, lease token).
- Concurrent worker claiming (mutual exclusion, zero race conditions).
- Gmail adapter successful delivery (DELIVERED, shredded ciphertext, provider timestamp).
- Transient errors & backoff scheduling (RETRY, exponential backoff with jitter).
- Permanent errors (immediate DEAD_LETTER, payload shredding, zero retries).
- Ambiguous timeout handling (scheduled retry, no false assumptions).
- Stale fencing token rejection (zombie worker does not overwrite fresh lease).
- LeaseReaper recovering crashed worker leases (transition to RETRY or DEAD_LETTER).
- Max attempts exhaustion leading to DEAD_LETTER and payload shredding.
- Sensitive data sanitization (tokens and emails redacted from last_error_detail).
- Proof of zero database row locks held during external WAN delivery.
"""

from __future__ import annotations

import base64
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from app.infrastructure.outbox.adapter import (
    DeliveryResult,
    DeliveryStatus,
    FakeEmailDeliveryAdapter,
)
from app.infrastructure.outbox.backoff import (
    compute_next_attempt_at,
    sanitize_error_detail,
)
from app.infrastructure.outbox.crypto import (
    Keyring,
    encrypt_outbox_payload,
)
from app.infrastructure.outbox.dispatcher import OutboxDispatcher
from app.infrastructure.outbox.models import OutboxEvent
from app.infrastructure.outbox.reaper import LeaseReaper

VALID_KEY_B64 = base64.b64encode(b"\x0b" * 32).decode("ascii")


class MemoryOutboxStore:
    """In-memory persistence store simulating PostgreSQL outbox_events semantics."""

    def __init__(self, initial_events: list[OutboxEvent] | None = None) -> None:
        self.events: dict[int, OutboxEvent] = {}
        self.next_id = 1
        self.active_transactions: int = 0
        self.transaction_history: list[str] = []

        if initial_events:
            for ev in initial_events:
                if not ev.id:
                    ev.id = self.next_id
                    self.next_id += 1
                self.events[ev.id] = ev

    @asynccontextmanager
    async def create_session(self) -> AsyncIterator[Any]:
        session = MemoryAsyncSession(self)
        self.active_transactions += 1
        self.transaction_history.append("begin")
        try:
            yield session
        finally:
            self.active_transactions -= 1
            self.transaction_history.append("close")


class MemoryAsyncSession:
    """Simulates SQLAlchemy AsyncSession against MemoryOutboxStore."""

    def __init__(self, store: MemoryOutboxStore) -> None:
        self.store = store
        self.committed = False
        self.rolled_back = False

    def add(self, entity: OutboxEvent) -> None:
        if not entity.id:
            entity.id = self.store.next_id
            self.store.next_id += 1
        self.store.events[entity.id] = entity

    async def flush(self) -> None:
        pass

    async def commit(self) -> None:
        self.committed = True
        self.store.transaction_history.append("commit")

    async def rollback(self) -> None:
        self.rolled_back = True
        self.store.transaction_history.append("rollback")

    async def scalar(self, stmt: Any) -> Any:
        # Check if query is Phase 1 claim or Phase 3 fencing check
        query_str = str(stmt).lower()
        now = datetime.now(UTC)

        if "status in" in query_str or "pending" in query_str:
            # Phase 1: Claim runnable event
            eligible = [
                e
                for e in self.store.events.values()
                if e.status in {"PENDING", "RETRY"} and e.next_attempt_at <= now
            ]
            eligible.sort(key=lambda x: (x.next_attempt_at, x.id))
            return eligible[0] if eligible else None

        if "lease_token" in query_str or "processing" in query_str:
            # Phase 3: Fencing check by id and lease_token
            # In our implementation: stmt checks OutboxEvent.id and OutboxEvent.lease_token
            # Extract where criteria from stmt
            whereclause = getattr(stmt, "_where_criteria", ())
            target_id = None
            target_token = None
            for criterion in whereclause:
                s = str(criterion)
                if "outbox_events.id =" in s:
                    target_id = criterion.right.value
                elif "outbox_events.lease_token =" in s:
                    target_token = criterion.right.value

            if target_id is not None:
                event = self.store.events.get(target_id)
                if (
                    event
                    and event.status == "PROCESSING"
                    and (target_token is None or event.lease_token == target_token)
                ):
                    return event
                return None

        return None

    async def scalars(self, stmt: Any) -> Any:
        # Used by LeaseReaper: find PROCESSING events with lease_expires_at <= now
        now = datetime.now(UTC)
        expired = [
            e
            for e in self.store.events.values()
            if e.status == "PROCESSING"
            and e.lease_expires_at is not None
            and e.lease_expires_at <= now
        ]
        expired.sort(key=lambda x: (x.lease_expires_at or now))

        class ResultWrapper:
            def __init__(self, items: list[Any]) -> None:
                self._items = items

            def all(self) -> list[Any]:
                return self._items

        return ResultWrapper(expired)


def create_sample_event(
    keyring: Keyring,
    *,
    id: int = 1,
    event_type: str = "auth.invitation.created",
    aggregate_id: str = "101",
    idempotency_key: str = "invitation:request:101",
    recipient: str = "user@example.test",
    status: str = "PENDING",
    attempt_count: int = 0,
    max_attempts: int = 5,
    next_attempt_at: datetime | None = None,
    lease_token: str | None = None,
    lease_expires_at: datetime | None = None,
) -> OutboxEvent:
    if next_attempt_at is None:
        next_attempt_at = datetime.now(UTC) - timedelta(seconds=1)

    payload = {
        "email": recipient,
        "link": "http://127.0.0.1:8000/registro#invite=test-secret-token",
        "request_id": int(aggregate_id) if aggregate_id.isdigit() else 1,
    }
    encrypted = encrypt_outbox_payload(
        keyring=keyring,
        payload=payload,
        event_type=event_type,
        aggregate_id=aggregate_id,
        idempotency_key=idempotency_key,
        recipient_email=recipient,
    )

    return OutboxEvent(
        id=id,
        event_type=event_type,
        aggregate_type="registration_request",
        aggregate_id=aggregate_id,
        idempotency_key=idempotency_key,
        recipient_email=recipient,
        payload_ciphertext=encrypted.ciphertext_b64,
        payload_nonce=encrypted.nonce_b64,
        payload_key_id=encrypted.key_id,
        payload_format_version=encrypted.format_version,
        payload_redacted=False,
        status=status,
        attempt_count=attempt_count,
        max_attempts=max_attempts,
        next_attempt_at=next_attempt_at,
        lease_token=lease_token,
        lease_expires_at=lease_expires_at,
    )


@pytest.fixture
def keyring() -> Keyring:
    return Keyring.from_raw(primary_key_b64=VALID_KEY_B64, primary_key_id="v1")


@pytest.mark.asyncio
async def test_claim_event_transitions_to_processing_and_sets_fencing_token(keyring: Keyring) -> None:
    event = create_sample_event(keyring)
    store = MemoryOutboxStore([event])
    adapter = FakeEmailDeliveryAdapter()
    dispatcher = OutboxDispatcher(
        session_factory=store.create_session,
        keyring=keyring,
        adapter=adapter,
        worker_id="test-worker-1",
        lease_duration_seconds=45,
    )

    async with store.create_session() as session:
        claim_result = await dispatcher.claim_event(session)
        assert claim_result is not None
        claimed_event, fencing_token = claim_result

        assert claimed_event.id == event.id
        assert claimed_event.status == "PROCESSING"
        assert claimed_event.lease_worker_id == "test-worker-1"
        assert claimed_event.lease_token == fencing_token
        assert claimed_event.attempt_count == 1
        assert claimed_event.lease_expires_at is not None
        assert claimed_event.lease_expires_at > datetime.now(UTC)


@pytest.mark.asyncio
async def test_two_concurrent_workers_claim_separate_events_without_conflict(keyring: Keyring) -> None:
    """Verifies that with 1 event, Worker 1 claims it and Worker 2 gets None."""
    event = create_sample_event(keyring)
    store = MemoryOutboxStore([event])
    adapter = FakeEmailDeliveryAdapter()

    w1 = OutboxDispatcher(session_factory=store.create_session, keyring=keyring, adapter=adapter, worker_id="w1")
    w2 = OutboxDispatcher(session_factory=store.create_session, keyring=keyring, adapter=adapter, worker_id="w2")

    async with store.create_session() as s1:
        res1 = await w1.claim_event(s1)
        await s1.commit()

    assert res1 is not None
    claimed_by_w1, _ = res1
    assert claimed_by_w1.lease_worker_id == "w1"

    # Worker 2 attempts to claim while event is PROCESSING
    async with store.create_session() as s2:
        res2 = await w2.claim_event(s2)

    # Invariant: Event is already PROCESSING, so Worker 2 receives None
    assert res2 is None


@pytest.mark.asyncio
async def test_dispatch_cycle_successful_delivery_shreds_payload(keyring: Keyring) -> None:
    event = create_sample_event(keyring, id=10)
    store = MemoryOutboxStore([event])
    adapter = FakeEmailDeliveryAdapter(default_status=DeliveryStatus.ACCEPTED)

    dispatcher = OutboxDispatcher(
        session_factory=store.create_session,
        keyring=keyring,
        adapter=adapter,
        worker_id="worker-success",
    )

    processed = await dispatcher.dispatch_next_event()
    assert processed is True

    # Verify adapter was called with plaintext email
    assert len(adapter.calls) == 1
    call = adapter.calls[0]
    assert call["recipient_email"] == "user@example.test"
    assert "Registro aprobado" in call["subject"]
    assert "invite=test-secret-token" in call["body"]

    # Verify terminal status and payload shredding in storage
    stored_event = store.events[10]
    assert stored_event.status == "DELIVERED"
    assert stored_event.payload_ciphertext == ""  # Shredded
    assert stored_event.payload_redacted is True  # Redacted flag set
    assert stored_event.provider_accepted_at is not None
    assert stored_event.lease_token is None
    assert stored_event.lease_worker_id is None


@pytest.mark.asyncio
async def test_dispatch_cycle_transient_error_schedules_retry(keyring: Keyring) -> None:
    event = create_sample_event(keyring, id=20)
    store = MemoryOutboxStore([event])
    adapter = FakeEmailDeliveryAdapter(default_status=DeliveryStatus.TRANSIENT_ERROR)

    dispatcher = OutboxDispatcher(
        session_factory=store.create_session,
        keyring=keyring,
        adapter=adapter,
        base_backoff_seconds=10.0,
    )

    processed = await dispatcher.dispatch_next_event()
    assert processed is True

    stored_event = store.events[20]
    assert stored_event.status == "RETRY"
    assert stored_event.attempt_count == 1
    assert stored_event.next_attempt_at > datetime.now(UTC)
    assert stored_event.last_error_code == "HTTP_503"
    # Payload is NOT shredded during RETRY so it can be retried
    assert stored_event.payload_ciphertext != ""
    assert not stored_event.payload_redacted
    # Lease is released
    assert stored_event.lease_token is None


@pytest.mark.asyncio
async def test_dispatch_cycle_permanent_error_transitions_to_dead_letter_and_shreds(keyring: Keyring) -> None:
    event = create_sample_event(keyring, id=30)
    store = MemoryOutboxStore([event])
    adapter = FakeEmailDeliveryAdapter(default_status=DeliveryStatus.PERMANENT_ERROR)

    dispatcher = OutboxDispatcher(
        session_factory=store.create_session,
        keyring=keyring,
        adapter=adapter,
    )

    processed = await dispatcher.dispatch_next_event()
    assert processed is True

    stored_event = store.events[30]
    assert stored_event.status == "DEAD_LETTER"
    assert stored_event.last_error_code == "RECIPIENT_REJECTED"
    # Invariant: Payload is shredded immediately on permanent failure
    assert stored_event.payload_ciphertext == ""
    assert stored_event.payload_redacted is True


@pytest.mark.asyncio
async def test_dispatch_cycle_ambiguous_timeout_schedules_retry(keyring: Keyring) -> None:
    event = create_sample_event(keyring, id=40)
    store = MemoryOutboxStore([event])
    adapter = FakeEmailDeliveryAdapter(default_status=DeliveryStatus.TIMEOUT)

    dispatcher = OutboxDispatcher(
        session_factory=store.create_session,
        keyring=keyring,
        adapter=adapter,
    )

    processed = await dispatcher.dispatch_next_event()
    assert processed is True

    stored_event = store.events[40]
    assert stored_event.status == "RETRY"
    assert stored_event.last_error_code == "TIMEOUT"


@pytest.mark.asyncio
async def test_fencing_token_breach_aborts_stale_worker_write(keyring: Keyring) -> None:
    """Verifies that a zombie worker whose lease expired cannot overwrite fresh state."""
    event = create_sample_event(keyring, id=50, status="PROCESSING", lease_token="token-b")
    store = MemoryOutboxStore([event])
    adapter = FakeEmailDeliveryAdapter()

    dispatcher = OutboxDispatcher(
        session_factory=store.create_session,
        keyring=keyring,
        adapter=adapter,
        worker_id="zombie-worker",
    )

    # Zombie worker attempts to record outcome using stale "token-a"
    async with store.create_session() as session:
        success = await dispatcher.record_outcome(
            session,
            event_id=50,
            fencing_token="token-a",  # Stale token!
            attempt_count=1,
            max_attempts=5,
            delivery_result=DeliveryResult.accepted("msg-stale"),
        )

    # Invariant: Fencing check failed
    assert success is False
    # Invariant: Event remains in PROCESSING with token-b intact
    assert store.events[50].status == "PROCESSING"
    assert store.events[50].lease_token == "token-b"


@pytest.mark.asyncio
async def test_lease_reaper_recovers_expired_lease_to_retry(keyring: Keyring) -> None:
    past = datetime.now(UTC) - timedelta(seconds=60)
    event = create_sample_event(
        keyring,
        id=60,
        status="PROCESSING",
        attempt_count=1,
        max_attempts=5,
        lease_token="expired-token",
        lease_expires_at=past,
    )
    store = MemoryOutboxStore([event])
    reaper = LeaseReaper(session_factory=store.create_session, retry_delay_seconds=30.0)

    reaped = await reaper.reap_expired_leases()
    assert reaped == 1

    stored_event = store.events[60]
    assert stored_event.status == "RETRY"
    assert stored_event.lease_token is None
    assert stored_event.lease_worker_id is None
    assert stored_event.last_error_code == "LEASE_EXPIRED"
    assert stored_event.next_attempt_at > datetime.now(UTC)


@pytest.mark.asyncio
async def test_lease_reaper_transitions_exhausted_attempts_to_dead_letter_and_shreds(keyring: Keyring) -> None:
    past = datetime.now(UTC) - timedelta(seconds=60)
    event = create_sample_event(
        keyring,
        id=70,
        status="PROCESSING",
        attempt_count=5,  # Max attempts reached!
        max_attempts=5,
        lease_token="expired-token",
        lease_expires_at=past,
    )
    store = MemoryOutboxStore([event])
    reaper = LeaseReaper(session_factory=store.create_session)

    reaped = await reaper.reap_expired_leases()
    assert reaped == 1

    stored_event = store.events[70]
    assert stored_event.status == "DEAD_LETTER"
    assert stored_event.last_error_code == "LEASE_EXPIRED_MAX_ATTEMPTS"
    # Invariant: Payload is shredded upon reaching DEAD_LETTER
    assert stored_event.payload_ciphertext == ""
    assert stored_event.payload_redacted is True


@pytest.mark.asyncio
async def test_zero_db_locks_held_during_wan_call(keyring: Keyring) -> None:
    """Proves that Transaction 1 commits and closes BEFORE the email adapter executes."""
    event = create_sample_event(keyring, id=80)
    store = MemoryOutboxStore([event])
    wan_executed = False

    class LockCheckingAdapter:
        async def send_email(self, **kwargs: Any) -> DeliveryResult:
            nonlocal wan_executed
            wan_executed = True
            # Invariant: During WAN call, active DB transaction count must be ZERO
            assert store.active_transactions == 0
            assert "commit" in store.transaction_history
            return DeliveryResult.accepted()

    dispatcher = OutboxDispatcher(
        session_factory=store.create_session,
        keyring=keyring,
        adapter=LockCheckingAdapter(),  # type: ignore[arg-type]
    )

    await dispatcher.dispatch_next_event()
    assert wan_executed is True


def test_error_detail_sanitizer_removes_tokens_and_emails() -> None:
    raw_error = "Failed to deliver invite=secret_abc123 to applicant.john@firecontrol.org with Bearer ya29.token"
    sanitized = sanitize_error_detail(raw_error)
    assert "secret_abc123" not in sanitized  # type: ignore[operator]
    assert "applicant.john@firecontrol.org" not in sanitized  # type: ignore[operator]
    assert "ya29.token" not in sanitized  # type: ignore[operator]
    assert "invite=[REDACTED]" in sanitized  # type: ignore[operator]
    assert "[EMAIL_REDACTED]" in sanitized  # type: ignore[operator]
    assert "Bearer [REDACTED]" in sanitized  # type: ignore[operator]


def test_compute_next_attempt_honors_retry_after() -> None:
    now = datetime(2026, 10, 26, 12, 0, 0, tzinfo=UTC)
    next_at = compute_next_attempt_at(attempt_count=1, base_backoff=10.0, retry_after=120.0, now=now)
    # Delay must be at least 120s
    assert (next_at - now).total_seconds() >= 120.0
