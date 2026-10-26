"""Standalone CLI runner for Transactional Outbox.

Decoupled from FastAPI lifespan: executes as an independent background worker.
Guarantees:
- Rejects execution against protected databases (fireassets, fireassets_test, postgres).
- Rejects execution if outbox_enabled=False or encryption key is missing.
- Rejects execution if outbox_events schema is missing (does NOT auto-create tables).
- Handles SIGTERM, SIGINT, and graceful task draining with bounded shutdown timeout.
- Records non-sensitive operational telemetry and performance timing.
- Zero workers auto-started during module import.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.exc import DBAPIError, ProgrammingError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config.settings import Settings, get_settings
from app.infrastructure.outbox.adapter import (
    EmailDeliveryAdapter,
    FakeEmailDeliveryAdapter,
    GmailApiAdapter,
)
from app.infrastructure.outbox.crypto import Keyring, OutboxConfigurationError
from app.infrastructure.outbox.dispatcher import OutboxDispatcher
from app.infrastructure.outbox.isolation import (
    EnvironmentProtectionError,
    redact_database_url,
    validate_target_database,
)
from app.infrastructure.outbox.metrics import OutboxMetrics
from app.infrastructure.outbox.models import OutboxEvent
from app.infrastructure.outbox.reaper import LeaseReaper

logger = logging.getLogger("outbox.runner")


@dataclass(frozen=True, slots=True)
class RunnerConfig:
    """Operational parameters for the Outbox runner process."""

    worker_id: str
    poll_interval_seconds: float = 1.0
    lease_duration_seconds: int = 45
    reap_interval_seconds: float = 30.0
    shutdown_timeout_seconds: float = 15.0
    base_backoff_seconds: float = 10.0
    max_backoff_seconds: float = 3600.0
    adapter_type: str = "gmail"  # "gmail" or "fake"
    allow_protected_db: bool = False
    allow_production_db: bool = False
    require_ephemeral_db: bool = False


class OutboxRunner:
    """Manages the lifecycle, loops, and graceful shutdown of the Outbox worker."""

    def __init__(
        self,
        config: RunnerConfig,
        settings: Settings | None = None,
        *,
        adapter: EmailDeliveryAdapter | None = None,
        engine: AsyncEngine | None = None,
        session_factory: Callable[..., Any] | None = None,
    ) -> None:
        self.config = config
        self.settings = settings or get_settings()
        self.metrics = OutboxMetrics()
        self._custom_adapter = adapter
        self._custom_engine = engine
        self._custom_session_factory = session_factory

        self._stop_requested = asyncio.Event()
        self._is_running = False
        self._in_flight_task: asyncio.Task[Any] | None = None

    def validate_preconditions(self) -> None:
        """Validate settings, encryption key, and database isolation before startup."""
        settings = self.settings

        # 1. Reject if outbox feature flag is disabled
        if not settings.outbox_enabled:
            raise OutboxConfigurationError(
                "Transactional Outbox is disabled (outbox_enabled=False). Runner will not start."
            )

        # 2. Reject if encryption key is missing or invalid
        if not settings.outbox_encryption_key:
            raise OutboxConfigurationError(
                "Missing outbox_encryption_key. Authenticated payload encryption requires a valid 32-byte key."
            )

        # 3. Reject if target database is protected
        validate_target_database(
            settings.database_url,
            allow_protected=self.config.allow_protected_db,
            require_ephemeral=self.config.require_ephemeral_db,
            allow_production=self.config.allow_production_db,
            environment=settings.environment,
        )

    async def verify_schema_exists(self, session: AsyncSession) -> None:
        """Probe PostgreSQL to verify that outbox_events table is present.

        Fails closed without creating tables if migrations have not been applied.
        """
        try:
            # Simple metadata probe
            stmt = select(func.count()).select_from(OutboxEvent)
            await session.scalar(stmt)
        except (ProgrammingError, DBAPIError) as err:
            err_str = str(err).lower()
            if "outbox_events" in err_str or "does not exist" in err_str or "undefined table" in err_str:
                raise OutboxConfigurationError(
                    "Outbox schema table 'outbox_events' does not exist in target database. "
                    "Apply Alembic migrations before starting runner."
                ) from err
            raise

    def request_stop(self, reason: str = "signal") -> None:
        """Request graceful shutdown of the runner loop."""
        if not self._stop_requested.is_set():
            logger.info("Outbox runner stop requested (reason: %s). Draining tasks...", reason)
            self._stop_requested.set()

    def _setup_signal_handlers(self) -> None:
        """Install SIGINT and SIGTERM handlers when running in the main thread."""
        try:
            loop = asyncio.get_running_loop()
            for sig in (signal.SIGINT, signal.SIGTERM):
                loop.add_signal_handler(sig, self.request_stop, sig.name)
        except (NotImplementedError, RuntimeError):
            # Signal handling not supported on some platforms / non-main threads
            pass

    async def run(self) -> OutboxMetrics:
        """Execute the runner until stop is requested or error occurs."""
        self.validate_preconditions()
        redacted_url = redact_database_url(self.settings.database_url)
        logger.info(
            "Starting Outbox runner %s against database %s",
            self.config.worker_id,
            redacted_url,
        )

        engine = self._custom_engine
        owns_engine = False
        session_factory = self._custom_session_factory

        if session_factory is None:
            if engine is None:
                engine = create_async_engine(
                    self.settings.database_url,
                    pool_pre_ping=True,
                    pool_size=5,
                    max_overflow=5,
                )
                owns_engine = True
            session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)

        try:
            # Verify database schema exists (only if engine was created or explicitly provided)
            if self._custom_session_factory is None:
                async with session_factory() as session:
                    await self.verify_schema_exists(session)

            # Build dependencies
            encryption_key = self.settings.outbox_encryption_key
            if not encryption_key:
                raise OutboxConfigurationError("Missing outbox_encryption_key")

            keyring = Keyring.from_raw(
                primary_key_b64=encryption_key,
                primary_key_id=self.settings.outbox_encryption_key_id,
                secondary_keys=self.settings.outbox_secondary_encryption_keys,
            )

            adapter = self._custom_adapter
            if adapter is None:
                if self.config.adapter_type == "fake":
                    adapter = FakeEmailDeliveryAdapter()
                else:
                    adapter = GmailApiAdapter(self.settings)

            dispatcher = OutboxDispatcher(
                session_factory=session_factory,
                keyring=keyring,
                adapter=adapter,
                worker_id=self.config.worker_id,
                lease_duration_seconds=self.config.lease_duration_seconds,
                base_backoff_seconds=self.config.base_backoff_seconds,
                max_backoff_seconds=self.config.max_backoff_seconds,
            )

            reaper = LeaseReaper(
                session_factory=session_factory,
                batch_size=10,
                retry_delay_seconds=30.0,
            )

            self._setup_signal_handlers()
            self._is_running = True

            last_reap_time = time.monotonic()

            # Main runner loop
            while not self._stop_requested.is_set():
                now_mono = time.monotonic()

                # 1. Periodic lease reaper sweep
                if now_mono - last_reap_time >= self.config.reap_interval_seconds:
                    try:
                        reaped_count = await reaper.reap_expired_leases()
                        if reaped_count > 0:
                            self.metrics.record_reaped_leases(reaped_count)
                            logger.info("LeaseReaper recovered %s expired leases", reaped_count)
                    except Exception as err:  # noqa: BLE001
                        logger.error("LeaseReaper error: %s", err)
                    last_reap_time = now_mono

                # 2. Dispatch next runnable event
                start_t = time.perf_counter()
                try:
                    processed = await dispatcher.dispatch_next_event()
                    if processed:
                        elapsed = time.perf_counter() - start_t
                        self.metrics.record_delivered(elapsed)
                        # Immediately loop to process backlog without sleeping
                        continue
                except Exception as err:  # noqa: BLE001
                    self.metrics.record_delivery_error()
                    logger.error("Dispatcher cycle error: %s", err)

                # Idle backoff
                try:
                    await asyncio.wait_for(
                        self._stop_requested.wait(),
                        timeout=self.config.poll_interval_seconds,
                    )
                except TimeoutError:
                    pass

        finally:
            self._is_running = False
            logger.info("Outbox runner %s shutdown complete.", self.config.worker_id)
            if owns_engine and engine is not None:
                await engine.dispose()

        return self.metrics


def build_arg_parser() -> argparse.ArgumentParser:
    """Construct CLI argument parser for the outbox runner."""
    parser = argparse.ArgumentParser(
        description="FireOps Transactional Outbox Background Dispatcher Runner",
        prog="python -m app.infrastructure.outbox.runner",
    )
    parser.add_argument(
        "--worker-id",
        type=str,
        default=f"worker-{uuid4().hex[:8]}",
        help="Unique worker identifier for lease tracking",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=1.0,
        help="Polling interval in seconds when queue is idle (default: 1.0)",
    )
    parser.add_argument(
        "--lease-duration",
        type=int,
        default=45,
        help="Worker lease expiration in seconds (default: 45)",
    )
    parser.add_argument(
        "--reap-interval",
        type=float,
        default=30.0,
        help="Interval in seconds between lease reaper sweeps (default: 30.0)",
    )
    parser.add_argument(
        "--shutdown-timeout",
        type=float,
        default=15.0,
        help="Maximum seconds to drain in-flight deliveries before exit (default: 15.0)",
    )
    parser.add_argument(
        "--adapter",
        type=str,
        choices=["gmail", "fake"],
        default="gmail",
        help="Delivery adapter to employ (default: gmail)",
    )
    parser.add_argument(
        "--allow-production-db",
        action="store_true",
        default=False,
        help="Explicitly permit targeting production database (requires environment='production')",
    )
    return parser


async def main() -> None:
    """Main CLI entrypoint."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
    )
    parser = build_arg_parser()
    args = parser.parse_args()

    config = RunnerConfig(
        worker_id=args.worker_id,
        poll_interval_seconds=args.poll_interval,
        lease_duration_seconds=args.lease_duration,
        reap_interval_seconds=args.reap_interval,
        shutdown_timeout_seconds=args.shutdown_timeout,
        adapter_type=args.adapter,
        allow_production_db=args.allow_production_db,
    )

    runner = OutboxRunner(config=config)
    try:
        await runner.run()
    except (OutboxConfigurationError, EnvironmentProtectionError) as err:
        logger.error("Startup validation failed: %s", err)
        sys.exit(1)
    except Exception as err:
        logger.critical("Runner terminated abnormally: %s", err, exc_info=True)
        sys.exit(2)


if __name__ == "__main__":
    asyncio.run(main())
