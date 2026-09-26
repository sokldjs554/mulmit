"""Institution resolution — turning "강남구청 스마트도시과", "서울 강남구", "강남구의회" into one entity.

Why this is harder than it looks:

* Six metropolitan cities each have a 중구, five have a 동구 — the bare name is ambiguous and only
  the document's context (which council published the minutes, which sido the 발주기관 sits in)
  can disambiguate. Ambiguity is surfaced, never guessed.
* Councils (구의회) talk about projects the executive (구청) will buy. Demand is attributed to the
  executive via ``executive_code``; the council is kept as the *speaker*.
* Departments are noise for identity but signal for sales ("스마트도시과" is who to call), so they
  are split off and kept.
"""

from __future__ import annotations

import csv
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from importlib import resources
from typing import Literal

from rapidfuzz import fuzz, process

from app.domain.text import normalize, to_jamo

InstitutionKind = Literal["local_gov", "council", "education_office", "public_agency", "central"]

SIDO_ALIASES: dict[str, tuple[str, ...]] = {
    "서울특별시": ("서울특별시", "서울시", "서울"),
    "부산광역시": ("부산광역시", "부산시", "부산"),
    "대구광역시": ("대구광역시", "대구시", "대구"),
    "인천광역시": ("인천광역시", "인천시", "인천"),
    "광주광역시": ("광주광역시", "광주시", "광주"),
    "대전광역시": ("대전광역시", "대전시", "대전"),
    "울산광역시": ("울산광역시", "울산시", "울산"),
    "세종특별자치시": ("세종특별자치시", "세종시", "세종"),
    "경기도": ("경기도", "경기"),
    "강원특별자치도": ("강원특별자치도", "강원도", "강원"),
    "충청북도": ("충청북도", "충북"),
    "충청남도": ("충청남도", "충남"),
    "전북특별자치도": ("전북특별자치도", "전라북도", "전북"),
    "전라남도": ("전라남도", "전남"),
    "경상북도": ("경상북도", "경북"),
    "경상남도": ("경상남도", "경남"),
    "제주특별자치도": ("제주특별자치도", "제주도", "제주"),
}
_SIDO_LOOKUP = {alias: full for full, aliases in SIDO_ALIASES.items() for alias in aliases}
# Longest alias first so "서울특별시" wins over "서울".
_SIDO_RE = re.compile("|".join(sorted(map(re.escape, _SIDO_LOOKUP), key=len, reverse=True)))

_DEPT_SUFFIX_RE = re.compile(
    r"^[가-힣A-Za-z0-9·]{2,}(?:과|팀|담당관|사업소|센터|보건소|국|실|단|본부|추진단|지원단)$"
)
_SIGUNGU_RE = re.compile(r"([가-힣]{1,5}(?:시|군|구))(?:청)?$")


@dataclass(frozen=True, slots=True)
class Institution:
    code: str
    name: str
    kind: InstitutionKind
    sido: str
    sigungu: str | None
    region_code: str
    executive_code: str | None = None
    aliases: tuple[str, ...] = ()

    @property
    def demand_owner_code(self) -> str:
        """Councils discuss what the executive will buy."""
        return self.executive_code or self.code


@dataclass(frozen=True, slots=True)
class ParsedName:
    raw: str
    sido: str | None
    sigungu: str | None
    is_council: bool
    is_education: bool
    department: str | None
    key: str
    sido_only: bool = False  # the name is the 시도 itself (plus its own departments)


@dataclass(slots=True)
class Resolution:
    institution: Institution | None
    department: str | None
    score: float
    method: Literal["code", "exact", "context", "fuzzy", "ambiguous", "none"]
    candidates: list[tuple[str, float]] = field(default_factory=list)

    @property
    def resolved(self) -> bool:
        return self.institution is not None


def _strip_sido_prefix(token: str) -> str:
    """ "서울특별시강남구청" -> "강남구청", but keep "부산진구" (a real 구, not 부산 + 진구)."""
    m = _SIDO_RE.match(token)
    if not m:
        return token
    rest = token[m.end() :]
    core = rest[:-1] if rest.endswith("청") else rest
    if rest and (len(m.group(0)) >= 3 or len(core) >= 3):
        return rest
    return token


