"""Board crawler — 지자체 누리집 게시판에서 첨부 문서(예산서·사업설명서 등)를 수집합니다.

지방재정365가 법정 예산서를 모아 주지만, 추경 예산서·사업설명서·기본계획처럼 기관 누리집의
"예산 공개" / "고시·공고" 게시판에 HWP·PDF 첨부로만 먼저 올라오는 문서가 많고, 여기에는 API가
없습니다. 이 어댑터는 게시판 목록 → 상세 → 첨부를 따라가며 문서를 가져옵니다.

A crawler that gets blocked collects nothing, so politeness is part of correctness:

* **robots.txt** is fetched once per host per run and obeyed (RFC 9309: a 4xx means no rules,
  a 5xx or unreachable robots.txt means "disallow everything" for this run).
* **Rate**: every request goes through the shared token bucket keyed per host
  (``<source>@<host>``), so several workers never add up to a burst; on top of that each host
  gets a minimum delay between requests (``delay_seconds``, default 1s).
* **Incremental**: boards list newest first; paging stops at the first page whose oldest row
  predates the fetch window (the ingest cursor keeps a 3-day overlap for late posts).
* **Untrusted files**: attachments are capped (``max_file_mb``) while streaming, and the type is
  decided by magic bytes, not by the server's Content-Type or the file name.

Boards differ in markup but almost all are a table (or list) of rows with a title link and a
date. The parser keys on that shape plus two URL patterns from the source config, so adding a
government is configuration, not code::

    {"boards": [{"url": "https://www.gangnam.go.kr/board/B_000052/list.do",
                 "institution_code": "LG-11680", "publisher": "서울특별시 강남구"}],
     "doc_type": "budget_book", "title_keywords": ["예산서", "사업명세서"],
     "detail_pattern": "view\\.do", "attachment_pattern": "download|fileDown|atchFile",
     "id_param": "nttId", "page_param": "pageIndex", "max_pages": 20}
"""

from __future__ import annotations

import asyncio
import re
import time
import urllib.robotparser
from collections.abc import AsyncIterator, Callable
from dataclasses import asdict, dataclass, field
from datetime import date
from html.parser import HTMLParser
from typing import Any
from urllib.parse import parse_qs, urlencode, urljoin, urlsplit, urlunsplit

from app.log import get_logger
from app.sources.base import DocType, FetchWindow, RawRecord
from app.sources.http import (
    FatalSourceError,
    ResilientClient,
    ResponseTooLargeError,
    TransientSourceError,
)

log = get_logger(__name__)

USER_AGENT = "procurement-forecast-collector"

_DATE_RE = re.compile(r"(20\d{2})[.\-/년]\s*(\d{1,2})[.\-/월]\s*(\d{1,2})")
_FISCAL_YEAR_RE = re.compile(r"(20\d{2})\s*년도")
_DOC_EXT_RE = re.compile(r"\.(pdf|hwp|hwpx)\s*$", re.IGNORECASE)


# ------------------------------------------------------------------------------------------------
# HTML parsing
# ------------------------------------------------------------------------------------------------
@dataclass(slots=True)
class Link:
    href: str
    text: str


@dataclass(slots=True)
class BoardRow:
    title: str
    url: str
    posted: date | None


@dataclass(slots=True)
class _Row:
    texts: list[str] = field(default_factory=list)
    links: list[Link] = field(default_factory=list)


class _RowCollector(HTMLParser):
    """Collects table rows (or list items when the board has no table) with their links."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[_Row] = []
        self.links: list[Link] = []
        self._row: _Row | None = None
        self._row_tag: str | None = None
        self._href: str | None = None
        self._link_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ("tr", "li") and self._row is None:
            self._row, self._row_tag = _Row(), tag
        elif tag == "a":
            self._href = dict(attrs).get("href") or None
            self._link_text = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._href is not None:
            link = Link(self._href, " ".join("".join(self._link_text).split()))
            self.links.append(link)
            if self._row is not None:
                self._row.links.append(link)
            self._href = None
        elif tag == self._row_tag and self._row is not None:
            self.rows.append(self._row)
            self._row, self._row_tag = None, None

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._link_text.append(data)
        if self._row is not None and data.strip():
            self._row.texts.append(data.strip())


def parse_date(text: str) -> date | None:
    m = _DATE_RE.search(text)
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def parse_board_rows(html: str, base_url: str, detail_pattern: str) -> list[BoardRow]:
    """Rows that link to a post: title = link text, date = first date in the row."""
    parser = _RowCollector()
    parser.feed(html)
    detail_re = re.compile(detail_pattern)
    rows: list[BoardRow] = []
    for row in parser.rows:
        link = next((ln for ln in row.links if detail_re.search(ln.href) and ln.text), None)
        if link is None:
            continue
        rows.append(
            BoardRow(
                title=link.text,
                url=urljoin(base_url, link.href),
                posted=parse_date(" ".join(row.texts)),
            )
        )
    return rows


def parse_attachments(html: str, base_url: str, attachment_pattern: str) -> list[Link]:
    """Links that look like file downloads (by URL pattern or by a document file name)."""
    parser = _RowCollector()
    parser.feed(html)
    attach_re = re.compile(attachment_pattern)
    seen: set[str] = set()
    found: list[Link] = []
    for link in parser.links:
        if not (attach_re.search(link.href) or _DOC_EXT_RE.search(link.text)):
            continue
        url = urljoin(base_url, link.href)
        if url not in seen:
            seen.add(url)
            found.append(Link(url, link.text))
    return found


def sniff_mime(content: bytes) -> str | None:
    """Decide the document type from the bytes; ``None`` for anything we can't parse."""
    if content[:5] == b"%PDF-":
        return "application/pdf"
    if content[:8] == bytes.fromhex("D0CF11E0A1B11AE1"):  # OLE2 compound file → HWP 5.x
        return "application/x-hwp"
    head = content[:65_536]
    if head[:4] == b"PK\x03\x04" and (b"Contents/section" in head or b"hwp+zip" in head):
        return "application/hwp+zip"  # HWPX (OWPML in a zip)
    return None


