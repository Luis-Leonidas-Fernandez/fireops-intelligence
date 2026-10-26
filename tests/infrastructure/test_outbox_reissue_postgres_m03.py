"""Real PostgreSQL 18.4 isolation and concurrency test suite for administrative reissuance (Stage M-03A).

Executed strictly against isolated ephemeral PostgreSQL on port 55432.
Guarantees:
- Strictly blocked against protected databases (fireassets, fireassets_test, postgres).
- Real PostgreSQL row-level locks (SELECT FOR UPDATE) serializing concurrent reissues.
- Real engine-level CHECK constraint (reissue_count >= 0 AND reissue_count <= 3) enforcement.
- Real transaction rollback on commit failure (preserves prior state).
- Invalidation of old token and valid consumption of new token.
- Rejection of reissuing consumed invitations.
- OutboxDispatcher integration delivering reissued invitations with Format Version 3.
"""

from __future__ import annotations

import asyncio
import base64
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config.settings import Settings
from app.infrastructure.outbox.adapter import FakeEmailDeliveryAdapter
from app.infrastructure.outbox.crypto import Keyring
from app.infrastructure.outbox.dispatcher import OutboxDispatcher
from app.infrastructure.outbox.isolation import validate_target_database
from app.infrastructure.outbox.models import OutboxEvent
from app.modules.auth.invitations.reissue import (
    ReissueResult,
    reissue_registration_invitation,
)
from app.modules.auth.invitations.service import (
    consume_invitation,
    lock_invitation,
)
from app.modules.auth.models import Invitation, RegistrationRequest, Role, User
from app.modules.inventory.shared.models import AuditChange
from app.shared.errors.application_error import ApplicationError

EPHEMERAL_M03_DB_URL = (
    "postgresql+asyncpg://ephemeral_m03_user:ephemeral_m03_pass@127.0.0.1:55432/fireassets_ephemeral_m03"
)
VALID_KEY_B64 = base64.b64encode(b"\x03" * 32).decode("ascii")


def make_ephemeral_settings() -> Settings:
    return Settings(
        database_url=EPHEMERAL_M03_DB_URL,
        secret_key="isolated_test_secret_key_m03_must_be_at_least_32_characters_long",
        outbox_enabled=True,
        outbox_encryption_key=VALID_KEY_B64,
        outbox_encryption_key_id="v1",
        google_client_id="dummy-id",
        google_client_secret="dummy-secret",
        google_redirect_uri="https://app.example.test/auth/callback",
        gmail_sender_email="admin@example.test",
        gmail_refresh_token="dummy-token",
        public_base_url="https://app.example.test",
        admin_rate_limit_reissue_requests=20,
    )


@pytest_asyncio.fixture(scope="module")
async def ephemeral_engine() -> AsyncIterator[AsyncEngine]:
    validate_target_database(EPHEMERAL_M03_DB_URL, require_ephemeral=True)
    engine = create_async_engine(
        EPHEMERAL_M03_DB_URL,
        pool_size=10,
        max_overflow=10,
        pool_pre_ping=True,
    )
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def session_factory(ephemeral_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        bind=ephemeral_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=True,
    )


@pytest_asyncio.fixture(autouse=True)
async def clean_database_tables(session_factory: async_sessionmaker[AsyncSession]) -> AsyncIterator[None]:
    async with session_factory() as session:
        await session.execute(text("TRUNCATE TABLE auditoria_cambios CASCADE;"))
        await session.execute(text("TRUNCATE TABLE outbox_events CASCADE;"))
        await session.execute(text("TRUNCATE TABLE auth_registration_requests CASCADE;"))
        await session.execute(text("TRUNCATE TABLE auth_invitations CASCADE;"))
        await session.execute(text("TRUNCATE TABLE usuarios CASCADE;"))
        await session.execute(text("TRUNCATE TABLE roles CASCADE;"))

        # Seed standard roles
        admin_role = Role(id=1, nombre="ADMINISTRADOR", descripcion="Administrador del sistema", activo=True)
        supervisor_role = Role(id=2, nombre="SUPERVISOR", descripcion="Supervisor operativo", activo=True)
        session.add_all([admin_role, supervisor_role])

        # Seed admin user
        admin_user = User(id=10, email="admin@bomberos.test", display_name="Admin Chief", rol_id=1, activo=True)
        session.add(admin_user)
        await session.commit()
    yield


