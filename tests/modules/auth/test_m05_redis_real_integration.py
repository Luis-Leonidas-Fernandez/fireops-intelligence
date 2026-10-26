"""Real Redis integration and distributed concurrency validation test suite (M-05R).

Validates:
- R01: 100 concurrent requests against a limit of 10 (exact atomic quota enforcement).
- R02: Key and tenant/station isolation (bursts on Key A never affect Key B).
- R03: TTL lifecycle and expiration hygiene (both ZSET and :seq keys expire at window + 60s).
- R04: Reset atomicity (deletes both ZSET member timestamps and sequence counter).
- R05: Sliding window recovery (quota gradually recovers as timestamps pass cutoff).
- R06: Redis failure policy (fail-closed HTTP 503 / RateLimitStorageUnavailable, zero bypass).
- R07: Real multi-process concurrency sharing quota across separate OS processes.
- R08: Client restart resilience (closing and recreating Redis client preserves quota).
- R09: HMAC pseudonymization hygiene (zero plaintext credentials in Redis, positive TTLs).
- R10: Clock drift evaluation (clock skew impact and monotonic sequence ordering).
- FastAPI Endpoints: /auth/login, /auth/registration-requests, /auth/google with real Redis.
- M-06 Inactive account protection preservation.

Operates with ZERO connections to forbidden databases (fireassets, fireassets_test, postgres).
Requires an isolated Redis instance on 127.0.0.1:6399.
"""

from __future__ import annotations

import asyncio
import multiprocessing as mp
import time
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
import redis
import redis.asyncio as aioredis
from httpx import ASGITransport, AsyncClient

from app.config.settings import get_settings
from app.infrastructure.database.session import get_database_session
from app.infrastructure.rate_limit.argon_guard import reset_argon2_guard
from app.infrastructure.rate_limit.limiter import (
    RateLimiterService,
    RateLimitStorageUnavailable,
    RedisRateLimitStorage,
    derive_rate_limit_key,
    pseudonymize,
    reset_rate_limit_storage,
)
from app.main import app
from app.modules.auth.validations.passwords import hash_password

REDIS_TEST_URL = "redis://127.0.0.1:6399/0"


@pytest.fixture(autouse=True)
def clean_redis_and_storage() -> Any:
    """Fixture to ensure a clean Redis DB before and after each test."""
    reset_rate_limit_storage(None)
    reset_argon2_guard(None)
    sync_client = redis.from_url(REDIS_TEST_URL)
    try:
        sync_client.flushdb()
    finally:
        sync_client.close()

    yield

    reset_rate_limit_storage(None)
    reset_argon2_guard(None)
    sync_client_post = redis.from_url(REDIS_TEST_URL)
    try:
        sync_client_post.flushdb()
    finally:
        sync_client_post.close()


# ---------------------------------------------------------------------------
# R01: 100 CONCURRENT REQUESTS AGAINST LIMIT 10
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_r01_100_concurrent_requests_against_limit_10() -> None:
    """R01: 100 parallel asynchronous requests against a limit of 10.

    Exactly 10 must be allowed and 90 rejected with valid Retry-After.
    """
    client = aioredis.from_url(REDIS_TEST_URL, encoding="utf-8", decode_responses=True)
    try:
        storage = RedisRateLimitStorage(client=client)
        key = "rl:test:r01:concurrency"
        window = 60
        limit = 10

        async def worker() -> tuple[bool, int, int]:
            return await storage.hit(key, window_seconds=window, max_hits=limit)

        # Launch 100 concurrent tasks
        results = await asyncio.gather(*(worker() for _ in range(100)))

        allowed = [r for r in results if r[0] is True]
        rejected = [r for r in results if r[0] is False]

        assert len(allowed) == 10, f"Expected exactly 10 allowed, got {len(allowed)}"
        assert len(rejected) == 90, f"Expected exactly 90 rejected, got {len(rejected)}"

        # Verify retry_after on all rejected requests
        for _, count, retry_after in rejected:
            assert count >= 10
            assert 1 <= retry_after <= 60

        # Check Redis ZSET card
        card = await client.zcard(key)
        assert card == 10
    finally:
        await client.aclose()