def budget_title_facts(title: str) -> dict[str, Any]:
    """ "2027년도 서울특별시 강남구 제1회 추가경정예산서" → fiscal year and 본/추경."""
    facts: dict[str, Any] = {}
    if m := _FISCAL_YEAR_RE.search(title):
        facts["fiscal_year"] = int(m.group(1))
    if "추가경정" in title or "추경" in title:
        facts["budget_kind"] = "제1회 추가경정" if "제1회" in title else "추가경정"
    elif "본예산" in title or "예산서" in title:
        facts["budget_kind"] = "본"
    return facts


def canonical_url(url: str, keep: tuple[str, ...]) -> str:
    """Drop session/tracking parameters so the same post always has the same URL."""
    parts = urlsplit(url)
    query = {k: v for k, v in parse_qs(parts.query).items() if k in keep}
    return urlunsplit(
        (parts.scheme, parts.netloc.lower(), parts.path, urlencode(query, doseq=True), "")
    )


# ------------------------------------------------------------------------------------------------
# Adapter
# ------------------------------------------------------------------------------------------------
@dataclass(slots=True)
class Board:
    url: str
    institution_code: str | None = None
    publisher: str | None = None


@dataclass(slots=True)
class CrawlStats:
    pages: int = 0
    posts: int = 0
    files: int = 0
    skipped_robots: int = 0
    skipped_type: int = 0
    skipped_size: int = 0
    skipped_title: int = 0


class _HostThrottle:
    """Minimum spacing between requests to one host, within this process."""

    def __init__(self, delay: float, clock: Callable[[], float] = time.monotonic) -> None:
        self._delay = delay
        self._clock = clock
        self._last: dict[str, float] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    async def wait(self, host: str) -> None:
        if self._delay <= 0:
            return
        lock = self._locks.setdefault(host, asyncio.Lock())
        async with lock:
            gap = self._last.get(host, float("-inf")) + self._delay - self._clock()
            if gap > 0:
                await asyncio.sleep(gap)
            self._last[host] = self._clock()


