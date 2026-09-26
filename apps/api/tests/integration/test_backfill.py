"""Real-shaped 조달청 records through ingest → process → link, and the backfill command's path."""

import dataclasses
from datetime import date
from functools import partial
from typing import Any

import httpx
from pydantic import SecretStr
from sqlalchemy import delete, func, select

from app.db.models import Document, IngestRun, InstitutionRow, OpportunitySignal, Signal, Source
from app.db.session import get_sessionmaker, session_scope
from app.domain.institutions import load_registry_csv
from app.pipeline.backfill import ingest_window
from app.pipeline.ingest import reresolve_institutions, upsert_record
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
    "bidNtceNoList": "R26BK90000001000",  # registered once the 공고 was out
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


async def test_a_plan_linked_after_its_bid_joins_the_bids_opportunity(demo_world, runtime) -> None:  # type: ignore[no-untyped-def]
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


async def test_look_alike_plans_with_different_numbers_stay_apart(demo_world, runtime) -> None:  # type: ignore[no-untyped-def]
    # One 기관, two 발주계획 a few days apart, titles one word apart (common in live data).
    first = PLAN | {"bizNm": "관내 도로 정비공사(1차)", "bidNtceNoList": ""}
    second = first | {"orderPlanUntyNo": "R26DD90000002", "bizNm": "관내 도로 정비공사(2차)"}
    second |= {"nticeDt": "2026-09-24 10:00:00"}
    bid = BID | {"bidNtceNo": "R26BK90000002", "bidNtceNm": "관내 도로 정비공사(2차)"}
    bid |= {"bidNtceDt": "2026-09-25 10:00:00", "orderPlanUntyNo": "R26DD90000002"}
    async with get_sessionmaker()() as s:
        source = Source(key="test_g2b_lookalike", name="t", adapter="g2b", enabled=False, config={})
        s.add(source)
        await s.flush()
        signal_ids: list[int] = []
        for doc_type, item in (("order_plan", first), ("order_plan", second), ("bid_notice", bid)):
            rec = map_item(doc_type, item)  # type: ignore[arg-type]
            assert rec is not None
            doc, _ = await upsert_record(s, source, rec, runtime)
            signal_ids += (await process_document(s, runtime, doc.id)).signal_ids
        await link_signals(s, runtime, signal_ids, today=date(2026, 9, 26))
        opp_of = dict(
            (
                await s.execute(
                    select(OpportunitySignal.signal_id, OpportunitySignal.opportunity_id).where(
                        OpportunitySignal.signal_id.in_(signal_ids)
                    )
                )
            ).all()
        )
        await s.rollback()
    plan1, plan2, bid_signal = signal_ids
    assert opp_of[plan1] != opp_of[plan2]
    assert opp_of[bid_signal] == opp_of[plan2]


SCHOOL_PLAN = {
    "orderPlanUntyNo": "R26DD90000010",
    "bizNm": "2027학년도 신입생 교복(동복)",
    "nticeDt": "2026-09-21 16:01:50",
    "orderInsttCd": "7069990",
    "orderInsttNm": "서울특별시중부교육청 테스트중학교",
    "sumOrderAmt": "29315000",
    "orderYear": "2027",
    "orderMnth": "02",
}


async def test_a_school_is_known_by_its_procurement_code(demo_world, runtime) -> None:  # type: ignore[no-untyped-def]
    rt = dataclasses.replace(runtime, registry=load_registry_csv())
    async with get_sessionmaker()() as s:
        source = Source(key="test_g2b_school", name="t", adapter="g2b", enabled=False, config={})
        s.add(source)
        await s.flush()
        first = map_item("order_plan", SCHOOL_PLAN)
        later = map_item(
            "order_plan",
            SCHOOL_PLAN | {"orderPlanUntyNo": "R26DD90000011", "orderInsttNm": "테스트중학교"},
        )
        assert first is not None and later is not None
        doc1, _ = await upsert_record(s, source, first, rt)
        doc2, _ = await upsert_record(s, source, later, rt)
        row = await s.get(InstitutionRow, "G2B-7069990")
        stored = (row.name, row.kind, row.sido, row.region_code) if row else None
        signal_ids = (await process_document(s, rt, doc1.id)).signal_ids
        verdict = await s.scalar(select(Signal.verdict).where(Signal.id == signal_ids[0]))
        methods = (
            doc1.structured["institution_resolution"],
            doc2.structured["institution_resolution"],
        )
        codes = (doc1.institution_code, doc2.institution_code)
        await s.rollback()
    assert stored == (
        "서울특별시중부교육청 테스트중학교",
        "public_agency",
        "서울특별시",
        "11",
    )
    assert codes == ("G2B-7069990", "G2B-7069990")
    assert methods == ("provider", "code")  # the second one never reaches name matching
    assert verdict == "accepted"  # so it is linked, not left in the review queue