# ---------------------------------------------------------------------------
# R02: KEY AND TENANT / IP ISOLATION
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_r02_key_and_tenant_isolation() -> None:
    """R02: Bursts on Key A do not affect Key B."""
    client = aioredis.from_url(REDIS_TEST_URL, encoding="utf-8", decode_responses=True)
    try:
        storage = RedisRateLimitStorage(client=client)
        key_a = "rl:test:r02:tenant_a"
        key_b = "rl:test:r02:tenant_b"
        window = 60
        limit = 5

        # Exhaust Key A
        for _ in range(limit):
            allowed, _, _ = await storage.hit(key_a, window, limit)
            assert allowed is True

        allowed_a_blocked, _, _ = await storage.hit(key_a, window, limit)
        assert allowed_a_blocked is False

        # Key B must still be completely untouched
        for _ in range(limit):
            allowed, _, _ = await storage.hit(key_b, window, limit)
            assert allowed is True

        allowed_b_blocked, _, _ = await storage.hit(key_b, window, limit)
        assert allowed_b_blocked is False
    finally:
        await client.aclose()


# ---------------------------------------------------------------------------
# R03: TTL LIFECYCLE AND EXPIRATION HYGIENE
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_r03_ttl_lifecycle_and_expiration() -> None:
    """R03: Both ZSET and :seq keys receive TTL = window + 60s without zombie persistence."""
    client = aioredis.from_url(REDIS_TEST_URL, encoding="utf-8", decode_responses=True)
    try:
        storage = RedisRateLimitStorage(client=client)
        key = "rl:test:r03:ttl"
        window = 30
        limit = 5

        await storage.hit(key, window, limit)

        ttl_key = await client.ttl(key)
        ttl_seq = await client.ttl(f"{key}:seq")

        expected_ttl = window + 60
        assert 0 < ttl_key <= expected_ttl
        assert 0 < ttl_seq <= expected_ttl
        assert ttl_key >= expected_ttl - 2
        assert ttl_seq >= expected_ttl - 2
    finally:
        await client.aclose()


# ---------------------------------------------------------------------------
# R04: RESET ATOMICITY
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_r04_reset_atomicity() -> None:
    """R04: Reset deletes both the ZSET and :seq keys, resetting quota to 0."""
    client = aioredis.from_url(REDIS_TEST_URL, encoding="utf-8", decode_responses=True)
    try:
        storage = RedisRateLimitStorage(client=client)
        key = "rl:test:r04:reset"

        # Record 3 hits
        for _ in range(3):
            await storage.hit(key, 60, 5)

        assert await client.exists(key) == 1
        assert await client.exists(f"{key}:seq") == 1

        await storage.reset(key)

        assert await client.exists(key) == 0
        assert await client.exists(f"{key}:seq") == 0

        # Subsequent hit starts cleanly at 1
        allowed, count, retry_after = await storage.hit(key, 60, 5)
        assert allowed is True
        assert count == 1
        assert retry_after == 0
    finally:
        await client.aclose()


# ---------------------------------------------------------------------------
# R05: SLIDING WINDOW RECOVERY
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_r05_sliding_window_recovery() -> None:
    """R05: Old hits outside window are pruned, allowing new requests."""
    client = aioredis.from_url(REDIS_TEST_URL, encoding="utf-8", decode_responses=True)
    try:
        storage = RedisRateLimitStorage(client=client)
        key = "rl:test:r05:sliding"
        now = time.time()

        # Manually populate 2 past timestamps outside a 10s window (e.g. now - 15)
        # and 1 timestamp inside the window (now - 2)
        old_ts = now - 15
        recent_ts = now - 2

        await client.zadd(key, {f"{old_ts}:1": old_ts, f"{old_ts}:2": old_ts, f"{recent_ts}:3": recent_ts})
        await client.set(f"{key}:seq", "3")

        # Limit is 2 in a 10-second window.
        # Cutoff is now - 10. The 2 old entries should be pruned, leaving 1 active hit.
        # So a new hit should be allowed as 2nd hit.
        allowed, count, retry_after = await storage.hit(key, window_seconds=10, max_hits=2)
        assert allowed is True
        assert count == 2
        assert retry_after == 0

        # And 3rd hit should now be rejected
        allowed_rej, count_rej, retry_rej = await storage.hit(key, window_seconds=10, max_hits=2)
        assert allowed_rej is False
        assert count_rej == 2
        assert retry_rej >= 1
    finally:
        await client.aclose()


