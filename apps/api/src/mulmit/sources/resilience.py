"""Rate limiting, daily quotas and circuit breaking for public-data APIs.

Public APIs in Korea are generous with data and stingy with calls: CLIK allows 1,000 calls/day
per key, data.go.kr development keys 1,000/day per operation, and both answer quota exhaustion
with HTTP 200 and an error body. The worker fleet shares these budgets, so state lives in Redis:

* **Token bucket** (per source) smooths bursts so one backfill cannot starve the hourly sync.
* **Daily quota** (per source, KST day) stops calling once the provider's cap is reached, and
  lets the job reschedule itself for after midnight KST instead of burning retries.
* **Circuit breaker** (per source) stops hammering a provider that is down; after a cool-down a
  single probe request decides whether to close it again.

In-memory implementations with the same interface keep unit tests hermetic.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol

from redis.asyncio import Redis

from mulmit.clock import KST


class QuotaExhaustedError(Exception):
    def __init__(self, source: str, resets_at: datetime) -> None:
        super().__init__(f"daily quota exhausted for {source}; resets at {resets_at.isoformat()}")
        self.source = source
        self.resets_at = resets_at


class CircuitOpenError(Exception):
    def __init__(self, source: str, retry_after: float) -> None:
        super().__init__(f"circuit open for {source}; retry after {retry_after:.0f}s")
        self.source = source
        self.retry_after = retry_after


def next_kst_midnight(now: datetime | None = None) -> datetime:
    now_kst = (now or datetime.now(KST)).astimezone(KST)
    return (now_kst + timedelta(days=1)).replace(hour=0, minute=5, second=0, microsecond=0)


class Limiter(Protocol):
    async def acquire(self, source: str) -> None: ...


class Breaker(Protocol):
    async def before_call(self, source: str) -> None: ...
    async def record_success(self, source: str) -> None: ...
    async def record_failure(self, source: str) -> None: ...


# --------------------------------------------------------------------------------------------
# Redis implementations
# --------------------------------------------------------------------------------------------
_TOKEN_BUCKET_LUA = """
local key = KEYS[1]
local capacity = tonumber(ARGV[1])
local refill_per_sec = tonumber(ARGV[2])
local now = tonumber(ARGV[3])
local state = redis.call('HMGET', key, 'tokens', 'ts')
local tokens = tonumber(state[1]) or capacity
local ts = tonumber(state[2]) or now
tokens = math.min(capacity, tokens + (now - ts) * refill_per_sec)
local wait = 0
if tokens < 1 then
  wait = (1 - tokens) / refill_per_sec
else
  tokens = tokens - 1
end
redis.call('HSET', key, 'tokens', tokens, 'ts', now)
redis.call('EXPIRE', key, 3600)
return tostring(wait)
"""


@dataclass(slots=True)
class RedisLimiter:
    redis: Redis
    capacity: float = 5.0
    refill_per_sec: float = 2.0
    daily_quota: dict[str, int] | None = None

    async def acquire(self, source: str) -> None:
        import asyncio

        quota = (self.daily_quota or {}).get(source)
        if quota is not None:
            day = datetime.now(KST).strftime("%Y%m%d")
            key = f"mulmit:quota:{source}:{day}"
            used = int(await self.redis.incr(key))
            if used == 1:
                await self.redis.expire(key, 60 * 60 * 26)
            if used > quota:
                raise QuotaExhaustedError(source, next_kst_midnight())
        while True:
            wait = float(
                await self.redis.eval(  # type: ignore[misc]
                    _TOKEN_BUCKET_LUA,
                    1,
                    f"mulmit:bucket:{source}",
                    str(self.capacity),
                    str(self.refill_per_sec),
                    str(time.time()),
                )
            )
            if wait <= 0:
                return
            await asyncio.sleep(min(wait, 5.0))


@dataclass(slots=True)
class RedisBreaker:
    redis: Redis
    failure_threshold: int = 5
    cooldown_seconds: int = 600

    def _key(self, source: str) -> str:
        return f"mulmit:circuit:{source}"

    async def before_call(self, source: str) -> None:
        opened_until = await self.redis.hget(self._key(source), "opened_until")  # type: ignore[misc]
        if opened_until is None:
            return
        remaining = float(opened_until) - time.time()
        if remaining > 0:
            raise CircuitOpenError(source, remaining)
        # Half-open: exactly one worker gets to probe.
        got_probe = await self.redis.set(f"{self._key(source)}:probe", "1", nx=True, ex=60)
        if not got_probe:
            raise CircuitOpenError(source, 30)

    async def record_success(self, source: str) -> None:
        await self.redis.delete(self._key(source), f"{self._key(source)}:probe")

    async def record_failure(self, source: str) -> None:
        key = self._key(source)
        failures = int(await self.redis.hincrby(key, "failures", 1))  # type: ignore[misc]
        await self.redis.expire(key, self.cooldown_seconds * 6)
        if failures >= self.failure_threshold:
            await self.redis.hset(  # type: ignore[misc]
                key, "opened_until", str(time.time() + self.cooldown_seconds)
            )
            await self.redis.delete(f"{key}:probe")

    async def state(self, source: str) -> dict[str, str]:
        raw: dict[bytes | str, bytes | str] = await self.redis.hgetall(self._key(source))  # type: ignore[misc]
        out = {
            (k.decode() if isinstance(k, bytes) else k): (v.decode() if isinstance(v, bytes) else v)
            for k, v in raw.items()
        }
        opened_until = float(out.get("opened_until", 0) or 0)
        out["state"] = "open" if opened_until > time.time() else "closed"
        return out


# --------------------------------------------------------------------------------------------
# In-memory implementations (tests, CLI one-offs)
# --------------------------------------------------------------------------------------------
@dataclass(slots=True)
class MemoryLimiter:
    daily_quota: dict[str, int] | None = None
    calls: dict[str, int] | None = None

    async def acquire(self, source: str) -> None:
        if self.calls is None:
            self.calls = {}
        self.calls[source] = self.calls.get(source, 0) + 1
        quota = (self.daily_quota or {}).get(source)
        if quota is not None and self.calls[source] > quota:
            raise QuotaExhaustedError(source, next_kst_midnight())


@dataclass(slots=True)
class MemoryBreaker:
    failure_threshold: int = 5
    cooldown_seconds: float = 600
    _failures: dict[str, int] | None = None
    _opened_until: dict[str, float] | None = None

    async def before_call(self, source: str) -> None:
        opened = (self._opened_until or {}).get(source, 0.0)
        if opened > time.monotonic():
            raise CircuitOpenError(source, opened - time.monotonic())

    async def record_success(self, source: str) -> None:
        (self._failures or {}).pop(source, None)
        (self._opened_until or {}).pop(source, None)

    async def record_failure(self, source: str) -> None:
        if self._failures is None:
            self._failures = {}
        if self._opened_until is None:
            self._opened_until = {}
        self._failures[source] = self._failures.get(source, 0) + 1
        if self._failures[source] >= self.failure_threshold:
            self._opened_until[source] = time.monotonic() + self.cooldown_seconds
