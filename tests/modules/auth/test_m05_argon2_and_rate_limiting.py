"""Deterministic, isolated test suite for finding M-05 remediation.

Covers:
1. Argon2AdmissionGuard: hardware bounds, timeout isolation, cancellation shielding, zero leaks.
2. Timing parity and dummy hash in authenticate_user.
3. RateLimiterService: IP limits, failed login (IP, Account) limits, NAT multi-user isolation,
   trusted proxy validation, Retry-After headers, and public registration idempotence.
Operates with ZERO connections to forbidden databases (fireassets, fireassets_test, postgres).
"""

from __future__ import annotations

import asyncio
import logging
import math
import threading
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.config.settings import get_settings
from app.infrastructure.database.session import get_database_session
from app.infrastructure.rate_limit.argon_guard import (
    Argon2AdmissionGuard,
    Argon2AdmissionSaturated,
    reset_argon2_guard,
)
from app.infrastructure.rate_limit.limiter import (
    InMemoryRateLimitStorage,
    RateLimiterService,
    RateLimitExceeded,
    RateLimitStorageUnavailable,
    RedisRateLimitStorage,
    derive_rate_limit_key,
    get_rate_limit_storage,
    get_trusted_client_ip,
    pseudonymize,
    reset_rate_limit_storage,
)
from app.main import app
from app.modules.auth.dependencies import require_authenticated_user
from app.modules.auth.models import User
from app.modules.auth.service import authenticate_user
from app.modules.auth.validations.passwords import (
    DUMMY_ARGON2_HASH,
    hash_password,
)
from app.shared.errors.authentication_error import AuthenticationError

# ---------------------------------------------------------------------------
# 1. ARGON2 ADMISSION GUARD TESTS
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_argon2_guard_concurrency_and_saturation() -> None:
    """Validate max_running=2, max_waiting=2 bounds and immediate rejection of 5th request."""
    guard = Argon2AdmissionGuard(max_running=2, max_waiting=2, queue_timeout=0.30)
    release_gate = threading.Event()

    def heavy_op() -> str:
        release_gate.wait()
        return "done"

    outcomes: list[str] = []

    async def client_call() -> None:
        try:
            res = await guard.run_verified(heavy_op)
            outcomes.append(res)
        except Argon2AdmissionSaturated as err:
            outcomes.append(err.code)

    async with asyncio.TaskGroup() as tg:
        # Start 4 requests (2 running + 2 waiting in queue = 4 admitted)
        for _ in range(4):
            tg.create_task(client_call())
        await asyncio.sleep(0.02)

        # 5th request must be rejected synchronously via acquire_nowait (WouldBlock)
        tg.create_task(client_call())
        await asyncio.sleep(0.02)

        release_gate.set()

    assert outcomes.count("done") == 4
    assert outcomes.count("ARGON2_CAPACITY_EXCEEDED") == 1
    assert guard.admission_limiter.available_tokens == 4
    assert guard.execution_slot.available_tokens == 2


@pytest.mark.asyncio
async def test_argon2_guard_queue_timeout_isolation() -> None:
    """Queue timeout must apply strictly to queue waiting, NOT to thread execution time."""
    guard = Argon2AdmissionGuard(max_running=1, max_waiting=2, queue_timeout=0.08)
    gate = threading.Event()

    def blocking_work() -> str:
        gate.wait()
        return "ok"

    async with asyncio.TaskGroup() as tg:
        # Task 0 occupies the single execution slot
        tg.create_task(guard.run_verified(blocking_work))
        await asyncio.sleep(0.01)

        # Task 1 waits in queue. Its queue_timeout (0.08s) will expire while Task 0 blocks
        timed_out = False
        try:
            await guard.run_verified(lambda: "never")
        except Argon2AdmissionSaturated as err:
            assert err.code == "ARGON2_CAPACITY_EXCEEDED"
            timed_out = True

        assert timed_out is True
        gate.set()

    # Now verify Case B: Task gets slot immediately, work takes 0.15s (> 0.08s timeout)
    t0 = time.monotonic()
    await guard.run_verified(time.sleep, 0.15)
    elapsed = time.monotonic() - t0
    assert elapsed >= 0.14
    assert guard.admission_limiter.available_tokens == 3
    assert guard.execution_slot.available_tokens == 1