# ---------------------------------------------------------------------------
# R06: REDIS DOWN / NETWORK FAILURE (FAIL-CLOSED HTTP 503)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_r06_redis_down_fail_closed_503() -> None:
    """R06: Unreachable Redis raises RateLimitStorageUnavailable and results in 503."""
    # Connect to an invalid closed port (e.g. 6398)
    dead_client = aioredis.from_url(
        "redis://127.0.0.1:6398/0",
        encoding="utf-8",
        decode_responses=True,
        socket_connect_timeout=0.2,
    )
    dead_storage = RedisRateLimitStorage(client=dead_client)

    try:
        with pytest.raises(RateLimitStorageUnavailable, match="temporalmente no disponible"):
            await dead_storage.hit("rl:test:dead", 60, 5)
    finally:
        await dead_client.aclose()


# ---------------------------------------------------------------------------
# R07: MULTI-PROCESS CONCURRENCY SHARING QUOTA
# ---------------------------------------------------------------------------


def _multiprocess_worker(
    redis_url: str, key: str, window: int, limit: int, n_attempts: int, out_queue: mp.Queue
) -> None:
    """Top-level function for multiprocessing spawn workers."""
    async def run() -> tuple[int, int]:
        client = aioredis.from_url(redis_url, encoding="utf-8", decode_responses=True)
        storage = RedisRateLimitStorage(client=client)
        allowed = 0
        blocked = 0
        try:
            for _ in range(n_attempts):
                ok, _, _ = await storage.hit(key, window, limit)
                if ok:
                    allowed += 1
                else:
                    blocked += 1
            return allowed, blocked
        finally:
            await client.aclose()

    res = asyncio.run(run())
    out_queue.put(res)


@pytest.mark.asyncio
async def test_r07_multiprocess_concurrency_sharing_quota() -> None:
    """R07: Multiple separate OS worker processes share the exact same quota in Redis."""
    ctx = mp.get_context("spawn")
    q = ctx.Queue()
    key = "rl:test:r07:multiprocess"
    window = 60
    limit = 10
    num_processes = 4
    attempts_per_process = 10  # Total 40 requests against limit 10

    processes = [
        ctx.Process(
            target=_multiprocess_worker,
            args=(REDIS_TEST_URL, key, window, limit, attempts_per_process, q),
        )
        for _ in range(num_processes)
    ]

    for p in processes:
        p.start()

    # Wait in thread executor to avoid blocking asyncio event loop
    def _join_all() -> None:
        for p in processes:
            p.join()

    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, _join_all)

    results = [q.get() for _ in range(num_processes)]
    total_allowed = sum(r[0] for r in results)
    total_blocked = sum(r[1] for r in results)

    assert total_allowed == 10, f"Expected 10 total allowed across processes, got {total_allowed}"
    assert total_blocked == 30, f"Expected 30 total blocked across processes, got {total_blocked}"


# ---------------------------------------------------------------------------
# R08: CLIENT RESTART PRESERVES QUOTA
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_r08_client_restart_preserves_quota() -> None:
    """R08: Destroying and recreating Redis client instances preserves state in Redis."""
    key = "rl:test:r08:persistence"
    window = 60
    limit = 5

    # Client instance 1
    c1 = aioredis.from_url(REDIS_TEST_URL, encoding="utf-8", decode_responses=True)
    try:
        s1 = RedisRateLimitStorage(client=c1)
        for expected_count in range(1, 4):
            allowed, count, _ = await s1.hit(key, window, limit)
            assert allowed is True
            assert count == expected_count
    finally:
        await c1.aclose()

    # Brand new Client instance 2
    c2 = aioredis.from_url(REDIS_TEST_URL, encoding="utf-8", decode_responses=True)
    try:
        s2 = RedisRateLimitStorage(client=c2)
        allowed, count, _ = await s2.hit(key, window, limit)
        assert allowed is True
        assert count == 4, f"Expected quota count 4 after restart, got {count}"
    finally:
        await c2.aclose()


