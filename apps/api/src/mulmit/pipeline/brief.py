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

from mulmit.billing.ledger import InsufficientCreditsError, apply_credits
from mulmit.billing.plans import BRIEF_CREDIT_COST
from mulmit.clock import today_kst
from mulmit.db.models import (
    Brief,
    CompanyProfile,
    InstitutionRow,
    Opportunity,
    OpportunitySignal,
    Organization,
    Signal,
)
from mulmit.domain.krw import format_krw
from mulmit.domain.stages import STAGE_LABEL, Stage
from mulmit.runtime import Runtime

__all__ = ["InsufficientCreditsError", "build_facts", "generate_brief", "template_brief"]


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
        f"- 현재 단계: {STAGE_LABEL[Stage(opp.stage)]} (상태 {opp.status})",
        f"- 추정 예산: {format_krw(opp.est_budget_krw) if opp.est_budget_krw else '미상'}",
        f"- 입찰 예상 시기: {opp.bid_window_start} ~ {opp.bid_window_end}",
        f"- 가장 강한 의지 표현: {opp.best_commitment or '없음'} / 공고 전환 확률(추정): {opp.conversion_prob:.0%}",
        "",
        "# 신호 (시간순, 원문 인용)",
    ]
    for s in signals:
        quote = next((e["quote"] for e in s.evidence if e.get("found")), "")
        budget = f", 금액 {format_krw(s.budget_krw)}" if s.budget_krw else ""
        lines.append(
            f"- {s.observed_at} [{STAGE_LABEL[Stage(s.stage)]}] {s.title}{budget}, "
            f"의지 {s.commitment or '-'}: 「{quote[:300]}」"
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
            "- 사전규격 공개 전 담당 부서에 기술 자료와 타 지자체 레퍼런스를 제공하세요.",
            "- 의회 발언에서 언급된 문제(민원·불편)를 제안의 첫 문단에 그대로 연결하세요.",
            "",
            "## 리스크",
            "- 예산 확정 전 단계라면 추경·본예산 심의에서 삭감될 수 있습니다.",
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
