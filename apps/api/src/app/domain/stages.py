"""The public-procurement lifecycle, as seen from the outside.

    의회 발언 ──► 예산 편성 ──► 발주계획 ──► 사전규격 ──► 입찰공고 ──► 낙찰·계약
    (6–18mo)     (3–12mo)      (1–6mo)      (2–8wk)       (D-day)

Each stage is a *signal type* with its own reliability and lead time. An opportunity's value to a
seller is the product of the two: a 사전규격 is near-certain but leaves weeks to act; a council
answer leaves a year but may never materialise. Ranking (see ``pipeline/recommend.py``) trades
them off using the conversion rates the backtest measures.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import date, timedelta
from enum import StrEnum
from typing import Any

from app.domain.timing import Half


class Stage(StrEnum):
    COUNCIL = "council_mention"
    BUDGET = "budget_line"
    ORDER_PLAN = "order_plan"
    PRESPEC = "prespec"
    BID = "bid_notice"
    AWARD = "award"


STAGE_ORDER: dict[Stage, int] = {s: i for i, s in enumerate(Stage)}

STAGE_LABEL: dict[Stage, str] = {
    Stage.COUNCIL: "의회 발언",
    Stage.BUDGET: "예산 편성",
    Stage.ORDER_PLAN: "발주계획",
    Stage.PRESPEC: "사전규격",
    Stage.BID: "입찰공고",
    Stage.AWARD: "낙찰·계약",
}

PRE_PROCUREMENT: frozenset[Stage] = frozenset({Stage.COUNCIL, Stage.BUDGET})

# (min_days, max_days) from a signal at this stage until the tender is published. Medians from
# procurement practice; the backtest reports the measured distribution so these can be re-fit.
BID_LAG_DAYS: dict[Stage, tuple[int, int]] = {
    Stage.COUNCIL: (180, 540),
    Stage.BUDGET: (60, 300),
    Stage.ORDER_PLAN: (20, 150),
    Stage.PRESPEC: (7, 45),
    Stage.BID: (0, 0),
    Stage.AWARD: (0, 0),
}

# Prior probability that a signal at this stage becomes a tender. Replaced by backtest-measured
# rates once enough history exists (see Settings / eval runs).
STAGE_PRIOR: dict[Stage, float] = {
    Stage.COUNCIL: 0.35,
    Stage.BUDGET: 0.7,
    Stage.ORDER_PLAN: 0.85,
    Stage.PRESPEC: 0.95,
    Stage.BID: 1.0,
    Stage.AWARD: 1.0,
}

COMMITMENT_MULTIPLIER: dict[str, float] = {
    "committed": 1.6,
    "planned": 1.2,
    "reviewing": 0.6,
    "declined": 0.15,
}


def tender_is_out(stage: Stage | str, bid_published_at: date | None) -> bool:
    """The 입찰공고 is out: from here nothing about the tender is a forecast any more. The
    conversion probability is 1.0 by definition, so it is not an estimate to show."""
    return bid_published_at is not None or STAGE_ORDER[Stage(stage)] >= STAGE_ORDER[Stage.BID]


# 나라장터 withdraws a 입찰공고 by publishing a 취소공고 as a later 차수 of the same number
# (1,738 of 30,522 live notices, 2026-09-26). The 취소 is no tender of its own.
CANCEL_NOTICE = "취소공고"
CANCELS_KEY = "cancels_bid_notice_no"


def withdrawn_bids(notices: Iterable[tuple[Mapping[str, Any], date]]) -> set[str]:
    """Bid numbers whose latest 차수 is a 취소공고, from (external_refs, observed_at) pairs. A
    재공고 under the same number after the 취소 puts it back; on the same day the 취소 wins,
    the safer reading for someone deciding whether to bid."""
    latest: dict[str, tuple[date, bool]] = {}
    for refs, at in notices:
        no = refs.get(CANCELS_KEY) or refs.get("bid_notice_no")
        if not no:
            continue
        key = (at, CANCELS_KEY in refs)
        if no not in latest or key > latest[no]:
            latest[no] = key
    return {no for no, (_, cancelled) in latest.items() if cancelled}


def later(a: Stage, b: Stage) -> Stage:
    return a if STAGE_ORDER[a] >= STAGE_ORDER[b] else b


def is_plausible_order(
    earlier_stage: Stage, earlier_at: date, later_stage: Stage, later_at: date
) -> bool:
    """A later stage should not precede an earlier one by more than a few weeks (documents are
    sometimes published late, e.g. minutes appear 1–2 months after the session)."""
    if STAGE_ORDER[later_stage] < STAGE_ORDER[earlier_stage]:
        earlier_stage, earlier_at, later_stage, later_at = (
            later_stage,
            later_at,
            earlier_stage,
            earlier_at,
        )
    return later_at >= earlier_at - timedelta(days=60)


def forecast_bid_window(
    stage: Stage,
    observed_at: date,
    *,
    expected_year: int | None = None,
    expected_half: Half | None = None,
) -> tuple[date, date]:
    """When will the tender most likely appear?"""
    if expected_year is not None:
        if expected_half == "H1":
            start, end = date(expected_year, 1, 1), date(expected_year, 6, 30)
        elif expected_half == "H2":
            start, end = date(expected_year, 7, 1), date(expected_year, 12, 31)
        else:
            start, end = date(expected_year, 1, 15), date(expected_year, 11, 30)
        # Never forecast into the past relative to what we just observed.
        if end < observed_at:
            lo, hi = BID_LAG_DAYS[stage]
            return observed_at + timedelta(days=lo), observed_at + timedelta(days=hi)
        return max(start, observed_at), end
    lo, hi = BID_LAG_DAYS[stage]
    return observed_at + timedelta(days=lo), observed_at + timedelta(days=hi)
