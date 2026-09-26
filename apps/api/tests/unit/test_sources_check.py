"""`manage sources check` against a fake 공공데이터포털: coverage, renamed fields, masked keys."""

import io
import re
from typing import Any

import httpx
import pytest

from app.log import configure_logging, get_logger, redact_secrets
from app.observability import _scrub, event_scrubber
from app.sources.check import check_g2b, problems, render
from app.sources.g2b import normalize_service_key

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
    # 사전규격: the key was never applied for on this service — the live gateway's answer
    return httpx.Response(
        403,
        json={
            "OpenAPI_ServiceResponse": {
                "cmmMsgHeader": {
                    "errMsg": "SERVICE_KEY_IS_NOT_REGISTERED_ERROR",
                    "returnAuthMsg": "등록되지 않은 서비스키",
                    "returnReasonCode": "30",
                }
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
    assert prespec.error and "30 SERVICE_KEY_IS_NOT_REGISTERED_ERROR" in prespec.error

    report = render(checks, days=7)
    assert "bidNtceTitle" in report and "실패" in report
    assert "## 활용신청이 필요한 서비스" in report
    assert "조달청_나라장터 사전규격정보서비스" in report
    assert "발주계획현황서비스" not in report  # that one answered


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


def test_sentry_errors_lose_keys_in_breadcrumbs_and_exceptions() -> None:
    event: Any = {
        "breadcrumbs": {
            "values": [
                # sentry-sdk's httpx integration keeps the query apart from the URL
                {"data": {"url": "https://apis.data.go.kr/x", "http.query": "serviceKey=SECRET"}},
                {"message": "source.retry error='cannot reach https://x?key=SECRET&page=1'"},
            ]
        },
        "exception": {"values": [{"value": "gave up: https://x?Key=SECRET"}]},
    }
    scrubbed = _scrub(event, {})
    assert scrubbed is not None
    assert "SECRET" not in str(scrubbed)


def test_sentry_transactions_lose_keys_in_span_data() -> None:
    transaction: Any = {
        "type": "transaction",
        "spans": [
            {
                "op": "http.client",
                "description": "GET https://apis.data.go.kr/x",
                "data": {"http.query": "serviceKey=SECRET&type=json", "url": "https://x"},
            }
        ],
    }
    scrubbed = _scrub(transaction, {})
    assert scrubbed is not None
    assert "SECRET" not in str(scrubbed)
    assert "type=json" in str(scrubbed)


def test_sentry_frame_variables_holding_keys_are_scrubbed() -> None:
    event: Any = {
        "exception": {
            "values": [
                {
                    "stacktrace": {
                        "frames": [
                            {"function": "fetch_page", "vars": {"service_key": "SECRET"}},
                            {"function": "request", "vars": {"params": {"serviceKey": "SECRET"}}},
                        ]
                    }
                }
            ]
        }
    }
    event_scrubber().scrub_event(event)
    assert "SECRET" not in str(event)


def test_log_lines_and_chained_tracebacks_are_redacted() -> None:
    out = io.StringIO()
    configure_logging(json=True, level="WARNING", stream=out)
    log = get_logger("test")
    log.warning("source.retry", error="cannot reach https://x?serviceKey=SECRET")
    try:
        try:
            raise httpx.ConnectError("cannot reach https://x?serviceKey=SECRET")
        except httpx.ConnectError as exc:
            raise RuntimeError("gave up") from exc  # the cause keeps the raw URL
    except RuntimeError:
        log.exception("job.failed")
    text = out.getvalue()
    assert "job.failed" in text and "serviceKey=***" in text
    assert "SECRET" not in text


def test_encoding_form_keys_are_sent_once_encoded() -> None:
    assert normalize_service_key("abc%2BDEF%2Fghi%3D%3D") == KEY
    assert normalize_service_key(KEY) == KEY


async def test_encoding_form_key_reaches_the_provider_as_the_real_key() -> None:
    seen: list[str] = []

    def capture(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.params["serviceKey"])
        return _ok([ORDER_PLAN])

    await check_g2b(
        "abc%2BDEF%2Fghi%3D%3D", sources=["g2b_order_plan"], transport=httpx.MockTransport(capture)
    )
    assert seen and set(seen) == {KEY}


async def test_exit_problems_and_unknown_sources() -> None:
    checks = await check_g2b(KEY, transport=httpx.MockTransport(_handler))
    issues = problems(checks)
    assert any("getPublicPrcureThngInfo" in i for i in issues)  # failed calls
    assert any("none mapped" in i for i in issues)  # renamed bid field
    assert not any("OrderPlanSttus" in i for i in issues)
    with pytest.raises(ValueError, match="unknown source"):
        await check_g2b(KEY, sources=["g2b_bid_notice"])


def test_report_cells_survive_pipes_and_newlines() -> None:
    from app.sources.check import OperationCheck

    bad = OperationCheck("g2b_bid", "/ad/X/op", error="HTTP 500 | upstream\nreset")
    lines = render([bad], days=7).splitlines()
    header = next(line for line in lines if line.startswith("| 수집원"))
    row = next(line for line in lines if "`op`" in line)
    unescaped_pipes = re.compile(r"(?<!\\)\|")
    assert len(unescaped_pipes.split(row)) == len(unescaped_pipes.split(header))


def test_sentry_is_initialised_with_all_three_scrubbers(monkeypatch: pytest.MonkeyPatch) -> None:
    import sentry_sdk

    from app.observability import init_sentry
    from app.settings import Settings

    seen: dict[str, Any] = {}
    monkeypatch.setattr(sentry_sdk, "init", lambda **kw: seen.update(kw))
    monkeypatch.setattr(sentry_sdk, "set_tag", lambda *_: None)
    assert init_sentry(Settings(sentry_dsn="https://k@o0.ingest.sentry.io/1"), component="worker")
    assert seen["before_send"] is _scrub
    assert seen["before_send_transaction"] is _scrub
    assert "servicekey" in seen["event_scrubber"].denylist
