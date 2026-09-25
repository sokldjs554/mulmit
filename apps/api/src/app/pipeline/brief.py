"""영업 브리핑 (sales brief) — a paid (credit-metered) one-page sales brief for one opportunity.

The brief is generated from *facts assembled by code* (signals with dated evidence, the buying
institution's recent purchase history, the vendor profile). The model writes; it does not
research — so every claim in the brief traces back to a stored signal.

Billing: credits are debited in the same transaction that stores the brief, keyed by the
client's idempotency key. If generation fails, the transaction rolls back and nothing is
charged; a double-clicked button returns the already-generated brief.
"""

from __future__ import annotations

import re
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.billing.ledger import InsufficientCreditsError, apply_credits
from app.billing.plans import BRIEF_CREDIT_COST
from app.clock import today_kst
from app.db.models import (
    Brief,
    CompanyProfile,
    InstitutionRow,
    Opportunity,
    OpportunitySignal,
    Organization,
    Signal,
)
from app.domain.krw import format_krw
from app.domain.stages import STAGE_LABEL, Stage
from app.runtime import Runtime

__all__ = ["InsufficientCreditsError", "build_facts", "generate_brief", "template_brief"]

COMMITMENT_KO = {
    "committed": "확약(반영·편성)",
    "planned": "추진 계획",
    "reviewing": "검토 중",
    "declined": "어렵다는 답변",
}
STATUS_KO = {"open": "공고 전", "bid_open": "입찰 진행", "closed": "종료", "dormant": "휴면"}

# Template-mode advice by the stage the opportunity has reached: what a seller can still
# influence, and what can still go wrong. Written the way a colleague would say it.
_STAGE_ADVICE: dict[Stage, tuple[list[str], list[str]]] = {
    Stage.COUNCIL: (
        [
            "아직 예산에 편성되기 전이에요. 담당 부서에 다른 지자체 도입 사례와 대략적인 비용을 먼저 건네면, "
            "기본계획이나 예산 요구안의 범위를 같이 잡을 수 있어요.",
            "의원이 꺼낸 문제(민원, 불편)를 제안서 첫 문단에 그대로 이어 주세요. 담당자가 내부 보고서에 옮겨 쓰기 쉬워져요.",
        ],
        [
            "본예산이나 추경 심의에서 빠지거나 깎일 수 있어요. 다음 예산서가 나오면 편성됐는지부터 확인해 보세요."
        ],
    ),
    Stage.BUDGET: (
        [
            "예산서에 세부사업명과 금액이 올라갔어요. 이 금액에 맞춘 구성안과 납품 실적을 챙겨서, "
            "발주계획이 나오기 전에 담당자를 만나 보세요.",
            "규격에 꼭 들어갔으면 하는 기능이 있다면 지금 기술 자료로 전달해야 해요. 사전규격이 나오면 늦어요.",
        ],
        ["발주 방식(협상, 제한경쟁)과 시기는 아직 바뀔 수 있어요."],
    ),
    Stage.ORDER_PLAN: (
        [
            "발주계획이 공개됐어요. 사전규격이 나오기 전에 규격 초안에 낼 의견을 준비하고, 담당자와 일정을 맞춰 보세요.",
            "참가 자격(실적, 인증)을 미리 따져 보고, 모자라면 컨소시엄 파트너를 찾아 두세요.",
        ],
        ["발주 시기가 한 분기씩 밀리는 일이 흔해요."],
    ),
    Stage.PRESPEC: (
        [
            "사전규격 의견등록 기간 안에 규격서를 꼼꼼히 보고, 특정 제품에만 유리한 조항이나 지나친 실적 요건이 "
            "있으면 의견을 내세요.",
            "입찰공고까지 몇 주 안 남았어요. 제안서 뼈대, 실적 증빙, 컨소시엄 구성을 이때 끝내 두세요.",
        ],
        ["사전규격 의견에 따라 규격이나 예산이 바뀌고, 공고가 늦어질 수도 있어요."],
    ),
    Stage.BID: (
        [
            "공고가 났어요. 제안요청서의 평가 배점과 제출 서류부터 확인하고, 마감일에서 거꾸로 일정을 짜 보세요."
        ],
        ["이제는 규격을 바꿀 수 없어요. 가격과 제안서 완성도로 승부해야 해요."],
    ),
}

# How a council answer reads in the brief's timeline.
_COMMITMENT_SAID = {
    "확약(반영·편성)": "'반영하겠다'고 답했어요.",
    "추진 계획": "추진하겠다는 계획을 밝혔어요.",
    "검토 중": "'검토하겠다'는 정도였어요.",
    "어렵다는 답변": "'어렵다'고 답했어요.",
}
_WEAK = ("검토 중", "어렵다는 답변")


def _dot(iso: str) -> str:
    return iso.strip().replace("-", ".")