@pytest.mark.asyncio
async def test_argon2_guard_cancellation_shielding() -> None:
    """Cancellation during execution must shield the C thread and not release slot prematurely."""
    import anyio

    guard = Argon2AdmissionGuard(max_running=1, max_waiting=1, queue_timeout=0.50)
    thread_started = threading.Event()
    thread_finished = threading.Event()

    def cancellable_target() -> str:
        thread_started.set()
        time.sleep(0.10)
        thread_finished.set()
        return "done"

    async def cancel_running() -> None:
        with anyio.CancelScope() as scope:

            async def target() -> None:
                await guard.run_verified(cancellable_target)

            async with anyio.create_task_group() as sub_tg:
                sub_tg.start_soon(target)
                await anyio.sleep(0.02)
                assert thread_started.is_set()
                scope.cancel()
                # Slot must still be occupied while C thread runs
                assert guard.execution_slot.available_tokens == 0

    await cancel_running()

    # Thread ran to completion before slot was released
    assert thread_finished.is_set()
    assert guard.execution_slot.available_tokens == 1
    assert guard.admission_limiter.available_tokens == 2


@pytest.mark.asyncio
async def test_argon2_guard_input_validation() -> None:
    """Invalid constructor arguments (booleans, <=0, inf, nan) must be rejected explicitly."""
    with pytest.raises(ValueError, match="max_running"):
        Argon2AdmissionGuard(max_running=0)
    with pytest.raises(ValueError, match="max_running"):
        Argon2AdmissionGuard(max_running=True)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="max_waiting"):
        Argon2AdmissionGuard(max_waiting=-1)
    with pytest.raises(ValueError, match="max_waiting"):
        Argon2AdmissionGuard(max_waiting=False)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="queue_timeout"):
        Argon2AdmissionGuard(queue_timeout=0)
    with pytest.raises(ValueError, match="queue_timeout"):
        Argon2AdmissionGuard(queue_timeout=-1.5)
    with pytest.raises(ValueError, match="queue_timeout"):
        Argon2AdmissionGuard(queue_timeout=True)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="queue_timeout"):
        Argon2AdmissionGuard(queue_timeout=float("inf"))
    with pytest.raises(ValueError, match="queue_timeout"):
        Argon2AdmissionGuard(queue_timeout=float("-inf"))
    with pytest.raises(ValueError, match="queue_timeout"):
        Argon2AdmissionGuard(queue_timeout=float("nan"))
    with pytest.raises(ValueError, match="queue_timeout"):
        Argon2AdmissionGuard(queue_timeout="invalid")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 2. DUMMY HASH & TIMING PARITY IN AUTH SERVICE
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_authenticate_user_with_dummy_hash_for_nonexistent_account() -> None:
    """Nonexistent email must execute Argon2 verification against DUMMY_ARGON2_HASH."""
    mock_session = AsyncMock()
    mock_session.scalar.return_value = None  # User does not exist

    with patch("app.modules.auth.service.verify_password") as mock_verify:
        mock_verify.return_value = False
        with pytest.raises(AuthenticationError) as exc_info:
            await authenticate_user(
                mock_session, "nonexistent@bomberos.gob.ar", "any_password"
            )

        assert exc_info.value.code == "INVALID_CREDENTIALS"
        # verify_password was called exactly once with DUMMY_ARGON2_HASH
        mock_verify.assert_called_once_with("any_password", DUMMY_ARGON2_HASH)


@pytest.mark.asyncio
async def test_authenticate_user_with_passwordless_oauth_account() -> None:
    """Existing account with password_hash=None must execute Argon2 against DUMMY_ARGON2_HASH."""
    mock_session = AsyncMock()
    user = User(
        id=1, email="oauth_only@bomberos.gob.ar", password_hash=None, activo=True
    )
    mock_session.scalar.return_value = user

    with patch("app.modules.auth.service.verify_password") as mock_verify:
        mock_verify.return_value = False
        with pytest.raises(AuthenticationError) as exc_info:
            await authenticate_user(mock_session, user.email, "any_password")

        assert exc_info.value.code == "INVALID_CREDENTIALS"
        mock_verify.assert_called_once_with("any_password", DUMMY_ARGON2_HASH)


@pytest.mark.asyncio
async def test_authenticate_user_inactive_account_preservation() -> None:
    """Inactive accounts (activo=False) must be rejected even with valid password (preserving M-06)."""
    mock_session = AsyncMock()
    valid_hash = hash_password("secret_123")
    user = User(
        id=2, email="inactive@bomberos.gob.ar", password_hash=valid_hash, activo=False
    )
    mock_session.scalar.return_value = user

    with pytest.raises(AuthenticationError) as exc_info:
        await authenticate_user(mock_session, user.email, "secret_123")

    assert exc_info.value.code == "INVALID_CREDENTIALS"


