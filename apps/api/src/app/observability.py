"""Error tracking (Sentry) for both the API process and the arq worker."""

from __future__ import annotations

from typing import Any

import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration
from sentry_sdk.scrubber import DEFAULT_DENYLIST, EventScrubber
from sentry_sdk.types import Event, Hint

from app import __version__
from app.log import redact_secrets
from app.settings import Settings

_SCRUB_KEYS = {"authorization", "cookie", "billing_key", "password", "service_key", "secret"}

# Names whose values Sentry's own scrubber replaces wherever they appear as keys — request data,
# and (recursive) stack-frame local variables such as ``service_key`` or ``params["serviceKey"]``.
_DENYLIST = [*DEFAULT_DENYLIST, "service_key", "servicekey", "key", "billing_key", "api_key"]


def event_scrubber() -> EventScrubber:
    return EventScrubber(denylist=_DENYLIST, recursive=True)


def _redact_strings(data: Any) -> None:
    if isinstance(data, dict):
        for k, v in data.items():
            if isinstance(v, str):
                data[k] = redact_secrets(v)


def _scrub(event: Event, _hint: Hint) -> Event | None:
    """Never ship credentials (Toss billing keys, public-data API keys) to Sentry.

    Registered for errors *and* transactions: the httpx integration puts each call's query
    string into breadcrumb and span data (``http.query``), where ``serviceKey=`` lives.
    """
    request: dict[str, Any] = event.get("request") or {}
    headers = request.get("headers") or {}
    for key in list(headers):
        if key.lower() in _SCRUB_KEYS:
            headers[key] = "[scrubbed]"
    breadcrumbs: Any = event.get("breadcrumbs") or {}
    for crumb in breadcrumbs.get("values", []) if isinstance(breadcrumbs, dict) else []:
        _redact_strings(crumb.get("data"))
        if isinstance(crumb.get("message"), str):  # log records, e.g. source.retry
            crumb["message"] = redact_secrets(crumb["message"])
    spans: Any = event.get("spans") or []
    for span in spans if isinstance(spans, list) else []:
        _redact_strings(span.get("data"))
        description = span.get("description")
        if isinstance(description, str):
            span["description"] = redact_secrets(description)
    for exc in (event.get("exception") or {}).get("values", []):
        if isinstance(exc.get("value"), str):
            exc["value"] = redact_secrets(exc["value"])
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
        before_send_transaction=_scrub,
        event_scrubber=event_scrubber(),
    )
    sentry_sdk.set_tag("component", component)
    return True
