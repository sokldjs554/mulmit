"""Subscriptions, renewals with dunning, credit packs."""

from __future__ import annotations

import uuid
from calendar import monthrange
from datetime import UTC, datetime, timedelta

from cryptography.fernet import Fernet
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.billing.ledger import apply_credits, expire_plan_credits
from app.billing.plans import CREDIT_PACKS, DUNNING_SCHEDULE_DAYS, PLANS
from app.billing.toss import (
    FakePaymentProvider,
    PaymentDeclinedError,
    PaymentProvider,
    PaymentUnavailableError,
    TossPaymentsClient,
)
from app.db.models import Organization, Payment, Subscription
from app.log import get_logger
from app.settings import Settings

log = get_logger(__name__)

_fake_singleton = FakePaymentProvider()


class BillingError(Exception):
    pass


def build_payment_provider(settings: Settings) -> PaymentProvider:
    if settings.payment_provider == "toss":
        if not settings.toss_secret_key:
            raise BillingError("APP_TOSS_SECRET_KEY is not configured")
        return TossPaymentsClient(settings.toss_secret_key.get_secret_value())
    return _fake_singleton


def _fernet(settings: Settings) -> Fernet:
    return Fernet(settings.billing_key_encryption_key.get_secret_value().encode())


def add_month(dt: datetime) -> datetime:
    year, month = (dt.year + 1, 1) if dt.month == 12 else (dt.year, dt.month + 1)
    day = min(dt.day, monthrange(year, month)[1])
    return dt.replace(year=year, month=month, day=day)


def period_key(start: datetime) -> str:
    """Identifies one billing period. Second precision: an upgrade on the day of signup starts a
    new period that must not collide with the free period that began the same morning."""
    return start.astimezone(UTC).strftime("%Y%m%dT%H%M%S")


async def ensure_subscription(session: AsyncSession, org: Organization) -> Subscription:
    sub = await session.get(Subscription, org.id)
    if sub is None:
        sub = Subscription(
            org_id=org.id,
            plan="free",
            status="active",
            customer_key=f"cus_{uuid.uuid4().hex}",
            failed_attempts=0,
        )
        session.add(sub)
        await session.flush()
    return sub


async def register_card(
    session: AsyncSession,
    settings: Settings,
    provider: PaymentProvider,
    org: Organization,
    *,
    auth_key: str,
    customer_key: str,
) -> Subscription:
    sub = await ensure_subscription(session, org)
    if customer_key != sub.customer_key:
        raise BillingError("customerKey mismatch")
    result = await provider.issue_billing_key(auth_key, customer_key)
    sub.billing_key_enc = _fernet(settings).encrypt(result.billing_key.encode()).decode()
    sub.card_summary = result.card_summary
    await session.flush()
    return sub


async def _charge(
    session: AsyncSession,
    settings: Settings,
    provider: PaymentProvider,
    org_id: int,
    sub: Subscription,
    *,
    amount: int,
    order_id: str,
    order_name: str,
    kind: str,
) -> Payment:
    if not sub.billing_key_enc:
        raise BillingError("등록된 결제수단이 없습니다")
    existing = await session.scalar(select(Payment).where(Payment.order_id == order_id))
    if existing is not None and existing.status == "paid":
        return existing
    payment = existing or Payment(
        org_id=org_id,
        order_id=order_id,
        kind=kind,
        order_name=order_name,
        amount=amount,
        status="pending",
        provider=provider.name,
    )
    session.add(payment)
    await session.flush()
    billing_key = _fernet(settings).decrypt(sub.billing_key_enc.encode()).decode()
    try:
        result = await provider.charge(
            billing_key=billing_key,
            customer_key=sub.customer_key,
            amount=amount,
            order_id=order_id,
            order_name=order_name,
            idempotency_key=order_id,
        )
    except PaymentDeclinedError as exc:
        payment.status = "failed"
        payment.failure_code, payment.failure_message = exc.code, exc.message
        await session.flush()
        raise
    except PaymentUnavailableError:
        # Outcome unknown: leave it pending; the reconcile job asks Toss by orderId.
        await session.flush()
        raise
    payment.status = "paid" if result.status == "DONE" else "failed"
    payment.provider_payment_key = result.payment_key
    payment.paid_at = result.approved_at
    payment.raw = {k: v for k, v in result.raw.items() if k not in ("card", "billingKey")}
    await session.flush()
    return payment


async def start_period(
    session: AsyncSession, org: Organization, sub: Subscription, now: datetime
) -> None:
    plan = PLANS[sub.plan]
    sub.current_period_start = now
    sub.current_period_end = add_month(now)
    sub.next_charge_at = sub.current_period_end if plan.monthly_price_krw else None
    sub.status = "active"
    sub.failed_attempts = 0
    org.plan = sub.plan
    key = period_key(now)
    await apply_credits(
        session,
        org_id=org.id,
        delta=plan.monthly_credits,
        reason="plan_grant",
        idempotency_key=f"grant:{org.id}:{sub.plan}:{key}",
        ref_type="period",
        ref_id=key,
    )


