import pytest

from app.domain.institutions import load_registry_csv, parse_name


@pytest.fixture(scope="module")
def registry():  # type: ignore[no-untyped-def]
    return load_registry_csv()


@pytest.mark.parametrize(
    ("raw", "code", "dept"),
    [
        ("서울특별시 강남구청 스마트도시과", "LG-11680", "스마트도시과"),
        ("강남구청", "LG-11680", None),
        ("서울 강남구", "LG-11680", None),
        ("서울특별시강남구청", "LG-11680", None),
        ("강남구의회", "CN-11680", None),
        ("수원특례시 정보통신과", "LG-41110", "정보통신과"),
        ("제주특별자치도 관광정책과", "LG-50000", "관광정책과"),
        ("세종시청", "LG-36110", None),
        ("부산진구청", "LG-26230", None),
        ("해운대구 스마트도시과", "LG-26350", "스마트도시과"),
    ],
)
def test_resolves_spelling_variants(registry, raw: str, code: str, dept: str | None) -> None:  # type: ignore[no-untyped-def]
    res = registry.resolve(raw)
    assert res.institution is not None, res
    assert res.institution.code == code
    assert res.department == dept


def test_ambiguous_sigungu_is_not_guessed(registry) -> None:  # type: ignore[no-untyped-def]
    res = registry.resolve("중구청 기획예산과")
    assert res.institution is None
    assert res.method == "ambiguous"
    assert len(res.candidates) == 6


def test_context_hint_disambiguates(registry) -> None:  # type: ignore[no-untyped-def]
    res = registry.resolve("중구청 기획예산과", sido_hint="대전")
    assert res.institution is not None
    assert res.institution.code == "LG-30140"
    assert res.method == "context"


def test_council_demand_is_attributed_to_executive(registry) -> None:  # type: ignore[no-untyped-def]
    res = registry.resolve("성남시의회")
    assert res.institution is not None
    assert res.institution.kind == "council"
    assert res.institution.demand_owner_code == "LG-41130"


def test_code_hint_short_circuits(registry) -> None:  # type: ignore[no-untyped-def]
    res = registry.resolve("아무 이름", code_hint="LG-47110")
    assert res.institution is not None
    assert res.method == "code"


def test_fuzzy_catches_ocr_typo(registry) -> None:  # type: ignore[no-untyped-def]
    res = registry.resolve("해운데구청")  # 대 -> 데 (OCR)
    assert res.institution is not None
    assert res.institution.code == "LG-26350"
    assert res.method == "fuzzy"


def test_parse_name_splits_department() -> None:
    parsed = parse_name("경기도 성남시청 (도시정보센터)")
    assert parsed.sido == "경기도"
    assert parsed.sigungu == "성남시"
    assert parsed.department == "도시정보센터"
