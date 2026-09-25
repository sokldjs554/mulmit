"""Daily LLM spend guard.

A backfill over three years of minutes can cost more in one night than the product earns in a
month. The guard keeps a per-KST-day counter in Redis (shared by every worker): calls check the
*projected* spend before running and record the *actual* spend after. When the cap is reached,
extraction degrades to the heuristic extractor (signals marked for review) instead of failing.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Protocol

from redis.asyncio import Redis

from mulmit.clock import KST
from mulmit.llm.types import LLMBudgetExceededError


class SpendGuard(Protocol):
    async def check(self, projected_usd: Decimal) -> None: ...
    async def record(self, actual_usd: Decimal) -> None: ...
    async def spent_today(self) -> Decimal: ...


def _day_key() -> str:
    return f"mulmit:llm:spend:{datetime.now(KST):%Y%m%d}"


class RedisSpendGuard:
    def __init__(self, redis: Redis, daily_cap_usd: float) -> None:
        self._redis = redis
        self._cap = Decimal(str(daily_cap_usd))

    async def spent_today(self) -> Decimal:
        raw = await self._redis.get(_day_key())
        return Decimal(raw.decode() if isinstance(raw, bytes) else raw) if raw else Decimal(0)

    async def check(self, projected_usd: Decimal) -> None:
        spent = await self.spent_today()
        if spent + projected_usd > self._cap:
            raise LLMBudgetExceededError(
                f"daily LLM budget ${self._cap} reached (spent ${spent:.4f})"
            )

    async def record(self, actual_usd: Decimal) -> None:
        key = _day_key()
        await self._redis.incrbyfloat(key, float(actual_usd))
        await self._redis.expire(key, 60 * 60 * 48)


class MemorySpendGuard:
    def __init__(self, daily_cap_usd: float = 1e9) -> None:
        self._cap = Decimal(str(daily_cap_usd))
        self._spent = Decimal(0)

    async def spent_today(self) -> Decimal:
        return self._spent

    async def check(self, projected_usd: Decimal) -> None:
        if self._spent + projected_usd > self._cap:
            raise LLMBudgetExceededError(f"daily LLM budget ${self._cap} reached")

    async def record(self, actual_usd: Decimal) -> None:
        self._spent += actual_usd