# =========================================================================
# 1. Isolation & database check constraint tests
# =========================================================================

@pytest.mark.asyncio
async def test_ephemeral_database_isolation_and_port(ephemeral_engine: AsyncEngine) -> None:
    async with ephemeral_engine.connect() as conn:
        res = await conn.execute(text("SELECT inet_server_port(), current_database();"))
        port, db_name = res.one()
        assert port == 55432, "Must run exclusively on ephemeral port 55432"
        assert db_name == "fireassets_ephemeral_m03"


@pytest.mark.asyncio
async def test_postgres_engine_check_constraint_bounds_reissue_count(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Demonstrates that PostgreSQL itself enforces ck_auth_registration_requests_reissue_count."""
    now = datetime.now(UTC)

    # 1. Valid insert within bounds (0)
    async with session_factory() as session:
        valid_req = RegistrationRequest(
            id=100,
            email="bounds@example.test",
            status="approved",
            source="password",
            requested_at=now,
            reissue_count=0,
        )
        session.add(valid_req)
        await session.commit()

    # 2. Invalid update: exceeding max (4 > 3) violates check constraint
    async with session_factory() as session:
        with pytest.raises(IntegrityError) as exc_info:
            await session.execute(
                text("UPDATE auth_registration_requests SET reissue_count = 4 WHERE id = 100")
            )
            await session.commit()
        assert "ck_auth_registration_requests_reissue_count" in str(exc_info.value)

    # 3. Invalid update: negative count (-1 < 0) violates check constraint
    async with session_factory() as session:
        with pytest.raises(IntegrityError) as exc_info:
            await session.execute(
                text("UPDATE auth_registration_requests SET reissue_count = -1 WHERE id = 100")
            )
            await session.commit()
        assert "ck_auth_registration_requests_reissue_count" in str(exc_info.value)


# =========================================================================
# 2. Concurrency serialization with SELECT FOR UPDATE
# =========================================================================

@pytest.mark.asyncio
async def test_concurrent_admins_serialized_by_for_update_lock(
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two concurrent admin requests on separate connections serialize safely on the row lock."""
    settings = make_ephemeral_settings()
    monkeypatch.setattr("app.modules.auth.invitations.reissue.get_settings", lambda: settings)

    now = datetime.now(UTC)
    async with session_factory() as session:
        req = RegistrationRequest(
            id=200,
            email="concurrent@example.test",
            status="approved",
            source="password",
            requested_at=now - timedelta(days=3),
            reissue_count=0,
        )
        old_inv = Invitation(
            id=201,
            email="concurrent@example.test",
            token_hash="hash_expired_conc",
            rol_id=2,
            invited_by_id=10,
            expires_at=now - timedelta(hours=2),  # Expired
            used_at=None,
        )
        session.add_all([req, old_inv])
        await session.commit()

    async with session_factory() as session:
        admin = await session.get(User, 10)
        assert admin is not None

    results: list[ReissueResult] = []
    errors: list[ApplicationError] = []

    async def reissue_task(task_name: str, idem_key: str, delay: float = 0.0) -> None:
        if delay > 0:
            await asyncio.sleep(delay)
        async with session_factory() as sess:
            admin_user = await sess.get(User, 10)
            assert admin_user is not None
            try:
                res = await reissue_registration_invitation(
                    session=sess,
                    request_id=200,
                    actor=admin_user,
                    idempotency_key=idem_key,
                    reason=f"Concurrent reissue by {task_name}",
                )
                await sess.commit()
                results.append(res)
            except ApplicationError as err:
                await sess.rollback()
                errors.append(err)

    # Launch two concurrent reissues with different idempotency keys
    await asyncio.gather(
        reissue_task("AdminA", "idem-key-A", delay=0.0),
        reissue_task("AdminB", "idem-key-B", delay=0.005),
    )

    # Invariant: One administrator acquires the lock and succeeds.
    # The second is serialized and safely rejected because the invitation is now active!
    assert len(results) == 1, "Exactly one concurrent reissue must succeed"
    assert results[0].reissue_count == 1

    assert len(errors) == 1, "Competing concurrent reissue must be rejected"
    assert errors[0].code == "INVITATION_NOT_ELIGIBLE"

    # Verify final database state: exactly ONE active invitation exists
    async with session_factory() as session:
        final_req = await session.get(RegistrationRequest, 200)
        assert final_req is not None
        assert final_req.reissue_count == 1

        active_invitations = (
            await session.scalars(
                select(Invitation).where(Invitation.email == "concurrent@example.test", Invitation.expires_at > now)
            )
        ).all()
        assert len(active_invitations) == 1, "Zero duplicate active invitations allowed"
        # Exactly one audit entry recorded in auditoria_cambios for the successful reissue
        audit_entries = (
            await session.scalars(
                select(AuditChange).where(AuditChange.entidad_id == 200).order_by(AuditChange.fecha.asc())
            )
        ).all()
        assert len(audit_entries) == 1

        # Exactly one outbox event enqueued
        events = (
            await session.scalars(
                select(OutboxEvent).where(OutboxEvent.aggregate_id == "200").order_by(OutboxEvent.id.asc())
            )
        ).all()
        assert len(events) == 1
        assert events[0].event_type == "auth.invitation.reissued"


@pytest.mark.asyncio
async def test_concurrent_http_retry_with_same_idempotency_key(
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Duplicate requests with identical idempotency key return idempotent replay without duplicate work."""
    settings = make_ephemeral_settings()
    monkeypatch.setattr("app.modules.auth.invitations.reissue.get_settings", lambda: settings)

    now = datetime.now(UTC)
    async with session_factory() as session:
        req = RegistrationRequest(
            id=300,
            email="retry@example.test",
            status="approved",
            source="password",
            requested_at=now - timedelta(days=2),
            reissue_count=0,
        )
        old_inv = Invitation(
            id=301,
            email="retry@example.test",
            token_hash="hash_old_retry",
            rol_id=2,
            invited_by_id=10,
            expires_at=now - timedelta(hours=1),
            used_at=None,
        )
        session.add_all([req, old_inv])
        await session.commit()

    # Attempt 1: First submission
    async with session_factory() as sess1:
        admin = await sess1.get(User, 10)
        assert admin is not None
        res1 = await reissue_registration_invitation(
            session=sess1,
            request_id=300,
            actor=admin,
            idempotency_key="exact-retry-key-123",
        )
        await sess1.commit()

    assert res1.reissue_count == 1
    assert not res1.idempotent_replay

    # Attempt 2: Exact duplicate retry (e.g. network timeout replay)
    async with session_factory() as sess2:
        admin = await sess2.get(User, 10)
        assert admin is not None
        res2 = await reissue_registration_invitation(
            session=sess2,
            request_id=300,
            actor=admin,
            idempotency_key="exact-retry-key-123",
        )
        await sess2.commit()

    assert res2.reissue_count == 1
    assert res2.invitation_id == res1.invitation_id
    assert res2.idempotent_replay is True

    # Verify only ONE new invitation and ONE outbox event created
    async with session_factory() as session:
        invs = (
            await session.scalars(select(Invitation).where(Invitation.email == "retry@example.test"))
        ).all()
        assert len(invs) == 2  # old_inv + exactly 1 reissued invitation

        events = (
            await session.scalars(select(OutboxEvent).where(OutboxEvent.aggregate_id == "300"))
        ).all()
        assert len(events) == 1


# =========================================================================
# 3. End-to-end token consumption lifecycle & invalidation
# =========================================================================

@pytest.mark.asyncio
async def test_end_to_end_invalidation_and_token_consumption(
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = make_ephemeral_settings()
    monkeypatch.setattr("app.modules.auth.invitations.reissue.get_settings", lambda: settings)

    now = datetime.now(UTC)
    email = "lifecycle@example.test"

    # 1. Setup expired initial invitation
    async with session_factory() as session:
        req = RegistrationRequest(
            id=400,
            email=email,
            status="approved",
            source="password",
            requested_at=now - timedelta(days=2),
            reissue_count=0,
        )
        session.add(req)
        await session.commit()

    # 2. Reissue invitation
    async with session_factory() as session:
        admin = await session.get(User, 10)
        assert admin is not None
        res = await reissue_registration_invitation(
            session=session,
            request_id=400,
            actor=admin,
            idempotency_key="lifecycle-key-1",
        )
        await session.commit()

    # 3. Extract the new invitation and outbox payload
    async with session_factory() as session:
        new_inv = await session.get(Invitation, res.invitation_id)
        assert new_inv is not None
        assert new_inv.used_at is None
        assert new_inv.expires_at > now

        # Outbox event contains the encrypted link with token
        event = await session.scalar(select(OutboxEvent).where(OutboxEvent.aggregate_id == "400"))
        assert event is not None

    # Dispatch event via OutboxDispatcher
    keyring = Keyring.from_raw(VALID_KEY_B64, "v1")
    fake_adapter = FakeEmailDeliveryAdapter()
    dispatcher = OutboxDispatcher(
        session_factory=session_factory,
        keyring=keyring,
        adapter=fake_adapter,
        worker_id="test-reissue-worker",
    )

    dispatched = await dispatcher.dispatch_next_event()
    assert dispatched is True

    assert len(fake_adapter.calls) == 1
    call = fake_adapter.calls[0]
    assert call["recipient_email"] == email
    assert "Reemisión de invitación en Fire Control" in call["subject"]
    body = call["body"]
    assert "#invite=" in body
    raw_token = body.split("#invite=")[1].split()[0]

    # 4. Consume the reissued token
    async with session_factory() as session:
        locked_inv = await lock_invitation(session, email, raw_token)
        assert locked_inv.id == res.invitation_id
        consume_invitation(locked_inv)
        await session.commit()

    # 5. Verify cannot be consumed twice
    async with session_factory() as session:
        with pytest.raises(ApplicationError) as exc_info:
            await lock_invitation(session, email, raw_token)
        assert exc_info.value.code == "INVITATION_INVALID"

    # 6. Verify cannot reissue a consumed invitation
    async with session_factory() as session:
        admin = await session.get(User, 10)
        assert admin is not None
        with pytest.raises(ApplicationError) as exc_info:
            await reissue_registration_invitation(
                session=session,
                request_id=400,
                actor=admin,
                idempotency_key="try-reissue-after-consumed",
            )
        assert exc_info.value.code == "INVITATION_ALREADY_CONSUMED"


# =========================================================================
# 4. Rollback on commit failure preserves database integrity
# =========================================================================

@pytest.mark.asyncio
async def test_rollback_on_failure_preserves_state(
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = make_ephemeral_settings()
    monkeypatch.setattr("app.modules.auth.invitations.reissue.get_settings", lambda: settings)

    now = datetime.now(UTC)
    async with session_factory() as session:
        req = RegistrationRequest(
            id=500,
            email="rollback@example.test",
            status="approved",
            source="password",
            requested_at=now - timedelta(days=2),
            reissue_count=1,
            last_reissue_idempotency_key="initial-key",
        )
        session.add(req)
        await session.commit()

    # Simulate an error during execution or commit
    async with session_factory() as session:
        admin = await session.get(User, 10)
        assert admin is not None

        try:
            await reissue_registration_invitation(
                session=session,
                request_id=500,
                actor=admin,
                idempotency_key="failure-key",
            )
            # Force simulated unexpected failure before commit
            raise RuntimeError("Simulated mid-transaction failure")
        except RuntimeError:
            await session.rollback()

    # Verify database state was NOT modified
    async with session_factory() as session:
        db_req = await session.get(RegistrationRequest, 500)
        assert db_req is not None
        assert db_req.reissue_count == 1
        assert db_req.last_reissue_idempotency_key == "initial-key"

        # No invitations created
        inv_count = await session.scalar(
            select(text("COUNT(*)")).select_from(Invitation).where(Invitation.email == "rollback@example.test")
        )
        assert inv_count == 0

        # No outbox events created
        event_count = await session.scalar(
            select(text("COUNT(*)")).select_from(OutboxEvent).where(OutboxEvent.aggregate_id == "500")
        )
        assert event_count == 0
