"""`manage sources check` against a fake 공공데이터포털: coverage, renamed fields, masked keys."""

from typing import Any

import httpx
import pytest

from app.observability import _scrub
from app.sources.check import check_g2b, render
from app.sources.http import redact_secrets

KEY = "abc+DEF/ghi=="  # data.go.kr keys contain URL-special characters

ORDER_PLAN = {
    "orderPlanUntyNo": "R26DD00001",
    "bizNm": "스마트쉘터 구축",
    "nticeDt": "2026-09-20",
    "sumOrderAmt": "350000000",
    "orderYear": "2026",
    "orderMnth": "11",
    "orderInsttNm": "서울특별시 강남구",
    "deptNm": "스마트도시과",
}
BID_RENAMED = {  # the provider renamed bidNtceNm → bidNtceTitle
    "bidNtceNo": "R26BK00012345",
    "bidNtceOrd": "000",
    "bidNtceTitle": "스마트폴 구축",
    "bidNtceDt": "2026-09-21 10:00:00",
    "dminsttNm": "서울특별시 강남구",
}


def _ok(items: list[dict[str, Any]]) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "response": {
                "header": {"resultCode": "00", "resultMsg": "NORMAL SERVICE."},
                "body": {"items": items, "totalCount": len(items) * 10},
            }
        },
    )


def _handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if "OrderPlanSttusService" in path:
        return _ok([ORDER_PLAN, ORDER_PLAN | {"sumOrderAmt": None, "deptNm": None}])
    if "BidPublicInfoService" in path:
        return _ok([BID_RENAMED])
    # 사전규격: the key was never applied for on this service
    return httpx.Response(
        200,
        json={
            "response": {
                "header": {"resultCode": "30", "resultMsg": "SERVICE_KEY_IS_NOT_REGISTERED_ERROR"}
            }
        },
    )


async def test_reports_coverage_renames_and_provider_errors() -> None:
    checks = await check_g2b(KEY, transport=httpx.MockTransport(_handler))
    by_source: dict[str, list[Any]] = {}
    for c in checks:
        by_source.setdefault(c.source, []).append(c)
    assert len(checks) == 9  # 3 sources × 용역/물품/공사

    plan = by_source["g2b_order_plan"][0]
    assert plan.ok and plan.items == plan.mapped == 2
    assert plan.coverage["amount_krw"] == 0.5
    assert plan.coverage["order_year"] == 1.0
    assert plan.sample and plan.sample["amount_krw"] == 350_000_000

    bid = by_source["g2b_bid"][0]
    assert bid.ok and bid.items == 1 and bid.mapped == 0
    assert "bidNtceTitle" in bid.dropped_item_keys  # what the provider really sent

    prespec = by_source["g2b_prespec"][0]
    assert not prespec.ok
    assert prespec.error and "SERVICE_KEY_IS_NOT_REGISTERED_ERROR" in prespec.error

    report = render(checks, days=7)
    assert "bidNtceTitle" in report and "실패" in report


async def test_the_key_never_appears_in_errors() -> None:
    def leaky(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(f"cannot reach {request.url}")  # URL carries ?serviceKey=

    checks = await check_g2b(KEY, sources=["g2b_bid"], transport=httpx.MockTransport(leaky))
    assert checks and all(not c.ok for c in checks)
    for c in checks:
        assert c.error is not None
        assert "***" in c.error
        for form in (KEY, "abc%2BDEF%2Fghi%3D%3D"):
            assert form not in c.error


@pytest.mark.parametrize(
    "text",
    [
        "https://apis.data.go.kr/1230000/x?serviceKey=SECRET%2B1&type=json",  # 조달청
        "https://clik.nanet.go.kr/openapi/minutes.do?key=SECRET%2B1&page=1",  # CLIK
        "https://lofin365.go.kr/api/budget?Key=SECRET%2B1",  # 지방재정365
        "source.retry error='gave up: api_key=SECRET%2B1'",
    ],
)
def test_credential_query_parameters_are_redacted(text: str) -> None:
    out = redact_secrets(text)
    assert "SECRET" not in out and "***" in out


def test_redaction_leaves_ordinary_parameters_alone() -> None:
    text = "/search?keyword=스마트쉘터&monkey=1&pageNo=2"
    assert redact_secrets(text) == text


def test_sentry_events_lose_keys_in_breadcrumbs_and_exceptions() -> None:
    event: Any = {
        "breadcrumbs": {
            "values": [
                {"data": {"url": "https://apis.data.go.kr/x?serviceKey=SECRET"}},
                {"message": "source.retry error='cannot reach https://x?key=SECRET&page=1'"},
            ]
        },
        "exception": {"values": [{"value": "gave up: https://x?Key=SECRET"}]},
    }
    scrubbed = _scrub(event, {})
    assert scrubbed is not None
    assert "SECRET" not in str(scrubbed)