def _window_span(window: str) -> str | None:
    """ "2026-09-01 ~ 2026-11-30" → "2026년 9~11월"; None when there is no forecast."""
    dates = re.findall(r"(\d{4})-(\d{2})-\d{2}", window)
    if not dates:
        return None
    (y1, m1), (y2, m2) = dates[0], dates[-1]
    if (y1, m1) == (y2, m2):
        return f"{y1}년 {int(m1)}월"
    if y1 == y2:
        return f"{y1}년 {int(m1)}~{int(m2)}월"
    return f"{y1}년 {int(m1)}월~{y2}년 {int(m2)}월"


async def build_facts(session: AsyncSession, opp: Opportunity, org_id: int) -> str:
    inst = await session.get(InstitutionRow, opp.institution_code) if opp.institution_code else None
    signals = (
        await session.scalars(
            select(Signal)
            .join(OpportunitySignal, OpportunitySignal.signal_id == Signal.id)
            .where(OpportunitySignal.opportunity_id == opp.id)
            .order_by(Signal.observed_at)
        )
    ).all()
    history = (
        await session.scalars(
            select(Opportunity)
            .where(
                Opportunity.institution_code == opp.institution_code,
                Opportunity.id != opp.id,
                Opportunity.bid_published_at.is_not(None),
            )
            .order_by(Opportunity.bid_published_at.desc())
            .limit(8)
        )
    ).all()
    profile = await session.get(CompanyProfile, org_id)
    window = (
        f"{opp.bid_window_start} ~ {opp.bid_window_end or opp.bid_window_start}"
        if opp.bid_window_start
        else "미정"
    )
    lines = [
        "# 기회",
        f"- 사업명: {opp.title}",
        f"- 기관: {inst.name if inst else '미상'}",
        *([f"- 부서: {opp.department}"] if opp.department else []),
        f"- 현재 단계: {STAGE_LABEL[Stage(opp.stage)]} ({STATUS_KO.get(opp.status, opp.status)})",
        f"- 추정 예산: {format_krw(opp.est_budget_krw) if opp.est_budget_krw else '미상'}",
        f"- 입찰 예상 시기: {window}",
        *([f"- 입찰공고일: {opp.bid_published_at}"] if opp.bid_published_at else []),
        f"- 가장 강한 의지 표현: {COMMITMENT_KO.get(opp.best_commitment or '', '없음')}",
        f"- 공고 전환 확률(추정): {opp.conversion_prob:.0%}",
        "",
        "# 신호 (시간순, 원문 인용)",
    ]
    for s in signals:
        quote = next((e["quote"] for e in s.evidence if e.get("found")), "")
        budget = f", 금액 {format_krw(s.budget_krw)}" if s.budget_krw else ""
        lines.append(
            f"- {s.observed_at} [{STAGE_LABEL[Stage(s.stage)]}] {s.title}{budget}, "
            f"{COMMITMENT_KO.get(s.commitment or '', '의지 표현 없음')}: 「{quote[:300]}」"
        )
    lines += ["", "# 이 기관의 최근 발주 이력"]
    lines += [
        f"- {h.bid_published_at} {h.title} ({format_krw(h.est_budget_krw) if h.est_budget_krw else '금액 미상'})"
        for h in history
    ] or ["- (수집된 이력 없음)"]
    lines += ["", "# 우리 회사 프로필"]
    if profile:
        lines += [
            f"- 소개: {profile.description or '-'}",
            f"- 주력 키워드: {', '.join(profile.keywords) or '-'}",
            f"- 선호 예산 범위: {profile.budget_min or '-'} ~ {profile.budget_max or '-'}",
        ]
    return "\n".join(lines)


_SIGNAL_LINE = re.compile(
    r"^- (?P<date>\d{4}-\d{2}-\d{2}) \[(?P<stage>[^\]]+)\] (?P<title>.+?)"
    r"(?:, 금액 (?P<budget>.+?))?, (?P<said>[^,:]+): 「(?P<quote>.*)」$"
)
_HISTORY_LINE = re.compile(r"^- (?P<date>\d{4}-\d{2}-\d{2}) (?P<rest>.+)$")


