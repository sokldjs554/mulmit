"""Resilient HTTP client + provider contract tests (no network)."""

from collections.abc import Callable
from datetime import date

import httpx
import pytest

from app.sources.base import FetchWindow
from app.sources.g2b import G2BAdapter, map_item
from app.sources.http import FatalSourceError, ResilientClient, TransientSourceError
from app.sources.resilience import (
    CircuitOpenError,
    MemoryBreaker,
    MemoryLimiter,
    QuotaExhaustedError,
)

DATA_GO_KR_QUOTA_XML = """<OpenAPI_ServiceResponse><cmmMsgHeader>
<errMsg>SERVICE ERROR</errMsg><returnAuthMsg>LIMITED_NUMBER_OF_SERVICE_REQUESTS_EXCEEDS_ERROR</returnAuthMsg>
<returnReasonCode>22</returnReasonCode></cmmMsgHeader></OpenAPI_ServiceResponse>"""
DATA_GO_KR_BAD_KEY_XML = DATA_GO_KR_QUOTA_XML.replace(">22<", ">30<")


async def _no_sleep(_: float) -> None:
    return None


def _client(handler: Callable[[httpx.Request], httpx.Response], **kwargs) -> ResilientClient:  # type: ignore[no-untyped-def]
    return ResilientClient(
        "g2b_bid",
        base_url="https://apis.example",
        limiter=kwargs.pop("limiter", MemoryLimiter()),
        breaker=kwargs.pop("breaker", MemoryBreaker(failure_threshold=3)),
        transport=httpx.MockTransport(handler),
        sleep=_no_sleep,
        **kwargs,
    )


async def test_retries_5xx_then_succeeds() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(503)
        return httpx.Response(200, json={"response": {"header": {"resultCode": "00"}, "body": {}}})

    client = _client(handler, max_attempts=4)
    data = await client.get_json("/x")
    assert calls["n"] == 3
    assert data["response"]["header"]["resultCode"] == "00"


async def test_gives_up_after_max_attempts() -> None:
    client = _client(lambda r: httpx.Response(502), max_attempts=2)
    with pytest.raises(TransientSourceError):
        await client.get_json("/x")


async def test_give_up_message_names_a_blank_transport_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("")  # what a stalled TLS handshake to data.go.kr looks like

    with pytest.raises(TransientSourceError, match="gave up after 2 attempts: ConnectTimeout"):
        await _client(handler, max_attempts=2).get_json("/x")


async def test_http_200_quota_envelope_is_not_retried() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, text=DATA_GO_KR_QUOTA_XML, headers={"content-type": "text/xml"})

    with pytest.raises(QuotaExhaustedError):
        await _client(handler).get_json("/x")
    assert calls["n"] == 1


async def test_bad_service_key_is_fatal() -> None:
    handler = lambda r: httpx.Response(200, text=DATA_GO_KR_BAD_KEY_XML)  # noqa: E731
    with pytest.raises(FatalSourceError):
        await _client(handler).get_json("/x")


# What apis.data.go.kr actually sent on 2026-09-26 for a service the key was not applied for:
# HTTP 403 with a JSON gateway envelope (not HTTP 200, not ``response.header``).
DATA_GO_KR_NOT_REGISTERED_JSON = {
    "OpenAPI_ServiceResponse": {
        "cmmMsgHeader": {
            "errMsg": "SERVICE_KEY_IS_NOT_REGISTERED_ERROR",
            "returnAuthMsg": "등록되지 않은 서비스키",
            "returnReasonCode": "30",
        }
    }
}


async def test_http_403_gateway_envelope_names_the_provider_code() -> None:
    calls = {"n": 0}
    breaker = MemoryBreaker(failure_threshold=1)

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(403, json=DATA_GO_KR_NOT_REGISTERED_JSON)

    with pytest.raises(FatalSourceError) as info:
        await _client(handler, breaker=breaker).get_json("/x")
    assert "30 SERVICE_KEY_IS_NOT_REGISTERED_ERROR" in str(info.value)
    assert info.value.status == 403 and calls["n"] == 1
    await breaker.before_call("g2b_bid")  # a key problem does not open the circuit