# ---------------------------------------------------------------------------
# 3. RATE LIMITING, TRUSTED PROXIES & BRUTE FORCE SHIELD
# ---------------------------------------------------------------------------


def test_trusted_proxy_ip_extraction() -> None:
    """Untrusted peers must never be able to spoof IP via X-Forwarded-For."""
    trusted = ["127.0.0.1", "::1"]

    # 1. Untrusted peer: 198.51.100.1 sends fake X-Forwarded-For -> IGNORED
    req_untrusted = MagicMock()
    req_untrusted.client.host = "198.51.100.1"
    req_untrusted.headers = {"x-forwarded-for": "8.8.8.8, 1.1.1.1"}
    ip = get_trusted_client_ip(req_untrusted, trusted)
    assert ip == "198.51.100.1"

    # 2. Trusted proxy: 127.0.0.1 forwards real client 203.0.113.50 -> TRUSTED
    req_trusted = MagicMock()
    req_trusted.client.host = "127.0.0.1"
    req_trusted.headers = {"x-forwarded-for": "203.0.113.50, 127.0.0.1"}
    ip_real = get_trusted_client_ip(req_trusted, trusted)
    assert ip_real == "203.0.113.50"


def test_hmac_pseudonymization_privacy() -> None:
    """Pseudonymization must be deterministic, non-reversible, and avoid plain PII."""
    settings = get_settings()
    key = derive_rate_limit_key(settings)
    assert len(key) == 32

    pseudo_1 = pseudonymize("Guardia@Bomberos.Gob.Ar", key, prefix="acct")
    pseudo_2 = pseudonymize("guardia@bomberos.gob.ar ", key, prefix="acct")
    assert pseudo_1 == pseudo_2  # Case & whitespace normalization
    assert pseudo_1.startswith("acct:")
    assert "bomberos" not in pseudo_1
    assert len(pseudo_1) == 5 + 16  # acct: + 16 hex chars


@pytest.mark.asyncio
async def test_login_rate_limit_and_nat_isolation() -> None:
    """5 failed attempts against account_a locks account_a for that IP, but account_b succeeds."""
    storage = InMemoryRateLimitStorage()
    reset_rate_limit_storage(storage)
    limiter = RateLimiterService()

    fake_request = MagicMock()
    fake_request.client.host = "192.0.2.1"
    fake_request.headers = {}

    # Record 5 login failures for user_a
    for _ in range(5):
        await limiter.record_login_failure(fake_request, "user_a@bomberos.gob.ar")

    # 6th attempt for user_a from same IP must raise RateLimitExceeded (HTTP 429)
    with pytest.raises(RateLimitExceeded) as exc_info:
        await limiter.check_login_pre_auth(fake_request, "user_a@bomberos.gob.ar")
    assert exc_info.value.status_code == 429
    assert exc_info.value.code == "ACCOUNT_LOCKED_FOR_IP"
    assert exc_info.value.headers is not None
    assert "Retry-After" in exc_info.value.headers

    # NAT isolation check: user_b from the SAME IP must NOT be blocked!
    # (Does not raise RateLimitExceeded)
    await limiter.check_login_pre_auth(fake_request, "user_b@bomberos.gob.ar")


