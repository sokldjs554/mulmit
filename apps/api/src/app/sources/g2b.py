"""조달청 나라장터 Open APIs on 공공데이터포털 (apis.data.go.kr/1230000).

Three operations feed three lifecycle stages:

=================  =============================================  ==========================
stage              service / operation                            id field
=================  =============================================  ==========================
order_plan         ao/OrderPlanSttusService/getOrderPlanSttusList*  ``orderPlanUntyNo``
prespec            ao/HrcspSsstndrdInfoService/getPublicPrcure*    ``bfSpecRgstNo``
bid_notice         ad/BidPublicInfoService/getBidPblancListInfo*   ``bidNtceNo``-``bidNtceOrd``
=================  =============================================  ==========================

Each exists per 업무구분 (용역 ``Servc`` / 물품 ``Thng`` / 공사 ``Cnstwk``). Paths live in
:data:`OPERATIONS` and field names in :func:`map_item` — both in code, one place each (the
provider has renamed services before: ``ad``/``ao`` prefixes arrived in 2025). The field mapping
was written against the published specs, exercised with contract fixtures in
``tests/unit/test_sources.py`` and checked against the live service on 2026-09-26 (``manage
sources check``; see ``docs/data-sources.md``). Fields the provider never fills are left alone:
사전규격 responses carry no ``orderPlanUntyNo`` at all, and 공사 입찰공고 rarely have a
``bfSpecRgstNo`` because 공사 사전규격 are rare.
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any
from urllib.parse import unquote

from app.sources.base import (
    DocType,
    FetchWindow,
    RawRecord,
    parse_compact_date,
    parse_int,
    pick,
)
from app.sources.http import ResilientClient

BASE_URL = "https://apis.data.go.kr/1230000"


@dataclass(frozen=True, slots=True)
class Operation:
    doc_type: DocType
    paths: tuple[str, ...]
    window_days: int = 7


OPERATIONS: dict[str, Operation] = {
    "g2b_order_plan": Operation(
        "order_plan",
        (
            "/ao/OrderPlanSttusService/getOrderPlanSttusListServc",
            "/ao/OrderPlanSttusService/getOrderPlanSttusListThng",
            "/ao/OrderPlanSttusService/getOrderPlanSttusListCnstwk",
        ),
    ),
    "g2b_prespec": Operation(
        "prespec",
        (
            "/ao/HrcspSsstndrdInfoService/getPublicPrcureThngInfoServc",
            "/ao/HrcspSsstndrdInfoService/getPublicPrcureThngInfoThng",
            "/ao/HrcspSsstndrdInfoService/getPublicPrcureThngInfoCnstwk",
        ),
    ),
    "g2b_bid": Operation(
        "bid_notice",
        (
            "/ad/BidPublicInfoService/getBidPblancListInfoServc",
            "/ad/BidPublicInfoService/getBidPblancListInfoThng",
            "/ad/BidPublicInfoService/getBidPblancListInfoCnstwk",
        ),
    ),
}


def _items(payload: Any) -> tuple[list[dict[str, Any]], int]:
    body = ((payload or {}).get("response") or {}).get("body") or {}
    items = body.get("items") or []
    if isinstance(items, dict):  # older services wrap as {"item": [...]} or {"item": {...}}
        items = items.get("item") or []
        if isinstance(items, dict):
            items = [items]
    total = parse_int(body.get("totalCount")) or len(items)
    return [i for i in items if isinstance(i, dict)], total


# Amounts under this are placeholders, not budgets: on 30 days of live data (2026-09-26) 2% of
# rows said 0, 1, 10 or 70원, mostly 단가계약 and undisclosed budgets ("…방수공사" at 10원).
# As a budget they would rank and link as if the project were free.
MIN_AMOUNT_KRW = 10_000


def _amount(item: dict[str, Any], *names: str) -> int | None:
    """First field among ``names`` holding a real amount; "0" or "1" falls through to the next
    (a 공고 with ``asignBdgtAmt`` "0" can still carry ``presmptPrce``)."""
    for name in names:
        value = parse_int(item.get(name))
        if value is not None and value >= MIN_AMOUNT_KRW:
            return value
    return None


def _bid_numbers(value: Any) -> list[str]:
    """``bidNtceNoList`` → bid numbers. 사전규격 send "R26BK01702619,R26BK01717858"; 발주계획
    append the 3-digit 차수 ("R26BK01739589000"), which is dropped so both match ``bidNtceNo``."""
    out: list[str] = []
    for raw in str(value or "").replace(" ", "").split(","):
        no = raw[:-3] if len(raw) == 16 and raw[-3:].isdigit() and raw[:3].isalnum() else raw
        if no and no not in out:
            out.append(no)
    return out


def normalize_service_key(key: str) -> str:
    """공공데이터포털 shows each key twice: "Encoding" (``%2B``…) and "Decoding" (``+``…).
    httpx encodes query values itself, so the Encoding form would be encoded a second time and
    every call would fail with error 30 as if the service had never been applied for."""
    return unquote(key) if "%" in key else key


async def fetch_page(
    client: ResilientClient,
    service_key: str,
    path: str,
    start: date,
    end: date,
    *,
    page: int = 1,
    rows: int = 100,
) -> tuple[list[dict[str, Any]], int]:
    """One page of one operation, by registration date: ``(items, totalCount)``."""
    params: dict[str, Any] = {
        "serviceKey": service_key,
        "type": "json",
        "inqryDiv": 1,
        "inqryBgnDt": start.strftime("%Y%m%d") + "0000",
        "inqryEndDt": end.strftime("%Y%m%d") + "2359",
        "pageNo": page,
        "numOfRows": rows,
    }
    if "/OrderPlanSttusService/" in path:
        # 발주계획 also requires the planned order month range (error 08 without it). Plans
        # registered this week are for this year or next; a year either side misses none
        # (live 2026-09-26: 1,152 for 2025-01~2027-12, the same as for 2020-01~2030-12).
        params["orderBgnYm"] = f"{start.year - 1}01"
        params["orderEndYm"] = f"{end.year + 1}12"
    payload = await client.get_json(path, params=params)
    return _items(payload)


def map_item(doc_type: DocType, item: dict[str, Any]) -> RawRecord | None:
    """Map one provider item to a :class:`RawRecord`. Returns ``None`` for unusable rows."""
    if doc_type == "order_plan":
        ext = pick(item, "orderPlanUntyNo", "orderPlanNo")
        title = pick(item, "bizNm", "prdctClsfcNoNm", "cnstwkNm")
        published = parse_compact_date(pick(item, "nticeDt", "rgstDt", "chgDt"))
        amount = _amount(item, "sumOrderAmt", "orderAmt", "asignBdgtAmt")
        structured = {
            "order_plan_no": ext,
            "amount_krw": amount,
            "order_year": parse_int(pick(item, "orderYear")),
            "order_month": parse_int(pick(item, "orderMnth")),
            # 72% of live plans (2026-09-26) already name the 공고 they became.
            "bid_notice_nos": _bid_numbers(pick(item, "bidNtceNoList")),
            "contract_method": pick(item, "cntrctMthdNm"),
            "department": pick(item, "deptNm", "orderInsttDeptNm"),
            "contact": pick(item, "ofclNm"),
            "phone": pick(item, "telNo", "ofclTelNo"),
        }
        publisher = pick(item, "orderInsttNm", "dminsttNm")
        inst_code = pick(item, "orderInsttCd", "dminsttCd")
    elif doc_type == "prespec":
        ext = pick(item, "bfSpecRgstNo")
        title = pick(item, "prdctClsfcNoNm", "bfSpecNm", "bizNm")
        published = parse_compact_date(pick(item, "rcptDt", "rgstDt"))
        amount = _amount(item, "asignBdgtAmt")
        structured = {
            "prespec_no": ext,
            "amount_krw": amount,
            "opinion_deadline": str(pick(item, "opninRgstClseDt") or "") or None,
            "order_plan_no": pick(item, "orderPlanUntyNo"),
            "bid_notice_nos": _bid_numbers(pick(item, "bidNtceNoList")),
            "spec_url": pick(item, "specDocFileUrl1"),
            "department": pick(item, "orderInsttDeptNm"),
        }
        publisher = pick(item, "rlDminsttNm", "orderInsttNm")
        inst_code = pick(item, "rlDminsttCd", "orderInsttCd")
    elif doc_type == "bid_notice":
        no = pick(item, "bidNtceNo")
        ord_ = pick(item, "bidNtceOrd") or "000"
        ext = f"{no}-{ord_}" if no else None
        title = pick(item, "bidNtceNm")
        published = parse_compact_date(pick(item, "bidNtceDt", "rgstDt"))
        # 용역·물품 send 배정예산 as asignBdgtAmt, 공사 as bdgtAmt (live 2026-09-26: 999/999 공사
        # rows had only bdgtAmt); presmptPrce (추정가격) excludes VAT, so it is the last resort.
        amount = _amount(item, "asignBdgtAmt", "bdgtAmt", "presmptPrce")
        structured = {
            "bid_notice_no": no,
            "bid_notice_ord": ord_,
            "amount_krw": amount,
            "estimated_price": _amount(item, "presmptPrce"),
            "bid_close_at": str(pick(item, "bidClseDt") or "") or None,
            "prespec_no": pick(item, "bfSpecRgstNo"),
            "order_plan_no": pick(item, "orderPlanUntyNo"),
            "contract_method": pick(item, "cntrctCnclsMthdNm"),
            "detail_url": pick(item, "bidNtceDtlUrl"),
        }
        publisher = pick(item, "dminsttNm", "ntceInsttNm")
        inst_code = pick(item, "dminsttCd", "ntceInsttCd")
    else:  # pragma: no cover - adapters only emit the three types above
        return None
    if not ext or not title or not published:
        return None
    return RawRecord(
        external_id=str(ext),
        doc_type=doc_type,
        title=str(title).strip(),
        published_at=published,
        mime="application/json",
        publisher_raw=str(publisher) if publisher else None,
        provider_institution_code=str(inst_code) if inst_code else None,
        url=structured.get("detail_url") or structured.get("spec_url"),
        structured={k: v for k, v in structured.items() if v not in (None, "", [])}
        | {"provider_institution_code": inst_code, "raw": item},
    )


@dataclass(slots=True)
class PathStats:
    """Per operation (업무구분) counts for one fetch, for ingest reports."""

    pages: int = 0
    items: int = 0
    mapped: int = 0
    total: int = 0  # sum of totalCount over the window's slices
    seconds: float = 0.0
    dropped_keys: list[list[str]] = field(default_factory=list)  # field names of unusable items


class G2BAdapter:
    def __init__(
        self, key: str, client: ResilientClient, service_key: str, *, rows: int = 100
    ) -> None:
        if key not in OPERATIONS:
            raise ValueError(f"unknown g2b operation {key}")
        self.key = key
        self.doc_type = OPERATIONS[key].doc_type
        self._op = OPERATIONS[key]
        self.client = client
        self._service_key = normalize_service_key(service_key)
        # Items per call. The services accept up to 999; a 30-day backfill of 입찰공고 is
        # ~20,000 rows, i.e. ~200 calls at 100 but ~25 at 999 (dev keys get 1,000 a day).
        self.rows = rows
        self.path_stats: dict[str, PathStats] = {p: PathStats() for p in self._op.paths}

    async def aclose(self) -> None:
        await self.client.aclose()

    async def fetch(self, window: FetchWindow) -> AsyncIterator[RawRecord]:
        start = window.since
        while start <= window.until:
            end = min(start + timedelta(days=self._op.window_days - 1), window.until)
            for path in self._op.paths:
                async for rec in self._fetch_slice(path, start, end):
                    yield rec
            start = end + timedelta(days=1)

    async def _fetch_slice(self, path: str, start: date, end: date) -> AsyncIterator[RawRecord]:
        page = 1
        rows = self.rows
        stats = self.path_stats[path]
        while True:
            started = time.perf_counter()
            items, total = await fetch_page(
                self.client, self._service_key, path, start, end, page=page, rows=rows
            )
            stats.seconds += time.perf_counter() - started
            stats.pages += 1
            stats.items += len(items)
            if page == 1:
                stats.total += total
            for item in items:
                rec = map_item(self.doc_type, item)
                if rec is None:
                    if len(stats.dropped_keys) < 3:
                        stats.dropped_keys.append(sorted(k for k, v in item.items() if v))
                    continue
                stats.mapped += 1
                yield rec
            if page * rows >= total or not items:
                break
            page += 1
