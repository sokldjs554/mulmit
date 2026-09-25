"""Run the arq worker with a minimal HTTP health endpoint (``manage worker``).

Cloud Run services must listen on ``$PORT``, and the worker has no API of its own. This serves
``GET /healthz`` from the worker's event loop: 200 while arq's health-check key in Redis is fresh
(arq rewrites it every ``health_check_interval``), 503 once it goes stale, so a wedged worker is
restarted instead of silently skipping its cron schedule. Without ``$PORT`` it is plain arq.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import time
from typing import Any, cast

from arq.worker import Worker, create_worker

STARTUP_GRACE_SECONDS = 60.0


async def is_healthy(
    pool: Any, health_key: str, started_at: float, now: float | None = None
) -> bool:
    """Healthy while arq's health key exists; before the first write, allow a startup grace."""
    now = time.monotonic() if now is None else now
    if pool is not None:
        with contextlib.suppress(Exception):
            if await pool.exists(health_key):
                return True
    return now - started_at < STARTUP_GRACE_SECONDS


async def serve_health(port: int, check: Any) -> asyncio.Server:
    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            with contextlib.suppress(Exception):
                await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout=5)
            ok = await check()
            body = b"ok" if ok else b"worker heartbeat is stale"
            status = "200 OK" if ok else "503 Service Unavailable"
            writer.write(
                f"HTTP/1.1 {status}\r\nContent-Type: text/plain\r\n"
                f"Content-Length: {len(body)}\r\nConnection: close\r\n\r\n".encode()
                + body
            )
            await writer.drain()
        finally:
            writer.close()

    return await asyncio.start_server(handle, host="0.0.0.0", port=port)  # noqa: S104


async def _main(port: int) -> None:
    from app.worker.settings import WorkerSettings

    worker: Worker = create_worker(cast(Any, WorkerSettings))
    started_at = time.monotonic()

    async def check() -> bool:
        return await is_healthy(worker._pool, worker.health_check_key, started_at)

    server = await serve_health(port, check) if port else None
    try:
        with contextlib.suppress(asyncio.CancelledError):
            await worker.async_run()
    finally:
        if server is not None:
            server.close()
            await server.wait_closed()
        # SIGTERM cancelled the in-flight jobs; let them unwind (their `tracked` wrapper records
        # the run as retrying) before arq's close() gathers what is left.
        await asyncio.gather(*worker.tasks.values(), return_exceptions=True)
        worker.tasks.clear()
        await worker.close()


def run() -> None:
    port = int(os.environ.get("PORT") or 0)
    asyncio.run(_main(port))
