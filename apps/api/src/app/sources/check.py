"""First contact with the real 조달청 APIs: one page per operation, checked field by field.

The G2B adapter's paths and field names were written from the published specs and tested
against contract fixtures, never against the live service. ``manage sources check`` calls each
of the nine operations once for a recent window and reports, per operation:

* whether the call worked, and the provider's own error if not (bad key, service not applied
  for, quota) — the key is masked in anything printed;
* how many items came back and how many the adapter could turn into records (an item without
  id, title or date is dropped — a renamed field shows up here as a gap, not as silence);
* how often the fields that linking and ranking rely on are filled (amount, 발주계획번호 on
  사전규격, 사전규격번호 on 입찰공고, …);
* when items were dropped, the keys the provider actually sent, so a rename can be fixed in
  ``g2b.map_item`` without guessing.

It reads nothing from and writes nothing to the database.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import asdict, dataclass, field
from datetime import timedelta
from typing import Any
from urllib.parse import quote, quote_plus

import httpx

from app.clock import today_kst
from app.log import redact_secrets
from app.sources import g2b
from app.sources.base import DocType
from app.sources.http import ResilientClient
from app.sources.resilience import MemoryBreaker, MemoryLimiter

# structured keys produced by g2b.map_item that downstream steps depend on
COVERAGE: dict[DocType, tuple[str, ...]] = {
    "order_plan": ("amount_krw", "order_year", "order_month", "department"),
    "prespec": ("amount_krw", "order_plan_no", "bid_notice_nos", "opinion_deadline"),
    "bid_notice": ("amount_krw", "prespec_no", "order_plan_no", "bid_close_at"),
}


@dataclass(slots=True)
class OperationCheck:
    source: str
    path: str
    ok: bool = False
    error: str | None = None
    total: int | None = None
    items: int = 0
    mapped: int = 0
    publisher: float | None = None
    coverage: dict[str, float | None] = field(default_factory=dict)
    dropped_item_keys: list[str] = field(default_factory=list)
    sample: dict[str, Any] | None = None
    latency_ms: int = 0


def _mask(text: str, secret: str) -> str:
    for form in {secret, quote(secret, safe=""), quote_plus(secret)}:
        if form:
            text = text.replace(form, "***")
    return redact_secrets(text)


def _share(n: int, d: int) -> float | None:
    return round(n / d, 3) if d else None


async def check_g2b(
    service_key: str,
    *,
    sources: list[str] | None = None,
    days: int = 7,
    rows: int = 20,
    concurrency: int = 3,
    transport: httpx.AsyncBaseTransport | None = None,
) -> list[OperationCheck]:
    unknown = sorted(set(sources or ()) - set(g2b.OPERATIONS))
    if unknown:
        raise ValueError(f"unknown source {', '.join(unknown)}; one of {', '.join(g2b.OPERATIONS)}")
    until = today_kst()
    since = until - timedelta(days=days - 1)
    key = g2b.normalize_service_key(service_key)
    breaker, limiter = MemoryBreaker(), MemoryLimiter()
    sem = asyncio.Semaphore(concurrency)

    async def one(source: str, doc_type: DocType, path: str) -> OperationCheck:
        check = OperationCheck(source, path)
        client = ResilientClient(
            f"g2b-check:{path.rsplit('/', 1)[-1]}",  # breaker state per operation
            base_url=g2b.BASE_URL,
            limiter=limiter,
            breaker=breaker,
            max_attempts=3,  # apis.data.go.kr resets some TLS handshakes; don't call that a key problem
            transport=transport,
        )
        started = time.perf_counter()
        try:
            async with sem:
                items, total = await g2b.fetch_page(client, key, path, since, until, rows=rows)
        except Exception as exc:  # report every failure mode, never the key
            text = _mask(_mask(f"{type(exc).__name__}: {exc}", service_key), key)
            check.error = text[:500]
        else:
            _inspect(check, doc_type, items, total)
        finally:
            await client.aclose()
        check.latency_ms = int((time.perf_counter() - started) * 1000)
        return check

    return list(
        await asyncio.gather(
            *(
                one(source, op.doc_type, path)
                for source, op in g2b.OPERATIONS.items()
                if not sources or source in sources
                for path in op.paths
            )
        )
    )


def problems(checks: list[OperationCheck]) -> list[str]:
    """What should make the command exit non-zero: failed calls, and operations that returned
    items none of which could be read (the field-rename case)."""
    out = [f"{c.path}: {c.error}" for c in checks if not c.ok]
    out += [
        f"{c.path}: {c.items} items, none mapped"
        for c in checks
        if c.ok and c.items and not c.mapped
    ]
    return out


def _inspect(
    check: OperationCheck, doc_type: DocType, items: list[dict[str, Any]], total: int
) -> None:
    check.ok = True
    check.total, check.items = total, len(items)
    records = []
    for item in items:
        rec = g2b.map_item(doc_type, item)
        if rec is not None:
            records.append(rec)
        elif not check.dropped_item_keys:
            check.dropped_item_keys = sorted(item)
    check.mapped = len(records)
    check.publisher = _share(sum(bool(r.publisher_raw) for r in records), len(records))
    check.coverage = {
        k: _share(sum(k in r.structured for r in records), len(records)) for k in COVERAGE[doc_type]
    }
    if records:
        r = records[0]
        check.sample = {
            "id": r.external_id,
            "title": r.title,
            "published": r.published_at.isoformat(),
            "publisher": r.publisher_raw,
            "amount_krw": r.structured.get("amount_krw"),
        }


# 공공데이터포털 lists each service separately and a key works only for services applied for.
PORTAL_SERVICES = {
    "OrderPlanSttusService": (
        "조달청_나라장터 발주계획현황서비스",
        "https://www.data.go.kr/data/15129462/openapi.do",
    ),
    "HrcspSsstndrdInfoService": (
        "조달청_나라장터 사전규격정보서비스",
        "https://www.data.go.kr/data/15129437/openapi.do",
    ),
    "BidPublicInfoService": (
        "조달청_나라장터 입찰공고정보서비스",
        "https://www.data.go.kr/data/15129394/openapi.do",
    ),
}


def _service(path: str) -> str:
    return path.rstrip("/").split("/")[-2]


def unregistered_services(checks: list[OperationCheck]) -> list[str]:
    """Services whose calls failed with code 30 — the key was not applied for (or approval
    has not reached the gateway yet)."""
    return sorted(
        {
            _service(c.path)
            for c in checks
            if not c.ok and "SERVICE_KEY_IS_NOT_REGISTERED_ERROR" in (c.error or "")
        }
    )


_LABEL = {
    "amount_krw": "금액",
    "order_year": "발주연도",
    "order_month": "발주월",
    "department": "부서",
    "order_plan_no": "발주계획번호",
    "bid_notice_nos": "공고번호 목록",
    "opinion_deadline": "의견마감",
    "prespec_no": "사전규격번호",
    "bid_close_at": "입찰마감",
}


def _cell(text: str) -> str:
    return " ".join(text.split()).replace("|", "\\|")


def _pct(v: float | None) -> str:
    return "–" if v is None else f"{v * 100:.0f}%"


def render(checks: list[OperationCheck], *, days: int) -> str:
    lines = [
        "# 조달청 API 실호출 점검 (자동 생성: `manage sources check`)",
        "",
        f"기준일 {today_kst().isoformat()} · 최근 {days}일 · 오퍼레이션마다 첫 페이지 1회 호출",
        "",
        "| 수집원 | 오퍼레이션 | 결과 | 전체 건수 | 받은 항목 | 레코드로 변환 | 기관명 | 연결·랭킹 필드 채움 비율 |",
        "|---|---|---|---:|---:|---:|---:|---|",
    ]
    for c in checks:
        op = c.path.rsplit("/", 1)[-1]
        result = "성공" if c.ok else f"실패: {_cell(c.error or '')}"
        cov = ", ".join(f"{_LABEL.get(k, k)} {_pct(v)}" for k, v in c.coverage.items()) or "–"
        lines.append(
            f"| `{c.source}` | `{op}` | {result} | {c.total if c.total is not None else '–'} | "
            f"{c.items} | {c.mapped} | {_pct(c.publisher)} | {cov} |"
        )
    if unregistered := unregistered_services(checks):
        lines += [
            "",
            "## 활용신청이 필요한 서비스",
            "",
            "오류 30(`SERVICE_KEY_IS_NOT_REGISTERED_ERROR`)은 이 키로 그 서비스를 활용신청하지 "
            "않았거나, 승인이 아직 게이트웨이에 반영되지 않았다는 뜻입니다. 공공데이터포털에서 "
            "서비스마다 신청한 뒤(개발계정은 보통 자동승인, 반영까지 1~2시간) 다시 점검합니다.",
            "",
        ]
        for svc in unregistered:
            name, url = PORTAL_SERVICES.get(svc, (svc, ""))
            lines.append(f"- [{name}]({url}) (`{svc}`)" if url else f"- `{svc}`")
    dropped = [c for c in checks if c.dropped_item_keys]
    if dropped:
        lines += [
            "",
            "## 버려진 항목의 실제 필드",
            "",
            "id·제목·날짜 중 하나를 찾지 못해 레코드로 만들지 못한 항목입니다. 필드명이 바뀌었다면 "
            "`apps/api/src/app/sources/g2b.py`의 `map_item`에 새 이름을 추가합니다.",
            "",
        ]
        for c in dropped:
            lines.append(f"- `{c.path}`: {', '.join(f'`{k}`' for k in c.dropped_item_keys)}")
    samples = [c for c in checks if c.sample]
    if samples:
        lines += ["", "## 예시 레코드 (오퍼레이션별 첫 건)", ""]
        for c in samples:
            s = c.sample or {}
            amount = f"{s['amount_krw']:,}원" if s.get("amount_krw") is not None else "금액 없음"
            lines.append(
                f"- `{c.path.rsplit('/', 1)[-1]}` {s['published']} · "
                f"{_cell(s['publisher'] or '기관 미상')} · {_cell(s['title'])} · {amount}"
            )
    return "\n".join(lines) + "\n"


def as_json(checks: list[OperationCheck]) -> list[dict[str, Any]]:
    return [asdict(c) for c in checks]
