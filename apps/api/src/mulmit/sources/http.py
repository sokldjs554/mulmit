"""HTTP client for flaky public-data APIs.

Retry policy (per request):

* Timeouts, connection errors, 429 and 5xx → retry with exponential backoff and full jitter,
  honouring ``Retry-After`` when present.
* Provider "soft errors" — data.go.kr answers *HTTP 200* with an XML ``OpenAPI_ServiceResponse``
  or a JSON ``resultCode != "00"`` — are classified: quota/traffic codes raise
  :class:`QuotaExhaustedError` (reschedule, do not retry), key/parameter codes raise
  :class:`FatalSourceError` (page an operator), transient codes retry.
* Every attempt goes through the shared rate limiter; every outcome feeds the circuit breaker.
"""

from __future__ import annotations

import asyncio
import json
import random
import re
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

import httpx

from mulmit.log import get_logger
from mulmit.sources.resilience import (
    Breaker,
    Limiter,
    QuotaExhaustedError,
    next_kst_midnight,
)

log = get_logger(__name__)

RETRYABLE_STATUS = {408, 425, 429, 500, 502, 503, 504}

# data.go.kr common error codes (공공데이터포털 OpenAPI 에러코드 표)
_DGK_QUOTA_CODES = {"22"}  # LIMITED_NUMBER_OF_SERVICE_REQUESTS_EXCEEDS_ERROR
_DGK_TRANSIENT_CODES = {"01", "02", "03", "04", "05", "99"}  # app/db/http/timeout/unknown
_DGK_FATAL_CODES = {"10", "11", "12", "20", "30", "31", "32", "33"}  # params / key problems


class FatalSourceError(Exception):
    """Misconfiguration (bad key, bad parameter). Retrying will not help."""


class TransientSourceError(Exception):
    pass


def _classify_soft_error(source: str, body: str) -> None:
    code: str | None = None
    message = ""
    if body.lstrip().startswith("<"):
        m = re.search(r"<returnReasonCode>\s*(\d+)\s*</returnReasonCode>", body)
        if m:
            code = m.group(1)
            mm = re.search(r"<returnAuthMsg>\s*([^<]+)</returnAuthMsg>", body)
            message = mm.group(1) if mm else ""
        else:
            m = re.search(r"<resultCode>\s*(\d+)\s*</resultCode>", body)
            if m and m.group(1) not in {"00", "0"}:
                code = m.group(1)
    else:
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError:
            return
        header = (parsed.get("response") or {}).get("header") if isinstance(parsed, dict) else None
        if isinstance(header, dict):
            rc = str(header.get("resultCode", "00"))
            if rc not in {"00", "0"}:
                code, message = rc, str(header.get("resultMsg", ""))
    if code is None:
        return
    if code in _DGK_QUOTA_CODES:
        raise QuotaExhaustedError(source, next_kst_midnight())
    if code in _DGK_FATAL_CODES:
        raise FatalSourceError(f"{source}: provider error {code} {message}".strip())
    raise TransientSourceError(f"{source}: provider error {code} {message}".strip())


class ResilientClient:
    def __init__(
        self,
        source: str,
        *,
        base_url: str,
        limiter: Limiter,
        breaker: Breaker,
        timeout: float = 20.0,
        max_attempts: int = 4,
        base_delay: float = 1.0,
        max_delay: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.source = source
        self._limiter = limiter
        self._breaker = breaker
        self._max_attempts = max_attempts
        self._base_delay = base_delay
        self._max_delay = max_delay
        self._sleep = sleep
        self._client = httpx.AsyncClient(
            base_url=base_url,
            timeout=httpx.Timeout(timeout, connect=5.0),
            transport=transport,
            headers={"User-Agent": "mulmit-collector/0.1 (+https://github.com/sokldjs554/mulmit)"},
            follow_redirects=True,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    def _backoff(self, attempt: int, retry_after: str | None) -> float:
        if retry_after:
            try:
                return min(float(retry_after), self._max_delay)
            except ValueError:
                pass
        # Full jitter (AWS architecture blog): uniform(0, min(cap, base * 2^attempt)).
        return random.uniform(0, min(self._max_delay, self._base_delay * 2**attempt))  # noqa: S311

    async def request(
        self,
        method: str,
        url: str,
        *,
        params: Mapping[str, Any] | None = None,
        soft_errors: bool = True,
    ) -> httpx.Response:
        last_exc: Exception | None = None
        for attempt in range(self._max_attempts):
            await self._breaker.before_call(self.source)
            await self._limiter.acquire(self.source)
            retry_after: str | None = None
            try:
                resp = await self._client.request(method, url, params=params)
                if resp.status_code in RETRYABLE_STATUS:
                    retry_after = resp.headers.get("Retry-After")
                    raise TransientSourceError(f"{self.source}: HTTP {resp.status_code}")
                if resp.status_code >= 400:
                    await self._breaker.record_success(self.source)  # provider is up; we're wrong
                    raise FatalSourceError(f"{self.source}: HTTP {resp.status_code} for {url}")
                # Error envelopes are small; don't re-parse multi-MB data pages to look for one.
                if soft_errors and (
                    len(resp.content) < 65_536 or resp.content.lstrip()[:1] == b"<"
                ):
                    _classify_soft_error(self.source, resp.text)
                await self._breaker.record_success(self.source)
                return resp
            except (QuotaExhaustedError, FatalSourceError):
                raise
            except (httpx.TimeoutException, httpx.TransportError, TransientSourceError) as exc:
                last_exc = exc
                await self._breaker.record_failure(self.source)
                if attempt + 1 >= self._max_attempts:
                    break
                delay = self._backoff(attempt, retry_after)
                log.warning(
                    "source.retry",
                    source=self.source,
                    attempt=attempt + 1,
                    delay=round(delay, 2),
                    error=str(exc),
                )
                await self._sleep(delay)
        assert last_exc is not None
        raise TransientSourceError(
            f"{self.source}: gave up after {self._max_attempts} attempts: {last_exc}"
        ) from last_exc

    async def get_json(self, url: str, *, params: Mapping[str, Any] | None = None) -> Any:
        resp = await self.request("GET", url, params=params)
        try:
            return resp.json()
        except json.JSONDecodeError as exc:
            raise TransientSourceError(f"{self.source}: non-JSON body") from exc

    async def get_bytes(self, url: str) -> bytes:
        resp = await self.request("GET", url, soft_errors=False)
        return resp.content
