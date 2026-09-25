"""Render one notification payload into each channel's format."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from jinja2 import Environment, PackageLoader, select_autoescape

_env = Environment(
    loader=PackageLoader("app.notify", "templates"),
    autoescape=select_autoescape(enabled_extensions=("html", "j2"), default_for_string=True),
    trim_blocks=True,
    lstrip_blocks=True,
)
_text_env = Environment(
    loader=PackageLoader("app.notify", "templates"),
    autoescape=False,  # noqa: S701 - plain-text email body, never rendered as HTML
    trim_blocks=True,
    lstrip_blocks=True,
)


_TEST_NOTE = "알림이 잘 도착하는지 확인하려고 보낸 메시지예요. 이게 보이면 설정은 끝났어요."


def when(item: dict[str, Any]) -> str:
    # Payloads queued before "when" existed carry only the bare forecast window.
    return str(item.get("when") or f"입찰 예상 {item.get('window') or '미정'}")


_env.globals.update(when=when, test_note=_TEST_NOTE)
_text_env.globals.update(when=when, test_note=_TEST_NOTE)


@dataclass(frozen=True, slots=True)
class RenderedEmail:
    subject: str
    html: str
    text: str


def render_email(payload: dict[str, Any]) -> RenderedEmail:
    subject = f"[발주 예측] {payload['headline']}"
    html = _env.get_template("digest.html.j2").render(**payload)
    text = _text_env.get_template("digest.txt.j2").render(**payload)
    return RenderedEmail(subject, html, text)


def render_slack(payload: dict[str, Any]) -> dict[str, Any]:
    blocks: list[dict[str, Any]] = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"발주 예측 · {payload['headline']}"},
        },
    ]
    if not payload["items"]:
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": _TEST_NOTE}})
    for item in payload["items"][:10]:
        meta = f"{item['stage_label']} · {item['institution']}"
        if item.get("budget"):
            meta += f" · {item['budget']}"
        meta += f" · {when(item)} · 적합도 {item['score_pct']}점"
        text = f"*<{item['url']}|{item['title']}>*\n{meta}"
        if item.get("evidence"):
            text += f"\n>「{item['evidence']}」"
        elif item.get("evidence_note"):
            text += f"\n{item['evidence_note']}"
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": text}})
    blocks.append(
        {
            "type": "context",
            "elements": [
                {"type": "mrkdwn", "text": f"<{payload['settings_url']}|알림 받는 방법 바꾸기>"}
            ],
        }
    )
    return {"text": f"[발주 예측] {payload['headline']}", "blocks": blocks}


def render_kakao_variables(payload: dict[str, Any]) -> dict[str, str]:
    """알림톡 templates are pre-approved with fixed #{변수}; we only fill variables."""
    first = payload["items"][0] if payload["items"] else {}
    return {
        "#{기관}": str(first.get("institution", "")),
        "#{사업명}": str(first.get("title", ""))[:40],
        "#{단계}": str(first.get("stage_label", "")),
        "#{건수}": str(len(payload["items"])),
        "#{링크}": str(first.get("url", payload.get("settings_url", ""))),
    }
