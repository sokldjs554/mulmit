"""Render one notification payload into each channel's format."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from jinja2 import Environment, PackageLoader, select_autoescape

_env = Environment(
    loader=PackageLoader("mulmit.notify", "templates"),
    autoescape=select_autoescape(enabled_extensions=("html", "j2"), default_for_string=True),
    trim_blocks=True,
    lstrip_blocks=True,
)
_text_env = Environment(
    loader=PackageLoader("mulmit.notify", "templates"),
    autoescape=False,  # noqa: S701 - plain-text email body, never rendered as HTML
    trim_blocks=True,
    lstrip_blocks=True,
)


@dataclass(frozen=True, slots=True)
class RenderedEmail:
    subject: str
    html: str
    text: str


def render_email(payload: dict[str, Any]) -> RenderedEmail:
    subject = f"[물밑] {payload['headline']}"
    html = _env.get_template("digest.html.j2").render(**payload)
    text = _text_env.get_template("digest.txt.j2").render(**payload)
    return RenderedEmail(subject, html, text)


def render_slack(payload: dict[str, Any]) -> dict[str, Any]:
    blocks: list[dict[str, Any]] = [
        {"type": "header", "text": {"type": "plain_text", "text": f"물밑 · {payload['headline']}"}},
    ]
    for item in payload["items"][:10]:
        meta = f"{item['stage_label']} · {item['institution']}"
        if item.get("budget"):
            meta += f" · 예산 {item['budget']}"
        meta += f" · 입찰 예상 {item['window']} · 적합도 {item['score_pct']}%"
        text = f"*<{item['url']}|{item['title']}>*\n{meta}"
        if item.get("evidence"):
            text += f"\n>「{item['evidence']}」"
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": text}})
    blocks.append(
        {
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": f"<{payload['settings_url']}|알림 설정>"}],
        }
    )
    return {"text": f"[물밑] {payload['headline']}", "blocks": blocks}


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
