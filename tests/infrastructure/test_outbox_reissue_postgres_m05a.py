"""Real PostgreSQL 18.4 isolation and concurrency test suite for Stage M-05A.

Executed strictly against isolated ephemeral PostgreSQL on port 55432.
Guarantees:
- Strictly blocked against protected databases (fireassets, fireassets_test, postgres).
- Persistent historical idempotency surviving multiple reissues and late replays (P1-B).
- Parameter mismatch conflict detection (HTTP 409).
- Atomic serialization under real PostgreSQL SELECT FOR UPDATE and UniqueConstraint.
- Fail-closed delivery gating (P1-A) with zero database mutations on failure.
- ACID rollback integrity across invitations, outbox, audit, and idempotency records.
"""

from __future__ import annotations

import asyncio
import base64
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config.settings import Settings
from app.infrastructure.outbox.isolation import validate_target_database
from app.modules.auth.invitations.reissue import (
    ReissueResult,
    reissue_registration_invitation,
)
from app.modules.auth.models import Invitation, RegistrationRequest, Role, User
from app.shared.errors.application_error import ApplicationError

EPHEMERAL_M05_DB_URL = (
    "postgresql+asyncpg://ephemeral_m05_user:ephemeral_m05_pass@127.0.0.1:55432/fireassets_ephemeral_m05"
)
VALID_KEY_B64 = base64.b64encode(b"\x05" * 32).decode("ascii")


def make_ephemeral_settings(*, outbox_enabled: bool = True, enable_gmail: bool = False) -> Settings:
    return Settings(
        database_url=EPHEMERAL_M05_DB_URL,
        secret_key="isolated_test_secret_key_m05a_must_be_at_least_32_characters_long",
        outbox_enabled=outbox_enabled,
        outbox_encryption_key=VALID_KEY_B64 if outbox_enabled else None,
        outbox_encryption_key_id="v1",
        google_client_id="dummy-id" if enable_gmail else None,
        google_client_secret="dummy-secret" if enable_gmail else None,
        google_redirect_uri="https://app.example.test/auth/callback" if enable_gmail else None,
        gmail_sender_email="admin@bomberos.test" if enable_gmail else None,
        gmail_refresh_token="dummy-token" if enable_gmail else None,
        public_base_url="https://app.example.test",
        admin_rate_limit_reissue_requests=20,
    )


