import asyncio

from app.worker.runner import STARTUP_GRACE_SECONDS, is_healthy, serve_health


class FakePool:
    def __init__(self, present: bool) -> None:
        self.present = present

    async def exists(self, *names: str) -> int:
        return 1 if self.present else 0


async def test_heartbeat_key_decides_health_after_startup_grace() -> None:
    late = STARTUP_GRACE_SECONDS + 1
    assert await is_healthy(FakePool(True), "q:health-check", started_at=0, now=late)
    assert not await is_healthy(FakePool(False), "q:health-check", started_at=0, now=late)
    # arq has not written its first heartbeat yet: don't let Cloud Run kill a booting worker
    assert await is_healthy(None, "q:health-check", started_at=0, now=STARTUP_GRACE_SECONDS - 1)


async def test_health_endpoint_speaks_http() -> None:
    state = {"ok": True}

    async def check() -> bool:
        return state["ok"]

    server = await serve_health(0, check)
    port = server.sockets[0].getsockname()[1]

    async def get() -> bytes:
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        writer.write(b"GET /healthz HTTP/1.1\r\nHost: worker\r\n\r\n")
        await writer.drain()
        data = await reader.read()
        writer.close()
        return data

    try:
        assert (await get()).startswith(b"HTTP/1.1 200 OK")
        state["ok"] = False
        assert (await get()).startswith(b"HTTP/1.1 503")
    finally:
        server.close()
        await server.wait_closed()
