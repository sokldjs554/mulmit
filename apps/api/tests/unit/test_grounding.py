from datetime import date

import pytest

from mulmit.domain.grounding import locate_quote, verify_extraction
from mulmit.domain.timing import resolve_timing

SOURCE = """○위원 박지훈  버스정류장에 냉난방이 되는 스마트쉘터를 더 늘릴 계획이 있습니까?
○스마트도시과장 이정민  네, 위원님. 현재 12개소를 운영 중이고, 내년도 본예산에
스마트쉘터 7개소 추가 설치 사업비 3억 5천만원을 반영하겠습니다.
하반기에 발주할 예정입니다."""


def test_exact_quote_is_located_with_original_offsets() -> None:
    check = locate_quote(SOURCE, "스마트쉘터 7개소 추가 설치 사업비 3억 5천만원을 반영하겠습니다")
    assert check.found
    assert check.method == "exact"
    assert check.start is not None and check.end is not None
    assert SOURCE[check.start : check.end].startswith("스마트쉘터 7개소")


def test_quote_spanning_a_line_break_still_matches() -> None:
    check = locate_quote(SOURCE, "내년도 본예산에 스마트쉘터 7개소")
    assert check.found and check.method == "exact"


def test_ocr_noise_matches_fuzzily() -> None:
    check = locate_quote(SOURCE, "스마트쉘티 7개소 추가 설지 사업비 3억 5천만원을 반영하겠습니다")
    assert check.found
    assert check.method == "fuzzy"
    assert check.score >= 88


def test_invented_quote_is_missing() -> None:
    check = locate_quote(SOURCE, "스마트 횡단보도 20개소를 2027년에 구축하겠습니다")
    assert not check.found


def _verify(**overrides):  # type: ignore[no-untyped-def]
    args = {
        "source": SOURCE,
        "evidence_quotes": ["스마트쉘터 7개소 추가 설치 사업비 3억 5천만원을 반영하겠습니다"],
        "budget_krw": 350_000_000,
        "budget_text": "3억 5천만원",
        "expected_year": 2026,
        "timing_text": "내년도 본예산에",
        "reference_date": date(2025, 11, 20),
        "confidence": 0.8,
    }
    args.update(overrides)
    return verify_extraction(**args)


def test_consistent_extraction_is_accepted() -> None:
    report = _verify()
    assert report.verdict == "accepted", report.issues
    assert report.budget_grounded and report.year_grounded


def test_wrong_budget_goes_to_review() -> None:
    report = _verify(budget_krw=3_500_000_000)
    assert report.verdict == "needs_review"
    assert "budget_mismatch" in report.issues
    assert report.budget_parsed == 350_000_000


def test_wrong_year_goes_to_review() -> None:
    report = _verify(expected_year=2027)
    assert "year_unverified" in report.issues


def test_hallucinated_evidence_is_rejected() -> None:
    report = _verify(evidence_quotes=["드론 배송 시범사업을 추진하겠습니다"])
    assert report.verdict == "rejected"


@pytest.mark.parametrize(
    ("phrase", "ref", "year", "half"),
    [
        ("내년도 본예산에", date(2025, 11, 20), 2026, None),
        ("2027년 상반기", date(2025, 11, 20), 2027, "H1"),
        ("'27년 하반기 발주", date(2025, 11, 20), 2027, "H2"),
        ("내후년", date(2025, 3, 1), 2027, None),
        ("하반기에 발주할 예정", date(2025, 3, 1), 2025, "H2"),
        ("상반기 중 착수", date(2025, 9, 1), 2026, "H1"),
        ("제2회 추경에", date(2025, 5, 1), None, "H2"),
    ],
)
def test_resolve_timing(phrase: str, ref: date, year: int | None, half: str | None) -> None:
    t = resolve_timing(phrase, ref)
    if year is None:
        assert t is not None and t.half == half
    else:
        assert t is not None
        assert (t.year, t.half) == (year, half)
