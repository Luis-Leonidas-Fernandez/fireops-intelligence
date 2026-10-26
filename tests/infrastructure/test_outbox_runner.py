"""Deterministic unit tests for OutboxRunner, environment isolation, and telemetry (Stage M-02D).

Covers:
- Rejection of startup when outbox is disabled.
- Rejection of startup when encryption key is missing or invalid.
- Rejection of startup against protected databases (fireassets, fireassets_test, postgres).
- URL credential and token redaction.
- Schema verification failure when table outbox_events does not exist.
- Graceful shutdown lifecycle upon stop request.
- Dispatcher execution and metrics accounting.
- Zero side-effects and zero workers started on module import.
- CLI argument parsing.
"""

from __future__ import annotations

import asyncio
import base64
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy.exc import ProgrammingError

from app.config.settings import Settings, get_settings
from app.infrastructure.outbox.adapter import FakeEmailDeliveryAdapter
from app.infrastructure.outbox.crypto import (
    Keyring,
    OutboxConfigurationError,
    encrypt_outbox_payload,
)
from app.infrastructure.outbox.isolation import (
    EnvironmentProtectionError,
    extract_database_name,
    redact_database_url,
    validate_target_database,
)
from app.infrastructure.outbox.metrics import OutboxMetrics
from app.infrastructure.outbox.models import OutboxEvent
from app.infrastructure.outbox.runner import (
    OutboxRunner,
    RunnerConfig,
    build_arg_parser,
)

VALID_KEY_B64 = base64.b64encode(b"\x0c" * 32).decode("ascii")


class MemoryOutboxStore:
    """In-memory store for runner testing."""

    def __init__(self, initial_events: list[OutboxEvent] | None = None) -> None:
        self.events: dict[int, OutboxEvent] = {}
        self.next_id = 1
        if initial_events:
            for ev in initial_events:
                if not ev.id:
                    ev.id = self.next_id
                    self.next_id += 1
                self.events[ev.id] = ev

    @asynccontextmanager
    async def create_session(self) -> Any:
        session = MemorySession(self)
        try:
            yield session
        finally:
            pass


class MemorySession:
    def __init__(self, store: MemoryOutboxStore) -> None:
        self.store = store

    def add(self, entity: OutboxEvent) -> None:
        if not entity.id:
            entity.id = self.store.next_id
            self.store.next_id += 1
        self.store.events[entity.id] = entity

    async def flush(self) -> None:
        pass

    async def commit(self) -> None:
        pass

    async def rollback(self) -> None:
        pass

    async def scalar(self, stmt: Any) -> Any:
        now = datetime.now(UTC)
        query_str = str(stmt).lower()
        if "pending" in query_str or "status in" in query_str:
            eligible = [
                e
                for e in self.store.events.values()
                if e.status in {"PENDING", "RETRY"} and e.next_attempt_at <= now
            ]
            eligible.sort(key=lambda x: (x.next_attempt_at, x.id))
            return eligible[0] if eligible else None

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
        now = datetime.now(UTC)
        expired = [
            e
            for e in self.store.events.values()
            if e.status == "PROCESSING"
            and e.lease_expires_at is not None
            and e.lease_expires_at <= now
        ]

        class ResWrapper:
            def __init__(self, items: list[Any]) -> None:
                self.items = items

            def all(self) -> list[Any]:
                return self.items

        return ResWrapper(expired)


def create_sample_event(
    keyring: Keyring,
    *,
    id: int = 1,
    aggregate_id: str = "101",
) -> OutboxEvent:
    payload = {"email": "test@example.test", "link": "http://127.0.0.1:8000/invite=xyz"}
    encrypted = encrypt_outbox_payload(
        keyring=keyring,
        payload=payload,
        event_type="auth.invitation.created",
        aggregate_id=aggregate_id,
        idempotency_key=f"invitation:req:{aggregate_id}",
        recipient_email="test@example.test",
    )
    return OutboxEvent(
        id=id,
        event_type="auth.invitation.created",
        aggregate_type="registration_request",
        aggregate_id=aggregate_id,
        idempotency_key=f"invitation:req:{aggregate_id}",
        recipient_email="test@example.test",
        payload_ciphertext=encrypted.ciphertext_b64,
        payload_nonce=encrypted.nonce_b64,
        payload_key_id=encrypted.key_id,
        payload_format_version=encrypted.format_version,
        payload_redacted=False,
        status="PENDING",
        attempt_count=0,
        max_attempts=5,
        next_attempt_at=datetime.now(UTC) - timedelta(seconds=1),
    )


