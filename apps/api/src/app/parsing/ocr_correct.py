"""Post-OCR correction for Korean administrative documents.

Tesseract's Korean model makes predictable mistakes on budget tables:

* digit look-alikes inside numbers (``O``→0, ``l``/``I``/``|``→1, ``S``→5 between digits),
* ``.`` for ``,`` as the thousands separator ("350.000" in a 천원 table),
* ``윈``/``원`` confusion after amounts, spaces inside numbers ("350, 000"),
* one-jamo slips in domain words ("세부샤업", "산출기쵸", "스마트쉘티").

The corrector fixes numbers with context-bound regexes and domain words with a jamo-level nearest
neighbour over a lexicon (taxonomy keywords + budget vocabulary + institution names). It only
replaces a token when exactly one lexicon word is close enough — ambiguity leaves the text alone.
Measured effect is recorded by ``manage eval all`` (CER before/after) — see docs/evaluation.md.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from rapidfuzz import fuzz, process

from app.domain.taxonomy import CATEGORIES, PROCUREMENT_VERBS
from app.domain.text import to_jamo

BUDGET_VOCAB: tuple[str, ...] = (
    "세부사업",
    "단위사업",
    "정책사업",
    "산출기초",
    "사업비",
    "예산액",
    "전년도",
    "증감",
    "세출예산",
    "사업명세서",
    "본예산",
    "추가경정",
    "부서",
    "개소",
    "운영",
    "유지관리",
    "설치",
    "구축",
    "조성",
    "보조금",
    "시설비",
    "자산취득비",
    "일반운영비",
    "위탁사업비",
    "천원",
)

_DIGIT_LOOKALIKE = str.maketrans({"O": "0", "o": "0", "l": "1", "I": "1", "|": "1", "S": "5"})
_NUMERIC_TOKEN_RE = re.compile(
    r"(?<![A-Za-z가-힣])[0-9OolI|S][0-9OolI|S,.]*[0-9OolI|S](?![A-Za-z가-힣])"
)
_THOUSANDS_DOT_RE = re.compile(r"(?<!\d)(\d{1,3})\.(\d{3})(?:\.(\d{3}))?(?!\d)")
_SPACED_THOUSANDS_RE = re.compile(r"(\d{1,3}),\s+(\d{3})(?!\d)")
_WON_FIX_RE = re.compile(r"(\d|[십백천만억])\s?[윈웜](?=[\s,.)]|$)")  # never 월: "3월" is a month


def _fix_numeric_token(match: re.Match[str]) -> str:
    token = match.group(0)
    if not any(ch.isdigit() for ch in token):
        return token  # words like "Is", "SOS" are not numbers
    return token.translate(_DIGIT_LOOKALIKE)


def fix_numbers(text: str, *, table_context: bool = True) -> str:
    text = _NUMERIC_TOKEN_RE.sub(_fix_numeric_token, text)
    text = _SPACED_THOUSANDS_RE.sub(r"\1,\2", text)
    if table_context:
        # In a 천원 table "350.000" is never three-hundred-fifty point zero.
        text = _THOUSANDS_DOT_RE.sub(
            lambda m: ",".join(g for g in m.groups() if g is not None), text
        )
    return _WON_FIX_RE.sub(lambda m: m.group(1) + "원", text)


def default_lexicon(extra: Iterable[str] = ()) -> list[str]:
    words: set[str] = set(BUDGET_VOCAB) | set(PROCUREMENT_VERBS)
    for info in CATEGORIES.values():
        words.update(kw for kw in info.keywords if len(kw) >= 3 and " " not in kw)
    words.update(w for w in extra if len(w) >= 3)
    return sorted(words)


_PARTICLES = frozenset(
    ("을", "를", "이", "가", "은", "는", "의", "에", "로", "와", "과", "도", "만", "에서", "으로")
)


class LexiconCorrector:
    def __init__(self, lexicon: Iterable[str], *, min_score: float = 84.0, margin: float = 4.0):
        self._words = sorted(set(lexicon))
        self._jamo = [to_jamo(w) for w in self._words]
        self._known = set(self._words)
        self._min = min_score
        self._margin = margin

    def correct_token(self, token: str) -> str:
        if token in self._known or len(token) < 3 or not re.fullmatch(r"[가-힣]+", token):
            return token
        # Particles glue onto words ("스마트쉘티를"); try the stem before common particles too.
        for stem_len in (len(token), len(token) - 1, len(token) - 2):
            if stem_len < 3:
                break
            stem, tail = token[:stem_len], token[stem_len:]
            if tail and tail not in _PARTICLES:
                continue  # "스마트폴구축" is a compound, not "스마트폴" + particle
            if stem in self._known:
                return token
            candidates = process.extract(
                to_jamo(stem),
                self._jamo,
                scorer=fuzz.ratio,
                limit=2,
                processor=None,
            )
            if not candidates:
                continue
            best_score = candidates[0][1]
            second = candidates[1][1] if len(candidates) > 1 else 0.0
            if best_score >= self._min and best_score - second >= self._margin:
                word = self._words[candidates[0][2]]
                if abs(len(word) - len(stem)) <= 1:
                    return word + tail
        return token

    def correct(self, text: str) -> str:
        return re.sub(r"[가-힣]{3,}", lambda m: self.correct_token(m.group(0)), text)


_UNIT_HEADER_VARIANTS = re.compile(r"\(?\s*단\s*위\s*[:：;]\s*천\s*원\s*\)?")


_AI_RE = re.compile(r"(?<![A-Za-z])A[l|1](?![a-z])")  # "Al 돌봄" — lowercase L read for capital I


def correct_ocr_text(text: str, corrector: LexiconCorrector | None = None) -> str:
    text = _UNIT_HEADER_VARIANTS.sub("(단위: 천원)", text)
    text = _AI_RE.sub("AI", text)
    text = fix_numbers(text, table_context="천원" in text)
    if corrector is not None:
        text = corrector.correct(text)
    return text
