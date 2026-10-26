"""Hardware admission controller for compute-intensive Argon2id password verification."""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import Any

from anyio import CapacityLimiter, WouldBlock, fail_after, to_thread

from app.shared.errors.application_error import ApplicationError


class Argon2AdmissionSaturated(ApplicationError):
    """Exception raised when Argon2id concurrency or waiting queue capacity is exceeded."""

    def __init__(self, message: str = "Servicio temporalmente saturado. Reintentá en unos segundos.") -> None:
        super().__init__(
            code="ARGON2_CAPACITY_EXCEEDED",
            message=message,
            status_code=503,
            headers={"Retry-After": "2"},
        )


class Argon2AdmissionGuard:
    """Thread-safe and async-safe admission guard for Argon2id hashing operations.

    Maintains strictly bounded hardware admission across three coordinated resources:
    1. admission_limiter: Total admitted requests (running + queued). Rejects excess synchronously.
    2. execution_slot: Concurrency limiter for slots awaiting execution, bounded by queue_timeout.
    3. dedicated_thread_limiter: Dedicated CapacityLimiter passed to anyio.to_thread.run_sync,
       completely isolated from the default 40-token threadpool.
    """

    def __init__(
        self,
        max_running: int = 2,
        max_waiting: int = 8,
        queue_timeout: float = 0.50,
    ) -> None:
        # Strictly reject booleans since isinstance(True, int) is True in Python
        if isinstance(max_running, bool) or not isinstance(max_running, int) or max_running < 1:
            raise ValueError("max_running debe ser un entero >= 1")
        if isinstance(max_waiting, bool) or not isinstance(max_waiting, int) or max_waiting < 0:
            raise ValueError("max_waiting debe ser un entero >= 0")
        if not (
            isinstance(queue_timeout, (int, float))
            and not isinstance(queue_timeout, bool)
            and math.isfinite(queue_timeout)
            and queue_timeout > 0
        ):
            raise ValueError("queue_timeout debe ser un número positivo finito")

        self.max_running = max_running
        self.max_waiting = max_waiting
        self.queue_timeout = float(queue_timeout)

        # Resource 1: Total admitted capacity (running + queued)
        self.admission_limiter = CapacityLimiter(max_running + max_waiting)
        # Resource 2: Execution slots gated by queue_timeout
        self.execution_slot = CapacityLimiter(max_running)
        # Resource 3: Dedicated execution limiter passed to anyio.to_thread.run_sync
        self.dedicated_thread_limiter = CapacityLimiter(max_running)

    async def run_verified(
        self,
        func: Callable[..., Any],
        *args: Any,
    ) -> Any:
        """Admit and execute the verification callable with strict bounds and timeout isolation."""
        # Phase 1: Atomic non-blocking check on total admitted capacity
        try:
            self.admission_limiter.acquire_nowait()
        except WouldBlock as err:
            raise Argon2AdmissionSaturated("Capacidad total de autenticación saturada.") from err

        try:
            # Phase 2: Wait for execution slot within queue_timeout
            try:
                with fail_after(self.queue_timeout) as queue_scope:
                    async with self.execution_slot:
                        # Once acquired, disarm the queue timeout so heavy CPU hashing is never aborted prematurely
                        queue_scope.deadline = float("inf")

                        # Phase 3: Execute in threadpool shielded against external cancellation during C computation
                        return await to_thread.run_sync(
                            func,
                            *args,
                            abandon_on_cancel=False,
                            limiter=self.dedicated_thread_limiter,
                        )
            except TimeoutError as err:
                raise Argon2AdmissionSaturated(
                    "Tiempo de espera en cola de autenticación excedido."
                ) from err
        finally:
            # Phase 4: Guarantee exact release of the admission token
            self.admission_limiter.release()


_singleton_argon2_guard: Argon2AdmissionGuard | None = None


def get_argon2_guard() -> Argon2AdmissionGuard:
    """Return the process-wide Argon2AdmissionGuard singleton."""
    global _singleton_argon2_guard
    if _singleton_argon2_guard is None:
        from app.config.settings import get_settings

        settings = get_settings()
        _singleton_argon2_guard = Argon2AdmissionGuard(
            max_running=settings.argon2_max_running,
            max_waiting=settings.argon2_max_waiting,
            queue_timeout=settings.argon2_queue_timeout,
        )
    return _singleton_argon2_guard


def reset_argon2_guard(guard: Argon2AdmissionGuard | None = None) -> None:
    """Reset the singleton (useful for test isolation)."""
    global _singleton_argon2_guard
    _singleton_argon2_guard = guard
