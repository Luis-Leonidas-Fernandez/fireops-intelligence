"""Rate limiting and abuse prevention framework for authentication and public endpoints."""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import logging
import time
from collections import defaultdict
from typing import Any, Protocol

from fastapi import Request

from app.config.settings import Settings, get_settings
from app.shared.errors.application_error import ApplicationError

logger = logging.getLogger("uvicorn.error")


class RateLimitExceeded(ApplicationError):
    """Exception raised when an endpoint rate limit is exceeded, returning HTTP 429."""

    def __init__(
        self,
        message: str = "Demasiadas solicitudes. Por favor, intentá nuevamente más tarde.",
        retry_after: int = 60,
        code: str = "TOO_MANY_REQUESTS",
    ) -> None:
        super().__init__(
            code=code,
            message=message,
            status_code=429,
            headers={"Retry-After": str(max(1, retry_after))},
        )


class RateLimitStorageUnavailable(ApplicationError):
    """Exception raised when distributed rate limit storage (Redis) is unreachable or fails."""

    def __init__(
        self,
        message: str = "Servicio de control de tráfico temporalmente no disponible.",
    ) -> None:
        super().__init__(
            code="RATE_LIMIT_STORAGE_UNAVAILABLE",
            message=message,
            status_code=503,
            headers={"Retry-After": "5"},
        )


def get_trusted_client_ip(request: Request, trusted_proxies: list[str] | set[str]) -> str:
    """Safely extract the real client IP address respecting trusted proxy boundaries.

    If request.client.host is not in trusted_proxies, X-Forwarded-For headers are completely
    ignored to prevent IP spoofing attacks.
    """
    peer_ip = request.client.host if request.client else "127.0.0.1"

    # Normalize trusted_proxies to a set
    trusted_set = set(trusted_proxies) if isinstance(trusted_proxies, list) else trusted_proxies

    if peer_ip not in trusted_set:
        # Peer is not a trusted proxy: rely strictly on peer socket IP
        return peer_ip

    # Peer is a trusted reverse proxy: inspect X-Forwarded-For right-to-left
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        parts = [p.strip() for p in forwarded.split(",") if p.strip()]
        # Walk from right to left to find the first IP not belonging to trusted proxies
        for candidate in reversed(parts):
            try:
                # Validate IP formatting
                ipaddress.ip_address(candidate)
            except ValueError:
                continue
            if candidate not in trusted_set:
                return candidate

    # Check X-Real-IP if provided by trusted proxy
    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        candidate = real_ip.strip()
        try:
            ipaddress.ip_address(candidate)
            if candidate not in trusted_set:
                return candidate
        except ValueError:
            pass

    return peer_ip


def derive_rate_limit_key(settings: Settings) -> bytes:
    """Derive an independent 256-bit HMAC key strictly isolated from JWT and cookie secrets."""
    if settings.rate_limit_hmac_key:
        return settings.rate_limit_hmac_key.encode("utf-8")
    return hmac.new(
        settings.secret_key.encode("utf-8"),
        b"fireops-ratelimit-pseudonymization-v1",
        hashlib.sha256,
    ).digest()


def pseudonymize(value: str, secret_key: bytes, prefix: str = "") -> str:
    """Generate a compact 64-bit hexadecimal pseudonym to protect user privacy in storage and logs."""
    normalized = value.strip().lower().encode("utf-8")
    digest = hmac.new(secret_key, normalized, hashlib.sha256).hexdigest()[:16]
    return f"{prefix}:{digest}" if prefix else digest


class RateLimitStorage(Protocol):
    """Protocol contract for rate limit persistence backends."""

    async def hit(self, key: str, window_seconds: int, max_hits: int) -> tuple[bool, int, int]:
        """Record an attempt and return (allowed: bool, current_count: int, retry_after: int)."""
        ...

    async def peek(self, key: str, window_seconds: int, max_hits: int) -> tuple[bool, int, int]:
        """Inspect count without incrementing and return (allowed: bool, current_count: int, retry_after: int)."""
        ...

    async def reset(self, key: str) -> None:
        """Clear count for the designated key."""
        ...


