"""Credit ledger — append-only, idempotent, never negative.

Invariants, enforced by the database rather than by hope:

* every movement is a row in ``credit_ledger`` with a unique ``idempotency_key`` — a retried
  webhook, a double-clicked "브리프 생성" button or a re-run renewal job cannot apply twice;
* the org row is locked (``SELECT … FOR UPDATE``) while the new balance is computed, so two
  concurrent spends cannot both see the same balance;
* ``balance_after >= 0`` is a CHECK constraint — an insufficient balance fails the transaction.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import CreditLedgerEntry, Organization


class InsufficientCreditsError(Exception):
    def __init__(self, balance: int, needed: int) -> None:
        super().__init__(f"insufficient credits: balance {balance}, needed {needed}")
        self.balance = balance
        self.needed = needed


@dataclass(frozen=True, slots=True)
class LedgerResult:
    entry: CreditLedgerEntry
    applied: bool  # False when the idempotency key had already been used


async def apply_credits(
    session: AsyncSession,
    *,
    org_id: int,
    delta: int,
    reason: str,
    idempotency_key: str,
    ref_type: str | None = None,
    ref_id: str | None = None,
    actor_user_id: int | None = None,
) -> LedgerResult:
    existing = await session.scalar(
        select(CreditLedgerEntry).where(CreditLedgerEntry.idempotency_key == idempotency_key)
    )
    if existing is not None:
        return LedgerResult(existing, applied=False)

    org = await session.scalar(
        select(Organization).where(Organization.id == org_id).with_for_update()
    )
    if org is None:
        raise LookupError(f"organization {org_id} not found")
    new_balance = org.credit_balance + delta
    if new_balance < 0:
        raise InsufficientCreditsError(org.credit_balance, -delta)
    entry = CreditLedgerEntry(
        org_id=org_id,
        delta=delta,
        balance_after=new_balance,
        reason=reason,
        ref_type=ref_type,
        ref_id=ref_id,
        idempotency_key=idempotency_key,
        actor_user_id=actor_user_id,
    )
    org.credit_balance = new_balance
    session.add(entry)
    await session.flush()
    return LedgerResult(entry, applied=True)


async def expire_plan_credits(
    session: AsyncSession,
    org_id: int,
    period_key: str,
    period_start: datetime,
    period_end: datetime,
) -> int:
    """At period end, remove what is left of the plan grant (purchased credits survive).

    Remaining plan credits = min(balance, plan grants this period − spends this period, ≥0).
    Spends are attributed to plan credits first (FIFO by expiry)."""
    granted = (
        await session.scalar(
            select(func.coalesce(func.sum(CreditLedgerEntry.delta), 0)).where(
                CreditLedgerEntry.org_id == org_id,
                CreditLedgerEntry.reason == "plan_grant",
                CreditLedgerEntry.ref_id == period_key,
            )
        )
        or 0
    )
    # Row timestamps are the transaction start; allow a little slack at the period edges.
    slack = timedelta(seconds=5)
    spent = -(
        await session.scalar(
            select(func.coalesce(func.sum(CreditLedgerEntry.delta), 0)).where(
                CreditLedgerEntry.org_id == org_id,
                CreditLedgerEntry.reason.in_(("brief", "refund")),
                CreditLedgerEntry.created_at >= period_start - slack,
                CreditLedgerEntry.created_at < period_end + slack,
            )
        )
        or 0
    )
    org = await session.get(Organization, org_id)
    if org is None:
        return 0
    remaining = max(0, min(org.credit_balance, granted - spent))
    if remaining:
        await apply_credits(
            session,
            org_id=org_id,
            delta=-remaining,
            reason="expiry",
            idempotency_key=f"expiry:{org_id}:{period_key}",
            ref_type="period",
            ref_id=period_key,
        )
    return remaining
