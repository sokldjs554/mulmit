"""Synthetic 지자체 누리집 — the demo world's budget books, published the way real governments do.

Each demo institution gets its own host (``lg-11680.gov.example``; ``.example`` is reserved, so
nothing here can leak onto the real network) with a "예산 공개" board. The markup copies the
usual eGovFrame board: a table of posts, ``pageIndex`` paging, detail links with session and
menu parameters, attachments behind ``download.do``. The pages also carry what a crawler meets in
the wild: notices that aren't budget books, a post under a robots-disallowed path, image
attachments, and downloads served as ``application/octet-stream``.

Served through ``httpx.MockTransport``, so the demo and the tests exercise the real crawler code
path (HTTP, robots.txt, paging, parsing, magic-byte sniffing) with no network.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from html import escape
from typing import Any
from urllib.parse import parse_qs, quote, urlsplit

import httpx

from app.sources.base import RawRecord

PAGE_SIZE = 5
_ROBOTS = "User-agent: *\nDisallow: /admin/\n"
_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64  # a poster image attached to budget posts
_EXT = {"application/pdf": "pdf", "application/hwp+zip": "hwpx", "application/x-hwp": "hwp"}


def host_for(institution_code: str) -> str:
    return f"{institution_code.lower()}.gov.example"


@dataclass(slots=True)
class _Post:
    ntt_id: str
    title: str
    posted: date
    files: list[tuple[str, bytes]]  # (file name, bytes)
    path: str = "/board/budget/view.do"


class SyntheticGovSites:
    def __init__(self, budget_records: list[RawRecord]) -> None:
        self._posts: dict[str, list[_Post]] = {}
        self._names: dict[str, str] = {}
        for rec in budget_records:
            code = rec.institution_code_hint or "unknown"
            self._names[code] = rec.publisher_raw or code
            ext = _EXT.get(rec.mime, "bin")
            file_name = f"{rec.title.replace(' ', '_')}.{ext}"
            files: list[tuple[str, bytes]] = [(file_name, rec.content or b"")]
            files.append(("예산설명회_안내_포스터.png", _PNG))
            self._posts.setdefault(code, []).append(
                _Post(rec.external_id, rec.title, rec.published_at, files)
            )
        for code, posts in self._posts.items():
            newest = max(p.posted for p in posts)
            posts += [
                _Post(f"N-{code}-1", "청사 주차장 이용 안내", newest - timedelta(days=20), []),
                _Post(
                    f"N-{code}-2",
                    "예산서 게시 전 검토본 (내부)",
                    newest - timedelta(days=3),
                    [],
                    path="/admin/board/view.do",
                ),
            ]
            posts.sort(key=lambda p: (p.posted, p.ntt_id), reverse=True)

    def boards(self) -> list[dict[str, Any]]:
        return [
            {
                "url": f"https://{host_for(code)}/board/budget/list.do?menuNo=200100",
                "institution_code": code,
                "publisher": self._names[code],
            }
            for code in sorted(self._posts)
        ]

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self._handle)

    # -- pages -----------------------------------------------------------------------------------
    def _handle(self, request: httpx.Request) -> httpx.Response:
        host = request.url.host
        code = next((c for c in self._posts if host_for(c) == host), None)
        path = request.url.path
        query = parse_qs(urlsplit(str(request.url)).query)
        if path == "/robots.txt":
            return httpx.Response(200, text=_ROBOTS)
        if code is None:
            return httpx.Response(404)
        posts = self._posts[code]
        if path == "/board/budget/list.do":
            page = int((query.get("pageIndex") or ["1"])[0])
            return self._html(self._list_page(posts, page))
        if path.endswith("/view.do"):
            post = next((p for p in posts if p.ntt_id == (query.get("nttId") or [""])[0]), None)
            return self._html(self._view_page(post)) if post else httpx.Response(404)
        if path == "/common/file/download.do":
            post = next((p for p in posts if p.ntt_id == (query.get("fileId") or [""])[0]), None)
            sn = int((query.get("fileSn") or ["0"])[0])
            if post is None or not 1 <= sn <= len(post.files):
                return httpx.Response(404)
            name, content = post.files[sn - 1]
            return httpx.Response(
                200,
                content=content,
                headers={
                    "Content-Type": "application/octet-stream",
                    "Content-Disposition": f"attachment; filename*=UTF-8''{quote(name)}",
                },
            )
        return httpx.Response(404)

    @staticmethod
    def _html(body: str) -> httpx.Response:
        page = f'<!doctype html><html lang="ko"><body>{body}</body></html>'
        return httpx.Response(200, text=page, headers={"Content-Type": "text/html; charset=utf-8"})

    def _list_page(self, posts: list[_Post], page: int) -> str:
        chunk = posts[(page - 1) * PAGE_SIZE : page * PAGE_SIZE] or posts[-PAGE_SIZE:]
        rows = "".join(
            "<tr>"
            f"<td>{len(posts) - posts.index(p)}</td>"
            f'<td class="subject"><a href="{p.path}?nttId={quote(p.ntt_id)}'
            f'&amp;menuNo=200100&amp;jsessionid=A1B2C3">{escape(p.title)}</a></td>'
            f"<td>{'첨부' if p.files else ''}</td>"
            f"<td>{p.posted:%Y-%m-%d}</td>"
            "</tr>"
            for p in chunk
        )
        return (
            '<table class="board_list"><thead><tr><th>번호</th><th>제목</th><th>파일</th>'
            f"<th>등록일</th></tr></thead><tbody>{rows}</tbody></table>"
            f'<div class="paging">{page} / {max(1, -(-len(posts) // PAGE_SIZE))}</div>'
        )

    @staticmethod
    def _view_page(post: _Post) -> str:
        files = "".join(
            f'<li><a href="/common/file/download.do?fileId={quote(post.ntt_id)}&amp;fileSn={i}">'
            f"{escape(name)}</a></li>"
            for i, (name, _content) in enumerate(post.files, start=1)
        )
        return (
            f'<div class="view"><h3>{escape(post.title)}</h3>'
            f'<p>등록일 {post.posted:%Y.%m.%d}</p><ul class="file">{files}</ul></div>'
        )