# ---------------------------------------------------------------------------
# R09: HMAC PSEUDONYMIZATION HYGIENE AND KEY TTLs
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_r09_pseudonymized_hmac_hygiene_and_ttls() -> None:
    """R09: Rate limit keys use HMAC pseudonymization, without plaintext emails or IPs, and have positive TTLs."""
    test_settings = get_settings().model_copy(
        update={
            "rate_limit_backend": "redis",
            "rate_limit_redis_url": REDIS_TEST_URL,
            "rate_limit_hmac_key": "super-secret-hmac-test-key-32chars",
        }
    )
    service = RateLimiterService(settings=test_settings)
    ip = "192.168.1.105"
    email = "bombero.jefe@estacioncentral.gov.ar"

    fake_request = MagicMock()
    fake_request.client.host = ip
    fake_request.headers = {}

    # Trigger failed login check
    await service.record_login_failure(fake_request, email)

    client = aioredis.from_url(REDIS_TEST_URL, encoding="utf-8", decode_responses=True)
    try:
        keys = await client.keys("rl:*")
        assert len(keys) >= 2

        # Verify plaintext email and IP are NOT in Redis keys
        for k in keys:
            assert ip not in k, f"Plaintext IP found in Redis key: {k}"
            assert email not in k, f"Plaintext email found in Redis key: {k}"

            ttl = await client.ttl(k)
            assert ttl > 0, f"Key {k} has missing or infinite TTL: {ttl}"

        # Verify HMAC match
        hmac_key = derive_rate_limit_key(test_settings)
        expected_ip_hash = pseudonymize(ip, hmac_key, prefix="ip")
        assert any(expected_ip_hash in k for k in keys)
    finally:
        await client.aclose()


# ---------------------------------------------------------------------------
# R10: CLOCK DRIFT EVALUATION
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_r10_clock_drift_evaluation() -> None:
    """R10: Verify monotonic order via :seq and sliding window cutoff under clock variance."""
    client = aioredis.from_url(REDIS_TEST_URL, encoding="utf-8", decode_responses=True)
    try:
        storage = RedisRateLimitStorage(client=client)
        key = "rl:test:r10:drift"
        window = 30
        limit = 5

        # Normal hit at t0
        allowed, count, _ = await storage.hit(key, window, limit)
        assert allowed is True
        assert count == 1

        # Second hit with simulated client clock slightly behind (-1s)
        # Should still be recorded with unique member because :seq is monotonic in Redis
        t_drifted = time.time() - 1.0
        res = await client.eval(
            """
            local key = KEYS[1]
            local now = tonumber(ARGV[1])
            local window = tonumber(ARGV[2])
            local max_hits = tonumber(ARGV[3])
            local cutoff = now - window
            redis.call('ZREMRANGEBYSCORE', key, '-inf', cutoff)
            local count = redis.call('ZCARD', key)
            if count >= max_hits then
                return {0, count, 1}
            else
                local seq = redis.call('INCR', key .. ':seq')
                local member = tostring(now) .. ':' .. tostring(seq)
                redis.call('ZADD', key, now, member)
                redis.call('EXPIRE', key, math.ceil(window) + 60)
                redis.call('EXPIRE', key .. ':seq', math.ceil(window) + 60)
                return {1, count + 1, 0}
            end
            """,
            1,
            key,
            str(t_drifted),
            str(window),
            str(limit),
        )
        assert bool(res[0]) is True
        assert int(res[1]) == 2

        # Verify 2 distinct members exist
        members = await client.zrange(key, 0, -1)
        assert len(members) == 2
    finally:
        await client.aclose()


# ---------------------------------------------------------------------------
# FASTAPI ENDPOINTS VALIDATION WITH REAL REDIS
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fastapi_login_rate_limit_with_real_redis() -> None:
    """FastAPI POST /auth/login with real Redis rate limiting, 429 response, and Retry-After."""
    redis_storage = RedisRateLimitStorage(
        client=aioredis.from_url(REDIS_TEST_URL, encoding="utf-8", decode_responses=True)
    )
    reset_rate_limit_storage(redis_storage)

    # Mock database session dependency override so NO DB is contacted
    mock_session = AsyncMock()
    mock_session.scalar.return_value = None  # user not found

    app.dependency_overrides[get_database_session] = lambda: mock_session

    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            # 5 failed attempts for test@fireops.com from 127.0.0.1
            for _ in range(5):
                resp = await client.post(
                    "/auth/login",
                    json={"email": "test@fireops.com", "password": "wrong_password"},
                )
                assert resp.status_code == 401

            # 6th attempt must be rejected with HTTP 429
            resp_blocked = await client.post(
                "/auth/login",
                json={"email": "test@fireops.com", "password": "wrong_password"},
            )
            assert resp_blocked.status_code == 429
            assert resp_blocked.json()["error"]["code"] == "ACCOUNT_LOCKED_FOR_IP"
            assert "retry-after" in resp_blocked.headers
            assert int(resp_blocked.headers["retry-after"]) >= 1
    finally:
        app.dependency_overrides.pop(get_database_session, None)
        await redis_storage.client.aclose()