async def change_plan(
    session: AsyncSession,
    settings: Settings,
    provider: PaymentProvider,
    org: Organization,
    plan_key: str,
    *,
    request_id: str,
    now: datetime | None = None,
) -> Subscription:
    if plan_key not in PLANS:
        raise BillingError(f"unknown plan {plan_key}")
    now = now or datetime.now(UTC)
    sub = await ensure_subscription(session, org)
    plan = PLANS[plan_key]
    if plan.monthly_price_krw == 0:
        # Downgrade at period end; keep what was paid for.
        sub.canceled_at = now
        await session.flush()
        return sub
    order_id = f"sub_{org.id}_{plan_key}_{request_id}"[:64]
    already = await session.scalar(
        select(Payment).where(Payment.order_id == order_id, Payment.status == "paid")
    )
    if already is not None and sub.plan == plan_key:
        return sub  # the same request was already applied (double click / client retry)
    await _charge(
        session,
        settings,
        provider,
        org.id,
        sub,
        amount=plan.monthly_price_krw,
        order_id=order_id,
        order_name=f"발주 예측 {plan.name} 월 구독",
        kind="subscription",
    )
    if sub.current_period_start and sub.current_period_end:
        await expire_plan_credits(
            session, org.id, period_key(sub.current_period_start), sub.current_period_start, now
        )
    sub.plan = plan_key
    sub.canceled_at = None
    await start_period(session, org, sub, now)
    await session.flush()
    return sub


async def renew_due(
    session: AsyncSession,
    settings: Settings,
    provider: PaymentProvider,
    *,
    now: datetime | None = None,
) -> dict[str, int]:
    """Charge every subscription whose period ended. Safe to run repeatedly (hourly cron)."""
    now = now or datetime.now(UTC)
    stats = {"renewed": 0, "failed": 0, "downgraded": 0, "pending": 0}
    due = (
        await session.scalars(
            select(Subscription)
            .where(
                Subscription.status.in_(("active", "past_due")),
                Subscription.next_charge_at.is_not(None),
                Subscription.next_charge_at <= now,
            )
            .with_for_update(skip_locked=True)
        )
    ).all()
    for sub in due:
        org = await session.get(Organization, sub.org_id)
        assert org is not None
        start = sub.current_period_start or now
        end = sub.current_period_end or now
        if sub.canceled_at is not None:
            await expire_plan_credits(session, org.id, period_key(start), start, end)
            sub.plan, sub.status, sub.next_charge_at = "free", "canceled", None
            org.plan = "free"
            stats["downgraded"] += 1
            continue
        plan = PLANS[sub.plan]
        attempt = sub.failed_attempts + 1
        try:
            await _charge(
                session,
                settings,
                provider,
                org.id,
                sub,
                amount=plan.monthly_price_krw,
                order_id=f"sub_{org.id}_{sub.plan}_{period_key(end)}_a{attempt}",
                order_name=f"발주 예측 {plan.name} 월 구독",
                kind="subscription",
            )
        except PaymentDeclinedError as exc:
            sub.failed_attempts = attempt
            if attempt > len(DUNNING_SCHEDULE_DAYS):
                sub.plan, sub.status, sub.next_charge_at = "free", "canceled", None
                org.plan = "free"
                stats["downgraded"] += 1
            else:
                sub.status = "past_due"
                sub.next_charge_at = now + timedelta(days=DUNNING_SCHEDULE_DAYS[attempt - 1])
                stats["failed"] += 1
            log.warning("billing.renewal_declined", org_id=org.id, attempt=attempt, code=exc.code)
            continue
        except PaymentUnavailableError:
            stats["pending"] += 1
            continue
        await expire_plan_credits(session, org.id, period_key(start), start, end)
        await start_period(session, org, sub, max(end, now - timedelta(days=1)))
        stats["renewed"] += 1
    await session.flush()
    return stats


async def purchase_credits(
    session: AsyncSession,
    settings: Settings,
    provider: PaymentProvider,
    org: Organization,
    pack_key: str,
    *,
    request_id: str,
) -> Payment:
    if pack_key not in CREDIT_PACKS:
        raise BillingError(f"unknown credit pack {pack_key}")
    credits, price = CREDIT_PACKS[pack_key]
    sub = await ensure_subscription(session, org)
    payment = await _charge(
        session,
        settings,
        provider,
        org.id,
        sub,
        amount=price,
        order_id=f"cred_{org.id}_{request_id}"[:64],
        order_name=f"발주 예측 크레딧 {credits}개",
        kind="credit_pack",
    )
    await apply_credits(
        session,
        org_id=org.id,
        delta=credits,
        reason="purchase",
        idempotency_key=f"purchase:{payment.order_id}",
        ref_type="payment",
        ref_id=payment.order_id,
    )
    return payment


async def reconcile_payment(
    session: AsyncSession, provider: PaymentProvider, order_id: str
) -> Payment | None:
    """Webhook/cron: trust only what the provider API says about an order."""
    payment = await session.scalar(select(Payment).where(Payment.order_id == order_id))
    if payment is None:
        return None
    remote = await provider.get_payment_by_order(order_id)
    if remote is None:
        return payment
    if remote.status == "DONE" and payment.status != "paid":
        payment.status = "paid"
        payment.provider_payment_key = remote.payment_key
        payment.paid_at = remote.approved_at
        if payment.kind == "credit_pack":
            credits = next((c for c, p in CREDIT_PACKS.values() if p == payment.amount), 0)
            if credits:
                await apply_credits(
                    session,
                    org_id=payment.org_id,
                    delta=credits,
                    reason="purchase",
                    idempotency_key=f"purchase:{payment.order_id}",
                    ref_type="payment",
                    ref_id=payment.order_id,
                )
    elif remote.status in ("CANCELED", "ABORTED", "EXPIRED") and payment.status == "pending":
        payment.status = "canceled" if remote.status == "CANCELED" else "failed"
    await session.flush()
    return payment