async def test_http_200_gateway_envelope_is_not_read_as_an_empty_page() -> None:
    handler = lambda r: httpx.Response(200, json=DATA_GO_KR_NOT_REGISTERED_JSON)  # noqa: E731
    with pytest.raises(FatalSourceError, match="SERVICE_KEY_IS_NOT_REGISTERED_ERROR"):
        await _client(handler).get_json("/x")


async def test_http_429_quota_envelope_waits_for_the_reset() -> None:
    body = {"OpenAPI_ServiceResponse": {"cmmMsgHeader": {"returnReasonCode": "22"}}}
    with pytest.raises(QuotaExhaustedError):
        await _client(lambda r: httpx.Response(429, json=body)).get_json("/x")


async def test_http_4xx_without_envelope_is_still_fatal() -> None:
    with pytest.raises(FatalSourceError, match="HTTP 404"):
        await _client(lambda r: httpx.Response(404, text="not found")).get_json("/x")


async def test_json_result_code_error_is_classified() -> None:
    body = {"response": {"header": {"resultCode": "22", "resultMsg": "LIMITED"}}}
    with pytest.raises(QuotaExhaustedError):
        await _client(lambda r: httpx.Response(200, json=body)).get_json("/x")


async def test_circuit_opens_after_consecutive_failures() -> None:
    breaker = MemoryBreaker(failure_threshold=2, cooldown_seconds=60)
    client = _client(lambda r: httpx.Response(500), breaker=breaker, max_attempts=2)
    with pytest.raises(TransientSourceError):
        await client.get_json("/x")
    with pytest.raises(CircuitOpenError):
        await client.get_json("/x")


async def test_daily_quota_counts_every_attempt() -> None:
    limiter = MemoryLimiter(daily_quota={"g2b_bid": 2})
    client = _client(lambda r: httpx.Response(503), limiter=limiter, max_attempts=5)
    with pytest.raises(QuotaExhaustedError):
        await client.get_json("/x")


def test_g2b_bid_item_contract() -> None:
    item = {
        "bidNtceNo": "R26BK00012345",
        "bidNtceOrd": "000",
        "bidNtceNm": "[긴급] 2026년 스마트쉘터 구축사업 (협상에 의한 계약)",
        "ntceInsttNm": "조달청",
        "dminsttNm": "서울특별시 강남구",
        "dminsttCd": "3220000",
        "bidNtceDt": "2026-03-15 14:00:00",
        "bidClseDt": "2026-03-29 10:00:00",
        "asignBdgtAmt": "350000000",
        "presmptPrce": "318181818",
        "bfSpecRgstNo": "R26BD00000001",
        "bidNtceDtlUrl": "https://www.g2b.go.kr/x",
    }
    rec = map_item("bid_notice", item)
    assert rec is not None
    assert rec.external_id == "R26BK00012345-000"
    assert rec.published_at == date(2026, 3, 15)
    assert rec.publisher_raw == "서울특별시 강남구"
    assert rec.structured["amount_krw"] == 350_000_000
    assert rec.structured["prespec_no"] == "R26BD00000001"


def test_g2b_rows_without_ids_are_dropped() -> None:
    assert map_item("prespec", {"prdctClsfcNoNm": "x", "rcptDt": "2026-01-01"}) is None


async def test_g2b_adapter_pages_and_slices_windows() -> None:
    seen: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        params = request.url.params
        seen.append((params["inqryBgnDt"], params["pageNo"]))
        page = int(params["pageNo"])
        items = [
            {
                "bidNtceNo": f"B{params['inqryBgnDt']}{page}{i}",
                "bidNtceNm": "스마트폴 구축",
                "bidNtceDt": "2026-01-02 10:00:00",
                "dminsttNm": "성남시",
            }
            for i in range(100 if page == 1 else 3)
        ]
        body = {
            "response": {
                "header": {"resultCode": "00"},
                "body": {"items": items, "totalCount": 103, "pageNo": page},
            }
        }
        return httpx.Response(200, json=body)

    adapter = G2BAdapter("g2b_bid", _client(handler), "KEY")
    records = [r async for r in adapter.fetch(FetchWindow(date(2026, 1, 1), date(2026, 1, 10)))]
    # 2 weekly slices x 3 service types x 2 pages
    assert len(seen) == 12
    assert len(records) == 2 * 3 * 103
