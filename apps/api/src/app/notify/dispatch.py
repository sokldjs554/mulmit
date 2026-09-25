"""Turn recommendations into notifications, and notifications into deliveries.

Two separate steps so that *what to say* (idempotent, keyed by ``dedupe_key``) is decided once,
and *delivering it* (flaky external services) can be retried independently per channel:

* ``enqueue_alerts`` — for each org, new or stage-advanced recommendations above the org's
  threshold become one notification per channel (instant mode) or one digest per channel.
  An opportunity advancing from 의회 발언 to 예산 편성 is news again; the same stage is not.
* ``deliver_pending`` — sends due notifications with ``FOR UPDATE SKIP LOCKED`` (several workers
  can run it), honours quiet hours in KST, retries transient failures with backoff and disables a
  channel after a permanent failure (revoked Slack webhook, invalid number).
"""

from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.billing.plans import PLANS
from app.clock import KST
from app.db.models import (
    AlertChannel,
    AlertRule,
    InstitutionRow,
    Notification,
    Opportunity,
    OpportunitySignal,
    Organization,
    Recommendation,
    Signal,
)
from app.domain.krw import format_krw
from app.domain.stages import STAGE_LABEL, STAGE_ORDER, Stage
from app.log import get_logger
from app.notify.channels import Channel, PermanentDeliveryError, TransientDeliveryError

log = get_logger(__name__)
MAX_ATTEMPTS = 5


def _when_label(opp: Opportunity) -> str:
    """The timing half of an alert line: when the tender came out, or when we expect it."""
    if opp.bid_published_at:
        return f"{opp.bid_published_at:%Y.%m.%d} 입찰공고"
    start, end = opp.bid_window_start, opp.bid_window_end
    if start is None:
        return "입찰 시기 미정"
    if end is None or (start.year, start.month) == (end.year, end.month):
        return f"입찰 예상 {start.year}년 {start.month}월"
    if start.year == end.year:
        return f"입찰 예상 {start.year}년 {start.month}~{end.month}월"
    return f"입찰 예상 {start.year}년 {start.month}월~{end.year}년 {end.month}월"


async def _best_evidence(session: AsyncSession, opp_id: int) -> tuple[str | None, str | None]:
    """(quote, note) for an alert line. People read a council answer; a budget-book row
    ("세부사업: …  197,000  0  197,000") means nothing out of its table, so it becomes a sentence."""
    rows = (
        await session.scalars(
            select(Signal)
            .join(OpportunitySignal, OpportunitySignal.signal_id == Signal.id)
            .where(OpportunitySignal.opportunity_id == opp_id)
            .order_by(Signal.observed_at.desc())
        )
    ).all()
    budget_row: Signal | None = None
    for s in rows:
        if s.stage == "council_mention":
            for ev in s.evidence:
                if ev.get("found"):
                    quote = str(ev.get("quote", ""))
                    return quote[:140] + ("…" if len(quote) > 140 else ""), None
        elif s.stage == "budget_line" and s.budget_krw and budget_row is None:
            budget_row = s
    if budget_row is not None and budget_row.budget_krw:
        year = f"{budget_row.expected_year}년도 " if budget_row.expected_year else ""
        return None, f"{year}예산서에 {format_krw(budget_row.budget_krw)}이 편성돼 있어요."
    return None, None


async def build_items(
    session: AsyncSession, recs: list[tuple[Recommendation, Opportunity]], web_url: str
) -> list[dict[str, Any]]:
    names = dict((await session.execute(select(InstitutionRow.code, InstitutionRow.name))).all())
    items = []
    for rec, opp in recs:
        quote, note = await _best_evidence(session, opp.id)
        items.append(
            {
                "opportunity_id": opp.id,
                "title": opp.title,
                "institution": names.get(opp.institution_code or "", "기관 미상"),
                "stage": opp.stage,
                "stage_label": STAGE_LABEL[Stage(opp.stage)],
                "budget": format_krw(opp.est_budget_krw) if opp.est_budget_krw else None,
                "when": _when_label(opp),
                "score_pct": round(rec.score * 100),
                "evidence": quote,
                "evidence_note": note,
                "url": f"{web_url}/app/opportunities/{opp.id}",
            }
        )
    return items


def _stage_advanced(rec: Recommendation, opp: Opportunity) -> bool:
    if rec.notified_stage is None:
        return True
    return STAGE_ORDER[Stage(opp.stage)] > STAGE_ORDER[Stage(rec.notified_stage)]


