"""Toss Payments 자동결제(빌링) client + a fake provider for local development.

Flow (https://docs.tosspayments.com/guides/v2/billing):

1. Browser: ``tossPayments.payment({customerKey}).requestBillingAuth({method: "CARD", …})`` →
   redirect to our success URL with ``authKey`` and ``customerKey``.
2. Server: ``POST /v1/billing/authorizations/issue {authKey, customerKey}`` → ``billingKey``.
   We store it encrypted (Fernet) — it is a reusable card credential.
3. Renewals: ``POST /v1/billing/{billingKey} {customerKey, amount, orderId, orderName}`` with an
   ``Idempotency-Key`` header so a retried job cannot charge twice.

Webhooks (``PAYMENT_STATUS_CHANGED``) are treated as *hints*: we re-fetch the payment by
``orderId`` from the API before changing any state, so a forged webhook cannot mark an order paid.
"""

from __future__ import annotations

import base64
import hashlib
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol

import httpx

TOSS_BASE_URL = "https://api.tosspayments.com"


class PaymentDeclinedError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


class PaymentUnavailableError(Exception):
    """Network error / 5xx — the outcome is unknown; reconcile by orderId before retrying."""


@dataclass(frozen=True, slots=True)
class BillingKeyResult:
    billing_key: str
    card_summary: str


@dataclass(frozen=True, slots=True)
class ChargeResult:
    payment_key: str
    order_id: str
    status: str  # DONE | CANCELED | ABORTED | …
    amount: int
    approved_at: datetime | None
    raw: dict[str, Any] = field(default_factory=dict)


class PaymentProvider(Protocol):
    name: str

    async def issue_billing_key(self, auth_key: str, customer_key: str) -> BillingKeyResult: ...

    async def charge(
        self,
        *,
        billing_key: str,
        customer_key: str,
        amount: int,
        order_id: str,
        order_name: str,
        idempotency_key: str,
    ) -> ChargeResult: ...

    async def get_payment_by_order(self, order_id: str) -> ChargeResult | None: ...


def _parse_payment(data: dict[str, Any]) -> ChargeResult:
    approved = data.get("approvedAt")
    return ChargeResult(
        payment_key=str(data.get("paymentKey", "")),
        order_id=str(data.get("orderId", "")),
        status=str(data.get("status", "")),
        amount=int(data.get("totalAmount") or 0),
        approved_at=datetime.fromisoformat(approved) if approved else None,
        raw=data,
    )


class TossPaymentsClient:
    name = "toss"

    def __init__(
        self,
        secret_key: str,
        *,
        timeout: float = 15.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        token = base64.b64encode(f"{secret_key}:".encode()).decode()
        self._client = httpx.AsyncClient(
            base_url=TOSS_BASE_URL,
            headers={"Authorization": f"Basic {token}", "Content-Type": "application/json"},
            timeout=httpx.Timeout(timeout, connect=5.0),
            transport=transport,
        )

    async def _post(
        self, path: str, body: dict[str, Any], idempotency_key: str | None = None
    ) -> dict[str, Any]:
        headers = {"Idempotency-Key": idempotency_key} if idempotency_key else {}
        try:
            resp = await self._client.post(path, json=body, headers=headers)
        except httpx.HTTPError as exc:
            raise PaymentUnavailableError(str(exc)) from exc
        if resp.status_code >= 500:
            raise PaymentUnavailableError(f"toss {resp.status_code}")
        data: dict[str, Any] = resp.json()
        if resp.status_code >= 400:
            raise PaymentDeclinedError(
                str(data.get("code", "UNKNOWN")), str(data.get("message", ""))
            )
        return data

    async def issue_billing_key(self, auth_key: str, customer_key: str) -> BillingKeyResult:
        data = await self._post(
            "/v1/billing/authorizations/issue", {"authKey": auth_key, "customerKey": customer_key}
        )
        card = data.get("card") or {}
        company = data.get("cardCompany") or card.get("issuerCode") or "카드"
        number = str(data.get("cardNumber") or card.get("number") or "")
        return BillingKeyResult(str(data["billingKey"]), f"{company} ****{number[-4:]}")

    async def charge(
        self,
        *,
        billing_key: str,
        customer_key: str,
        amount: int,
        order_id: str,
        order_name: str,
        idempotency_key: str,
    ) -> ChargeResult:
        data = await self._post(
            f"/v1/billing/{billing_key}",
            {
                "customerKey": customer_key,
                "amount": amount,
                "orderId": order_id,
                "orderName": order_name,
            },
            idempotency_key=idempotency_key,
        )
        return _parse_payment(data)

    async def get_payment_by_order(self, order_id: str) -> ChargeResult | None:
        try:
            resp = await self._client.get(f"/v1/payments/orders/{order_id}")
        except httpx.HTTPError as exc:
            raise PaymentUnavailableError(str(exc)) from exc
        if resp.status_code == 404:
            return None
        if resp.status_code >= 400:
            raise PaymentUnavailableError(f"toss {resp.status_code}")
        return _parse_payment(resp.json())


class FakePaymentProvider:
    """Deterministic stand-in: auth keys starting with ``fail`` are rejected at issue time,
    billing keys derived from them decline at charge time when the key contains ``decline``."""

    name = "fake"

    def __init__(self) -> None:
        self.charges: dict[str, ChargeResult] = {}

    async def issue_billing_key(self, auth_key: str, customer_key: str) -> BillingKeyResult:
        if auth_key.startswith("fail"):
            raise PaymentDeclinedError("INVALID_CARD", "테스트 카드 인증 실패")
        digest = hashlib.sha256(f"{auth_key}:{customer_key}".encode()).hexdigest()[:16]
        tag = "decline_" if "decline" in auth_key else ""
        return BillingKeyResult(f"bk_fake_{tag}{digest}", "테스트카드 ****4242")

    async def charge(
        self,
        *,
        billing_key: str,
        customer_key: str,
        amount: int,
        order_id: str,
        order_name: str,
        idempotency_key: str,
    ) -> ChargeResult:
        if idempotency_key in self.charges:
            return self.charges[idempotency_key]
        if "decline" in billing_key:
            raise PaymentDeclinedError("REJECT_CARD_PAYMENT", "한도초과 혹은 잔액부족")
        result = ChargeResult(
            payment_key=f"pay_fake_{hashlib.sha256(order_id.encode()).hexdigest()[:20]}",
            order_id=order_id,
            status="DONE",
            amount=amount,
            approved_at=datetime.now(UTC),
            raw={"orderName": order_name, "provider": "fake"},
        )
        self.charges[idempotency_key] = result
        return result

    async def get_payment_by_order(self, order_id: str) -> ChargeResult | None:
        return next((c for c in self.charges.values() if c.order_id == order_id), None)
