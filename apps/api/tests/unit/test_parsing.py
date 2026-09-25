import struct
import zlib

import pytest

from mulmit.demo.synth import render_hwpx
from mulmit.parsing.chunking import chunk_budget, chunk_minutes, split_turns
from mulmit.parsing.dispatch import decode_text, structured_to_text
from mulmit.parsing.hwp import (
    HWPTAG_PARA_TEXT,
    HwpError,
    decode_para_text,
    extract_hwpx,
    iter_records,
    section_text,
)
from mulmit.parsing.ocr_correct import LexiconCorrector, correct_ocr_text, fix_numbers
from mulmit.sources.clik import html_to_text

MINUTES = """제301회 강남구의회 임시회
(10시 02분 개의)
○위원장 윤서준  의석을 정돈하여 주시기 바랍니다.
○위원 박지훈  스마트쉘터를 더 늘릴 계획이 있습니까?
○스마트도시과장 이정민  네, 내년도 본예산에 3억 5천만원을 반영하겠습니다.
추가로 말씀드리면 하반기에 발주할 예정입니다.
○위원 김현윤  단속 실적이 줄었다는데 이유가 뭡니까?
○교통행정과장 최민석  인력 두 명이 휴직 중이라 그렇습니다.
(12시 10분 산회)"""


def _record(tag: int, payload: bytes, level: int = 0) -> bytes:
    size = len(payload)
    if size < 0xFFF:
        return struct.pack("<I", tag | (level << 10) | (size << 20)) + payload
    return (
        struct.pack("<I", tag | (level << 10) | (0xFFF << 20)) + struct.pack("<I", size) + payload
    )


def test_split_turns_keeps_continuation_lines() -> None:
    turns = split_turns(MINUTES)
    assert [t.role for t in turns] == ["위원장", "위원", "스마트도시과장", "위원", "교통행정과장"]
    answer = turns[2]
    assert "하반기에 발주할 예정" in MINUTES[answer.start : answer.end]


def test_chunk_minutes_groups_question_with_answers() -> None:
    chunks = chunk_minutes(MINUTES)
    kinds = [c.kind for c in chunks]
    assert kinds == ["procedure", "exchange", "exchange"]
    first = chunks[1]
    assert "스마트쉘터" in first.text and "반영하겠습니다" in first.text
    assert MINUTES[first.char_start : first.char_end] == first.text
    assert first.labels == ["위원 박지훈", "스마트도시과장 이정민"]


def test_chunk_budget_attaches_basis_lines_and_department() -> None:
    text = (
        "2026년도 강남구 세출예산 사업명세서\n(단위: 천원)\n부서: 스마트도시과\n"
        "세부사업: 스마트쉘터 설치  352,000  0  352,000\n  ㅇ 스마트쉘터 7개소 × 50,000천원 = 350,000\n"
        "부서: 총무과\n세부사업: 업무추진비  51,555  48,977  2,578\n"
    )
    chunks = chunk_budget(text)
    assert len(chunks) == 2
    assert chunks[0].labels == ["부서: 스마트도시과"]
    assert "7개소" in chunks[0].text
    assert chunks[1].labels == ["부서: 총무과"]


def test_hwp5_record_parser_handles_controls_and_extended_size() -> None:
    text = "스마트쉘터 설치\t352,000"
    units = [ord(c) for c in text.replace("\t", "")]
    # inline tab control occupies 8 WCHARs; an extended control (code 11, a table) too.
    payload = struct.pack("<8H", 11, 0, 0, 0, 0, 0, 0, 11)
    payload += struct.pack(f"<{len('스마트쉘터 설치')}H", *[ord(c) for c in "스마트쉘터 설치"])
    payload += struct.pack("<8H", 9, 0, 0, 0, 0, 0, 0, 9)
    payload += struct.pack(f"<{len('352,000')}H", *[ord(c) for c in "352,000"])
    payload += struct.pack("<H", 13)
    big = "가" * 3000  # forces the 0xFFF extended size form
    stream = (
        _record(66, b"\x00" * 20)  # PARA_HEADER, ignored
        + _record(HWPTAG_PARA_TEXT, payload, level=1)
        + _record(HWPTAG_PARA_TEXT, struct.pack(f"<{len(big)}H", *[ord(c) for c in big]), level=1)
    )
    records = iter_records(stream)
    assert [r[0] for r in records] == [66, HWPTAG_PARA_TEXT, HWPTAG_PARA_TEXT]
    assert decode_para_text(records[1][2]) == "스마트쉘터 설치\t352,000\n"
    assert section_text(stream).splitlines()[0] == "스마트쉘터 설치\t352,000"
    assert len(units) > 0
    # And compressed streams decode the same way (raw deflate, wbits=-15).
    compressor = zlib.compressobj(wbits=-15)
    compressed = compressor.compress(stream) + compressor.flush()
    assert section_text(zlib.decompress(compressed, -15)) == section_text(stream)


def test_hwp5_truncated_stream_raises() -> None:
    with pytest.raises(HwpError):
        iter_records(struct.pack("<I", HWPTAG_PARA_TEXT | (100 << 20)) + b"\x00" * 10)


def test_hwpx_round_trip() -> None:
    text = "2026년도 예산서\n(단위: 천원)\n세부사업: 스마트폴 구축  334,000"
    assert extract_hwpx(render_hwpx(text)) == text


def test_fix_numbers_in_table_context() -> None:
    assert fix_numbers("스마트폴 구축 33O,OOO 0 l,806.000", table_context=True) == (
        "스마트폴 구축 330,000 0 1,806,000"
    )
    assert fix_numbers("사업비 3억 5천만윈") == "사업비 3억 5천만원"
    assert fix_numbers("3월 중 착수") == "3월 중 착수"  # a month is not money


def test_correct_ocr_text_fixes_ai_and_unit_header() -> None:
    corrector = LexiconCorrector(["스마트쉘터", "세부사업", "산출기초"])
    out = correct_ocr_text("(단 위 : 천 원)\n세부샤업: 스마트쉘티 설치 Al 기반", corrector)
    assert out.startswith("(단위: 천원)")
    assert "세부사업" in out and "스마트쉘터" in out and "AI 기반" in out


def test_lexicon_corrector_leaves_compounds_alone() -> None:
    corrector = LexiconCorrector(["스마트폴", "구축"])
    assert corrector.correct_token("스마트폴구축") == "스마트폴구축"
    assert corrector.correct_token("스마트풀을") == "스마트폴을"


def test_decode_text_falls_back_to_cp949() -> None:
    assert decode_text("예산서".encode("cp949")) == "예산서"


def test_structured_to_text_renders_amount() -> None:
    text = structured_to_text(
        "bid_notice", "스마트쉘터 구축사업", "서울특별시 강남구", {"amount_krw": 350_000_000}
    )
    assert "[입찰공고] 스마트쉘터 구축사업" in text
    assert "3억 5,000만원" in text


def test_html_to_text_keeps_speaker_lines() -> None:
    html = "<p>○위원 박지훈&nbsp; 질문입니다.<br>○과장 이정민 답변입니다.</p>"
    assert html_to_text(html).splitlines() == [
        "○위원 박지훈 질문입니다.",
        "○과장 이정민 답변입니다.",
    ]