async def enqueue_alerts(
    session: AsyncSession,
    org_id: int,
    *,
    web_url: str,
    mode_filter: str | None = None,
    now: datetime | None = None,
) -> int:
    now = now or datetime.now(UTC)
    org = await session.get(Organization, org_id)
    rule = await session.get(AlertRule, org_id)
    if org is None or rule is None:
        return 0
    if mode_filter and rule.mode != mode_filter:
        return 0
    plan = PLANS[org.plan]
    if rule.mode == "instant" and not plan.instant_alerts:
        return 0
    channels = (
        await session.scalars(
            select(AlertChannel).where(
                AlertChannel.org_id == org_id, AlertChannel.enabled.is_(True)
            )
        )
    ).all()
    channels = [c for c in channels if c.kind in plan.channels]
    if not channels:
        return 0
    rows = (
        await session.execute(
            select(Recommendation, Opportunity)
            .join(Opportunity, Opportunity.id == Recommendation.opportunity_id)
            .where(
                Recommendation.org_id == org_id,
                Recommendation.score >= rule.min_score,
                Recommendation.feedback.is_(None) | (Recommendation.feedback == "relevant"),
                Opportunity.status.in_(("open", "bid_open")),
            )
            .order_by(Recommendation.score.desc())
        )
    ).all()
    fresh = [
        (rec, opp)
        for rec, opp in rows
        if (not rule.stages or opp.stage in rule.stages) and _stage_advanced(rec, opp)
    ]
    if not fresh:
        return 0
    created = 0
    # A digest shows the top 15 and counts the rest; everything fresh is marked as told, so the
    # remainder does not trickle out as tomorrow's "new" items.
    batches = [[pair] for pair in fresh[:20]] if rule.mode == "instant" else [fresh[:15]]
    more = 0 if rule.mode == "instant" else max(len(fresh) - 15, 0)
    for batch in batches:
        items = await build_items(session, batch, web_url)
        local = now.astimezone(KST)
        headline = (
            f"{items[0]['institution']} · {items[0]['title']}"
            if rule.mode == "instant"
            else f"{local.month}월 {local.day}일, 새로 찾은 사업 {len(items) + more}건"
        )
        payload = {
            "org_name": org.name,
            "headline": headline,
            "items": items,
            "more": more,
            "feed_url": f"{web_url}/app",
            "settings_url": f"{web_url}/app/alerts",
        }
        ids = ",".join(f"{i['opportunity_id']}:{i['stage']}" for i in items)
        digest = hashlib.sha256(ids.encode()).hexdigest()[:16]
        for ch in channels:
            key = f"{rule.mode}:{org_id}:{ch.id}:{digest}"
            result = await session.execute(
                insert(Notification)
                .values(
                    org_id=org_id,
                    channel_id=ch.id,
                    kind=rule.mode,
                    dedupe_key=key,
                    payload=payload,
                    status="pending",
                    scheduled_at=now,
                )
                .on_conflict_do_nothing(index_elements=["dedupe_key"])
            )
            created += int(result.rowcount or 0)  # type: ignore[attr-defined]
    for rec, opp in fresh if rule.mode != "instant" else fresh[:20]:
        rec.notified_stage = opp.stage
    await session.flush()
    return created


def _quiet_until(now: datetime, quiet_start: int, quiet_end: int) -> datetime | None:
    local = now.astimezone(KST)
    hour = local.hour
    in_quiet = (
        quiet_start <= hour or hour < quiet_end
        if quiet_start > quiet_end
        else quiet_start <= hour < quiet_end
    )
    if not in_quiet or quiet_start == quiet_end:
        return None
    resume = local.replace(hour=quiet_end, minute=0, second=0, microsecond=0)
    if resume <= local:
        resume += timedelta(days=1)
    return resume.astimezone(UTC)


async def deliver_pending(
    session: AsyncSession,
    channels: dict[str, Channel],
    *,
    now: datetime | None = None,
    limit: int = 100,
) -> dict[str, int]:
    now = now or datetime.now(UTC)
    stats = {"sent": 0, "retry": 0, "failed": 0, "deferred": 0}
    pending = (
        await session.scalars(
            select(Notification)
            .where(Notification.status == "pending", Notification.scheduled_at <= now)
            .order_by(Notification.scheduled_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
    ).all()
    for note in pending:
        channel_row = await session.get(AlertChannel, note.channel_id)
        rule = await session.get(AlertRule, note.org_id)
        if channel_row is None or not channel_row.enabled:
            note.status = "skipped"
            continue
        if rule is not None and note.kind != "test":
            resume = _quiet_until(now, rule.quiet_start, rule.quiet_end)
            if resume is not None:
                note.scheduled_at = resume
                stats["deferred"] += 1
                continue
        channel = channels[channel_row.kind]
        note.attempts += 1
        try:
            await channel.send(channel_row.target, note.payload)
        except TransientDeliveryError as exc:
            note.last_error = str(exc)[:1000]
            if note.attempts >= MAX_ATTEMPTS:
                note.status = "failed"
                stats["failed"] += 1
            else:
                note.scheduled_at = now + timedelta(minutes=5 * 2 ** (note.attempts - 1))
                stats["retry"] += 1
            continue
        except PermanentDeliveryError as exc:
            note.status = "failed"
            note.last_error = str(exc)[:1000]
            channel_row.enabled = False
            channel_row.last_error = str(exc)[:1000]
            stats["failed"] += 1
            log.warning("notify.channel_disabled", channel_id=channel_row.id, error=str(exc))
            continue
        note.status = "sent"
        note.sent_at = now
        stats["sent"] += 1
    await session.flush()
    return stats


def today_kst(now: datetime | None = None) -> date:
    return (now or datetime.now(UTC)).astimezone(KST).date()
