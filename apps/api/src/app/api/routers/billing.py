from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Header, HTTPException, Request, status
from sqlalchemy import select

from app.api.deps import PrincipalDep, SessionDep, SettingsDep
from app.api.schemas import (
    BillingOut,
    CardIn,
    CreditPackOut,
    CreditPurchaseIn,
    LedgerOut,
    PaymentOut,
    PlanChangeIn,
    PlanOut,
    SubscriptionOut,
)
from app.billing.plans import BRIEF_CREDIT_COST, CREDIT_PACKS, PLANS
from app.billing.service import (
    BillingError,
    build_payment_provider,
    change_plan,
    ensure_subscription,
    purchase_credits,
    reconcile_payment,
    register_card,
)
from app.billing.toss import PaymentDeclinedError, PaymentUnavailableError
from app.db.models import CreditLedgerEntry, Payment
from app.log import get_logger

router = APIRouter(prefix="/api/billing", tags=["billing"])
log = get_logger(__name__)

IdempotencyKey = Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=64)]


def _payment_error(exc: Exception) -> HTTPException:
    if isinstance(exc, PaymentDeclinedError):
        return HTTPException(
            status.HTTP_402_PAYMENT_REQUIRED, f"결제가 거절되었습니다: {exc.message}"
        )
    if isinstance(exc, PaymentUnavailableError):
        return HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "결제사 응답이 지연되고 있습니다. 잠시 후 확인해 주세요",
        )
    return HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


@router.get("", response_model=BillingOut)
async def billing(
    principal: PrincipalDep, session: SessionDep, settings: SettingsDep
) -> BillingOut:
    sub = await ensure_subscription(session, principal.org)
    ledger = await session.scalars(
        select(CreditLedgerEntry)
        .where(CreditLedgerEntry.org_id == principal.org.id)
        .order_by(CreditLedgerEntry.id.desc())
        .limit(30)
    )
    payments = await session.scalars(
        select(Payment)
        .where(Payment.org_id == principal.org.id)
        .order_by(Payment.id.desc())
        .limit(20)
    )
    return BillingOut(
        subscription=SubscriptionOut.model_validate(sub),
        credit_balance=principal.org.credit_balance,
        brief_cost=BRIEF_CREDIT_COST,
        plans=[
            PlanOut(
                key=p.key,
                name=p.name,
                monthly_price_krw=p.monthly_price_krw,
                monthly_credits=p.monthly_credits,
                max_regions=p.max_regions,
                channels=list(p.channels),
                instant_alerts=p.instant_alerts,
            )
            for p in PLANS.values()
        ],
        credit_packs=[
            CreditPackOut(key=k, credits=c, price_krw=p) for k, (c, p) in CREDIT_PACKS.items()
        ],
        ledger=[LedgerOut.model_validate(e) for e in ledger],
        payments=[PaymentOut.model_validate(p) for p in payments],
        payment_provider=settings.payment_provider,
        toss_client_key=settings.toss_client_key,
        customer_key=sub.customer_key,
    )


@router.post("/card", response_model=SubscriptionOut)
async def card(
    body: CardIn, principal: PrincipalDep, session: SessionDep, settings: SettingsDep
) -> SubscriptionOut:
    try:
        sub = await register_card(
            session,
            settings,
            build_payment_provider(settings),
            principal.org,
            auth_key=body.auth_key,
            customer_key=body.customer_key,
        )
    except (BillingError, PaymentDeclinedError, PaymentUnavailableError) as exc:
        raise _payment_error(exc) from exc
    return SubscriptionOut.model_validate(sub)


@router.post("/plan", response_model=SubscriptionOut)
async def plan(
    body: PlanChangeIn,
    principal: PrincipalDep,
    session: SessionDep,
    settings: SettingsDep,
    idempotency_key: IdempotencyKey,
) -> SubscriptionOut:
    try:
        sub = await change_plan(
            session,
            settings,
            build_payment_provider(settings),
            principal.org,
            body.plan,
            request_id=idempotency_key,
        )
    except (BillingError, PaymentDeclinedError, PaymentUnavailableError) as exc:
        await session.commit()  # keep the failed Payment row for the audit trail
        raise _payment_error(exc) from exc
    return SubscriptionOut.model_validate(sub)


@router.post("/credits", response_model=PaymentOut)
async def credits(
    body: CreditPurchaseIn,
    principal: PrincipalDep,
    session: SessionDep,
    settings: SettingsDep,
    idempotency_key: IdempotencyKey,
) -> PaymentOut:
    try:
        payment = await purchase_credits(
            session,
            settings,
            build_payment_provider(settings),
            principal.org,
            body.pack,
            request_id=idempotency_key,
        )
    except (BillingError, PaymentDeclinedError, PaymentUnavailableError) as exc:
        await session.commit()
        raise _payment_error(exc) from exc
    return PaymentOut.model_validate(payment)


webhook_router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])


@webhook_router.post("/toss", status_code=status.HTTP_200_OK)
async def toss_webhook(
    request: Request, session: SessionDep, settings: SettingsDep
) -> dict[str, Any]:
    """Toss retries until it gets a 200, so always answer 200 and reconcile against the API."""
    try:
        body = await request.json()
    except ValueError:
        return {"ok": False}
    data = body.get("data") or {}
    order_id = data.get("orderId")
    if body.get("eventType") == "PAYMENT_STATUS_CHANGED" and isinstance(order_id, str):
        try:
            await reconcile_payment(session, build_payment_provider(settings), order_id)
        except PaymentUnavailableError:
            log.warning("toss.webhook.reconcile_deferred", order_id=order_id)
    return {"ok": True}
