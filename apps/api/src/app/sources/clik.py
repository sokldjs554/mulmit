"""국회도서관 지방의정포털(CLIK) Open API — local council minutes.

Minutes are the earliest public trace of most municipal purchases: a council member asks, a
department head answers "내년도 본예산에 반영하겠습니다", and 6–18 months later a tender appears.

Constraints that shape this adapter:

* 1,000 calls/day per key and ≤100 rows per call → the list call pages by meeting date and the
  detail (full transcript) call is only made for minutes we have not stored yet.
* Transcripts come as HTML fragments with ``<br>`` line breaks and speaker markers (○ / ◯).
  We convert to text here and keep speaker lines intact for ``parsing/chunking.py``, which
  splits minutes into question/answer exchanges.

Endpoint paths and field names live in ``DEFAULTS`` and can be overridden per source row
(``sources.config``) — they follow the portal's published guide and were not verified live from
the dev container (no egress to clik.nanet.go.kr); see docs/data-sources.md.
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator
from html.parser import HTMLParser
from typing import Any

from app.sources.base import DocType, FetchWindow, RawRecord, parse_compact_date, pick
from app.sources.http import ResilientClient

BASE_URL = "https://clik.nanet.go.kr"

DEFAULTS: dict[str, Any] = {
    "list_path": "/openapi/minutes.do",
    "detail_path": "/openapi/minutes.do",
    "page_size": 100,
    "id_fields": ["MINTS_ID", "DOCID", "minutesId", "id"],
    "title_fields": ["MTGNM", "MTG_NM", "TITLE", "title"],
    "council_fields": ["RASMBLY_NM", "rasmblyNm", "COUNCIL_NM"],
    "date_fields": ["MTG_DE", "MTGDT", "MEETING_DATE", "meetingDate"],
    "body_fields": ["MINTS_HTML", "CONTENT", "MINTS_CN", "content"],
    "url_fields": ["DETAIL_URL", "URL", "url"],
}


class _TextExtractor(HTMLParser):
    _BREAKS = frozenset({"br", "p", "div", "tr", "li", "h1", "h2", "h3", "h4"})

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self._BREAKS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self._BREAKS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def html_to_text(html: str) -> str:
    parser = _TextExtractor()
    parser.feed(html)
    text = "".join(parser.parts)
    text = re.sub(r"[ \t ]+", " ", text)
    return re.sub(r"\n\s*\n+", "\n", text).strip()


class ClikMinutesAdapter:
    doc_type: DocType = "council_minutes"

    def __init__(
        self,
        client: ResilientClient,
        api_key: str,
        *,
        key: str = "clik_minutes",
        council_ids: list[str] | None = None,
        overrides: dict[str, Any] | None = None,
    ) -> None:
        self.key = key
        self._client = client
        self._api_key = api_key
        self._councils = council_ids or [""]
        self._cfg = DEFAULTS | (overrides or {})

    async def aclose(self) -> None:
        await self._client.aclose()

    async def fetch(self, window: FetchWindow) -> AsyncIterator[RawRecord]:
        for council in self._councils:
            start = 0
            while True:
                params: dict[str, Any] = {
                    "key": self._api_key,
                    "type": "json",
                    "displayType": "list",
                    "startCount": start,
                    "listCount": self._cfg["page_size"],
                    "searchType": "ALL",
                    "startDate": window.since.strftime("%Y%m%d"),
                    "endDate": window.until.strftime("%Y%m%d"),
                }
                if council:
                    params["rasmblyId"] = council
                payload = await self._client.get_json(self._cfg["list_path"], params=params)
                rows = self._rows(payload)
                for row in rows:
                    rec = await self._detail(row)
                    if rec is not None:
                        yield rec
                if len(rows) < self._cfg["page_size"]:
                    break
                start += self._cfg["page_size"]

    @staticmethod
    def _rows(payload: Any) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            return [r for r in payload if isinstance(r, dict)]
        if isinstance(payload, dict):
            for key in ("LIST", "list", "items", "ROWS", "data"):
                value = payload.get(key)
                if isinstance(value, list):
                    return [r for r in value if isinstance(r, dict)]
                if isinstance(value, dict):
                    return ClikMinutesAdapter._rows(value)
        return []

    async def _detail(self, row: dict[str, Any]) -> RawRecord | None:
        cfg = self._cfg
        ext = pick(row, *cfg["id_fields"])
        meeting_date = parse_compact_date(pick(row, *cfg["date_fields"]))
        if not ext or not meeting_date:
            return None
        body = pick(row, *cfg["body_fields"])
        if not body:
            detail = await self._client.get_json(
                cfg["detail_path"],
                params={
                    "key": self._api_key,
                    "type": "json",
                    "displayType": "detail",
                    "docid": ext,
                },
            )
            rows = self._rows(detail) or ([detail] if isinstance(detail, dict) else [])
            body = pick(rows[0], *cfg["body_fields"]) if rows else None
        if not body:
            return None
        text = html_to_text(str(body)) if "<" in str(body) else str(body)
        council = pick(row, *cfg["council_fields"])
        title = pick(row, *cfg["title_fields"]) or f"{council or ''} 회의록"
        return RawRecord(
            external_id=str(ext),
            doc_type="council_minutes",
            title=str(title),
            published_at=meeting_date,
            mime="text/plain; charset=utf-8",
            publisher_raw=str(council) if council else None,
            url=pick(row, *cfg["url_fields"]),
            content=text.encode("utf-8"),
            structured={"meeting_date": meeting_date.isoformat(), "council": council},
        )
