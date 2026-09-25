"""PDF text extraction with per-page OCR fallback.

Budget books are often *mixed*: typeset narrative pages followed by scanned appendix tables.
Deciding per page (text layer present and plausible → use it; otherwise render at 300 dpi and
OCR) keeps OCR cost proportional to the scanned part only.
"""

from __future__ import annotations

import io
from dataclasses import dataclass

from app.log import get_logger
from app.parsing.ocr import OCREngine
from app.parsing.ocr_correct import LexiconCorrector, correct_ocr_text

log = get_logger(__name__)


@dataclass(slots=True)
class ParsedText:
    text: str
    method: str  # text_layer | ocr | mixed | hwp5 | hwpx | plain | structured
    quality: float  # 1.0 for born-digital text, mean OCR confidence otherwise
    pages: int = 1
    ocr_pages: int = 0


def _looks_like_text(text: str, min_chars: int) -> bool:
    stripped = "".join(text.split())
    if len(stripped) < min_chars:
        return False
    # Broken font maps produce PUA / replacement characters instead of hangul.
    bad = sum(1 for ch in stripped if ch == "�" or 0xE000 <= ord(ch) <= 0xF8FF)
    return bad / len(stripped) < 0.1


async def extract_pdf(
    data: bytes,
    *,
    ocr: OCREngine | None,
    corrector: LexiconCorrector | None = None,
    min_chars_per_page: int = 40,
    dpi: int = 300,
) -> ParsedText:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    page_texts: list[str] = []
    ocr_pages = 0
    confidences: list[float] = []
    pdfium_doc = None
    try:
        for index, page in enumerate(reader.pages):
            text = page.extract_text() or ""
            if _looks_like_text(text, min_chars_per_page):
                page_texts.append(text)
                confidences.append(1.0)
                continue
            if ocr is None:
                page_texts.append(text)
                confidences.append(0.0)
                continue
            if pdfium_doc is None:
                import pypdfium2 as pdfium

                pdfium_doc = pdfium.PdfDocument(data)
            image = pdfium_doc[index].render(scale=dpi / 72).to_pil()
            result = await ocr.recognize(image)
            page_texts.append(correct_ocr_text(result.text, corrector))
            confidences.append(result.confidence)
            ocr_pages += 1
    finally:
        if pdfium_doc is not None:
            pdfium_doc.close()
    total = len(page_texts)
    method = "text_layer" if ocr_pages == 0 else ("ocr" if ocr_pages == total else "mixed")
    quality = sum(confidences) / len(confidences) if confidences else 0.0
    if ocr_pages:
        log.info("pdf.ocr", pages=total, ocr_pages=ocr_pages, quality=round(quality, 3))
    return ParsedText("\n".join(page_texts), method, round(quality, 3), total, ocr_pages)