class BoardCrawlerAdapter:
    def __init__(
        self,
        key: str,
        config: dict[str, Any],
        client_for_host: Callable[[str], ResilientClient],
    ) -> None:
        self.key = key
        self.doc_type: DocType = config.get("doc_type", "budget_book")
        self.boards = [Board(**b) for b in config.get("boards", [])]
        self.title_keywords: list[str] = config.get("title_keywords", ["예산서", "사업명세서"])
        self.detail_pattern: str = config.get("detail_pattern", r"view\.do")
        self.attachment_pattern: str = config.get(
            "attachment_pattern", r"download|fileDown|atchFile"
        )
        self.id_param: str = config.get("id_param", "nttId")
        self.page_param: str = config.get("page_param", "pageIndex")
        self.max_pages: int = int(config.get("max_pages", 20))
        self.max_bytes: int = int(float(config.get("max_file_mb", 50)) * 1024 * 1024)
        self.extra_structured: dict[str, Any] = config.get("structured", {})
        self.stats = CrawlStats()
        self._client_for_host = client_for_host
        self._clients: dict[str, ResilientClient] = {}
        self._robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}
        self._throttle = _HostThrottle(float(config.get("delay_seconds", 1.0)))

    async def aclose(self) -> None:
        for client in self._clients.values():
            await client.aclose()

    # -- HTTP ------------------------------------------------------------------------------------
    def _client(self, host: str) -> ResilientClient:
        if host not in self._clients:
            self._clients[host] = self._client_for_host(host)
        return self._clients[host]

    async def _get(self, url: str, *, max_bytes: int | None = None) -> bytes:
        host = urlsplit(url).netloc.lower()
        await self._throttle.wait(host)
        resp = await self._client(host).request("GET", url, soft_errors=False, max_bytes=max_bytes)
        return resp.content

    async def _allowed(self, url: str) -> bool:
        parts = urlsplit(url)
        host = parts.netloc.lower()
        if host not in self._robots:
            robots_url = urlunsplit((parts.scheme, parts.netloc, "/robots.txt", "", ""))
            parser: urllib.robotparser.RobotFileParser | None = urllib.robotparser.RobotFileParser()
            try:
                body = await self._get(robots_url, max_bytes=512 * 1024)
                assert parser is not None
                parser.parse(body.decode("utf-8", errors="replace").splitlines())
            except FatalSourceError as exc:
                if exc.status is not None and 400 <= exc.status < 500:
                    assert parser is not None
                    parser.parse([])  # no robots.txt → no restrictions
                else:
                    parser = None
            except (TransientSourceError, ResponseTooLargeError):
                parser = None  # unreachable → treat the whole host as disallowed this run
            self._robots[host] = parser
        rules = self._robots[host]
        return rules is not None and rules.can_fetch(USER_AGENT, url)

    # -- crawl -----------------------------------------------------------------------------------
    def _page_url(self, board: Board, page: int) -> str:
        parts = urlsplit(board.url)
        query = parse_qs(parts.query)
        query[self.page_param] = [str(page)]
        return urlunsplit(
            (parts.scheme, parts.netloc, parts.path, urlencode(query, doseq=True), "")
        )

    def _wanted(self, title: str) -> bool:
        return not self.title_keywords or any(k in title for k in self.title_keywords)

    async def fetch(self, window: FetchWindow) -> AsyncIterator[RawRecord]:
        for board in self.boards:
            async for rec in self._crawl_board(board, window):
                yield rec
        log.info("crawler.finished", source=self.key, **asdict(self.stats))

    async def _crawl_board(self, board: Board, window: FetchWindow) -> AsyncIterator[RawRecord]:
        seen: set[str] = set()
        for page in range(1, self.max_pages + 1):
            url = self._page_url(board, page)
            if not await self._allowed(url):
                self.stats.skipped_robots += 1
                return
            html = (await self._get(url)).decode("utf-8", errors="replace")
            self.stats.pages += 1
            rows = parse_board_rows(html, url, self.detail_pattern)
            fresh = [r for r in rows if r.url not in seen]
            if not fresh:
                return  # past the last page (many boards repeat the last page)
            for row in fresh:
                seen.add(row.url)
                if row.posted is None or not (window.since <= row.posted <= window.until):
                    continue
                if not self._wanted(row.title):
                    self.stats.skipped_title += 1
                    continue
                async for rec in self._crawl_post(board, row):
                    yield rec
            dated = [r.posted for r in fresh if r.posted is not None]
            if dated and min(dated) < window.since:
                return  # newest-first board: everything further back is older still

    async def _crawl_post(self, board: Board, row: BoardRow) -> AsyncIterator[RawRecord]:
        if not await self._allowed(row.url):
            self.stats.skipped_robots += 1
            return
        self.stats.posts += 1
        html = (await self._get(row.url)).decode("utf-8", errors="replace")
        post_url = canonical_url(row.url, (self.id_param,))
        post_id = parse_qs(urlsplit(post_url).query).get(self.id_param, [post_url])[0]
        docs: list[tuple[Link, bytes, str]] = []
        for att in parse_attachments(html, row.url, self.attachment_pattern):
            if not await self._allowed(att.href):
                self.stats.skipped_robots += 1
                continue
            try:
                content = await self._get(att.href, max_bytes=self.max_bytes)
            except ResponseTooLargeError:
                self.stats.skipped_size += 1
                log.warning("crawler.file_too_large", url=att.href)
                continue
            mime = sniff_mime(content)
            if mime is None:
                self.stats.skipped_type += 1
                continue
            docs.append((att, content, mime))
        for i, (att, content, mime) in enumerate(docs, start=1):
            self.stats.files += 1
            assert row.posted is not None
            yield RawRecord(
                external_id=post_id if len(docs) == 1 else f"{post_id}-{i}",
                doc_type=self.doc_type,
                title=row.title,
                published_at=row.posted,
                mime=mime,
                publisher_raw=board.publisher,
                institution_code_hint=board.institution_code,
                url=post_url,
                content=content,
                structured={
                    **(budget_title_facts(row.title) if self.doc_type == "budget_book" else {}),
                    "file_name": att.text,
                    "file_url": att.href,
                    "board_url": board.url,
                    **self.extra_structured,
                },
            )