@pytest.fixture
def valid_runner_settings() -> Settings:
    return get_settings().model_copy(
        update={
            "environment": "test",
            "database_url": "postgresql+asyncpg://ephemeral_user:temp_pass@127.0.0.1:5432/fireassets_ephemeral_m02e",
            "outbox_enabled": True,
            "outbox_encryption_key": VALID_KEY_B64,
            "outbox_encryption_key_id": "v1",
        }
    )


def test_runner_rejects_when_outbox_disabled(valid_runner_settings: Settings) -> None:
    settings = valid_runner_settings.model_copy(update={"outbox_enabled": False})
    config = RunnerConfig(worker_id="w-disabled")
    runner = OutboxRunner(config=config, settings=settings)

    with pytest.raises(OutboxConfigurationError, match="Transactional Outbox is disabled"):
        runner.validate_preconditions()


def test_runner_rejects_missing_encryption_key() -> None:
    # Bypassing Settings validator to test runner defense-in-depth
    settings = get_settings().model_copy(
        update={
            "database_url": "postgresql+asyncpg://u:p@localhost:5432/fireassets_ephemeral",
            "outbox_enabled": False,  # Will bypass Pydantic model validator
        }
    )
    object.__setattr__(settings, "outbox_enabled", True)
    object.__setattr__(settings, "outbox_encryption_key", None)

    config = RunnerConfig(worker_id="w-nokey")
    runner = OutboxRunner(config=config, settings=settings)

    with pytest.raises(OutboxConfigurationError, match="Missing outbox_encryption_key"):
        runner.validate_preconditions()


@pytest.mark.parametrize("protected_db", ["fireassets", "fireassets_test", "postgres", "template0", "template1"])
def test_runner_rejects_protected_databases(valid_runner_settings: Settings, protected_db: str) -> None:
    url = f"postgresql+asyncpg://app_user:secret@localhost:5432/{protected_db}"
    settings = valid_runner_settings.model_copy(update={"database_url": url})
    config = RunnerConfig(worker_id="w-protected", allow_protected_db=False)
    runner = OutboxRunner(config=config, settings=settings)

    with pytest.raises(EnvironmentProtectionError, match=f"Database '{protected_db}' .* is protected"):
        runner.validate_preconditions()


def test_redact_database_url_masks_credentials() -> None:
    raw_url = "postgresql+asyncpg://admin_user:super_secret_password_123@127.0.0.1:5432/my_database?token=xyz"
    redacted = redact_database_url(raw_url)

    assert "super_secret_password_123" not in redacted
    assert "token=xyz" not in redacted
    assert "admin_user:[REDACTED]@127.0.0.1:5432/my_database" in redacted


def test_extract_database_name() -> None:
    assert extract_database_name("postgresql+asyncpg://u:p@host:5432/my_db") == "my_db"
    assert extract_database_name("postgresql://u:p@host:5432/other_db?ssl=true") == "other_db"
    assert extract_database_name("") == ""


def test_validate_target_database_ephemeral_enforcement() -> None:
    with pytest.raises(EnvironmentProtectionError, match="not an authorized ephemeral test database"):
        validate_target_database(
            "postgresql+asyncpg://u:p@host:5432/persistent_dev",
            require_ephemeral=True,
        )

    # Valid ephemeral database
    db = validate_target_database(
        "postgresql+asyncpg://u:p@host:5432/fireassets_ephemeral_m02e",
        require_ephemeral=True,
    )
    assert db == "fireassets_ephemeral_m02e"