def parse_name(raw: str) -> ParsedName:
    text = normalize(raw).replace("(", " ").replace(")", " ").strip()
    is_council = "의회" in text
    is_education = "교육청" in text or "교육지원청" in text
    sido_match = _SIDO_RE.search(text)
    sido = _SIDO_LOOKUP[sido_match.group(0)] if sido_match else None

    department: str | None = None
    sigungu: str | None = None
    for tok in text.split():
        tok_clean = tok.replace("의회", "")
        # "강남구청장", "성남시장", "영월군수" name the institution through its head.
        tok_clean = re.sub(r"^([가-힣]{1,5}(?:구|시|군))(?:청장|장|수)$", r"\1", tok_clean)
        if tok_clean in _SIDO_LOOKUP and sido and _SIDO_LOOKUP[tok_clean] != sido:
            # "경기도 광주시" is a 시 in 경기도, not 광주광역시 (seen on 조달청 data).
            if not sigungu and tok_clean.endswith("시"):
                sigungu = tok_clean
            continue
        if tok_clean in _SIDO_LOOKUP or not tok_clean:
            continue
        if _DEPT_SUFFIX_RE.match(tok_clean) and not re.search(r"(?:시|군|구)(?:청)?$", tok_clean):
            department = department or tok_clean
            continue
        stripped = _strip_sido_prefix(tok_clean)
        m = _SIGUNGU_RE.search(stripped)
        if m and not sigungu and m.group(1) not in _SIDO_LOOKUP:
            candidate = m.group(1)
            # "서울시" alone is a sido, not a sigungu.
            if candidate not in {
                "서울시",
                "부산시",
                "대구시",
                "인천시",
                "광주시",
                "대전시",
                "울산시",
            }:
                sigungu = candidate
            trailing = stripped[m.end() :]
            if trailing and _DEPT_SUFFIX_RE.match(trailing):
                department = department or trailing
        elif not sigungu and not department:
            m2 = re.match(
                r"^([가-힣]{1,5}(?:시|군|구))(?:청)?([가-힣]{2,}(?:과|팀|센터|담당관))$", tok_clean
            )
            if m2:
                sigungu, department = m2.group(1), m2.group(2)
    key = re.sub(r"\s+", "", f"{sido or ''}{sigungu or ''}{'의회' if is_council else ''}")
    if not key:
        key = re.sub(r"\s+", "", text)
    return ParsedName(
        raw, sido, sigungu, is_council, is_education, department, key, _is_sido_only(text, sido)
    )


# Bodies of their own that often follow a 시도 name: "경기도 신성중학교", "서울시 강서구시설관리공단".
_NOT_SIDO_OFFICE = ("학교", "공사", "공단", "조합")


def _leading_sido(text: str) -> str | None:
    """The 시도 when the name *starts* with one as a word ("경기도 …", "서울시청 …"). The ``sido``
    found by searching anywhere is looser: "해운대구" contains 대구, "서울교통공사" 서울."""
    tokens = text.split()
    if not tokens:
        return None
    head = tokens[0].replace("의회", "")
    if head.endswith("청") and head[:-1] in _SIDO_LOOKUP:
        head = head[:-1]
    return _SIDO_LOOKUP.get(head)


def _is_sido_only(text: str, sido: str | None) -> bool:
    """ "경기도", "서울시청 스마트도시과", "서울특별시 영등포소방서": the 시도 and its own offices.
    Not "서울교통공사", "부산대학교 산학협력단" or "국토교통부 부산지방국토관리청 …", which only carry
    a place name, and not "경기도 신성중학교" (the 교육청's) or a 구's 시설관리공단. On 30 days of
    조달청 data (2026-09-26) names like these were most of what resolved to a 시도, all to the
    wrong demand owner."""
    if sido is None or _leading_sido(text) != sido:
        return False
    return not any(
        any(w in t for w in _NOT_SIDO_OFFICE) or _SIDO_LOOKUP.get(t, sido) != sido
        for t in text.split()[1:]
    )


