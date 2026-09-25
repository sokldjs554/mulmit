from collections.abc import Callable
from datetime import date

import httpx
import pytest

from app.sources.base import FetchWindow
from app.sources.crawler import (
    BoardCrawlerAdapter,
    budget_title_facts,
    canonical_url,
    parse_attachments,
    parse_board_rows,
    sniff_mime,
)
from app.sources.http import ResilientClient
from app.sources.resilience import MemoryBreaker, MemoryLimiter

PDF = b"%PDF-1.7\n" + b"x" * 100
HWP5 = bytes.fromhex("D0CF11E0A1B11AE1") + b"\x00" * 100
HWPX = b"PK\x03\x04" + b"\x00" * 26 + b"mimetypeapplication/hwp+zip Contents/section0.xml"


def test_board_rows_take_title_link_and_row_date() -> None:
    html = """
    <table><thead><tr><th>번호</th><th>제목</th><th>등록일</th></tr></thead><tbody>
      <tr><td>12</td><td><a href="view.do?nttId=77&amp;menuNo=1">2027년도 강남구 본예산서</a></td>
          <td>2026.12.18</td></tr>
      <tr><td>11</td><td><a href="/other/list.do">게시판 이동</a></td><td>2026-12-01</td></tr>
    </tbody></table>"""
    rows = parse_board_rows(html, "https://gov.example/board/list.do", r"view\.do")
    assert len(rows) == 1
    assert rows[0].title == "2027년도 강남구 본예산서"
    assert rows[0].url == "https://gov.example/board/view.do?nttId=77&menuNo=1"
    assert rows[0].posted == date(2026, 12, 18)


def test_attachments_by_url_pattern_or_document_name_without_duplicates() -> None:
    html = """
      <a href="/cmm/fms/FileDown.do?atchFileId=A1&fileSn=0">예산서.hwp</a>
      <a href="/files/2027_budget.pdf">2027 예산서.pdf</a>
      <a href="/cmm/fms/FileDown.do?atchFileId=A1&fileSn=0">예산서.hwp (다시)</a>
      <a href="/board/list.do">목록</a>"""
    found = parse_attachments(html, "https://gov.example/board/view.do", r"FileDown|download")
    assert [a.href for a in found] == [
        "https://gov.example/cmm/fms/FileDown.do?atchFileId=A1&fileSn=0",
        "https://gov.example/files/2027_budget.pdf",
    ]


def test_type_comes_from_bytes_not_names() -> None:
    assert sniff_mime(PDF) == "application/pdf"
    assert sniff_mime(HWP5) == "application/x-hwp"
    assert sniff_mime(HWPX) == "application/hwp+zip"
    assert sniff_mime(b"\x89PNG\r\n\x1a\n") is None
    assert (
        sniff_mime("<html>로그인이 필요합니다</html>".encode()) is None
    )  # error page saved as .pdf


def test_budget_title_facts_and_canonical_urls() -> None:
    assert budget_title_facts("2027년도 서울특별시 강남구 제1회 추가경정예산서") == {
        "fiscal_year": 2027,
        "budget_kind": "제1회 추가경정",
    }
    assert budget_title_facts("2027년도 본예산서")["budget_kind"] == "본"
    assert (
        canonical_url("https://Gov.Example/view.do?nttId=7&jsessionid=X&menuNo=3#top", ("nttId",))
        == "https://gov.example/view.do?nttId=7"
    )


