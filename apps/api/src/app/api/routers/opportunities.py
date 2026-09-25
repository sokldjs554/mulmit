from __future__ import annotations

import base64
import json
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, Query, status
from sqlalchemy import and_, func, or_, select

from app.api.deps import PrincipalDep, RuntimeDep, SessionDep
from app.api.presenters import card, institution_names, signals_for_opportunity
from app.api.schemas import (
    BriefOut,
    BudgetPoint,
    FeedbackIn,
    FeedPage,
    OpportunityDetail,
)
from app.billing.ledger import InsufficientCreditsError
from app.clock import today_kst
from app.db.models import Brief, Opportunity, Recommendation
from app.domain.stages import STAGE_LABEL, Stage
from app.pipeline.brief import generate_brief

router = APIRouter(prefix="/api/opportunities", tags=["opportunities"])


def _encode_cursor(score: float, opp_id: int) -> str:
    return base64.urlsafe_b64encode(json.dumps([score, opp_id]).encode()).decode()


def _decode_cursor(cursor: str) -> tuple[float, int]:
    try:
        score, opp_id = json.loads(base64.urlsafe_b64decode(cursor.encode()))
        return float(score), int(opp_id)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid cursor") from exc


@router.get("", response_model=FeedPage)
async def feed(
    principal: PrincipalDep,
    session: SessionDep,
    stage: Annotated[list[str] | None, Query()] = None,
    category: Annotated[list[str] | None, Query()] = None,
    status_: Annotated[list[str] | None, Query(alias="status")] = None,
    q: str | None = None,
    include_dismissed: bool = False,
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> FeedPage:
    """The recommended feed: keyset-paginated on (score desc, id desc)."""
    conds = [Recommendation.org_id == principal.org.id]
    if stage:
        conds.append(Opportunity.stage.in_(stage))
    if category:
        conds.append(Opportunity.category.in_(category))
    conds.append(Opportunity.status.in_(status_ or ["open", "bid_open"]))
    if q:
        conds.append(or_(Opportunity.title.ilike(f"%{q}%"), Opportunity.keywords.contains([q])))
    if not include_dismissed:
        conds.append(
            or_(
                Recommendation.feedback.is_(None),
                Recommendation.feedback.not_in(("dismissed", "irrelevant")),
            )
        )
    base = (
        select(Recommendation, Opportunity)
        .join(Opportunity, Opportunity.id == Recommendation.opportunity_id)
        .where(and_(*conds))
    )
    total = await session.scalar(select(func.count()).select_from(base.subquery())) or 0
    page_q = base
    if cursor:
        c_score, c_id = _decode_cursor(cursor)
        page_q = page_q.where(
            or_(
                Recommendation.score < c_score,
                and_(Recommendation.score == c_score, Opportunity.id < c_id),
            )
        )
    rows = (
        await session.execute(
            page_q.order_by(Recommendation.score.desc(), Opportunity.id.desc()).limit(limit + 1)
        )
    ).all()
    names = await institution_names(session)
    today = today_kst()
    items = [card(opp, names, rec, today) for rec, opp in rows[:limit]]
    next_cursor = None
    if len(rows) > limit:
        last_rec, last_opp = rows[limit - 1]
        next_cursor = _encode_cursor(last_rec.score, last_opp.id)
    return FeedPage(items=items, next_cursor=next_cursor, total=total)


@router.get("/{opportunity_id}", response_model=OpportunityDetail)
async def detail(
    opportunity_id: int, principal: PrincipalDep, session: SessionDep
) -> OpportunityDetail:
    opp = await session.get(Opportunity, opportunity_id)
    if opp is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "기회를 찾을 수 없습니다")
    rec = await session.get(Recommendation, (principal.org.id, opp.id))
    names = await institution_names(session)
    base = card(opp, names, rec, today_kst())
    signals = await signals_for_opportunity(session, opp.id)
    trajectory = [
        BudgetPoint(
            observed_at=s.observed_at,
            amount=s.budget_krw,
            stage=s.stage,
            stage_label=STAGE_LABEL[Stage(s.stage)],
        )
        for s in signals
        if s.budget_krw
    ]
    briefs = (
        await session.scalars(
            select(Brief)
            .where(Brief.org_id == principal.org.id, Brief.opportunity_id == opp.id)
            .order_by(Brief.created_at.desc())
        )
    ).all()
    return OpportunityDetail(
        **base.model_dump(),
        keywords=opp.keywords,
        best_commitment=opp.best_commitment,
        signals=signals,
        budget_trajectory=trajectory,
        breakdown=rec.breakdown if rec else None,
        briefs=[BriefOut.model_validate(b) for b in briefs],
    )


@router.post("/{opportunity_id}/feedback", status_code=status.HTTP_204_NO_CONTENT)
async def feedback(
    opportunity_id: int, body: FeedbackIn, principal: PrincipalDep, session: SessionDep
) -> None:
    rec = await session.get(Recommendation, (principal.org.id, opportunity_id))
    if rec is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "추천 내역이 없습니다")
    rec.feedback = body.feedback
    rec.feedback_at = datetime.now(UTC) if body.feedback else None


@router.post(
    "/{opportunity_id}/briefs", response_model=BriefOut, status_code=status.HTTP_201_CREATED
)
async def create_brief(
    opportunity_id: int,
    principal: PrincipalDep,
    session: SessionDep,
    runtime: RuntimeDep,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=100)],
) -> BriefOut:
    try:
        brief = await generate_brief(
            session,
            runtime,
            org=principal.org,
            opportunity_id=opportunity_id,
            user_id=principal.user.id,
            idempotency_key=f"{principal.org.id}:{idempotency_key}",
        )
    except InsufficientCreditsError as exc:
        raise HTTPException(
            status.HTTP_402_PAYMENT_REQUIRED,
            f"크레딧이 부족합니다 (보유 {exc.balance}, 필요 {exc.needed})",
        ) from exc
    except LookupError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return BriefOut.model_validate(brief)