class InstitutionRegistry:
    def __init__(self, institutions: Iterable[Institution]) -> None:
        self._by_code: dict[str, Institution] = {}
        self._by_sigungu: dict[str, list[Institution]] = {}
        self._alias_index: dict[str, str] = {}
        self._jamo_index: dict[str, str] = {}
        for inst in institutions:
            self.add(inst)

    def add(self, inst: Institution) -> None:
        self._by_code[inst.code] = inst
        if inst.sigungu:
            self._by_sigungu.setdefault(inst.sigungu, []).append(inst)
        for alias in (inst.name, *inst.aliases):
            compact = re.sub(r"\s+", "", normalize(alias))
            self._alias_index[compact] = inst.code
            self._jamo_index[to_jamo(compact)] = inst.code

    def __len__(self) -> int:
        return len(self._by_code)

    def __iter__(self) -> Iterable[Institution]:
        return iter(self._by_code.values())

    def get(self, code: str) -> Institution | None:
        return self._by_code.get(code)

    def all(self) -> Sequence[Institution]:
        return list(self._by_code.values())

    def resolve(
        self,
        raw: str | None,
        *,
        sido_hint: str | None = None,
        code_hint: str | None = None,
        fuzzy_threshold: float = 90.0,
    ) -> Resolution:
        if code_hint and (inst := self._by_code.get(code_hint)):
            dept = parse_name(raw).department if raw else None
            return Resolution(inst, dept, 1.0, "code")
        if not raw or not raw.strip():
            return Resolution(None, None, 0.0, "none")
        parsed = parse_name(raw)
        sido = parsed.sido or (_SIDO_LOOKUP.get(sido_hint, sido_hint) if sido_hint else None)

        compact = re.sub(r"\s+", "", normalize(raw))
        if (code := self._alias_index.get(compact)) is not None:
            return Resolution(self._by_code[code], parsed.department, 1.0, "exact")

        if parsed.sigungu:
            pool = self._by_sigungu.get(parsed.sigungu, [])
            wanted: InstitutionKind = "council" if parsed.is_council else "local_gov"
            pool = [i for i in pool if i.kind == wanted] or pool
            if parsed.sido:
                pool = [i for i in pool if i.sido == parsed.sido]
            if len(pool) == 1:
                return Resolution(pool[0], parsed.department, 1.0, "exact")
            if len(pool) > 1 and sido:
                narrowed = [i for i in pool if i.sido == sido]
                if len(narrowed) == 1:
                    return Resolution(narrowed[0], parsed.department, 0.9, "context")
            if len(pool) > 1:
                return Resolution(
                    None, parsed.department, 0.0, "ambiguous", [(i.code, 1.0) for i in pool]
                )
        elif parsed.sido_only and not parsed.is_education:
            # "경기도" alone, or "제주특별자치도 관광정책과".
            wanted_sido: InstitutionKind = "council" if parsed.is_council else "local_gov"
            sido_level = [
                i
                for i in self._by_code.values()
                if i.sido == parsed.sido and i.sigungu is None and i.kind == wanted_sido
            ]
            if len(sido_level) == 1:
                return Resolution(sido_level[0], parsed.department, 0.95, "exact")

        found = self._fuzzy(compact, parsed.department, fuzzy_threshold)
        inst = found.institution
        if inst is not None and (
            (parsed.department and any(w in parsed.department for w in _NOT_SIDO_OFFICE))
            or ((lead := _leading_sido(normalize(raw))) is not None and inst.sido != lead)
            or (
                parsed.sigungu
                and inst.sigungu
                and parsed.sigungu.endswith("구")
                and inst.sigungu.endswith("구")
                and len(inst.sigungu) != len(parsed.sigungu)
            )
        ):
            # A misread swaps a syllable ("해운데구"); a different name ("대전 서구" → 유성구,
            # "부산 동래구" → 동구, both seen on 조달청 data) is another institution, and so is
            # a 공단 parsed as a department ("서울시 강서구시설관리공단").
            return Resolution(None, parsed.department, 0.0, "none", found.candidates)
        return found

    def _fuzzy(self, compact: str, department: str | None, threshold: float) -> Resolution:
        # Compare at jamo level so one-jamo OCR slips (대→데) cost little. Strip the department
        # first: it is not part of the institution's identity.
        if department:
            compact = compact.replace(department, "")
        scored = process.extract(
            to_jamo(compact), list(self._jamo_index), scorer=fuzz.ratio, limit=12
        )
        best_by_code: dict[str, float] = {}
        for alias_jamo, score, _ in scored:
            code = self._jamo_index[alias_jamo]
            best_by_code[code] = max(best_by_code.get(code, 0.0), float(score))
        ranked = sorted(best_by_code.items(), key=lambda kv: kv[1], reverse=True)
        if not ranked:
            return Resolution(None, department, 0.0, "none")
        best_code, best_score = ranked[0]
        runner_up = ranked[1][1] if len(ranked) > 1 else 0.0
        if best_score >= threshold and best_score - runner_up >= 4:
            return Resolution(
                self._by_code[best_code], department, best_score / 100, "fuzzy", ranked[:3]
            )
        return Resolution(None, department, 0.0, "none", ranked[:3])


def load_registry_csv(path: str | None = None) -> InstitutionRegistry:
    """Load the institution table. The bundled CSV is a curated subset for the demo; production
    imports the 행정표준코드 table through the admin console."""
    if path is None:
        ref = resources.files("app.domain").joinpath("data/institutions.csv")
        text = ref.read_text(encoding="utf-8")
    else:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    rows = csv.DictReader(text.splitlines())
    institutions = [
        Institution(
            code=row["code"],
            name=row["name"],
            kind=row["kind"],  # type: ignore[arg-type]
            sido=row["sido"],
            sigungu=row["sigungu"] or None,
            region_code=row["region_code"],
            executive_code=row["executive_code"] or None,
            aliases=tuple(a for a in row["aliases"].split("|") if a),
        )
        for row in rows
    ]
    return InstitutionRegistry(institutions)
