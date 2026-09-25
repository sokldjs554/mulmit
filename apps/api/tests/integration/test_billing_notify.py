import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import select

from app.billing.ledger import InsufficientCreditsError, apply_credits
from app.billing.service import (
    build_payment_provider,
    change_plan,
    ensure_subscription,
    register_card,
    renew_due,
)
from app.db.models import AlertChannel, AlertRule, Notification, Organization, Subscription
from app.db.session import session_scope
from app.notify.channels import PermanentDeliveryError
from app.notify.dispatch import deliver_pending, enqueue_alerts


async def _new_org(name: str, credits: int = 0) -> int:
    async with session_scope() as s:
        org = Organization(name=name, plan="free", credit_balance=0)
        s.add(org)
        await s.flush()
        if credits:
            await apply_credits(
                s,
                org_id=org.id,
                delta=credits,
                reason="adjustment",
                idempotency_key=f"seed:{org.id}",
            )
        return org.id


async def test_concurrent_spends_cannot_overdraw(demo_world) -> None:  # type: ignore[no-untyped-def]
    org_id = await _new_org("동시성", credits=3)

    async def spend(key: str) -> str:
        try:
            async with session_scope() as s:
                await apply_credits(s, org_id=org_id, delta=-3, reason="brief", idempotency_key=key)
                await asyncio.sleep(0.05)  # hold the row lock while the other tries
            return "ok"
        except InsufficientCreditsError:
            return "insufficient"

    results = await asyncio.gather(spend("a"), spend("b"))
    assert sorted(results) == ["insufficient", "ok"]
    async with session_scope() as s:
        org = await s.get(Organization, org_id)
        assert org is not None and org.credit_balance == 0


async def test_ledger_idempotency(demo_world) -> None:  # type: ignore[no-untyped-def]
    org_id = await _new_org("멱등", credits=10)
    async with session_scope() as s:
        first = await apply_credits(
            s, org_id=org_id, delta=-3, reason="brief", idempotency_key="same"
        )
        second = await apply_credits(
            s, org_id=org_id, delta=-3, reason="brief", idempotency_key="same"
        )
        assert first.applied and not second.applied
        org = await s.get(Organization, org_id)
        assert org is not None and org.credit_balance == 7


async def test_renewal_dunning_then_downgrade(demo_world, runtime) -> None:  # type: ignore[no-untyped-def]
    settings = runtime.settings
    provider = build_payment_provider(settings)
    org_id = await _new_org("던닝")
    now = datetime(2026, 9, 1, tzinfo=UTC)
    async with session_scope() as s:
        org = await s.get(Organization, org_id)
        assert org is not None
        sub = await ensure_subscription(s, org)
        await register_card(
            s, settings, provider, org, auth_key="ok", customer_key=sub.customer_key
        )
        await change_plan(s, settings, provider, org, "pro", request_id="dunning-1", now=now)
        # The card starts failing: swap in a billing key the fake provider declines.
        replacement = await provider.issue_billing_key("decline-card", sub.customer_key)
        from app.billing.service import _fernet

        sub.billing_key_enc = _fernet(settings).encrypt(replacement.billing_key.encode()).decode()

    moments = [now + timedelta(days=d) for d in (31, 32, 35, 42, 50)]
    statuses = []
    for moment in moments:
        async with session_scope() as s:
            await renew_due(s, settings, provider, now=moment)
            sub_row = await s.get(Subscription, org_id)
            assert sub_row is not None
            statuses.append((sub_row.status, sub_row.failed_attempts, sub_row.plan))
    assert statuses[0] == ("past_due", 1, "pro")
    assert statuses[-1][0] == "canceled" and statuses[-1][2] == "free"


class RecordingChannel:
    def __init__(self, fail: Exception | None = None) -> None:
        self.sent: list[tuple[str, dict[str, Any]]] = []
        self.fail = fail
        self.kind = "email"

    async def send(self, target: str, payload: dict[str, Any]) -> None:
        if self.fail:
            raise self.fail
        self.sent.append((target, payload))


async def test_digest_is_created_once_and_respects_quiet_hours(demo_world) -> None:  # type: ignore[no-untyped-def]
    from app.db.models import User

    async with session_scope() as s:
        demo = await s.scalar(select(User).where(User.email == "demo@example.com"))
        assert demo is not None
        org_id = demo.org_id
        rule = await s.get(AlertRule, org_id)
        assert rule is not None
        rule.min_score = 0.0
    noon_kst = datetime(2026, 9, 25, 3, 0, tzinfo=UTC)
    async with session_scope() as s:
        created = await enqueue_alerts(s, org_id, web_url="https://app", now=noon_kst)
        again = await enqueue_alerts(s, org_id, web_url="https://app", now=noon_kst)
    assert created >= 1 and again == 0, "same recommendations must not notify twice"

    channel = RecordingChannel()
    night = datetime(2026, 9, 25, 14, 0, tzinfo=UTC)  # 23:00 KST
    async with session_scope() as s:
        stats = await deliver_pending(
            s, {"email": channel, "slack": channel, "kakao": channel}, now=night
        )
    assert stats["deferred"] >= 1 and not channel.sent
    async with session_scope() as s:
        stats = await deliver_pending(
            s,
            {"email": channel, "slack": channel, "kakao": channel},
            now=datetime(2026, 9, 26, 0, 30, tzinfo=UTC),
        )
    assert stats["sent"] >= 1
    target, payload = channel.sent[0]
    assert target == "demo@example.com" and payload["items"]


async def test_permanent_failure_disables_channel(demo_world) -> None:  # type: ignore[no-untyped-def]
    org_id = await _new_org("웹훅")
    async with session_scope() as s:
        s.add(AlertRule(org_id=org_id, mode="daily", quiet_start=0, quiet_end=0))
        ch = AlertChannel(org_id=org_id, kind="slack", target="https://hooks.slack.com/x", label="")
        s.add(ch)
        await s.flush()
        s.add(
            Notification(
                org_id=org_id,
                channel_id=ch.id,
                kind="daily",
                dedupe_key=f"t:{ch.id}",
                payload={"items": [], "headline": "x", "settings_url": "", "org_name": ""},
                status="pending",
                scheduled_at=datetime.now(UTC),
            )
        )
        channel_id = ch.id
    broken = RecordingChannel(fail=PermanentDeliveryError("webhook revoked"))
    async with session_scope() as s:
        await deliver_pending(s, {"email": broken, "slack": broken, "kakao": broken})
    async with session_scope() as s:
        ch_row = await s.get(AlertChannel, channel_id)
        assert ch_row is not None and not ch_row.enabled and ch_row.last_error


@pytest.mark.parametrize("plan", ["pro"])
async def test_plan_change_is_idempotent_per_request(demo_world, runtime, plan: str) -> None:  # type: ignore[no-untyped-def]
    settings = runtime.settings
    provider = build_payment_provider(settings)
    org_id = await _new_org("요청멱등")
    async with session_scope() as s:
        org = await s.get(Organization, org_id)
        assert org is not None
        sub = await ensure_subscription(s, org)
        await register_card(
            s, settings, provider, org, auth_key="ok2", customer_key=sub.customer_key
        )
        await change_plan(s, settings, provider, org, plan, request_id="same-request")
        await change_plan(s, settings, provider, org, plan, request_id="same-request")
        assert org.credit_balance == 40  # one grant, not two