@pytest_asyncio.fixture(scope="module")
async def ephemeral_engine() -> AsyncIterator[AsyncEngine]:
    validate_target_database(EPHEMERAL_M05_DB_URL, require_ephemeral=True)
    engine = create_async_engine(
        EPHEMERAL_M05_DB_URL,
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
        await session.execute(text("TRUNCATE TABLE idempotency_records CASCADE;"))
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
# 1. Isolation & Setup Verification
# =========================================================================


@pytest.mark.asyncio
async def test_ephemeral_database_isolation_and_port(ephemeral_engine: AsyncEngine) -> None:
    async with ephemeral_engine.connect() as conn:
        res = await conn.execute(text("SELECT inet_server_port(), current_database();"))
        port, db_name = res.one()
        assert port == 55432, "Must run exclusively on ephemeral port 55432"
        assert db_name == "fireassets_ephemeral_m05"


# =========================================================================
# 2. P1-A Fail-Closed Delivery Gating Tests
# =========================================================================


@pytest.mark.asyncio
async def test_reissue_real_postgres_both_delivery_disabled_zero_db_mutations(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """When both delivery channels are disabled, real PostgreSQL receives zero mutations."""
    now = datetime.now(UTC)
    async with session_factory() as session:
        req = RegistrationRequest(
            id=100,
            email="aspirante100@bomberos.test",
            status="approved",
            source="password",
            requested_at=now - timedelta(days=2),
            reissue_count=0,
        )
        old_inv = Invitation(
            id=500,
            email=req.email,
            token_hash="hash_old_500",
            rol_id=2,
            invited_by_id=10,
            expires_at=now - timedelta(hours=1),
        )
        session.add_all([req, old_inv])
        await session.commit()

    disabled_settings = make_ephemeral_settings(outbox_enabled=False, enable_gmail=False)
    admin_user = User(id=10, email="admin@bomberos.test", rol_id=1, activo=True)

    async with session_factory() as session:
        with pytest.raises(ApplicationError) as exc_info:
            await reissue_registration_invitation(
                session=session,
                request_id=100,
                actor=admin_user,
                idempotency_key="key-fail-closed-test",
                settings=disabled_settings,
            )
        assert exc_info.value.status_code == 503
        assert exc_info.value.code == "INVITATION_DELIVERY_UNAVAILABLE"
        await session.rollback()

    # Verify zero mutations in real PostgreSQL
    async with session_factory() as session:
        req_db = await session.scalar(select(RegistrationRequest).where(RegistrationRequest.id == 100))
        assert req_db.reissue_count == 0
        assert req_db.last_reissue_idempotency_key is None

        inv_count = await session.scalar(select(text("COUNT(*) FROM auth_invitations WHERE email = 'aspirante100@bomberos.test'")))
        assert inv_count == 1, "No new invitation should be created"

        outbox_count = await session.scalar(select(text("COUNT(*) FROM outbox_events")))
        assert outbox_count == 0

        idem_count = await session.scalar(select(text("COUNT(*) FROM idempotency_records")))
        assert idem_count == 0

        audit_count = await session.scalar(select(text("COUNT(*) FROM auditoria_cambios")))
        assert audit_count == 0


# =========================================================================
# 3. P1-B Persistent Historical Idempotency Tests
# =========================================================================


@pytest.mark.asyncio
async def test_reissue_historical_idempotency_preserves_count_after_k2(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Core P1-B demonstration: Replay of historical K1 after K2 does NOT consume count=3."""
    now = datetime.now(UTC)
    async with session_factory() as session:
        req = RegistrationRequest(
            id=200,
            email="aspirante200@bomberos.test",
            status="approved",
            source="password",
            requested_at=now - timedelta(days=5),
            reissue_count=0,
        )
        inv0 = Invitation(
            id=600,
            email=req.email,
            token_hash="hash_inv0",
            rol_id=2,
            invited_by_id=10,
            expires_at=now - timedelta(days=3),
        )
        session.add_all([req, inv0])
        await session.commit()

    admin_user = User(id=10, email="admin@bomberos.test", rol_id=1, activo=True)
    test_settings = make_ephemeral_settings(outbox_enabled=True)

    # 1. Reissue 1 with K1
    async with session_factory() as session:
        res1 = await reissue_registration_invitation(
            session=session,
            request_id=200,
            actor=admin_user,
            idempotency_key="key-k1",
            reason="Primera reemisión",
            settings=test_settings,
        )
        await session.commit()

    assert res1.reissue_count == 1
    assert res1.idempotent_replay is False
    k1_inv_id = res1.invitation_id

    # 2. Immediate replay with K1
    async with session_factory() as session:
        res1_replay = await reissue_registration_invitation(
            session=session,
            request_id=200,
            actor=admin_user,
            idempotency_key="key-k1",
            reason="Primera reemisión",
            settings=test_settings,
        )
        await session.commit()

    assert res1_replay.reissue_count == 1
    assert res1_replay.invitation_id == k1_inv_id
    assert res1_replay.idempotent_replay is True

    # 3. Manually expire invitation 1 to make request eligible for reissuance 2
    async with session_factory() as session:
        inv1 = await session.scalar(select(Invitation).where(Invitation.id == k1_inv_id))
        inv1.expires_at = datetime.now(UTC) - timedelta(hours=1)
        await session.commit()

    # 4. Reissue 2 with K2
    async with session_factory() as session:
        res2 = await reissue_registration_invitation(
            session=session,
            request_id=200,
            actor=admin_user,
            idempotency_key="key-k2",
            reason="Segunda reemisión",
            settings=test_settings,
        )
        await session.commit()

    assert res2.reissue_count == 2
    assert res2.idempotent_replay is False
    k2_inv_id = res2.invitation_id
    assert k2_inv_id != k1_inv_id

    # 5. Manually expire invitation 2
    async with session_factory() as session:
        inv2 = await session.scalar(select(Invitation).where(Invitation.id == k2_inv_id))
        inv2.expires_at = datetime.now(UTC) - timedelta(hours=1)
        await session.commit()

    # 6. Delayed replay with historical key K1 arrives!
    async with session_factory() as session:
        res_k1_late = await reissue_registration_invitation(
            session=session,
            request_id=200,
            actor=admin_user,
            idempotency_key="key-k1",  # Historical K1
            reason="Primera reemisión",
            settings=test_settings,
        )
        await session.commit()

    # MUST be recognized as replay of operation 1!
    assert res_k1_late.reissue_count == 1, "Must return original operation count=1"
    assert res_k1_late.invitation_id == k1_inv_id, "Must return original invitation ID"
    assert res_k1_late.idempotent_replay is True

    # Verify that in real PostgreSQL, reissue_count is STILL 2 (NOT incremented to 3!)
    async with session_factory() as session:
        req_db = await session.scalar(select(RegistrationRequest).where(RegistrationRequest.id == 200))
        assert req_db.reissue_count == 2, "Quota MUST NOT be consumed by historical replay!"

        # Total invitations in DB must be exactly 3 (inv0 + inv1 + inv2), NOT 4!
        total_invs = await session.scalar(select(text("COUNT(*) FROM auth_invitations WHERE email = 'aspirante200@bomberos.test'")))
        assert total_invs == 3


@pytest.mark.asyncio
async def test_reissue_idempotency_key_reuse_different_params_conflict(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Reusing the same key with different parameters returns HTTP 409 Conflict."""
    now = datetime.now(UTC)
    async with session_factory() as session:
        req = RegistrationRequest(
            id=300,
            email="aspirante300@bomberos.test",
            status="approved",
            source="password",
            requested_at=now - timedelta(days=3),
            reissue_count=0,
        )
        inv0 = Invitation(
            id=700,
            email=req.email,
            token_hash="hash_inv300",
            rol_id=2,
            invited_by_id=10,
            expires_at=now - timedelta(days=1),
        )
        session.add_all([req, inv0])
        await session.commit()

    admin_user = User(id=10, email="admin@bomberos.test", rol_id=1, activo=True)
    test_settings = make_ephemeral_settings(outbox_enabled=True)

    # Reissue with Reason A
    async with session_factory() as session:
        await reissue_registration_invitation(
            session=session,
            request_id=300,
            actor=admin_user,
            idempotency_key="key-conflict-check",
            reason="Motivo Original A",
            settings=test_settings,
        )
        await session.commit()

    # Reissue with same key but Reason B
    async with session_factory() as session:
        with pytest.raises(ApplicationError) as exc_info:
            await reissue_registration_invitation(
                session=session,
                request_id=300,
                actor=admin_user,
                idempotency_key="key-conflict-check",
                reason="Motivo Alterado B",
                settings=test_settings,
            )
        assert exc_info.value.status_code == 409
        assert exc_info.value.code == "IDEMPOTENCY_CONFLICT"


@pytest.mark.asyncio
async def test_reissue_concurrent_same_key_produces_single_invitation(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Under real PostgreSQL concurrency, two parallel calls with same key produce exactly 1 reissue."""
    now = datetime.now(UTC)
    async with session_factory() as session:
        req = RegistrationRequest(
            id=400,
            email="aspirante400@bomberos.test",
            status="approved",
            source="password",
            requested_at=now - timedelta(days=3),
            reissue_count=0,
        )
        inv0 = Invitation(
            id=800,
            email=req.email,
            token_hash="hash_inv400",
            rol_id=2,
            invited_by_id=10,
            expires_at=now - timedelta(days=1),
        )
        session.add_all([req, inv0])
        await session.commit()

    admin_user = User(id=10, email="admin@bomberos.test", rol_id=1, activo=True)
    test_settings = make_ephemeral_settings(outbox_enabled=True)

    async def run_reissue_task() -> ReissueResult:
        async with session_factory() as session:
            res = await reissue_registration_invitation(
                session=session,
                request_id=400,
                actor=admin_user,
                idempotency_key="key-concurrent-race-1",
                reason="Reemisión concurrente",
                settings=test_settings,
            )
            await session.commit()
            return res

    results = await asyncio.gather(run_reissue_task(), run_reissue_task())
    non_replays = [r for r in results if not r.idempotent_replay]
    replays = [r for r in results if r.idempotent_replay]

    assert len(non_replays) == 1, "Exactly one task should execute the creation"
    assert len(replays) == 1, "The other task should return idempotent replay"
    assert non_replays[0].invitation_id == replays[0].invitation_id
    assert non_replays[0].reissue_count == replays[0].reissue_count == 1

    # Database invariant check
    async with session_factory() as session:
        req_db = await session.scalar(select(RegistrationRequest).where(RegistrationRequest.id == 400))
        assert req_db.reissue_count == 1

        idem_count = await session.scalar(select(text("COUNT(*) FROM idempotency_records WHERE aggregate_id = '400'")))
        assert idem_count == 1


@pytest.mark.asyncio
async def test_reissue_max_three_reissues_ceiling(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Enforces that after 3 reissuances, the 4th non-idempotent attempt is rejected with HTTP 429."""
    now = datetime.now(UTC)
    async with session_factory() as session:
        req = RegistrationRequest(
            id=500,
            email="aspirante500@bomberos.test",
            status="approved",
            source="password",
            requested_at=now - timedelta(days=10),
            reissue_count=0,
        )
        inv0 = Invitation(id=900, email=req.email, token_hash="h900", rol_id=2, invited_by_id=10, expires_at=now - timedelta(days=5))
        session.add_all([req, inv0])
        await session.commit()

    admin_user = User(id=10, email="admin@bomberos.test", rol_id=1, activo=True)
    test_settings = make_ephemeral_settings(outbox_enabled=True)

    for i in range(1, 4):
        async with session_factory() as session:
            # Expire prior invitations
            prior = (await session.scalars(select(Invitation).where(Invitation.email == "aspirante500@bomberos.test"))).all()
            for inv in prior:
                inv.expires_at = datetime.now(UTC) - timedelta(hours=1)
            await session.commit()

        async with session_factory() as session:
            res = await reissue_registration_invitation(
                session=session,
                request_id=500,
                actor=admin_user,
                idempotency_key=f"key-round-{i}",
                settings=test_settings,
            )
            await session.commit()
            assert res.reissue_count == i

    # 4th attempt with fresh key
    async with session_factory() as session:
        # Expire prior
        prior = (await session.scalars(select(Invitation).where(Invitation.email == "aspirante500@bomberos.test"))).all()
        for inv in prior:
            inv.expires_at = datetime.now(UTC) - timedelta(hours=1)
        await session.commit()

    async with session_factory() as session:
        with pytest.raises(ApplicationError) as exc_info:
            await reissue_registration_invitation(
                session=session,
                request_id=500,
                actor=admin_user,
                idempotency_key="key-round-4-exceeded",
                settings=test_settings,
            )
        assert exc_info.value.status_code == 429
        assert exc_info.value.code == "REISSUE_LIMIT_EXCEEDED"


@pytest.mark.asyncio
async def test_reissue_rollback_leaves_zero_state(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Verifies complete ACID rollback if an error occurs before commit."""
    now = datetime.now(UTC)
    async with session_factory() as session:
        req = RegistrationRequest(
            id=600,
            email="aspirante600@bomberos.test",
            status="approved",
            source="password",
            requested_at=now - timedelta(days=3),
            reissue_count=0,
        )
        inv0 = Invitation(id=1000, email=req.email, token_hash="h1000", rol_id=2, invited_by_id=10, expires_at=now - timedelta(days=1))
        session.add_all([req, inv0])
        await session.commit()

    admin_user = User(id=10, email="admin@bomberos.test", rol_id=1, activo=True)
    test_settings = make_ephemeral_settings(outbox_enabled=True)

    async with session_factory() as session:
        try:
            await reissue_registration_invitation(
                session=session,
                request_id=600,
                actor=admin_user,
                idempotency_key="key-will-rollback",
                settings=test_settings,
            )
            # Simulate unexpected crash before commit
            raise RuntimeError("Forced crash before commit")
        except RuntimeError:
            await session.rollback()

    # Verify state in PostgreSQL
    async with session_factory() as session:
        req_db = await session.scalar(select(RegistrationRequest).where(RegistrationRequest.id == 600))
        assert req_db.reissue_count == 0

        idem_count = await session.scalar(select(text("COUNT(*) FROM idempotency_records WHERE aggregate_id = '600'")))
        assert idem_count == 0

        outbox_count = await session.scalar(select(text("COUNT(*) FROM outbox_events WHERE aggregate_id = '600'")))
        assert outbox_count == 0
