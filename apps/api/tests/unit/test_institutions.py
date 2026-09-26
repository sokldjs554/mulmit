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


# 수요기관 names from 30 days of 조달청 data (2026-09-26). Each of these used to resolve to the
# 시도 or 구 in the left column; none of them is that institution.
@pytest.mark.parametrize(
    "raw",
    [
        "서울교통공사",  # was 서울특별시: the 시도 name anywhere in the text was enough
        "분당서울대학교병원",
        "부산대학교 산학협력단",
        "국토교통부 부산지방국토관리청 포항국토관리사무소",
        "한국농어촌공사 제주지역본부",
        "경기주택도시공사",
        "경기도 광주시",  # was 경기도: 광주시 read as 광주광역시 and skipped
        "경기도 신성중학교",
        "서울시 강서구시설관리공단",
        "대전광역시 서구",  # was 유성구 (fuzzy)
        "부산광역시 동래구",  # was 동구 (fuzzy)
        "인천광역시 부평구",  # was 중구 (fuzzy)
    ],
)
def test_names_that_only_carry_a_place_name_stay_unresolved(registry, raw: str) -> None:  # type: ignore[no-untyped-def]
    assert registry.resolve(raw).institution is None


@pytest.mark.parametrize(
    ("raw", "code"),
    [
        ("서울특별시", "LG-11000"),
        ("서울특별시 물재생센터 중랑물재생센터", "LG-11000"),
        ("서울특별시 영등포소방서", "LG-11000"),
        ("경기도 경기도건설본부", "LG-41000"),
        ("경기도청 북부청사", "LG-41000"),
        ("제주특별자치도 상하수도본부", "LG-50000"),
        ("경상북도 포항시 맑은물사업소", "LG-47110"),
        ("한국도로공사 서울경기본부", "PA-EXKR"),
    ],
)
def test_live_names_of_the_institution_itself_resolve(registry, raw: str, code: str) -> None:  # type: ignore[no-untyped-def]
    res = registry.resolve(raw)
    assert res.institution is not None, res
    assert res.institution.code == code


def test_gyeonggi_gwangju_is_a_city_of_gyeonggi() -> None:
    parsed = parse_name("경기도 광주시")
    assert (parsed.sido, parsed.sigungu) == ("경기도", "광주시")
    assert parse_name("광주광역시 동구").sido == "광주광역시"
