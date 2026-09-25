"""Pick the right reader for a stored document."""

from __future__ import annotations

from typing import Any

from mulmit.domain.krw import format_krw
from mulmit.parsing.hwp import extract_hwp5, extract_hwpx
from mulmit.parsing.ocr import OCREngine
from mulmit.parsing.ocr_correct import LexiconCorrector
from mulmit.parsing.pdf import ParsedText, extract_pdf
from mulmit.sources.clik import html_to_text

_STAGE_LABEL = {
    "order_plan": "발주계획",
    "prespec": "사전규격 공개",
    "bid_notice": "입찰공고",
    "award": "낙찰",
}


def decode_text(data: bytes) -> str:
    """UTF-8 first; fall back to CP949 (EUC-KR superset) — still common on older portals."""
    for encoding in ("utf-8", "cp949"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def structured_to_text(doc_type: str, title: str, publisher: str | None, s: dict[str, Any]) -> str:
    """Render a structured procurement record as one line of text: this is what the verifier
    grounds against and what the UI shows as the record's 'evidence'."""
    parts = [f"[{_STAGE_LABEL.get(doc_type, doc_type)}] {title}"]
    if publisher:
        parts.append(f"수요기관: {publisher}")
    if s.get("department"):
        parts.append(f"부서: {s['department']}")
    amount = s.get("amount_krw")
    if isinstance(amount, int) and amount > 0:
        parts.append(f"금액: {amount:,}원 ({format_krw(amount)})")
    if s.get("order_year"):
        month = f" {s['order_month']}월" if s.get("order_month") else ""
        parts.append(f"발주시기: {s['order_year']}년{month}")
    if s.get("contract_method"):
        parts.append(f"계약방법: {s['contract_method']}")
    if s.get("bid_close_at"):
        parts.append(f"입찰마감: {s['bid_close_at']}")
    return " | ".join(parts)


async def parse_content(
    *,
    mime: str,
    content: bytes | None,
    doc_type: str,
    title: str,
    publisher: str | None,
    structured: dict[str, Any],
    ocr: OCREngine | None,
    corrector: LexiconCorrector | None,
    min_chars_per_page: int = 40,
) -> ParsedText:
    base_mime = mime.split(";", maxsplit=1)[0].strip().lower()
    if base_mime == "application/json" or content is None:
        return ParsedText(
            structured_to_text(doc_type, title, publisher, structured), "structured", 1.0
        )
    if base_mime == "application/pdf" or content[:5] == b"%PDF-":
        return await extract_pdf(
            content, ocr=ocr, corrector=corrector, min_chars_per_page=min_chars_per_page
        )
    if base_mime in ("application/hwp+zip", "application/vnd.hancom.hwpx") or content[:2] == b"PK":
        return ParsedText(extract_hwpx(content), "hwpx", 1.0)
    if base_mime in ("application/x-hwp", "application/haansofthwp") or content[
        :8
    ] == bytes.fromhex("d0cf11e0a1b11ae1"):
        return ParsedText(extract_hwp5(content), "hwp5", 1.0)
    text = decode_text(content)
    if base_mime == "text/html" or text.lstrip().startswith("<"):
        return ParsedText(html_to_text(text), "html", 1.0)
    return ParsedText(text, "plain", 1.0)
