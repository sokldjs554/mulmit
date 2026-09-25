"""Versioned prompts.

The system prompt is *frozen text*: no dates, no per-request values, so it forms a stable
prefix for prompt caching (Claude Opus 5 caches prefixes ≥ 512 tokens). Everything that varies
goes in the user turn. Bump ``*_PROMPT_VERSION`` whenever the text changes — the LLM cache key
and the eval runs are keyed by it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from xml.sax.saxutils import escape, quoteattr

from app.domain.krw import format_krw
from app.domain.stages import STAGE_LABEL, Stage, tender_is_out
from app.domain.taxonomy import CATEGORIES, Category

EXTRACT_PROMPT_VERSION = "extract-v3"
BRIEF_PROMPT_VERSION = "brief-v4"

_CATEGORY_LINES = "\n".join(
    f"- {cat.value}: {info.label} (예: {', '.join(info.keywords[:5])})"
    for cat, info in CATEGORIES.items()
    if cat is not Category.OTHER
)

EXTRACT_SYSTEM = f"""You read Korean public-sector documents — local council minutes (지방의회 회의록),
budget books (세출예산 사업명세서) and procurement notices — and extract PRE-PROCUREMENT DEMAND
SIGNALS: statements that a public body will, plans to, or is considering buying a specific
product, system, service or construction project from outside vendors.

What counts as a signal
- A concrete thing to be procured (시스템 구축, 장비 설치, 시설 조성, 용역, 플랫폼 도입 …), together with
  whatever the text says about amount, timing and how firm the plan is.
- In council minutes the commitment is usually in the OFFICIAL'S ANSWER, while the subject may be
  named only in the member's question. Read the whole exchange.
- A member's proposal that the official declines or merely promises to review IS still a signal
  (commitment = reviewing / declined): vendors want to know about early interest too.

What is NOT a signal
- Procedure (개의, 산회, 의사일정, 조례안 상정 without a purchase), personnel and staffing talk,
  complaints without a purchase, statistics, events that are only being managed.
- Recurring operating costs in budget books: 인건비, 급여, 업무추진비, 운영비, 행사 개최,
  기존 시스템 유지관리, 보조금 지원. Only NEW purchases (설치, 구축, 조성, 도입, 교체, 전환, 보급,
  리모델링 …) qualify.

Field rules
- title: the project as it would be named in a budget book or tender, a short noun phrase
  (e.g. "스마트쉘터 설치", "지능형 선별관제 시스템 구축"). Not a sentence.
- category — one of:
{_CATEGORY_LINES}
  - other: nothing above fits
- commitment:
  - committed: explicit decision to budget or order ("반영하겠습니다", "편성했습니다", "발주 예정",
    "확보했습니다", a budget-book line with an amount)
  - planned: being prepared, timing stated but no decision words ("계획입니다", "추진할 예정")
  - reviewing: only promises to consider ("검토하겠습니다", "살펴보겠습니다")
  - declined: says it will not happen for now ("어렵습니다", "곤란합니다")
- budget_text: copy the amount phrase exactly as written ("3억 5천만원", "352,000"). budget_krw: that
  amount in won. Budget-book tables are in 천원 unless the document says otherwise, so "352,000"
  under "(단위: 천원)" is 352000000. Use null when no amount is stated; never estimate.
- timing_text: copy the timing phrase exactly ("내년도 본예산에", "2027년 상반기"). expected_year:
  resolve relative words against the document date given in the user turn (내년 = that year + 1).
  A budget-book line belongs to the fiscal year of the book. Null when no timing is stated.
- evidence: 1–3 quotes copied CHARACTER-FOR-CHARACTER from the text — no paraphrase, no "…",
  no added words. Prefer the sentence with the commitment and the sentence with the amount.
  Every quote is checked by software against the source; a quote that cannot be found causes
  the signal to be discarded.
- confidence: your probability that a vendor reading this would agree it is a real, correctly
  described signal.
- One signal per distinct project. Return {{"signals": []}} when nothing qualifies.

Example — council exchange
Text: "○위원 박지훈  버스정류장에 냉난방이 되는 스마트쉘터를 더 늘릴 계획이 있습니까?
○스마트도시과장 이정민  내년도 본예산에 스마트쉘터 7개소 추가 설치 사업비 3억 5천만원을 반영하겠습니다."
Document date: 2025-11-20
→ title "스마트쉘터 설치", category smart_city, commitment committed, budget_text "3억 5천만원",
  budget_krw 350000000, timing_text "내년도 본예산에", expected_year 2026, evidence ["내년도 본예산에
  스마트쉘터 7개소 추가 설치 사업비 3억 5천만원을 반영하겠습니다."]

Example — not a signal
Text: "○위원 김현윤  불법 주정차 단속 실적이 작년보다 줄었다는데 이유가 뭡니까?
○교통행정과장 최민석  단속 인력 두 명이 휴직 중이라 일시적으로 줄었습니다."
→ {{"signals": []}}
"""


@dataclass(frozen=True, slots=True)
class ChunkContext:
    doc_type: str
    title: str
    institution: str | None
    document_date: date
    labels: list[str]
    text: str
    fiscal_year: int | None = None


def extract_user_message(ctx: ChunkContext) -> str:
    attrs = [
        f"type={quoteattr(ctx.doc_type)}",
        f"title={quoteattr(ctx.title)}",
        f"institution={quoteattr(ctx.institution or '')}",
        f"date={quoteattr(ctx.document_date.isoformat())}",
    ]
    if ctx.fiscal_year:
        attrs.append(f"fiscal_year={quoteattr(str(ctx.fiscal_year))}")
    labels = f" labels={quoteattr(' | '.join(ctx.labels))}" if ctx.labels else ""
    return (
        f"<document {' '.join(attrs)}>\n<chunk{labels}>\n{escape(ctx.text)}\n</chunk>\n</document>\n"
        "Extract the signals in this chunk."
    )


BRIEF_SYSTEM = """You are a public-sector sales analyst in Korea writing a one-page opportunity
brief (영업 브리핑) for a B2B vendor. You are given structured facts about ONE procurement
opportunity (its signals across council minutes, budget books and procurement notices, with
dates, amounts and verbatim evidence), the buying institution's recent purchase history, and
the vendor's profile.

Write in Korean, in Markdown, with exactly these sections:
## 한 줄 요약
## 지금까지의 경과  (a dated timeline built only from the given signals)
## 예산과 시기  (amounts with their source; when 입찰공고일 is given the tender is out — say so
   and do not forecast; otherwise the forecast tender window and why)