# -- the adapter against a small fake site ------------------------------------------------------
def _site(
    *,
    robots: httpx.Response | None = None,
    posts: int = 12,
    big_file: bool = False,
) -> Callable[[httpx.Request], httpx.Response]:
    """Newest-first board, 5 rows per page, one budget book per post (day i of Jan 2026)."""
    items = [(f"P{i}", f"2026년도 예산서 {i}", date(2026, 1, i)) for i in range(posts, 0, -1)]

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        params = request.url.params
        if path == "/robots.txt":
            return robots or httpx.Response(200, text="User-agent: *\nDisallow: /secret/\n")
        if path == "/list.do":
            page = int(params.get("pageIndex", "1"))
            chunk = items[(page - 1) * 5 : page * 5]
            rows = "".join(
                f'<tr><td><a href="view.do?nttId={n}">{t}</a></td><td>{d:%Y-%m-%d}</td></tr>'
                for n, t, d in chunk
            )
            return httpx.Response(200, text=f"<table>{rows}</table>")
        if path == "/view.do":
            n = params["nttId"]
            return httpx.Response(200, text=f'<a href="/download.do?id={n}">{n}.pdf</a>')
        if path == "/download.do":
            body = PDF + (b"y" * 3 * 1024 * 1024 if big_file else b"")
            return httpx.Response(200, content=body)
        return httpx.Response(404)

    return handler


def _adapter(
    handler: Callable[[httpx.Request], httpx.Response], **config: object
) -> tuple[BoardCrawlerAdapter, list[str]]:
    requested: list[str] = []

    def recording(request: httpx.Request) -> httpx.Response:
        requested.append(f"{request.url.path}?{request.url.query.decode()}")
        return handler(request)

    transport = httpx.MockTransport(recording)

    async def no_sleep(_s: float) -> None:
        return None

    def client_for_host(host: str) -> ResilientClient:
        return ResilientClient(
            f"test@{host}",
            base_url=f"https://{host}",
            limiter=MemoryLimiter(),
            breaker=MemoryBreaker(),
            max_attempts=2,
            transport=transport,
            sleep=no_sleep,
        )

    cfg = {
        "boards": [{"url": "https://gov.example/list.do", "institution_code": "LG-1"}],
        "detail_pattern": r"view\.do",
        "attachment_pattern": r"download\.do",
        "delay_seconds": 0,
        **config,
    }
    return BoardCrawlerAdapter("test", cfg, client_for_host), requested


async def _crawl(adapter: BoardCrawlerAdapter, since: date) -> list[str]:
    out = [r.external_id async for r in adapter.fetch(FetchWindow(since, date(2026, 12, 31)))]
    await adapter.aclose()
    return out


async def test_incremental_crawl_stops_paging_once_rows_predate_the_window() -> None:
    adapter, requested = _adapter(_site())
    ids = await _crawl(adapter, since=date(2026, 1, 9))
    assert ids == ["P12", "P11", "P10", "P9"]
    # page 1 (P12..P8) already reaches back past Jan 9 → page 2 is never requested
    assert not any("pageIndex=2" in r for r in requested)
    assert adapter.stats.files == 4


async def test_full_crawl_walks_pages_until_the_board_runs_out() -> None:
    adapter, requested = _adapter(_site(posts=12))
    ids = await _crawl(adapter, since=date(2025, 1, 1))
    assert len(ids) == 12
    assert sum("list.do" in r for r in requested) == 4  # pages 1-3, then an empty page 4


async def test_robots_disallow_blocks_the_board() -> None:
    robots = httpx.Response(200, text="User-agent: *\nDisallow: /list.do\n")
    adapter, requested = _adapter(_site(robots=robots))
    assert await _crawl(adapter, since=date(2025, 1, 1)) == []
    assert adapter.stats.skipped_robots == 1
    assert requested == ["/robots.txt?"]


@pytest.mark.parametrize(
    ("status", "crawled"),
    [(404, True), (503, False)],  # RFC 9309: 4xx = no rules; 5xx/unreachable = stay away
)
async def test_robots_errors_follow_rfc_9309(status: int, crawled: bool) -> None:
    adapter, _ = _adapter(_site(robots=httpx.Response(status), posts=3))
    ids = await _crawl(adapter, since=date(2025, 1, 1))
    assert bool(ids) is crawled


async def test_oversized_files_are_dropped_not_buffered() -> None:
    adapter, _ = _adapter(_site(big_file=True, posts=2), max_file_mb=1)
    assert await _crawl(adapter, since=date(2025, 1, 1)) == []
    assert adapter.stats.skipped_size == 2
