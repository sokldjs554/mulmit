"""행정안전부 지방재정365 — 우리 지자체 예산서 (links to each government's budget book).

Budget books are published as large PDF (sometimes scanned) or HWP files, one per 회계연도 and
per 본예산/추경. The listing API returns metadata and a file URL; we download the file and let
``parsing/`` decide between the PDF text layer, OCR, or the HWP reader.

Field names are configurable (see ``DEFAULTS``); the dev container could not reach
lofin.mois.go.kr, so the mapping follows the published spec and contract fixtures.
"""

from __future__ import annotations

import mimetypes
from collections.abc import AsyncIterator
from datetime import date
from typing import Any

from mulmit.sources.base import (
    DocType,
    FetchWindow,
    RawRecord,
    parse_compact_date,
    parse_int,
    pick,
)
from mulmit.sources.http import ResilientClient

BASE_URL = "https://lofin.mois.go.kr"

DEFAULTS: dict[str, Any] = {
    "list_path": "/HUB/BGTBOOK",
    "institution_fields": ["laf_nm", "LAF_NM", "wa_nm", "institutionName"],
    "year_fields": ["fyr", "FYR", "accnut_year", "year"],
    "kind_fields": ["bgt_kind_nm", "BGT_KIND_NM", "budgetKind"],
    "url_fields": ["file_url", "FILE_URL", "link_url", "url"],
    "id_fields": ["bgtbook_id", "BGTBOOK_ID", "seq"],
    "published_fields": ["reg_dt", "REG_DT", "published"],
}


class LofinBudgetAdapter:
    doc_type: DocType = "budget_book"

    def __init__(
        self,
        client: ResilientClient,
        api_key: str,
        *,
        key: str = "lofin_budget",
        overrides: dict[str, Any] | None = None,
    ) -> None:
        self.key = key
        self._client = client
        self._api_key = api_key
        self._cfg = DEFAULTS | (overrides or {})

    async def aclose(self) -> None:
        await self._client.aclose()

    async def fetch(self, window: FetchWindow) -> AsyncIterator[RawRecord]:
        cfg = self._cfg
        for year in range(window.since.year, window.until.year + 2):  # next FY books appear in Dec
            page = 1
            while True:
                payload = await self._client.get_json(
                    cfg["list_path"],
                    params={
                        "Key": self._api_key,
                        "Type": "json",
                        "pIndex": page,
                        "pSize": 100,
                        "fyr": year,
                    },
                )
                rows = _rows(payload)
                for row in rows:
                    rec = await self._to_record(row, year)
                    if rec is not None and window.since <= rec.published_at <= window.until:
                        yield rec
                if len(rows) < 100:
                    break
                page += 1

    async def _to_record(self, row: dict[str, Any], year: int) -> RawRecord | None:
        cfg = self._cfg
        url = pick(row, *cfg["url_fields"])
        inst = pick(row, *cfg["institution_fields"])
        if not url or not inst:
            return None
        fy = parse_int(pick(row, *cfg["year_fields"])) or year
        kind = pick(row, *cfg["kind_fields"]) or "본예산"
        published_raw = pick(row, *cfg["published_fields"])
        published = parse_compact_date(published_raw) or date(fy - 1, 12, 20)
        content = await self._client.get_bytes(str(url))
        mime = mimetypes.guess_type(str(url))[0] or "application/pdf"
        if str(url).lower().endswith(".hwp"):
            mime = "application/x-hwp"
        ext = pick(row, *cfg["id_fields"]) or f"{inst}-{fy}-{kind}"
        return RawRecord(
            external_id=str(ext),
            doc_type="budget_book",
            title=f"{fy}년도 {inst} {kind} 예산서",
            published_at=published,
            mime=mime,
            publisher_raw=str(inst),
            url=str(url),
            content=content,
            structured={"fiscal_year": fy, "budget_kind": kind},
        )


def _rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        for value in payload.values():
            if isinstance(value, list):
                for part in value:
                    if isinstance(part, dict) and isinstance(part.get("row"), list):
                        return [r for r in part["row"] if isinstance(r, dict)]
                if value and all(isinstance(r, dict) for r in value):
                    return value
    return []