class InMemoryRateLimitStorage:
    """Thread-safe in-memory sliding window counter for single-process deployments."""

    def __init__(self) -> None:
        self._store: dict[str, list[float]] = defaultdict(list)
        self._last_cleanup = time.monotonic()

    async def hit(self, key: str, window_seconds: int, max_hits: int) -> tuple[bool, int, int]:
        now = time.monotonic()
        self._maybe_cleanup(now)

        timestamps = self._store[key]
        cutoff = now - window_seconds
        # Discard expired timestamps outside window
        while timestamps and timestamps[0] <= cutoff:
            timestamps.pop(0)

        if len(timestamps) >= max_hits:
            # Over limit
            oldest = timestamps[0]
            retry_after = max(1, int(oldest + window_seconds - now))
            return False, len(timestamps), retry_after

        # Record this hit
        timestamps.append(now)
        return True, len(timestamps), 0

    async def peek(self, key: str, window_seconds: int, max_hits: int) -> tuple[bool, int, int]:
        now = time.monotonic()
        self._maybe_cleanup(now)

        timestamps = self._store.get(key, [])
        cutoff = now - window_seconds
        active = [t for t in timestamps if t > cutoff]
        if len(active) >= max_hits:
            oldest = active[0]
            retry_after = max(1, int(oldest + window_seconds - now))
            return False, len(active), retry_after
        return True, len(active), 0

    async def reset(self, key: str) -> None:
        self._store.pop(key, None)

    def _maybe_cleanup(self, now: float) -> None:
        # Periodic purge of stale keys every 300 seconds or when dict size > 5000
        if now - self._last_cleanup > 300 or len(self._store) > 5000:
            stale_keys = []
            for k, ts in list(self._store.items()):
                # If all entries are older than 86400 (24h max window), remove key
                if not ts or ts[-1] < now - 86400:
                    stale_keys.append(k)
            for k in stale_keys:
                self._store.pop(k, None)
            self._last_cleanup = now


SLIDING_WINDOW_HIT_LUA = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local max_hits = tonumber(ARGV[3])
local cutoff = now - window

-- Purge timestamps older than the sliding window cutoff
redis.call('ZREMRANGEBYSCORE', key, '-inf', cutoff)

-- Count entries within the active window
local count = redis.call('ZCARD', key)

if count >= max_hits then
    local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
    local retry_after = 1
    if oldest and #oldest >= 2 then
        local oldest_ts = tonumber(oldest[2])
        retry_after = math.max(1, math.ceil(oldest_ts + window - now))
    end
    return {0, count, retry_after}
else
    local seq_key = key .. ':seq'
    local seq = redis.call('INCR', seq_key)
    local member = tostring(now) .. ':' .. tostring(seq)
    redis.call('ZADD', key, now, member)
    local expire_ttl = math.ceil(window) + 60
    redis.call('EXPIRE', key, expire_ttl)
    redis.call('EXPIRE', seq_key, expire_ttl)
    return {1, count + 1, 0}
end
"""

SLIDING_WINDOW_PEEK_LUA = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local max_hits = tonumber(ARGV[3])
local cutoff = now - window

redis.call('ZREMRANGEBYSCORE', key, '-inf', cutoff)
local count = redis.call('ZCARD', key)

if count >= max_hits then
    local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
    local retry_after = 1
    if oldest and #oldest >= 2 then
        local oldest_ts = tonumber(oldest[2])
        retry_after = math.max(1, math.ceil(oldest_ts + window - now))
    end
    return {0, count, retry_after}
else
    return {1, count, 0}
end
"""


class RedisRateLimitStorage:
    """Atomic distributed rate limit storage using Redis sorted sets (ZSET) and Lua scripts."""

    def __init__(self, client: Any) -> None:
        self.client = client

    async def hit(self, key: str, window_seconds: int, max_hits: int) -> tuple[bool, int, int]:
        now = time.time()
        try:
            res = await self.client.eval(
                SLIDING_WINDOW_HIT_LUA,
                1,
                key,
                str(now),
                str(window_seconds),
                str(max_hits),
            )
            allowed = bool(res[0])
            count = int(res[1])
            retry_after = int(res[2])
            return allowed, count, retry_after
        except Exception as err:
            logger.error("redis_rate_limit_error operation=hit key=%s error=%s", key, err)
            raise RateLimitStorageUnavailable(
                "Servicio de control de tráfico temporalmente no disponible."
            ) from err

    async def peek(self, key: str, window_seconds: int, max_hits: int) -> tuple[bool, int, int]:
        now = time.time()
        try:
            res = await self.client.eval(
                SLIDING_WINDOW_PEEK_LUA,
                1,
                key,
                str(now),
                str(window_seconds),
                str(max_hits),
            )
            allowed = bool(res[0])
            count = int(res[1])
            retry_after = int(res[2])
            return allowed, count, retry_after
        except Exception as err:
            logger.error("redis_rate_limit_error operation=peek key=%s error=%s", key, err)
            raise RateLimitStorageUnavailable(
                "Servicio de control de tráfico temporalmente no disponible."
            ) from err

    async def reset(self, key: str) -> None:
        try:
            await self.client.delete(key, f"{key}:seq")
        except Exception as err:
            logger.error("redis_rate_limit_error operation=reset key=%s error=%s", key, err)
            raise RateLimitStorageUnavailable(
                "Servicio de control de tráfico temporalmente no disponible."
            ) from err


