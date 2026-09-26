"""Real-shaped 조달청 records through ingest → process → link, and the backfill command's path."""

import dataclasses
from datetime import date
from functools import partial
from typing import Any

import httpx
from pydantic import SecretStr
from sqlalchemy import delete, func, select

from app.db.models import Document, IngestRun, OpportunitySignal, Source
from app.db.session import get_sessionmaker, session_scope
from app.pipeline.backfill import ingest_window
from app.pipeline.ingest import upsert_record
from app.pipeline.link import link_signals
from app.pipeline.process import process_document
from app.sources import registry as registry_module
from app.sources.base import FetchWindow
from app.sources.g2b import map_item
from app.sources.http import ResilientClient

# Trimmed from live rows (2026-09-26); names and numbers changed, contacts removed.
PLAN = {
    "orderPlanUntyNo": "R26DD90000001",
    "bizNm": "유성구 청사 UPS 배터리 교체공사",
    "nticeDt": "2026-09-22 10:00:00",
    "orderInsttNm": "대전광역시 유성구",
    "sumOrderAmt": "76230000",
    "orderYear": "2026",
    "orderMnth": "10",
    "bidNtceNoList": "R26BK90000001000",  # the plan was registered after its 공고
}
BID = {
    "bidNtceNo": "R26BK90000001",
    "bidNtceOrd": "000",
    "bidNtceNm": "유성구 청사 UPS 배터리 교체공사",
    "bidNtceDt": "2026-09-20 09:00:00",
    "dminsttNm": "대전광역시 유성구",
    "bdgtAmt": "76230000",
    "presmptPrce": "69300000",
    "bfSpecRgstNo": "",
    "orderPlanUntyNo": "",  # 26% of live 공고 leave it empty
}


async def test_a_plan_registered_after_its_bid_joins_the_bids_opportunity(
    demo_world, runtime
) -> None:  # type: ignore[no-untyped-def]
    async with get_sessionmaker()() as s:
        source = Source(key="test_g2b_shapes", name="t", adapter="g2b", enabled=False, config={})
        s.add(source)
        await s.flush()
        signal_ids: list[int] = []
        for doc_type, item in (("bid_notice", BID), ("order_plan", PLAN)):  # publication order
            rec = map_item(doc_type, item)  # type: ignore[arg-type]
            assert rec is not None
            doc, _ = await upsert_record(s, source, rec, runtime)
            signal_ids += (await process_document(s, runtime, doc.id)).signal_ids
        await link_signals(s, runtime, signal_ids, today=date(2026, 9, 26))
        links = (
            await s.execute(
                select(OpportunitySignal.opportunity_id, OpportunitySignal.method).where(
                    OpportunitySignal.signal_id.in_(signal_ids)
                )
            )
        ).all()
        await s.rollback()
    assert len(links) == 2
    assert len({opp for opp, _ in links}) == 1
    assert [m for _, m in links] == ["seed", "ref"]


def _g2b_transport(calls: dict[str, int]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        path = request.url.path
        items: list[dict[str, Any]] = []
        if path.endswith("Servc") and request.url.params["inqryBgnDt"].startswith("20260920"):
            items = [BID | {"bidNtceNo": f"R26BK9100000{i}"} for i in range(3)]
        body = {"response": {"header": {"resultCode": "00"}, "body": {"items": items}}}
        body["response"]["body"]["totalCount"] = len(items)  # type: ignore[index]
        return httpx.Response(200, json=body)

    return httpx.MockTransport(handler)


async def test_backfill_twice_stores_each_record_once(demo_world, runtime, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    calls = {"n": 0}
    monkeypatch.setattr(
        registry_module,
        "ResilientClient",
        partial(ResilientClient, transport=_g2b_transport(calls)),
    )
    settings = runtime.settings.model_copy(update={"data_go_kr_service_key": SecretStr("KEY")})
    rt = dataclasses.replace(runtime, settings=settings)
    window = FetchWindow(date(2026, 9, 20), date(2026, 9, 26))
    reports = []
    try:
        for _ in range(2):
            async with session_scope() as s:
                src = await s.scalar(select(Source).where(Source.key == "g2b_bid"))
                reports += await ingest_window(s, rt, [src], window, rows=999, max_calls=10)
        async with session_scope() as s:
            stored = await s.scalar(
                select(func.count()).select_from(Document).where(Document.source_id == src.id)
            )
    finally:
        async with session_scope() as s:
            src = await s.scalar(select(Source).where(Source.key == "g2b_bid"))
            await s.execute(delete(Document).where(Document.source_id == src.id))
            await s.execute(delete(IngestRun).where(IngestRun.source_id == src.id))
            src.cursor = {}
    first, second = reports
    assert stored == 3
    assert (first["created"], first["skipped"]) == (3, 0)
    assert (second["created"], second["updated"], second["skipped"]) == (0, 0, 3)
    assert first["calls"] == second["calls"] == 3  # one slice x 3 업무구분, one page each
    assert calls["n"] == 6
    assert first["operations"]["getBidPblancListInfoServc"]["mapped"] == 3
    assert first["error"] is None


async def test_backfill_stops_a_source_at_its_call_budget(demo_world, runtime, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    calls = {"n": 0}
    monkeypatch.setattr(
        registry_module,
        "ResilientClient",
        partial(ResilientClient, transport=_g2b_transport(calls)),
    )
    settings = runtime.settings.model_copy(update={"data_go_kr_service_key": SecretStr("KEY")})
    rt = dataclasses.replace(runtime, settings=settings)
    try:
        async with session_scope() as s:
            src = await s.scalar(select(Source).where(Source.key == "g2b_bid"))
            [report] = await ingest_window(
                s, rt, [src], FetchWindow(date(2026, 9, 20), date(2026, 9, 26)), max_calls=1
            )
    finally:
        async with session_scope() as s:
            src = await s.scalar(select(Source).where(Source.key == "g2b_bid"))
            await s.execute(delete(Document).where(Document.source_id == src.id))
            await s.execute(delete(IngestRun).where(IngestRun.source_id == src.id))
            src.cursor = {}
    assert calls["n"] == 1
    assert report["calls"] == 1
    assert report["status"] == "partial"  # what the first call brought in is kept
    assert report["created"] == 3
    assert "CallBudgetExhaustedError" in report["error"]
