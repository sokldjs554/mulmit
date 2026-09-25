"""Delivery channels: email (SMTP), Slack (incoming webhook), KakaoTalk 알림톡 (via Solapi).

Each channel raises :class:`TransientDeliveryError` for things worth retrying (timeouts, 5xx,
429) and :class:`PermanentDeliveryError` for things that are not (revoked webhook, invalid phone
number) — the dispatcher disables a channel after a permanent error and tells the customer.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import UTC, datetime
from email.message import EmailMessage
from typing import Any, Protocol

import aiosmtplib
import httpx

from app.notify.render import render_email, render_kakao_variables, render_slack
from app.settings import Settings


class TransientDeliveryError(Exception):
    pass


class PermanentDeliveryError(Exception):
    pass


class Channel(Protocol):
    kind: str

    async def send(self, target: str, payload: dict[str, Any]) -> None: ...


class EmailChannel:
    kind = "email"

    def __init__(self, settings: Settings) -> None:
        self._s = settings

    async def send(self, target: str, payload: dict[str, Any]) -> None:
        rendered = render_email(payload)
        msg = EmailMessage()
        msg["From"] = self._s.mail_from
        msg["To"] = target
        msg["Subject"] = rendered.subject
        msg.set_content(rendered.text)
        msg.add_alternative(rendered.html, subtype="html")
        try:
            await aiosmtplib.send(
                msg,
                hostname=self._s.smtp_host,
                port=self._s.smtp_port,
                username=self._s.smtp_username,
                password=self._s.smtp_password.get_secret_value()
                if self._s.smtp_password
                else None,
                start_tls=self._s.smtp_use_tls,
                timeout=15,
            )
        except aiosmtplib.SMTPRecipientsRefused as exc:
            raise PermanentDeliveryError(f"recipient refused: {exc}") from exc
        except (aiosmtplib.SMTPException, OSError) as exc:
            raise TransientDeliveryError(str(exc)) from exc


class SlackChannel:
    kind = "slack"

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._client = httpx.AsyncClient(timeout=10, transport=transport)

    async def send(self, target: str, payload: dict[str, Any]) -> None:
        if not target.startswith("https://hooks.slack.com/"):
            raise PermanentDeliveryError("not a Slack incoming-webhook URL")
        try:
            resp = await self._client.post(target, json=render_slack(payload))
        except httpx.HTTPError as exc:
            raise TransientDeliveryError(str(exc)) from exc
        if resp.status_code in (404, 410) or resp.text in ("no_service", "channel_not_found"):
            raise PermanentDeliveryError(f"webhook revoked: {resp.status_code} {resp.text}")
        if resp.status_code == 429 or resp.status_code >= 500:
            raise TransientDeliveryError(f"slack {resp.status_code}")
        if resp.status_code >= 400:
            raise PermanentDeliveryError(f"slack {resp.status_code}: {resp.text}")


class KakaoAlimtalkChannel:
    """Solapi REST API (HMAC-SHA256 auth). 알림톡 requires a registered 카카오 채널(pfId) and a
    pre-approved template; message text is fixed by the template, we send variables only."""

    kind = "kakao"
    _URL = "https://api.solapi.com/messages/v4/send"

    def __init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None):
        self._s = settings
        self._client = httpx.AsyncClient(timeout=10, transport=transport)

    def _auth_header(self) -> str:
        if not (self._s.solapi_api_key and self._s.solapi_api_secret):
            raise PermanentDeliveryError("Solapi credentials are not configured")
        date = datetime.now(UTC).isoformat()
        salt = secrets.token_hex(16)
        signature = hmac.new(
            self._s.solapi_api_secret.get_secret_value().encode(),
            (date + salt).encode(),
            hashlib.sha256,
        ).hexdigest()
        return (
            f"HMAC-SHA256 apiKey={self._s.solapi_api_key.get_secret_value()}, "
            f"date={date}, salt={salt}, signature={signature}"
        )

    async def send(self, target: str, payload: dict[str, Any]) -> None:
        phone = "".join(ch for ch in target if ch.isdigit())
        if not phone.startswith("01") or len(phone) not in (10, 11):
            raise PermanentDeliveryError("invalid mobile number")
        body = {
            "message": {
                "to": phone,
                "from": self._s.kakao_sender_number,
                "kakaoOptions": {
                    "pfId": self._s.kakao_pf_id,
                    "templateId": self._s.kakao_template_id,
                    "variables": render_kakao_variables(payload),
                },
            }
        }
        try:
            resp = await self._client.post(
                self._URL, json=body, headers={"Authorization": self._auth_header()}
            )
        except httpx.HTTPError as exc:
            raise TransientDeliveryError(str(exc)) from exc
        if resp.status_code == 429 or resp.status_code >= 500:
            raise TransientDeliveryError(f"solapi {resp.status_code}")
        if resp.status_code >= 400:
            raise PermanentDeliveryError(f"solapi {resp.status_code}: {resp.text[:200]}")


def build_channels(settings: Settings) -> dict[str, Channel]:
    return {
        "email": EmailChannel(settings),
        "slack": SlackChannel(),
        "kakao": KakaoAlimtalkChannel(settings),
    }
