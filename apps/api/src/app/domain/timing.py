"""Resolve the *when* of a spoken commitment against the meeting date.

"내년도 본예산에 반영하겠습니다" said in a December 2025 session means FY2026 — and so does
"'26년" or "2026년도". The same phrase said in March 2026 means FY2027. Getting this right is what
turns a transcript line into a forecast bid window.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Literal

Half = Literal["H1", "H2"]

_ABS_YEAR_RE = re.compile(r"(?<!\d)(20\d{2})\s*년")
_SHORT_YEAR_RE = re.compile(r"[’'`]\s?(\d{2})\s*년|(?<![\d.])(\d{2})\s*년도")
_RELATIVE = (
    ("내후년", 2),
    ("다다음 해", 2),
    ("내년", 1),
    ("다음 연도", 1),
    ("다음연도", 1),
    ("명년", 1),
    ("차년도", 1),
    ("올해", 0),
    ("금년", 0),
    ("당해", 0),
    ("연내", 0),
    ("올 하반기", 0),
)


@dataclass(frozen=True, slots=True)
class Timing:
    year: int
    half: Half | None
    basis: str  # the phrase the year came from


def _half(text: str) -> Half | None:
    if "하반기" in text or "추경" in text:
        return "H2"
    if "상반기" in text or "연초" in text:
        return "H1"
    m = re.search(r"(\d{1,2})\s*월", text)
    if m:
        month = int(m.group(1))
        if 1 <= month <= 12:
            return "H1" if month <= 6 else "H2"
    return None


def resolve_timing(text: str, reference: date) -> Timing | None:
    """Best-effort year (and half) for a timing phrase, relative to ``reference``."""
    m = _ABS_YEAR_RE.search(text)
    if m:
        return Timing(int(m.group(1)), _half(text), m.group(0))
    m2 = _SHORT_YEAR_RE.search(text)
    if m2:
        yy = int(m2.group(1) or m2.group(2))
        return Timing(2000 + yy, _half(text), m2.group(0))
    for phrase, offset in _RELATIVE:
        if phrase in text:
            return Timing(reference.year + offset, _half(text), phrase)
    half = _half(text)
    if half is not None:
        # "하반기에 발주" with no year: the current year if the half is still ahead, else next.
        year = reference.year
        if half == "H1" and reference.month > 6:
            year += 1
        return Timing(year, half, "하반기" if half == "H2" else "상반기")
    return None


def month_span(start: date, end: date | None = None) -> str:
    """A window as people say it: "2026년 7월", "2026년 9~11월", "2026년 11월~2027년 2월"."""
    if end is None or (start.year, start.month) == (end.year, end.month):
        return f"{start.year}년 {start.month}월"
    if start.year == end.year:
        return f"{start.year}년 {start.month}~{end.month}월"
    return f"{start.year}년 {start.month}월~{end.year}년 {end.month}월"