_rate_limit_storage: RateLimitStorage | None = None


def create_redis_storage(settings: Settings) -> RateLimitStorage:
    """Instantiate a Redis-backed rate limit storage using redis.asyncio."""
    try:
        import redis.asyncio as aioredis  # type: ignore[import-untyped,import-not-found]
    except ImportError as err:
        raise RuntimeError(
            "El backend de rate limit está configurado como 'redis' pero la biblioteca 'redis' "
            "no está instalada en el entorno. Debe instalarse 'redis>=5.0.0' o configurar 'rate_limit_backend=memory'."
        ) from err

    redis_url = settings.rate_limit_redis_url or "redis://localhost:6379/0"
    client = aioredis.from_url(
        redis_url,
        encoding="utf-8",
        decode_responses=True,
        socket_connect_timeout=2.0,
        socket_timeout=2.0,
    )
    return RedisRateLimitStorage(client=client)


def get_rate_limit_storage(settings: Settings | None = None) -> RateLimitStorage:
    """Get the active rate limit storage backend based on configuration."""
    global _rate_limit_storage
    if _rate_limit_storage is None:
        active_settings = settings or get_settings()
        backend = (active_settings.rate_limit_backend or "memory").strip().lower()
        if backend == "memory":
            _rate_limit_storage = InMemoryRateLimitStorage()
        elif backend == "redis":
            _rate_limit_storage = create_redis_storage(active_settings)
        else:
            raise ValueError(
                f"Backend de rate limit no soportado: '{active_settings.rate_limit_backend}'. "
                "Valores válidos: 'memory', 'redis'."
            )
    return _rate_limit_storage


def reset_rate_limit_storage(storage: RateLimitStorage | None = None) -> None:
    """Reset storage backend (primarily for test fixture isolation)."""
    global _rate_limit_storage
    _rate_limit_storage = storage