@pytest.mark.asyncio
async def test_global_account_failure_alert_no_lockout(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """15 failures across multiple IPs emits CRITICAL alert but does not block account globally."""
    storage = InMemoryRateLimitStorage()
    reset_rate_limit_storage(storage)
    limiter = RateLimiterService()

    caplog.set_level(logging.CRITICAL)

    # Simulate 15 failed logins coming from 15 distinct distributed IPs
    for i in range(15):
        req = MagicMock()
        req.client.host = f"198.51.100.{i + 1}"
        req.headers = {}
        await limiter.record_login_failure(req, "victim@bomberos.gob.ar")

    # Critical security log was emitted
    assert any(
        "security_alert: high_login_failure_rate_for_account" in record.message
        for record in caplog.records
    )

    # Legitimate station IP (which has not failed 5 times) is STILL allowed to attempt login!
    station_req = MagicMock()
    station_req.client.host = "203.0.113.10"
    station_req.headers = {}
    # Must NOT raise RateLimitExceeded
    await limiter.check_login_pre_auth(station_req, "victim@bomberos.gob.ar")


@pytest.mark.asyncio
async def test_registration_request_limits_and_idempotence() -> None:
    """5 req/hour per IP triggers 429; duplicate email within 24h returns False for silent 202."""
    storage = InMemoryRateLimitStorage()
    reset_rate_limit_storage(storage)
    limiter = RateLimiterService()

    req = MagicMock()
    req.client.host = "192.0.2.100"
    req.headers = {}

    email = "applicant@example.test"

    # First attempt: allowed (Hit 1 for IP)
    allowed = await limiter.check_registration_request_allowed(req, email)
    assert allowed is True

    # Immediate second attempt with same email: returns False for silent 202 (Hit 2 for IP)
    allowed_second = await limiter.check_registration_request_allowed(req, email)
    assert allowed_second is False

    # Simulate 3 more requests with different emails from same IP (Hits 3, 4, 5 for IP)
    for i in range(3):
        res = await limiter.check_registration_request_allowed(
            req, f"other_{i}@example.test"
        )
        assert res is True

    # 6th request from same IP within the hour: raises RateLimitExceeded (HTTP 429)
    with pytest.raises(RateLimitExceeded) as exc_info:
        await limiter.check_registration_request_allowed(req, "exceeding@example.test")
    assert exc_info.value.status_code == 429
    assert exc_info.value.code == "REGISTRATION_IP_RATE_LIMIT_EXCEEDED"


# ---------------------------------------------------------------------------
# 4. END-TO-END HTTP INTEGRATION TESTS (FASTAPI VIA ASGITRANSPORT)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_http_login_rate_limit_exceeded() -> None:
    """Overloading POST /auth/login returns HTTP 429 with Retry-After header."""
    reset_rate_limit_storage(InMemoryRateLimitStorage())
    reset_argon2_guard(None)

    # Mock database session dependency override so no DB is contacted
    mock_session = AsyncMock()
    mock_session.scalar.return_value = None  # user not found

    app.dependency_overrides[get_database_session] = lambda: mock_session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        # Trigger 5 password failures for test@example.com from 127.0.0.1
        for _ in range(5):
            resp = await client.post(
                "/auth/login",
                json={"email": "test@example.com", "password": "wrong_password"},
            )
            assert resp.status_code == 401

        # 6th attempt must be rejected with HTTP 429
        resp_blocked = await client.post(
            "/auth/login",
            json={"email": "test@example.com", "password": "wrong_password"},
        )
        assert resp_blocked.status_code == 429
        assert resp_blocked.json()["error"]["code"] == "ACCOUNT_LOCKED_FOR_IP"
        assert "retry-after" in resp_blocked.headers

    app.dependency_overrides.pop(get_database_session, None)


@pytest.mark.asyncio
async def test_http_registration_requests_rate_limit() -> None:
    """POST /auth/registration-requests enforces 5/hour IP limit with HTTP 429."""
    reset_rate_limit_storage(InMemoryRateLimitStorage())

    mock_session = AsyncMock()
    app.dependency_overrides[get_database_session] = lambda: mock_session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        for i in range(5):
            resp = await client.post(
                "/auth/registration-requests",
                json={"email": f"applicant_{i}@example.com"},
            )
            assert resp.status_code == 202

        # 6th request from same IP returns HTTP 429
        resp_limit = await client.post(
            "/auth/registration-requests",
            json={"email": "applicant_over@example.com"},
        )
        assert resp_limit.status_code == 429
        assert (
            resp_limit.json()["error"]["code"] == "REGISTRATION_IP_RATE_LIMIT_EXCEEDED"
        )
        assert "retry-after" in resp_limit.headers

    app.dependency_overrides.pop(get_database_session, None)


@pytest.mark.asyncio
async def test_http_google_oauth_rate_limits() -> None:
    """GET /auth/google/start and /auth/google/callback enforce IP limits."""
    reset_rate_limit_storage(InMemoryRateLimitStorage())

    mock_session = AsyncMock()
    app.dependency_overrides[get_database_session] = lambda: mock_session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        # 15 requests allowed to /auth/google/start
        for _ in range(15):
            await client.get("/auth/google/start")

        # 16th request returns HTTP 429
        resp_start_limit = await client.get("/auth/google/start")
        assert resp_start_limit.status_code == 429
        assert "retry-after" in resp_start_limit.headers

        # 10 requests allowed to /auth/google/callback
        for _ in range(10):
            await client.get("/auth/google/callback")

        # 11th request returns HTTP 429
        resp_callback_limit = await client.get("/auth/google/callback")
        assert resp_callback_limit.status_code == 429
        assert "retry-after" in resp_callback_limit.headers

    app.dependency_overrides.pop(get_database_session, None)


# ---------------------------------------------------------------------------
# 5. REDIS BACKEND, LUA ATOMICITY, AND FAILURE POLICY TESTS
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rate_limit_backend_selection_and_validation() -> None:
    """Validate explicit backend selection, rejection of invalid names, and prohibition of silent fallback."""
    reset_rate_limit_storage(None)

    # 1. Valid 'memory' backend returns InMemoryRateLimitStorage
    settings_mem = get_settings().model_copy(update={"rate_limit_backend": "memory"})
    storage_mem = get_rate_limit_storage(settings_mem)
    assert isinstance(storage_mem, InMemoryRateLimitStorage)

    # 2. Unknown backend name raises ValueError explicitly
    reset_rate_limit_storage(None)
    settings_invalid = get_settings().model_copy(update={"rate_limit_backend": "dynamodb"})
    with pytest.raises(ValueError, match="Backend de rate limit no soportado"):
        get_rate_limit_storage(settings_invalid)

    # 3. 'redis' backend when redis-py is not installed raises RuntimeError without silent fallback
    reset_rate_limit_storage(None)
    settings_redis = get_settings().model_copy(update={"rate_limit_backend": "redis"})
    with pytest.raises(RuntimeError, match="biblioteca 'redis' no está instalada"):
        get_rate_limit_storage(settings_redis)

    reset_rate_limit_storage(InMemoryRateLimitStorage())


@pytest.mark.asyncio
async def test_redis_rate_limit_storage_lua_operations() -> None:
    """Verify RedisRateLimitStorage correctly invokes Lua scripts for atomic hit, peek, and reset."""
    mock_redis_client = AsyncMock()

    # Case A: hit allowed (Lua returns [1, 1, 0])
    mock_redis_client.eval.return_value = [1, 1, 0]
    redis_storage = RedisRateLimitStorage(client=mock_redis_client)

    allowed, count, retry_after = await redis_storage.hit("rl:test:key", window_seconds=60, max_hits=5)
    assert allowed is True
    assert count == 1
    assert retry_after == 0
    assert mock_redis_client.eval.await_count == 1

    # Case B: hit over limit (Lua returns [0, 5, 45])
    mock_redis_client.eval.return_value = [0, 5, 45]
    allowed, count, retry_after = await redis_storage.hit("rl:test:key", window_seconds=60, max_hits=5)
    assert allowed is False
    assert count == 5
    assert retry_after == 45

    # Case C: peek within limit (Lua returns [1, 3, 0])
    mock_redis_client.eval.return_value = [1, 3, 0]
    allowed, count, retry_after = await redis_storage.peek("rl:test:key", window_seconds=60, max_hits=5)
    assert allowed is True
    assert count == 3
    assert retry_after == 0

    # Case D: peek over limit (Lua returns [0, 5, 20])
    mock_redis_client.eval.return_value = [0, 5, 20]
    allowed, count, retry_after = await redis_storage.peek("rl:test:key", window_seconds=60, max_hits=5)
    assert allowed is False
    assert count == 5
    assert retry_after == 20

    # Case E: reset deletes primary key and sequence key
    await redis_storage.reset("rl:test:key")
    mock_redis_client.delete.assert_awaited_once_with("rl:test:key", "rl:test:key:seq")


@pytest.mark.asyncio
async def test_redis_rate_limit_storage_failure_policy_and_isolation() -> None:
    """Redis errors must raise RateLimitStorageUnavailable (503) without exposing credentials."""
    mock_redis_client = AsyncMock()
    mock_redis_client.eval.side_effect = ConnectionError("Connection refused to redis://secret_user:secret_pass@10.0.0.1:6379")
    mock_redis_client.delete.side_effect = TimeoutError("Timed out waiting for Redis socket")

    redis_storage = RedisRateLimitStorage(client=mock_redis_client)

    # 1. hit failure raises 503 with Retry-After: 5
    with pytest.raises(RateLimitStorageUnavailable) as exc_hit:
        await redis_storage.hit("rl:fail:key", window_seconds=60, max_hits=5)
    assert exc_hit.value.status_code == 503
    assert exc_hit.value.headers == {"Retry-After": "5"}
    assert "secret_pass" not in str(exc_hit.value.message)
    assert "10.0.0.1" not in str(exc_hit.value.message)

    # 2. peek failure raises 503
    with pytest.raises(RateLimitStorageUnavailable) as exc_peek:
        await redis_storage.peek("rl:fail:key", window_seconds=60, max_hits=5)
    assert exc_peek.value.status_code == 503

    # 3. reset failure raises 503
    with pytest.raises(RateLimitStorageUnavailable) as exc_reset:
        await redis_storage.reset("rl:fail:key")
    assert exc_reset.value.status_code == 503


# ---------------------------------------------------------------------------
# 6. ADMINISTRATIVE ROUTES RATE LIMITING AND ISOLATION TESTS
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_admin_registration_requests_rate_limiting_and_isolation() -> None:
    """Administrative registration request endpoints enforce per-admin rate limits and NAT isolation."""
    reset_rate_limit_storage(InMemoryRateLimitStorage())

    admin1 = User(id=101, email="admin1@cuartel.gob.ar", display_name="Admin Uno", rol_id=1, activo=True)
    admin2 = User(id=102, email="admin2@cuartel.gob.ar", display_name="Admin Dos", rol_id=1, activo=True)

    current_admin = admin1
    app.dependency_overrides[require_authenticated_user] = lambda: current_admin

    mock_session = AsyncMock()
    mock_session.scalars.return_value.all.return_value = []
    app.dependency_overrides[get_database_session] = lambda: mock_session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        # Patch require_admin and list_pending_requests
        with (
            patch("app.modules.auth.invitations.router.require_admin", new=AsyncMock(return_value=None)),
            patch("app.modules.auth.invitations.router.list_pending_requests", new=AsyncMock(return_value=[])),
        ):
            # Admin 1 performs 30 list requests (allowed)
            for _ in range(30):
                resp = await client.get("/auth/registration-requests")
                assert resp.status_code == 200

            # 31st request from Admin 1 returns 429
            resp_admin1_limit = await client.get("/auth/registration-requests")
            assert resp_admin1_limit.status_code == 429
            assert resp_admin1_limit.json()["error"]["code"] == "ADMIN_RATE_LIMIT_EXCEEDED"
            assert "retry-after" in resp_admin1_limit.headers

            # Isolation check: Admin 2 from the SAME station IP makes a request -> allowed!
            current_admin = admin2
            resp_admin2 = await client.get("/auth/registration-requests")
            assert resp_admin2.status_code == 200

    app.dependency_overrides.pop(require_authenticated_user, None)
    app.dependency_overrides.pop(get_database_session, None)


@pytest.mark.asyncio
async def test_admin_review_registration_rate_limiting() -> None:
    """POST /auth/registration-requests/{id}/review enforces review rate limits."""
    reset_rate_limit_storage(InMemoryRateLimitStorage())

    admin = User(id=201, email="reviewer@cuartel.gob.ar", display_name="Reviewer", rol_id=1, activo=True)
    app.dependency_overrides[require_authenticated_user] = lambda: admin

    mock_session = AsyncMock()
    app.dependency_overrides[get_database_session] = lambda: mock_session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        with (
            patch("app.modules.auth.invitations.router.require_admin", new=AsyncMock(return_value=None)),
            patch("app.modules.auth.invitations.router.review_registration_request", new=AsyncMock(return_value=None)),
        ):
            # 20 review requests allowed
            for _ in range(20):
                resp = await client.post(
                    "/auth/registration-requests/1/review",
                    json={"decision": "rejected"},
                )
                assert resp.status_code == 200

            # 21st review request triggers 429
            resp_review_limit = await client.post(
                "/auth/registration-requests/1/review",
                json={"decision": "rejected"},
            )
            assert resp_review_limit.status_code == 429
            assert resp_review_limit.json()["error"]["code"] == "ADMIN_RATE_LIMIT_EXCEEDED"
            assert "retry-after" in resp_review_limit.headers

    app.dependency_overrides.pop(require_authenticated_user, None)
    app.dependency_overrides.pop(get_database_session, None)


# ---------------------------------------------------------------------------
# 7. ADVERSARIAL REDIS LUA LIFECYCLE, ATOMICITY, AND TIMING DRIFT TESTS (T01-T14)
# ---------------------------------------------------------------------------


class DeterministicRedisSimulator:
    """Accurate in-memory simulator of Redis state for Lua sliding window operations."""

    def __init__(self) -> None:
        from collections import defaultdict

        self.zsets: dict[str, dict[str, float]] = defaultdict(dict)
        self.strings: dict[str, int] = defaultdict(int)
        self.ttls: dict[str, float] = {}
        self.commands_called: list[str] = []

    def _purge_expired(self, current_time: float) -> None:
        for k, exp in list(self.ttls.items()):
            if current_time >= exp:
                self.zsets.pop(k, None)
                self.strings.pop(k, None)
                self.ttls.pop(k, None)

    async def eval(
        self, script: str, numkeys: int, key: str, now_str: str, window_str: str, max_hits_str: str
    ) -> list[int]:
        now = float(now_str)
        window = float(window_str)
        max_hits = int(max_hits_str)
        cutoff = now - window

        self._purge_expired(now)

        # 1. ZREMRANGEBYSCORE key -inf cutoff
        self.commands_called.append("ZREMRANGEBYSCORE")
        active_zset = self.zsets[key]
        for member, score in list(active_zset.items()):
            if score <= cutoff:
                active_zset.pop(member)

        # 2. ZCARD key
        self.commands_called.append("ZCARD")
        count = len(active_zset)

        if "INCR" not in script:
            # SLIDING_WINDOW_PEEK_LUA
            if count >= max_hits:
                self.commands_called.append("ZRANGE")
                oldest_score = min(active_zset.values()) if active_zset else now
                retry_after = max(1, math.ceil(oldest_score + window - now))
                return [0, count, retry_after]
            return [1, count, 0]

        # SLIDING_WINDOW_HIT_LUA
        if count >= max_hits:
            self.commands_called.append("ZRANGE")
            oldest_score = min(active_zset.values()) if active_zset else now
            retry_after = max(1, math.ceil(oldest_score + window - now))
            return [0, count, retry_after]
        else:
            self.commands_called.append("INCR")
            seq_key = f"{key}:seq"
            self.strings[seq_key] += 1
            seq = self.strings[seq_key]

            self.commands_called.append("ZADD")
            member = f"{now}:{seq}"
            active_zset[member] = now

            self.commands_called.append("EXPIRE")
            expire_ttl = math.ceil(window) + 60
            self.ttls[key] = now + expire_ttl
            self.ttls[seq_key] = now + expire_ttl

            return [1, count + 1, 0]

    async def delete(self, *keys: str) -> int:
        deleted = 0
        for k in keys:
            if k in self.zsets or k in self.strings:
                deleted += 1
            self.zsets.pop(k, None)
            self.strings.pop(k, None)
            self.ttls.pop(k, None)
        return deleted


@pytest.mark.asyncio
async def test_t01_t02_t03_first_request_and_ttl_lifecycle() -> None:
    """T01, T02, T03: First request creates ZSET and sequence key; all receive valid TTL and expire after inactivity."""
    sim = DeterministicRedisSimulator()
    storage = RedisRateLimitStorage(client=sim)

    # T01: First hit creates primary ZSET and sequence key
    allowed, count, retry_after = await storage.hit("rl:user1", window_seconds=60, max_hits=5)
    assert allowed is True
    assert count == 1
    assert retry_after == 0
    assert "rl:user1" in sim.zsets
    assert "rl:user1:seq" in sim.strings

    # T02: Both keys receive TTL = window + 60 = 120s
    assert "rl:user1" in sim.ttls
    assert "rl:user1:seq" in sim.ttls
    assert sim.ttls["rl:user1"] > time.time()
    assert sim.ttls["rl:user1:seq"] > time.time()

    # T03: Inactivity past TTL purges keys completely
    sim._purge_expired(sim.ttls["rl:user1"] + 1)
    assert "rl:user1" not in sim.zsets
    assert "rl:user1:seq" not in sim.strings
    assert "rl:user1" not in sim.ttls


@pytest.mark.asyncio
async def test_t04_t05_t06_rejection_at_limit_retry_after_and_sliding_recovery() -> None:
    """T04, T05, T06: Limit rejection, boundary retry_after calculation, and sliding window recovery."""
    sim = DeterministicRedisSimulator()
    storage = RedisRateLimitStorage(client=sim)

    t0 = 1000.0
    # Simulate 5 hits within window 60
    with patch("time.time", side_effect=[t0, t0 + 1, t0 + 2, t0 + 3, t0 + 4]):
        for _ in range(5):
            allowed, _, _ = await storage.hit("rl:limit_test", window_seconds=60, max_hits=5)
            assert allowed is True

    # T04 & T05: 6th request at t0 + 10 must be rejected; retry_after must point to t0 + 60
    with patch("time.time", return_value=t0 + 10):
        allowed, count, retry_after = await storage.hit("rl:limit_test", window_seconds=60, max_hits=5)
        assert allowed is False
        assert count == 5
        # Oldest timestamp is t0. Window is 60. Now is t0 + 10. retry_after = t0 + 60 - (t0 + 10) = 50s
        assert retry_after == 50

    # T06: Advance time to t0 + 60.5: only t0 has expired (cutoff 1000.5), sliding window permits a new request
    with patch("time.time", return_value=t0 + 60.5):
        allowed, count, _ = await storage.hit("rl:limit_test", window_seconds=60, max_hits=5)
        assert allowed is True
        assert count == 5  # 1 expired (t0), 4 remaining + 1 new = 5


@pytest.mark.asyncio
async def test_t07_t08_reset_and_isolation() -> None:
    """T07 & T08: reset() deletes both keys, and distinct identifiers are strictly isolated."""
    sim = DeterministicRedisSimulator()
    storage = RedisRateLimitStorage(client=sim)

    # T08: Isolation
    await storage.hit("rl:ident_a", window_seconds=60, max_hits=2)
    await storage.hit("rl:ident_a", window_seconds=60, max_hits=2)
    allowed_a, _, _ = await storage.hit("rl:ident_a", window_seconds=60, max_hits=2)
    assert allowed_a is False

    # Ident B is fresh and allowed
    allowed_b, _, _ = await storage.hit("rl:ident_b", window_seconds=60, max_hits=2)
    assert allowed_b is True

    # T07: reset() on ident_a deletes both keys
    await storage.reset("rl:ident_a")
    assert "rl:ident_a" not in sim.zsets
    assert "rl:ident_a:seq" not in sim.strings
    # But ident_b remains
    assert "rl:ident_b" in sim.zsets


@pytest.mark.asyncio
async def test_t09_t10_concurrency_and_failure_policy() -> None:
    """T09 & T10: Concurrency serialization and failure policy raising 503 without fallback."""
    sim = DeterministicRedisSimulator()
    storage = RedisRateLimitStorage(client=sim)

    # T09: Concurrent requests
    results = await asyncio.gather(
        storage.hit("rl:conc", window_seconds=60, max_hits=3),
        storage.hit("rl:conc", window_seconds=60, max_hits=3),
        storage.hit("rl:conc", window_seconds=60, max_hits=3),
        storage.hit("rl:conc", window_seconds=60, max_hits=3),
    )
    allowed_count = sum(1 for r in results if r[0] is True)
    rejected_count = sum(1 for r in results if r[0] is False)
    assert allowed_count == 3
    assert rejected_count == 1

    # T10: Failure raises RateLimitStorageUnavailable (503)
    broken_client = AsyncMock()
    broken_client.eval.side_effect = ConnectionError("Redis unreachable")
    broken_storage = RedisRateLimitStorage(client=broken_client)
    with pytest.raises(RateLimitStorageUnavailable) as exc_info:
        await broken_storage.hit("rl:broken", window_seconds=60, max_hits=5)
    assert exc_info.value.status_code == 503
    assert exc_info.value.headers == {"Retry-After": "5"}


@pytest.mark.asyncio
async def test_t11_t12_t13_t14_advanced_invariants_and_drift() -> None:
    """T11, T12, T13, T14: Rejected requests leave no orphan keys, bulk keys expire, clock drift shift, and Lua API."""
    sim = DeterministicRedisSimulator()
    storage = RedisRateLimitStorage(client=sim)

    # T11: Saturated request does not create new sequence keys
    await storage.hit("rl:sat", window_seconds=60, max_hits=1)
    seq_val_before = sim.strings["rl:sat:seq"]
    await storage.hit("rl:sat", window_seconds=60, max_hits=1)  # Rejected
    assert sim.strings["rl:sat:seq"] == seq_val_before

    # T12: Large number of distinct identifiers all receive TTLs (no leaks)
    for i in range(50):
        await storage.hit(f"rl:bulk_{i}", window_seconds=30, max_hits=2)
    assert len(sim.zsets) == 51  # 50 bulk + 1 sat
    assert len(sim.ttls) == 102  # (50 + 1) * 2 keys, all with TTL
    assert all(ttl > 0 for ttl in sim.ttls.values())

    # T13: Clock drift analysis: if worker B has +5s drift, timestamps shift by 5s
    t_ref = 2000.0
    with patch("time.time", return_value=t_ref):
        await storage.hit("rl:drift", window_seconds=60, max_hits=5)
    with patch("time.time", return_value=t_ref + 5.0):
        await storage.hit("rl:drift", window_seconds=60, max_hits=5)
    scores = sorted(sim.zsets["rl:drift"].values())
    assert scores == [2000.0, 2005.0]

    # T14: Command compatibility with Redis API
    expected_commands = {"ZREMRANGEBYSCORE", "ZCARD", "ZRANGE", "INCR", "ZADD", "EXPIRE"}
    assert expected_commands.issubset(set(sim.commands_called))
