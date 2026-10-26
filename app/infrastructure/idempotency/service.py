"""Idempotency service providing deterministic hashing and persistence helpers."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.idempotency.models import IdempotencyRecord


def compute_request_hash(payload: dict[str, Any]) -> str:
    """Compute a deterministic SHA-256 hash of canonical request parameters."""
    canonical_json = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


async def get_idempotency_record(
    session: AsyncSession,
    *,
    scope: str,
    aggregate_id: str,
    idempotency_key: str,
    for_update: bool = False,
) -> IdempotencyRecord | None:
    """Retrieve an idempotency record by its unique tuple (scope, aggregate_id, key)."""
    stmt = select(IdempotencyRecord).where(
        IdempotencyRecord.scope == scope,
        IdempotencyRecord.aggregate_id == aggregate_id,
        IdempotencyRecord.idempotency_key == idempotency_key,
    )
    if for_update:
        stmt = stmt.with_for_update()
    return await session.scalar(stmt)


async def record_idempotent_operation(
    session: AsyncSession,
    *,
    scope: str,
    aggregate_id: str,
    idempotency_key: str,
    request_hash: str,
    response_status: int,
    response_data: dict[str, Any],
    expires_at: datetime | None = None,
) -> IdempotencyRecord:
    """Persist an executed operation result into the idempotency registry."""
    record = IdempotencyRecord(
        scope=scope,
        aggregate_id=aggregate_id,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        response_status=response_status,
        response_data=response_data,
        expires_at=expires_at,
    )
    session.add(record)
    return record
