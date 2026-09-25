"""Enqueue helpers shared by the API and the worker.

Job ids are derived from the work item (``process:<doc>:<hash>``) so enqueuing the same work
twice — a retried webhook, an overlapping cron, a user double-click — is a no-op in arq.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from arq import ArqRedis, create_pool
from arq.connections import RedisSettings

from app.settings import Settings

QUEUE = "app:queue"


def redis_settings(settings: Settings) -> RedisSettings:
    return RedisSettings.from_dsn(settings.redis_url)


async def create_queue(settings: Settings) -> ArqRedis:
    return await create_pool(redis_settings(settings), default_queue_name=QUEUE)


async def enqueue(
    pool: ArqRedis,
    job: str,
    *args: Any,
    job_id: str | None = None,
    defer_by: timedelta | None = None,
    **kwargs: Any,
) -> str | None:
    result = await pool.enqueue_job(
        job, *args, _job_id=job_id, _defer_by=defer_by, _queue_name=QUEUE, **kwargs
    )
    return result.job_id if result is not None else None
