"""Backtest: were the early signals right, and how early were they?

For every opportunity whose *first* signal was pre-procurement (의회 발언 or 예산 편성) and is old
enough to have had a chance to mature (``horizon_days``), did a tender (입찰공고) follow, and how
many days ahead of it did we know? Conversely, of all tenders in covered institutions, what
share had any earlier public signal?

The same numbers calibrate the ranker: conversion rate by (stage, commitment) replaces the
priors in ``domain/stages.py`` once there are enough samples.
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from datetime import date, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mulmit.clock import today_kst
from mulmit.db.models import EvalRun, Opportunity, OpportunitySignal, Signal
from mulmit.domain.stages import PRE_PROCUREMENT, Stage


async def run_backtest(
    session: AsyncSession,
    *,
    today: date | None = None,
    horizon_days: int = 540,
    min_samples: int = 5,
) -> dict[str, Any]:
    today = today or today_kst()
    rows = (
        await session.execute(
            select(Opportunity, Signal)
            .join(OpportunitySignal, OpportunitySignal.opportunity_id == Opportunity.id)
            .join(Signal, Signal.id == OpportunitySignal.signal_id)
            .order_by(Opportunity.id, Signal.observed_at)
        )
    ).all()
    by_opp: dict[int, tuple[Opportunity, list[Signal]]] = {}
    for opp, sig in rows:
        by_opp.setdefault(opp.id, (opp, []))[1].append(sig)

    cohorts: dict[str, list[int]] = defaultdict(list)  # key -> [converted 0/1]
    lead_days: list[int] = []
    lead_by_first_stage: dict[str, list[int]] = defaultdict(list)
    tenders_total = 0
    tenders_with_early = 0
    for opp, sigs in by_opp.values():
        first = sigs[0]
        bid_at = opp.bid_published_at
        if bid_at is not None and opp.category != "other":
            tenders_total += 1
            early = [
                s for s in sigs if Stage(s.stage) in PRE_PROCUREMENT and s.observed_at < bid_at
            ]
            if early:
                tenders_with_early += 1
                lead = (bid_at - early[0].observed_at).days
                lead_days.append(lead)
                lead_by_first_stage[early[0].stage].append(lead)
        if Stage(first.stage) not in PRE_PROCUREMENT:
            continue
        if first.observed_at > today - timedelta(days=horizon_days) and bid_at is None:
            continue  # too young to judge
        commitment = (
            max(
                (s.commitment for s in sigs if s.stage == first.stage and s.commitment),
                key=("declined", "reviewing", "planned", "committed").index,
                default=None,
            )
            if first.stage == Stage.COUNCIL.value
            else "committed"
        )
        converted = int(bid_at is not None)
        cohorts[f"{first.stage}:{commitment or 'none'}"].append(converted)
        cohorts[f"{first.stage}:*"].append(converted)

    conversion = {
        k: {"n": len(v), "rate": round(sum(v) / len(v), 3)} for k, v in sorted(cohorts.items()) if v
    }
    calibration = {
        k: v["rate"]
        for k, v in conversion.items()
        if v["n"] >= min_samples and not k.endswith(":*")
    }
    metrics = {
        "as_of": today.isoformat(),
        "horizon_days": horizon_days,
        "conversion_by_first_signal": conversion,
        "calibration": calibration,
        "lead_time_days": {
            "n": len(lead_days),
            "median": statistics.median(lead_days) if lead_days else None,
            "p25": statistics.quantiles(lead_days, n=4)[0] if len(lead_days) >= 4 else None,
            "p75": statistics.quantiles(lead_days, n=4)[2] if len(lead_days) >= 4 else None,
            "by_first_stage": {
                k: {"n": len(v), "median": statistics.median(v)}
                for k, v in lead_by_first_stage.items()
            },
        },
        "tender_early_coverage": {
            "tenders": tenders_total,
            "with_early_signal": tenders_with_early,
            "rate": round(tenders_with_early / tenders_total, 3) if tenders_total else None,
        },
    }
    return metrics


async def latest_calibration(session: AsyncSession) -> dict[str, float] | None:
    run = await session.scalar(
        select(EvalRun)
        .where(EvalRun.kind == "backtest")
        .order_by(EvalRun.created_at.desc())
        .limit(1)
    )
    if run is None:
        return None
    cal = run.metrics.get("calibration")
    return {str(k): float(v) for k, v in cal.items()} if isinstance(cal, dict) else None