@pytest.mark.asyncio
async def test_fastapi_registration_and_nat_isolation_with_real_redis() -> None:
    """FastAPI POST /auth/registration-requests and NAT isolation on real Redis."""
    redis_client = aioredis.from_url(REDIS_TEST_URL, encoding="utf-8", decode_responses=True)
    redis_storage = RedisRateLimitStorage(client=redis_client)
    reset_rate_limit_storage(redis_storage)

    mock_session = AsyncMock()
    app.dependency_overrides[get_database_session] = lambda: mock_session

    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            for i in range(5):
                resp = await client.post(
                    "/auth/registration-requests",
                    json={"email": f"aspirante_{i}@cuartelcentral.gov.ar"},
                )
                assert resp.status_code == 202

            # 6th from same IP rejected with HTTP 429
            resp_limit = await client.post(
                "/auth/registration-requests",
                json={"email": "aspirante_over@cuartelcentral.gov.ar"},
            )
            assert resp_limit.status_code == 429
            assert resp_limit.json()["error"]["code"] == "REGISTRATION_IP_RATE_LIMIT_EXCEEDED"
            assert "retry-after" in resp_limit.headers
    finally:
        app.dependency_overrides.pop(get_database_session, None)
        await redis_client.aclose()


@pytest.mark.asyncio
async def test_fastapi_inactive_account_preservation_with_real_redis() -> None:
    """FastAPI rejects inactive accounts (M-06) while updating failed login limits on real Redis."""
    redis_client = aioredis.from_url(REDIS_TEST_URL, encoding="utf-8", decode_responses=True)
    redis_storage = RedisRateLimitStorage(client=redis_client)
    reset_rate_limit_storage(redis_storage)

    # Mock inactive user from database with valid hash for "any_password"
    mock_user = AsyncMock()
    mock_user.id = 42
    mock_user.email = "inactivo@cuartelcentral.gov.ar"
    mock_user.activo = False
    mock_user.password_hash = hash_password("any_password")

    mock_session = AsyncMock()
    mock_session.scalar.return_value = mock_user

    app.dependency_overrides[get_database_session] = lambda: mock_session

    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.post(
                "/auth/login",
                json={"email": "inactivo@cuartelcentral.gov.ar", "password": "any_password"},
            )
            # Inactive account returns 401 with INVALID_CREDENTIALS to prevent account enumeration (M-06)
            assert resp.status_code == 401
            assert resp.json()["error"]["code"] == "INVALID_CREDENTIALS"

            # Check that failed login counter in Redis recorded this failure
            keys = await redis_client.keys("rl:fail:*")
            assert len(keys) > 0, "Failed login must be recorded in Redis even for inactive accounts"
    finally:
        app.dependency_overrides.pop(get_database_session, None)
        await redis_client.aclose()


@pytest.mark.asyncio
async def test_fastapi_fail_closed_on_redis_crash() -> None:
    """FastAPI returns HTTP 503 when Redis crashes or is unreachable (fail-closed)."""
    # Create storage pointing to dead port
    dead_client = aioredis.from_url(
        "redis://127.0.0.1:6398/0",
        encoding="utf-8",
        decode_responses=True,
        socket_connect_timeout=0.2,
    )
    dead_storage = RedisRateLimitStorage(client=dead_client)
    reset_rate_limit_storage(dead_storage)

    mock_session = AsyncMock()
    app.dependency_overrides[get_database_session] = lambda: mock_session

    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.post(
                "/auth/registration-requests",
                json={"email": "aspirante@bomberos.gov.ar"},
            )
            assert resp.status_code == 503
            assert resp.json()["error"]["code"] == "RATE_LIMIT_STORAGE_UNAVAILABLE"
            assert "temporalmente no disponible" in resp.json()["error"]["message"]
    finally:
        app.dependency_overrides.pop(get_database_session, None)
        await dead_client.aclose()
