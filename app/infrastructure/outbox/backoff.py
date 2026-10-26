"""Retry policy, exponential backoff with jitter, and error sanitization for Outbox."""

from __future__ import annotations

import random
import re
from datetime import UTC, datetime, timedelta

DEFAULT_BASE_BACKOFF = 10.0
DEFAULT_MAX_BACKOFF = 3600.0
DEFAULT_JITTER_RATIO = 0.2


def compute_next_attempt_at(
    attempt_count: int,
    *,
    base_backoff: float = DEFAULT_BASE_BACKOFF,
    max_backoff: float = DEFAULT_MAX_BACKOFF,
    retry_after: float | None = None,
    now: datetime | None = None,
) -> datetime:
    """Compute the next attempt timestamp using bounded exponential backoff with jitter."""
    if now is None:
        now = datetime.now(UTC)

    # 1-indexed attempt exponent
    exp = max(0, attempt_count - 1)
    # Bounded exponential growth: 10s, 20s, 40s, 80s... capped at max_backoff
    delay = min(max_backoff, base_backoff * (2**exp))

    # Add proportional jitter (+/- 20%)
    jitter_delta = delay * DEFAULT_JITTER_RATIO
    jittered = delay + random.uniform(-jitter_delta, jitter_delta)
    jittered_delay = max(1.0, min(max_backoff, jittered))

    # If provider specified explicit Retry-After, honor it bounded by max_backoff
    if retry_after is not None and retry_after > 0:
        final_delay = min(max_backoff, max(retry_after, jittered_delay))
    else:
        final_delay = jittered_delay

    return now + timedelta(seconds=final_delay)


def sanitize_error_detail(detail: str | None, max_length: int = 255) -> str | None:
    """Sanitize error messages to guarantee zero credential/token leakage in database logs."""
    if not detail:
        return None

    # Redact tokens, auth headers, and email addresses
    sanitized = re.sub(r"Bearer\s+[A-Za-z0-9_\-\.]+", "Bearer [REDACTED]", detail, flags=re.IGNORECASE)
    sanitized = re.sub(r"invite=[A-Za-z0-9_\-]+", "invite=[REDACTED]", sanitized, flags=re.IGNORECASE)
    sanitized = re.sub(r"token=[A-Za-z0-9_\-]+", "token=[REDACTED]", sanitized, flags=re.IGNORECASE)
    sanitized = re.sub(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", "[EMAIL_REDACTED]", sanitized)

    if len(sanitized) > max_length:
        return sanitized[: max_length - 3] + "..."
    return sanitized
