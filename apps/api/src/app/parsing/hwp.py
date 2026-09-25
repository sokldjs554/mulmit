"""Text extraction from 한글(HWP) documents — the format most Korean public bodies publish in.

* **HWPX** (한컴오피스 2014+): a ZIP of OWPML XML; text lives in ``<hp:t>`` under ``<hp:p>``.
* **HWP 5.0** (binary): an OLE2 compound file. ``FileHeader`` says whether streams are
  deflate-compressed; ``BodyText/SectionN`` streams are sequences of *records*
  (32-bit header: tag 10 bits, level 10 bits, size 12 bits, size 0xFFF → next DWORD). Paragraph
  text is the ``HWPTAG_PARA_TEXT`` (tag 67) record, UTF-16LE with inline control characters that
  occupy 8 code units and must be skipped.

Reference: 한글과컴퓨터 "한글 문서 파일 형식 5.0" (공개 문서).
"""

from __future__ import annotations

import io
import re
import struct
import zipfile
import zlib
from xml.etree import ElementTree as ET

HWPTAG_BEGIN = 0x10
HWPTAG_PARA_TEXT = HWPTAG_BEGIN + 51

# Control characters in PARA_TEXT (spec table 6): these occupy 8 WCHARs (1 + 7 payload units).
_EXTENDED_CONTROLS = {1, 2, 3, 11, 12, 14, 15, 16, 17, 18, 21, 22, 23}
_INLINE_CONTROLS = {4, 5, 6, 7, 8, 9, 19, 20}
_CHAR_CONTROLS = {0, 10, 13, 24, 25, 26, 27, 28, 29, 30, 31}


class HwpError(Exception):
    pass


def iter_records(stream: bytes) -> list[tuple[int, int, bytes]]:
    """Split a BodyText section stream into ``(tag, level, payload)`` records."""
    records: list[tuple[int, int, bytes]] = []
    pos = 0
    n = len(stream)
    while pos + 4 <= n:
        (header,) = struct.unpack_from("<I", stream, pos)
        pos += 4
        tag = header & 0x3FF
        level = (header >> 10) & 0x3FF
        size = (header >> 20) & 0xFFF
        if size == 0xFFF:
            if pos + 4 > n:
                raise HwpError("truncated extended record size")
            (size,) = struct.unpack_from("<I", stream, pos)
            pos += 4
        if pos + size > n:
            raise HwpError(f"record overruns stream at {pos}")
        records.append((tag, level, stream[pos : pos + size]))
        pos += size
    return records


def decode_para_text(payload: bytes) -> str:
    units = struct.unpack(f"<{len(payload) // 2}H", payload[: len(payload) // 2 * 2])
    out: list[str] = []
    i = 0
    while i < len(units):
        code = units[i]
        if code < 32:
            if code in _EXTENDED_CONTROLS or code in _INLINE_CONTROLS:
                if code == 9:
                    out.append("\t")
                i += 8
                continue
            if code in (10, 13):
                out.append("\n")
            elif code == 24:
                out.append("-")
            elif code in (30, 31):
                out.append(" ")
            i += 1
            continue
        out.append(chr(code))
        i += 1
    return "".join(out)


def section_text(stream: bytes) -> str:
    paragraphs = [
        decode_para_text(payload)
        for tag, _level, payload in iter_records(stream)
        if tag == HWPTAG_PARA_TEXT
    ]
    return "\n".join(p.rstrip("\n") for p in paragraphs)


def extract_hwp5(data: bytes) -> str:
    import olefile

    if not olefile.isOleFile(io.BytesIO(data)):
        raise HwpError("not an OLE2 compound file")
    ole = olefile.OleFileIO(io.BytesIO(data))
    try:
        header = ole.openstream("FileHeader").read()
        if not header.startswith(b"HWP Document File"):
            raise HwpError("missing HWP signature")
        (properties,) = struct.unpack_from("<I", header, 36)
        compressed = bool(properties & 0x1)
        if properties & 0x2:
            raise HwpError("password-protected HWP")
        sections = sorted(
            (entry for entry in ole.listdir() if entry[0] == "BodyText"),
            key=lambda e: int(re.sub(r"\D", "", e[1]) or 0),
        )
        texts: list[str] = []
        for entry in sections:
            raw = ole.openstream(entry).read()
            if compressed:
                raw = zlib.decompress(raw, -15)
            texts.append(section_text(raw))
        return "\n".join(texts)
    finally:
        ole.close()


def extract_hwpx(data: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        names = sorted(
            (n for n in zf.namelist() if re.fullmatch(r"Contents/section\d+\.xml", n)),
            key=lambda n: int(re.sub(r"\D", "", n)),
        )
        if not names:
            raise HwpError("no sections in HWPX package")
        lines: list[str] = []
        for name in names:
            root = ET.fromstring(zf.read(name))  # noqa: S314
            for para in root.iter():
                if not para.tag.endswith("}p"):
                    continue
                text = "".join(t.text or "" for t in para.iter() if t.tag.endswith("}t"))
                lines.append(text)
        return "\n".join(lines)