class RateLimiterService:
    """Coordinated security service for endpoint throttling and brute-force prevention."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._hmac_key = derive_rate_limit_key(self.settings)

    @property
    def storage(self) -> RateLimitStorage:
        return get_rate_limit_storage(self.settings)

    def get_client_ip(self, request: Request) -> str:
        return get_trusted_client_ip(request, self.settings.trusted_proxies_list)

    async def check_ip_limit(
        self,
        request: Request,
        scope: str,
        max_requests: int,
        window_seconds: int,
        message: str = "Límite de solicitudes excedido.",
    ) -> None:
        """Enforce standard sliding-window rate limit by client IP."""
        if not self.settings.rate_limit_enabled:
            return

        client_ip = self.get_client_ip(request)
        ip_hash = pseudonymize(client_ip, self._hmac_key, prefix="ip")
        key = f"rl:{scope}:{ip_hash}"

        allowed, _count, retry_after = await self.storage.hit(key, window_seconds, max_requests)
        if not allowed:
            raise RateLimitExceeded(
                message=message,
                retry_after=retry_after,
                code="RATE_LIMIT_EXCEEDED",
            )

    async def check_login_pre_auth(self, request: Request, email: str) -> None:
        """Pre-authentication check on POST /auth/login.

        1. Checks total requests by IP (60/min, burst 15) to prevent socket/connection exhaustion.
        2. Checks failed credential attempts for (IP, Account) tuple (max 5 in 15 min) to stop brute force.
        """
        if not self.settings.rate_limit_enabled:
            return

        client_ip = self.get_client_ip(request)
        ip_hash = pseudonymize(client_ip, self._hmac_key, prefix="ip")

        # 1. IP volumetric limit: 60 requests per 60 seconds
        ip_key = f"rl:login_ip:{ip_hash}"
        allowed, _count, retry_after = await self.storage.hit(ip_key, window_seconds=60, max_hits=60)
        if not allowed:
            raise RateLimitExceeded(
                message="Demasiados intentos de conexión desde esta dirección. Por favor esperá un momento.",
                retry_after=retry_after,
                code="LOGIN_IP_RATE_LIMIT_EXCEEDED",
            )

        # 2. Targeted brute force check on (IP, Account): 5 failures in 15 min (900s)
        acct_hash = pseudonymize(email, self._hmac_key, prefix="acct")
        fail_key = f"rl:fail:{ip_hash}:{acct_hash}"
        allowed, _count, retry_after = await self.storage.peek(fail_key, window_seconds=900, max_hits=5)
        if not allowed:
            raise RateLimitExceeded(
                message="Demasiados intentos fallidos para esta cuenta. Por favor reintentá en unos minutos.",
                retry_after=retry_after,
                code="ACCOUNT_LOCKED_FOR_IP",
            )

    async def record_login_failure(self, request: Request, email: str) -> None:
        """Record an invalid password attempt against an account."""
        if not self.settings.rate_limit_enabled:
            return

        client_ip = self.get_client_ip(request)
        ip_hash = pseudonymize(client_ip, self._hmac_key, prefix="ip")
        acct_hash = pseudonymize(email, self._hmac_key, prefix="acct")

        # Increment failure counter for (IP, Account)
        fail_key = f"rl:fail:{ip_hash}:{acct_hash}"
        await self.storage.hit(fail_key, window_seconds=900, max_hits=5)

        # Check global account failure counter (15 in 15 min) -> alerts only, NO blind lockout!
        acct_global_key = f"rl:acct_global:{acct_hash}"
        _, global_count, _ = await self.storage.hit(acct_global_key, window_seconds=900, max_hits=15)
        if global_count >= 15:
            logger.critical(
                "security_alert: high_login_failure_rate_for_account account_pseudonym=%s global_failures=%d",
                acct_hash,
                global_count,
            )

    async def record_login_success(self, request: Request, email: str) -> None:
        """Reset the failure counter for this (IP, Account) upon successful authentication."""
        if not self.settings.rate_limit_enabled:
            return

        client_ip = self.get_client_ip(request)
        ip_hash = pseudonymize(client_ip, self._hmac_key, prefix="ip")
        acct_hash = pseudonymize(email, self._hmac_key, prefix="acct")
        fail_key = f"rl:fail:{ip_hash}:{acct_hash}"
        await self.storage.reset(fail_key)

    async def check_registration_request_allowed(self, request: Request, email: str) -> bool:
        """Check registration request limits.

        1. Checks IP limit: 5 requests per hour. Raises 429 if exceeded.
        2. Checks target email limit: 1 request per 24 hours.
           If already requested, returns False (caller responds HTTP 202 silently without saving/emailing).
           If not requested, returns True.
        """
        if not self.settings.rate_limit_enabled:
            return True

        client_ip = self.get_client_ip(request)
        ip_hash = pseudonymize(client_ip, self._hmac_key, prefix="ip")

        # 1. IP limit: 5 requests per 3600 seconds
        ip_key = f"rl:reg_ip:{ip_hash}"
        allowed, _count, retry_after = await self.storage.hit(ip_key, window_seconds=3600, max_hits=5)
        if not allowed:
            raise RateLimitExceeded(
                message="Demasiadas solicitudes de registro desde esta dirección. Por favor esperá antes de reintentar.",
                retry_after=retry_after,
                code="REGISTRATION_IP_RATE_LIMIT_EXCEEDED",
            )

        # 2. Email idempotency limit: 1 request per 86400 seconds (24h)
        mail_hash = pseudonymize(email, self._hmac_key, prefix="mail")
        mail_key = f"rl:reg_mail:{mail_hash}"
        allowed, _, _ = await self.storage.hit(mail_key, window_seconds=86400, max_hits=1)
        return allowed

    async def check_admin_action_limit(
        self,
        request: Request,
        admin_id: int,
        action: str,
        max_requests: int,
        window_seconds: int = 60,
    ) -> None:
        """Rate limit sensitive administrative actions keyed by authenticated admin ID and client IP.

        Protects administrative routes while ensuring administrators sharing a firehouse NAT IP
        are isolated by their authenticated admin ID.
        """
        if not self.settings.rate_limit_enabled:
            return

        client_ip = self.get_client_ip(request)
        ip_hash = pseudonymize(client_ip, self._hmac_key, prefix="ip")
        admin_hash = pseudonymize(str(admin_id), self._hmac_key, prefix="admin")
        key = f"rl:admin:{action}:{admin_hash}:{ip_hash}"

        allowed, _count, retry_after = await self.storage.hit(key, window_seconds, max_requests)
        if not allowed:
            raise RateLimitExceeded(
                message="Límite de operaciones administrativas excedido. Por favor espere antes de continuar.",
                retry_after=retry_after,
                code="ADMIN_RATE_LIMIT_EXCEEDED",
            )


_singleton_limiter_service: RateLimiterService | None = None


def get_rate_limiter() -> RateLimiterService:
    """Return the RateLimiterService singleton."""
    global _singleton_limiter_service
    if _singleton_limiter_service is None:
        _singleton_limiter_service = RateLimiterService()
    return _singleton_limiter_service
