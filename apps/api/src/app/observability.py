"""Error tracking (Sentry) for both the API process and the arq worker."""

from __future__ import annotations

from typing import Any

import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration
from sentry_sdk.types import Event, Hint

from app import __version__
from app.settings import Settings

_SCRUB_KEYS = {"authorization", "cookie", "billing_key", "password", "service_key", "secret"}


def _scrub(event: Event, _hint: Hint) -> Event | None:
    """Never ship credentials (Toss billing keys, data.go.kr service keys) to Sentry."""
    request: dict[str, Any] = event.get("request") or {}
    headers = request.get("headers") or {}
    for key in list(headers):
        if key.lower() in _SCRUB_KEYS:
            headers[key] = "[scrubbed]"
    breadcrumbs: Any = event.get("breadcrumbs") or {}
    for crumb in breadcrumbs.get("values", []) if isinstance(breadcrumbs, dict) else []:
        data = crumb.get("data") or {}
        url = data.get("url")
        if isinstance(url, str) and "serviceKey=" in url:
            data["url"] = url.split("serviceKey=")[0] + "serviceKey=[scrubbed]"
    return event


def init_sentry(settings: Settings, *, component: str) -> bool:
    if not settings.sentry_dsn:
        return False
    integrations: list[Any] = [StarletteIntegration(), FastApiIntegration()]
    if component == "worker":
        from sentry_sdk.integrations.arq import ArqIntegration

        integrations = [ArqIntegration()]
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.env,
        release=f"app@{__version__}",
        traces_sample_rate=settings.sentry_traces_sample_rate,
        send_default_pii=False,
        integrations=integrations,
        before_send=_scrub,
    )
    sentry_sdk.set_tag("component", component)
    return True