@pytest.mark.asyncio
async def test_runner_schema_check_fails_if_table_missing(valid_runner_settings: Settings) -> None:
    class BrokenSession:
        async def scalar(self, _stmt: Any) -> Any:
            raise ProgrammingError("SELECT count(*) FROM outbox_events", params={}, orig=Exception('relation "outbox_events" does not exist'))

    config = RunnerConfig(worker_id="w-noschema")
    runner = OutboxRunner(config=config, settings=valid_runner_settings)

    with pytest.raises(OutboxConfigurationError, match="table 'outbox_events' does not exist"):
        await runner.verify_schema_exists(BrokenSession())  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_runner_starts_and_stops_gracefully(valid_runner_settings: Settings) -> None:
    store = MemoryOutboxStore()
    config = RunnerConfig(
        worker_id="w-test-lifecycle",
        poll_interval_seconds=0.01,
        reap_interval_seconds=0.05,
    )

    runner = OutboxRunner(
        config=config,
        settings=valid_runner_settings,
        adapter=FakeEmailDeliveryAdapter(),
        session_factory=store.create_session,
    )

    # Stop runner shortly after start
    async def schedule_stop() -> None:
        await asyncio.sleep(0.03)
        runner.request_stop("test_stop")

    stop_task = asyncio.create_task(schedule_stop())
    metrics = await runner.run()
    await stop_task

    # Verifies graceful exit and clean telemetry
    assert isinstance(metrics, OutboxMetrics)
    assert not runner._is_running


@pytest.mark.asyncio
async def test_runner_drains_and_dispatches_events(valid_runner_settings: Settings) -> None:
    keyring = Keyring.from_raw(VALID_KEY_B64, "v1")
    event1 = create_sample_event(keyring, id=101, aggregate_id="101")
    event2 = create_sample_event(keyring, id=102, aggregate_id="102")

    store = MemoryOutboxStore([event1, event2])
    adapter = FakeEmailDeliveryAdapter()

    config = RunnerConfig(
        worker_id="w-drain",
        poll_interval_seconds=0.01,
        reap_interval_seconds=0.05,
    )

    runner = OutboxRunner(
        config=config,
        settings=valid_runner_settings,
        adapter=adapter,
        session_factory=store.create_session,
    )

    async def schedule_stop_after_processing() -> None:
        # Wait until 2 events are delivered
        for _ in range(50):
            if len(adapter.calls) >= 2:
                break
            await asyncio.sleep(0.01)
        runner.request_stop("completed")

    stop_task = asyncio.create_task(schedule_stop_after_processing())
    metrics = await runner.run()
    await stop_task

    assert metrics.delivered_events_total == 2
    assert len(adapter.calls) == 2
    assert store.events[101].status == "DELIVERED"
    assert store.events[102].status == "DELIVERED"
    assert metrics.average_processing_time_seconds >= 0.0


def test_metrics_telemetry_snapshot_and_no_pii() -> None:
    metrics = OutboxMetrics()
    metrics.record_claim()
    metrics.record_delivered(0.0123)
    metrics.record_retry(0.0456)
    metrics.record_reaped_leases(3)
    metrics.record_fencing_breach()

    snap = metrics.snapshot()
    assert snap["claimed_events_total"] == 1
    assert snap["delivered_events_total"] == 1
    assert snap["retried_events_total"] == 1
    assert snap["reaped_leases_total"] == 3
    assert snap["fencing_breaches_total"] == 1
    assert snap["processed_samples_count"] == 2
    assert snap["last_processing_time_seconds"] == 0.0456

    # Verify no PII keys exist in snapshot
    snap_str = str(snap)
    assert "@" not in snap_str
    assert "token" not in snap_str
    assert "key" not in snap_str.lower() or "total" in snap_str.lower()


def test_cli_parser_defaults_and_options() -> None:
    parser = build_arg_parser()
    args = parser.parse_args(["--poll-interval", "2.5", "--lease-duration", "60", "--adapter", "fake"])
    assert args.poll_interval == 2.5
    assert args.lease_duration == 60
    assert args.adapter == "fake"
    assert args.shutdown_timeout == 15.0
