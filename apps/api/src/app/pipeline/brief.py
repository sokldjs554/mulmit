"""Deep Brief — a paid (credit-metered) one-page sales brief for one opportunity.

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
# influence, and what can still go wrong.
_STAGE_ADVICE: dict[Stage, tuple[list[str], list[str]]] = {
    Stage.COUNCIL: (
        [
            "아직 예산에 편성되기 전입니다. 담당 부서에 타 지자체 도입 사례와 개략 비용을 제공해 기본계획·예산 요구안의 범위를 함께 잡으세요.",
            "의회 발언에서 언급된 문제(민원·불편)를 제안의 첫 문단에 그대로 연결하세요.",
        ],
        [
            "본예산·추경 심의에서 빠지거나 삭감될 수 있습니다. 다음 예산서 공개 때 편성 여부를 확인하세요."
        ],
    ),
    Stage.BUDGET: (
        [
            "예산서 세부사업명과 금액이 확정됐습니다. 금액에 맞춘 구성안과 레퍼런스를 준비해 발주계획 등록 전에 담당자를 만나세요.",
            "규격에 반영되기를 바라는 기능은 지금 기술 자료로 전달해야 합니다.",
        ],
        ["발주 방식(협상·제한경쟁)과 시기는 아직 바뀔 수 있습니다."],
    ),
    Stage.ORDER_PLAN: (
        [
            "발주계획이 공개됐습니다. 사전규격 공개 전에 규격 초안에 대한 의견을 준비하고 담당자와 일정을 확인하세요.",
            "참가 자격(실적·인증) 요건을 미리 점검하고, 부족하면 컨소시엄 파트너를 찾으세요.",
        ],
        ["발주 시기가 분기 단위로 밀리는 경우가 흔합니다."],
    ),
    Stage.PRESPEC: (
        [
            "사전규격 의견등록 기간 안에 규격서를 검토해 특정 제품에 유리한 조항·과도한 실적 요건에 대한 의견을 제출하세요.",
            "입찰공고까지 남은 몇 주 동안 제안서 골격·실적 증빙·컨소시엄 구성을 끝내 두세요.",
        ],
        ["사전규격 의견에 따라 규격·예산이 조정되거나 공고가 늦어질 수 있습니다."],
    ),
    Stage.BID: (
        [
            "공고가 났습니다. 제안요청서의 평가 배점과 제출 서류를 확인하고 마감일에서 일정을 역산하세요.",
        ],
        ["이 단계에서는 규격을 바꿀 수 없습니다. 가격·제안 품질로 경쟁해야 합니다."],
    ),
}


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
    lines = [
        "# 기회",
        f"- 사업명: {opp.title}",
        f"- 기관: {inst.name if inst else '미상'}"
        + (f" / 부서: {opp.department}" if opp.department else ""),
        f"- 현재 단계: {STAGE_LABEL[Stage(opp.stage)]} ({STATUS_KO.get(opp.status, opp.status)})",
        f"- 추정 예산: {format_krw(opp.est_budget_krw) if opp.est_budget_krw else '미상'}",
        f"- 입찰 예상 시기: {opp.bid_window_start} ~ {opp.bid_window_end}",
        f"- 가장 강한 의지 표현: {COMMITMENT_KO.get(opp.best_commitment or '', '없음')}"
        f" / 공고 전환 확률(추정): {opp.conversion_prob:.0%}",
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


def template_brief(facts: str) -> str:
    """Deterministic brief used when no LLM is configured or the call fails."""

    def section(name: str) -> list[str]:
        m = re.search(rf"# {name}\n(.*?)(?:\n# |\Z)", facts, re.S)
        return [ln for ln in (m.group(1).splitlines() if m else []) if ln.strip()]

    opp = section("기회")
    signals = section(r"신호 \(시간순, 원문 인용\)")
    history = section("이 기관의 최근 발주 이력")
    title = next((ln.split(": ", 1)[1] for ln in opp if ln.startswith("- 사업명")), "이 사업")
    stage_line = next((ln for ln in opp if ln.startswith("- 현재 단계")), "")
    stage = next(
        (st for st, label in STAGE_LABEL.items() if f": {label} " in stage_line), Stage.COUNCIL
    )
    actions, risks = _STAGE_ADVICE.get(stage, _STAGE_ADVICE[Stage.BID])
    if any("어렵다는 답변" in ln or "검토 중" in ln for ln in signals[-1:]):
        risks = [*risks, "가장 최근 발언이 확약이 아닙니다. 다음 회기 발언과 예산서를 확인하세요."]
    return "\n".join(
        [
            "## 한 줄 요약",
            f"{title} — 아래 신호를 근거로 한 자동 요약입니다 (템플릿 모드: LLM 미사용).",
            "",
            "## 지금까지의 경과",
            *(signals or ["- 신호 없음"]),
            "",
            "## 예산과 시기",
            *[ln for ln in opp if "예산" in ln or "시기" in ln or "확률" in ln],
            "",
            "## 누구를 만나야 하나",
            *([ln for ln in opp if ln.startswith("- 기관")] or ["- 기관 정보 없음"]),
            "",
            "## 제안 전략",
            *(f"- {a}" for a in actions),
            "",
            "## 리스크",
            *(f"- {r}" for r in risks),
            "",
            "## 참고: 기관 발주 이력",
            *(history or ["- 없음"]),
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