def template_brief(facts: str) -> str:
    """Deterministic brief used when no LLM is configured or the call fails. It reads the same
    facts the model would get, and says nothing the facts do not."""

    def section(name: str) -> list[str]:
        m = re.search(rf"# {name}\n(.*?)(?:\n# |\Z)", facts, re.S)
        return [ln for ln in (m.group(1).splitlines() if m else []) if ln.strip()]

    fields = {}
    for ln in section("기회"):
        key, sep, value = ln.removeprefix("- ").partition(": ")
        if sep:
            fields[key] = value.strip()
    signals = [m for ln in section(r"신호 \(시간순, 원문 인용\)") if (m := _SIGNAL_LINE.match(ln))]
    history = [m for ln in section("이 기관의 최근 발주 이력") if (m := _HISTORY_LINE.match(ln))]

    title = fields.get("사업명", "이 사업")
    institution = fields.get("기관", "미상")
    department = fields.get("부서")
    who = " ".join(x for x in (institution if institution != "미상" else "", department) if x)
    stage_label = fields.get("현재 단계", "").split(" (")[0]
    stage = next((st for st, label in STAGE_LABEL.items() if label == stage_label), Stage.COUNCIL)
    budget = fields.get("추정 예산", "미상")
    published = fields.get("입찰공고일")
    span = _window_span(fields.get("입찰 예상 시기", ""))
    if published:
        timing, when = f"입찰공고는 {_dot(published)}에 나왔어요.", f"- 입찰공고: {_dot(published)}"
    elif span:
        timing, when = f"입찰은 {span}쯤 나올 것으로 보고 있어요.", f"- 입찰 예상 시기: {span}"
    else:
        timing, when = "입찰 시기는 아직 가늠하기 어려워요.", "- 입찰 시기: 아직 가늠하기 어려워요."
    prob = fields.get("공고 전환 확률(추정)")

    actions, risks = _STAGE_ADVICE.get(stage, _STAGE_ADVICE[Stage.BID])
    if signals and signals[-1]["said"] in _WEAK:
        risks = [
            *risks,
            "가장 최근 발언이 확약은 아니었어요. 다음 회기 회의록과 예산서를 꼭 확인해 보세요.",
        ]

    summary = f"{who + '의 ' if who else ''}「{title}」 건이에요. 지금은 {stage_label or '초기'} 단계예요. {timing}"
    if budget != "미상":
        summary += f" 예산은 {budget}으로 잡혀 있어요."

    timeline: list[str] = []
    for s in signals:
        head = f"- **{_dot(s['date'])} · {s['stage']}** — {s['title']}"
        if s["budget"]:
            head += f" ({s['budget']})"
        said = _COMMITMENT_SAID.get(s["said"]) if s["stage"] == STAGE_LABEL[Stage.COUNCIL] else None
        timeline.append(f"{head}. {said}" if said else head)
        if s["quote"].strip("…").strip():
            timeline.append(f"  > 「{s['quote']}」")

    money = [
        f"- 추정 예산: {budget} (가장 최근 문서 기준)"
        if budget != "미상"
        else "- 추정 예산: 아직 금액이 나온 문서가 없어요.",
        when,
    ]
    if prob:
        money.append(
            f"- 공고로 이어질 가능성: {prob} 정도예요. 같은 종류의 첫 신호가 지난 데이터에서 실제 입찰까지 간 비율이에요."
        )

    if department:
        meet = [f"- {who}. 문서에 담당으로 나온 부서라서 여기부터 연락해 보세요."]
    elif who:
        meet = [
            f"- {who}. 담당 부서는 아직 문서에 안 나왔어요. 다음 회의록이나 예산서에서 부서명을 확인해 보세요."
        ]
    else:
        meet = ["- 수요 기관을 아직 특정하지 못했어요."]

    past = [f"- {_dot(h['date'])} · {h['rest']}" for h in history] or [
        "- 아직 모아 둔 발주 이력이 없어요."
    ]

    return "\n".join(
        [
            "## 한 줄 요약",
            summary,
            "",
            "## 지금까지의 경과",
            *(timeline or ["- 아직 잡힌 신호가 없어요."]),
            "",
            "## 예산과 시기",
            *money,
            "",
            "## 누구를 만나야 하나",
            *meet,
            "",
            "## 제안 전략",
            *(f"- {a}" for a in actions),
            "",
            "## 리스크",
            *(f"- {r}" for r in risks),
            "",
            "## 참고: 이 기관의 최근 발주",
            *past,
        ]
    )


async def generate_brief(
    session: AsyncSession,
    runtime: Runtime,
    *,
    org: Organization,
    opportunity_id: int,
    user_id: int,
    idempotency_key: str,
) -> Brief:
    existing = await session.scalar(select(Brief).where(Brief.idempotency_key == idempotency_key))
    if existing is not None:
        return existing
    opp = await session.get(Opportunity, opportunity_id)
    if opp is None:
        raise LookupError("opportunity not found")
    if org.credit_balance < BRIEF_CREDIT_COST:
        raise InsufficientCreditsError(org.credit_balance, BRIEF_CREDIT_COST)
    facts = await build_facts(session, opp, org.id)
    markdown, model = await runtime.llm.brief(session, facts)
    brief = Brief(
        org_id=org.id,
        opportunity_id=opp.id,
        content_md=markdown,
        model=model,
        credits_spent=BRIEF_CREDIT_COST,
        idempotency_key=idempotency_key,
    )
    session.add(brief)
    await session.flush()
    await apply_credits(
        session,
        org_id=org.id,
        delta=-BRIEF_CREDIT_COST,
        reason="brief",
        idempotency_key=f"brief:{idempotency_key}",
        ref_type="brief",
        ref_id=str(brief.id),
        actor_user_id=user_id,
    )
    return brief


def brief_cache_date() -> date:
    return today_kst()
