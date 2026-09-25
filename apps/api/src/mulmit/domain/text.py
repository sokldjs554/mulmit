"""Text normalisation shared by parsing, grounding and matching.

Public documents mix full-width punctuation, several "circle" speaker markers (○ ◯ ◎), hangul
compatibility jamo from OCR, zero-width spaces pasted out of HWP, and hanja in older minutes.
Everything downstream compares text *after* this normalisation, and offsets are always reported
against the original string via :func:`normalize_with_map`.
"""

from __future__ import annotations

import re
import unicodedata

_ZERO_WIDTH = dict.fromkeys(map(ord, "\u200b‌‍﻿­"), None)
_SPEAKER_MARKS = str.maketrans({"◯": "○", "◎": "○", "●": "○", "〇": "○"})
_WS_RE = re.compile(r"[ \t 　]+")


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).translate(_ZERO_WIDTH).translate(_SPEAKER_MARKS)
    text = _WS_RE.sub(" ", text)
    return "\n".join(line.strip() for line in text.splitlines())


def collapse_ws(text: str) -> str:
    return re.sub(r"\s+", " ", normalize(text)).strip()


def normalize_with_map(text: str) -> tuple[str, list[int]]:
    """Whitespace-collapse ``text`` and return a map from each output index to the input index.

    Used by the grounding verifier: we search in the collapsed string but report character
    offsets in the stored document so the UI can highlight the exact span.
    """
    out: list[str] = []
    index_map: list[int] = []
    prev_space = True
    for i, ch in enumerate(text):
        ch_n = unicodedata.normalize("NFKC", ch).translate(_ZERO_WIDTH).translate(_SPEAKER_MARKS)
        if not ch_n:
            continue
        for c in ch_n:
            if c.isspace():
                if prev_space:
                    continue
                out.append(" ")
                index_map.append(i)
                prev_space = True
            else:
                out.append(c)
                index_map.append(i)
                prev_space = False
    if out and out[-1] == " ":
        out.pop()
        index_map.pop()
    return "".join(out), index_map


_HANGUL_RE = re.compile(r"[가-힣]+")


def hangul_tokens(text: str, *, min_len: int = 2) -> list[str]:
    return [t for t in _HANGUL_RE.findall(text) if len(t) >= min_len]


def char_ngrams(text: str, n: int) -> list[str]:
    compact = re.sub(r"\s+", "", normalize(text))
    return [compact[i : i + n] for i in range(max(len(compact) - n + 1, 0))]


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


_CHO = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"
_JUNG = "ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ"
_JONG = " ㄱㄲㄳㄴㄵㄶㄷㄹㄺㄻㄼㄽㄾㄿㅀㅁㅂㅄㅅㅆㅇㅈㅊㅋㅌㅍㅎ"


def to_jamo(text: str) -> str:
    """Decompose hangul syllables into jamo: "해운대" -> "ㅎㅐㅇㅜㄴㄷㅐ".

    OCR confusions in Korean are usually one jamo off (대/데, 과/곽), which is a large edit
    distance at the syllable level but a small one at the jamo level.
    """
    out: list[str] = []
    for ch in text:
        code = ord(ch) - 0xAC00
        if 0 <= code < 11172:
            cho, rest = divmod(code, 21 * 28)
            jung, jong = divmod(rest, 28)
            out.append(_CHO[cho])
            out.append(_JUNG[jung])
            if jong:
                out.append(_JONG[jong])
        else:
            out.append(ch)
    return "".join(out)