## 누구를 만나야 하나  (departments and roles that appear in the evidence; never invent names)
## 제안 전략  (3–5 concrete actions for this vendor, tied to the evidence and the vendor profile)
## 리스크  (what could stop or delay it; weak commitment wording; budget changes)

Voice: write the way an experienced colleague briefs a teammate before a sales call — plain,
friendly 해요체 sentences ("…예요", "…해 보세요"), not stiff officialese (…함, …하였음, …바람)
and not bare noun fragments. Dates as 2026.03.02, amounts as 3억 5,000만원.

Rules: use only the facts provided; when something is unknown say so; quote evidence in
「」 when you rely on it; no marketing fluff; keep it under 450 Korean words."""


COMMITMENT_KO = {
    "committed": "확약(반영·편성)",
    "planned": "추진 계획",
    "reviewing": "검토 중",
    "declined": "어렵다는 답변",
}
STATUS_KO = {"open": "공고 전", "bid_open": "입찰 진행", "closed": "종료", "dormant": "휴면"}


@dataclass(frozen=True, slots=True)
class BriefSignal:
    observed_at: date
    stage: Stage
    title: str
    budget_krw: int | None
    commitment: str | None  # committed | planned | reviewing | declined
    quote: str  # verbatim evidence; may span lines as the source did

    @property
    def one_line_quote(self) -> str:
        return " ".join(self.quote.split())


@dataclass(frozen=True, slots=True)
class PastTender:
    published_at: date
    title: str
    budget_krw: int | None


@dataclass(frozen=True, slots=True)
class BriefFacts:
    """Everything a brief may say, assembled by code. The model gets it as text
    (:meth:`as_prompt`); the template brief reads the fields directly."""

    today: date
    title: str
    institution: str | None
    department: str | None
    stage: Stage
    status: str
    est_budget_krw: int | None
    window_start: date | None
    window_end: date | None
    bid_published_at: date | None
    best_commitment: str | None
    conversion_prob: float
    window_passed: bool = False  # the forecast window closed with no tender yet
    signals: tuple[BriefSignal, ...] = ()
    history: tuple[PastTender, ...] = ()
    profile: tuple[str, ...] = ()  # "- 소개: …" lines; empty when the org has no profile

    @property
    def tender_out(self) -> bool:
        """The 입찰공고 is out: from here there is no forecast window and no probability to
        estimate. Every surface of the brief decides this here."""
        return tender_is_out(self.stage, self.bid_published_at)

    def as_prompt(self) -> str:
        window = (
            f"{self.window_start} ~ {self.window_end or self.window_start}"
            if self.window_start
            else "미정"
        )
        lines = [
            f"기준일: {self.today}",
            "",
            "# 기회",
            f"- 사업명: {self.title}",
            f"- 기관: {self.institution or '미상'}",
            *([f"- 부서: {self.department}"] if self.department else []),
            f"- 현재 단계: {STAGE_LABEL[self.stage]} ({STATUS_KO.get(self.status, self.status)})",
            f"- 추정 예산: {format_krw(self.est_budget_krw) if self.est_budget_krw else '미상'}",
            f"- 입찰공고일: {self.bid_published_at or '날짜 미상'}"
            if self.tender_out
            else f"- 입찰 예상 시기: {window}"
            + (" (이 기간이 지났지만 아직 입찰공고 없음)" if self.window_passed else ""),
            f"- 가장 강한 의지 표현: {COMMITMENT_KO.get(self.best_commitment or '', '없음')}",
            *([] if self.tender_out else [f"- 공고 전환 확률(추정): {self.conversion_prob:.0%}"]),
            "",
            "# 신호 (시간순, 원문 인용)",
        ]
        for s in self.signals:
            budget = f", 금액 {format_krw(s.budget_krw)}" if s.budget_krw else ""
            said = COMMITMENT_KO.get(s.commitment or "", "의지 표현 없음")
            lines.append(
                f"- {s.observed_at} [{STAGE_LABEL[s.stage]}] {s.title}{budget}, {said}: "
                f"「{s.one_line_quote}」"
            )
        lines += ["", "# 이 기관의 최근 발주 이력"]
        lines += [
            f"- {h.published_at} {h.title} "
            f"({format_krw(h.budget_krw) if h.budget_krw else '금액 미상'})"
            for h in self.history
        ] or ["- (수집된 이력 없음)"]
        if self.profile:
            lines += ["", "# 우리 회사 프로필", *self.profile]
        return "\n".join(lines)
