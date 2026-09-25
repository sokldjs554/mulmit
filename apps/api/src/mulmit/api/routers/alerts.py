from __future__ import annotations

import re
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from mulmit.api.deps import PrincipalDep, SessionDep, SettingsDep
from mulmit.api.schemas import AlertChannelIn, AlertChannelOut, AlertRuleIO, NotificationOut
from mulmit.billing.plans import PLANS
from mulmit.db.models import AlertChannel, AlertRule, Notification

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


@router.get("/rule", response_model=AlertRuleIO)
async def get_rule(principal: PrincipalDep, session: SessionDep) -> AlertRuleIO:
    rule = await session.get(AlertRule, principal.org.id)
    return AlertRuleIO.model_validate(rule) if rule else AlertRuleIO()


@router.put("/rule", response_model=AlertRuleIO)
async def put_rule(body: AlertRuleIO, principal: PrincipalDep, session: SessionDep) -> AlertRuleIO:
    if body.mode == "instant" and not PLANS[principal.org.plan].instant_alerts:
        raise HTTPException(
            status.HTTP_402_PAYMENT_REQUIRED, "즉시 알림은 Pro 플랜부터 사용할 수 있습니다"
        )
    rule = await session.get(AlertRule, principal.org.id)
    if rule is None:
        rule = AlertRule(org_id=principal.org.id)
        session.add(rule)
    for field, value in body.model_dump().items():
        setattr(rule, field, value)
    await session.flush()
    return AlertRuleIO.model_validate(rule)


@router.get("/channels", response_model=list[AlertChannelOut])
async def channels(principal: PrincipalDep, session: SessionDep) -> list[AlertChannelOut]:
    rows = await session.scalars(
        select(AlertChannel)
        .where(AlertChannel.org_id == principal.org.id)
        .order_by(AlertChannel.id)
    )
    return [AlertChannelOut.model_validate(r) for r in rows]


def _validate_target(kind: str, target: str) -> str:
    target = target.strip()
    if kind == "email" and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", target):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "이메일 형식이 아닙니다")
    if kind == "slack" and not target.startswith("https://hooks.slack.com/"):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "Slack Incoming Webhook URL을 입력하세요"
        )
    if kind == "kakao":
        digits = re.sub(r"\D", "", target)
        if not re.fullmatch(r"01\d{8,9}", digits):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "휴대폰 번호 형식이 아닙니다")
        target = digits
    return target


@router.post("/channels", response_model=AlertChannelOut, status_code=status.HTTP_201_CREATED)
async def add_channel(
    body: AlertChannelIn, principal: PrincipalDep, session: SessionDep
) -> AlertChannelOut:
    plan = PLANS[principal.org.plan]
    if body.kind not in plan.channels:
        raise HTTPException(
            status.HTTP_402_PAYMENT_REQUIRED,
            f"{plan.name} 플랜에서는 {body.kind} 채널을 쓸 수 없습니다",
        )
    channel = AlertChannel(
        org_id=principal.org.id,
        kind=body.kind,
        target=_validate_target(body.kind, body.target),
        label=body.label,
    )
    session.add(channel)
    await session.flush()
    return AlertChannelOut.model_validate(channel)


@router.delete("/channels/{channel_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_channel(channel_id: int, principal: PrincipalDep, session: SessionDep) -> None:
    channel = await session.get(AlertChannel, channel_id)
    if channel is None or channel.org_id != principal.org.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "채널을 찾을 수 없습니다")
    await session.delete(channel)


@router.post("/channels/{channel_id}/test", status_code=status.HTTP_202_ACCEPTED)
async def test_channel(
    channel_id: int, principal: PrincipalDep, session: SessionDep, settings: SettingsDep
) -> dict[str, str]:
    channel = await session.get(AlertChannel, channel_id)
    if channel is None or channel.org_id != principal.org.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "채널을 찾을 수 없습니다")
    channel.enabled = True
    channel.last_error = None
    now = datetime.now(UTC)
    session.add(
        Notification(
            org_id=principal.org.id,
            channel_id=channel.id,
            kind="test",
            dedupe_key=f"test:{channel.id}:{now.timestamp():.0f}",
            payload={
                "org_name": principal.org.name,
                "headline": "테스트 알림입니다",
                "items": [],
                "settings_url": f"{settings.public_web_url}/app/alerts",
            },
            status="pending",
            scheduled_at=now,
        )
    )
    return {"status": "queued"}


@router.get("/notifications", response_model=list[NotificationOut])
async def notifications(principal: PrincipalDep, session: SessionDep) -> list[NotificationOut]:
    rows = await session.scalars(
        select(Notification)
        .where(Notification.org_id == principal.org.id)
        .order_by(Notification.created_at.desc())
        .limit(50)
    )
    return [
        NotificationOut(
            id=n.id,
            kind=n.kind,
            status=n.status,
            attempts=n.attempts,
            last_error=n.last_error,
            created_at=n.created_at,
            sent_at=n.sent_at,
            channel_id=n.channel_id,
            headline=str(n.payload.get("headline", "")),
        )
        for n in rows
    ]