async def test_a_local_government_the_table_misses_goes_to_review(demo_world, runtime) -> None:  # type: ignore[no-untyped-def]
    rt = dataclasses.replace(runtime, registry=load_registry_csv())
    item = SCHOOL_PLAN | {"orderInsttCd": "3999990", "orderInsttNm": "인천광역시 제물포구"}
    async with get_sessionmaker()() as s:
        source = Source(key="test_g2b_gap", name="t", adapter="g2b", enabled=False, config={})
        s.add(source)
        await s.flush()
        rec = map_item("order_plan", item)
        assert rec is not None
        doc, _ = await upsert_record(s, source, rec, rt)
        stored = await s.get(InstitutionRow, "G2B-3999990")
        await s.rollback()
    assert doc.institution_code is None
    assert stored is None


async def test_reresolve_picks_up_documents_stored_before_the_table_knew_them(
    demo_world, runtime
) -> None:  # type: ignore[no-untyped-def]
    rt = dataclasses.replace(runtime, registry=load_registry_csv())
    async with get_sessionmaker()() as s:
        source = Source(key="test_g2b_again", name="t", adapter="g2b", enabled=False, config={})
        s.add(source)
        await s.flush()
        rec = map_item("order_plan", SCHOOL_PLAN)
        assert rec is not None
        rec.provider_institution_code = None  # as ingested before codes were used
        doc, _ = await upsert_record(s, source, rec, rt)
        await process_document(s, rt, doc.id)
        before = (doc.institution_code, doc.parse_status)

        report = await reresolve_institutions(s, rt)
        await s.refresh(doc)
        after = (doc.institution_code, doc.parse_status, doc.structured["institution_resolution"])
        await s.rollback()
    assert before == (None, "parsed")
    assert after == ("G2B-7069990", "pending", "provider")
    assert report["resolved"] >= 1
    assert report["institutions_added"] >= 1


async def test_reresolve_gives_a_codeless_prespec_the_institution_its_bid_names(
    demo_world, runtime
) -> None:  # type: ignore[no-untyped-def]
    # 사전규격 responses have no institution code; the same name on a coded 공고 supplies it,
    # even when the 사전규격 was stored first.
    rt = dataclasses.replace(runtime, registry=load_registry_csv())
    prespec = map_item(
        "prespec",
        {
            "bfSpecRgstNo": "R26BD90000020",
            "prdctClsfcNoNm": "본관 냉난방기 교체",
            "rcptDt": "2026-09-14 10:00:00",
            "orderInsttNm": "테스트시설관리공단",
            "rlDminsttNm": "테스트시설관리공단",
            "asignBdgtAmt": "88000000",
        },
    )
    bid = map_item(
        "bid_notice",
        BID
        | {
            "bidNtceNo": "R26BK90000020",
            "bidNtceNm": "본관 냉난방기 교체",
            "dminsttCd": "B559990",
            "dminsttNm": "테스트시설관리공단",
            "bfSpecRgstNo": "R26BD90000020",
        },
    )
    assert prespec is not None and bid is not None
    assert prespec.provider_institution_code is None
    async with get_sessionmaker()() as s:
        source = Source(key="test_g2b_order", name="t", adapter="g2b", enabled=False, config={})
        s.add(source)
        await s.flush()
        bid.provider_institution_code = None  # both stored before codes were used
        docs = [(await upsert_record(s, source, rec, rt))[0] for rec in (prespec, bid)]
        await reresolve_institutions(s, rt)
        for doc in docs:
            await s.refresh(doc)
        codes = [d.institution_code for d in docs]
        await s.rollback()
    assert codes == ["G2B-B559990", "G2B-B559990"]
