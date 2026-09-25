"""`manage eval llm`: scoring, the verifier's effect, the spend cap — with a fake provider."""

from typing import Any

import pytest

from app.eval.llm_compare import Candidate, compare, render
from app.eval.realistic import Prediction, Tally, load_realistic
from app.llm.prompts import ChunkContext
from app.llm.schemas import ExtractedSignal, ExtractionOutput
from app.llm.types import LLMConfigError, LLMResult, Usage

CASES: list[dict[str, Any]] = [
    {
        "id": "c1",
        "doc_type": "council_minutes",
        "date": "2025-11-20",
        "institution": "서울특별시 강남구의회",
        "labels": [],
        "text": "○스마트도시과장  내년도 본예산에 스마트쉘터 7개소 설치 사업비 3억 5천만원을 반영하겠습니다.",
        "expected": [
            {
                "title_keywords": ["쉘터"],
                "category": "smart_city",
                "commitment": "committed",
                "budget_krw": 350000000,
                "expected_year": 2026,
            }
        ],
    },
    {
        "id": "c2",
        "doc_type": "council_minutes",
        "date": "2025-11-20",
        "institution": "서울특별시 강남구의회",
        "labels": [],
        "text": "○총무과장  청사 주차 문제는 인근 공영주차장과 협약해서 해결했습니다.",
        "expected": [],
    },
]


def _signal(title: str, budget: int | None, evidence: str, **kw: Any) -> ExtractedSignal:
    return ExtractedSignal.model_validate(
        {
            "title": title,
            "summary": title,
            "category": kw.get("category", "smart_city"),
            "institution_mention": None,
            "department": None,
            "budget_text": kw.get("budget_text"),
            "budget_krw": budget,
            "timing_text": "내년도 본예산에",
            "expected_year": 2026,
            "expected_half": None,
            "commitment": "committed",
            "procurement_type": "goods",
            "keywords": [],
            "evidence": [evidence],
            "confidence": 0.9,
        }
    )


class FakeProvider:
    """c1: right project, wrong amount (the parser should fix it). c2: an invented signal
    whose quote is not in the text (the verifier should drop it)."""

    name = "anthropic"
    brief_model = "claude-opus-5"

    def __init__(self, model: str = "claude-opus-5", effort: str | None = "low") -> None:
        self.extract_model = model
        self.extract_effort = effort
        self.calls = 0
        self.fail_with: Exception | None = None

    async def extract(self, ctx: ChunkContext) -> LLMResult[ExtractionOutput]:
        self.calls += 1
        if self.fail_with is not None:
            raise self.fail_with
        if ctx.title == "c1":
            signals = [
                _signal(
                    "스마트쉘터 설치",
                    35_000_000,  # a zero dropped
                    "내년도 본예산에 스마트쉘터 7개소 설치 사업비 3억 5천만원을 반영하겠습니다.",
                    budget_text="3억 5천만원",
                )
            ]
        else:
            signals = [_signal("공영주차장 조성", None, "주차장 200면을 새로 짓겠습니다.")]
        return LLMResult(
            value=ExtractionOutput(signals=signals),
            provider=self.name,
            model=self.extract_model,
            prompt_version="test",
            usage=Usage(input_tokens=400, output_tokens=600, cache_read_tokens=1400),
            latency_ms=1200,
            served_by=self.extract_model,
        )


def test_candidate_specs() -> None:
    assert Candidate.parse("claude-opus-5:low") == Candidate("claude-opus-5", "low")
    assert Candidate.parse("claude-haiku-4-5") == Candidate("claude-haiku-4-5", None)
    assert not Candidate.parse("heuristic").is_llm
    with pytest.raises(ValueError, match="unknown effort"):
        Candidate.parse("claude-opus-5:fast")


async def test_verifier_drops_invented_signals_and_fixes_amounts() -> None:
    fake = FakeProvider()
    result = await compare(
        [Candidate("claude-opus-5", "low")],
        api_key=None,
        max_usd=5,
        cases=CASES,
        providers={"claude-opus-5 · low": fake},  # type: ignore[dict-item]
    )
    [x] = result["candidates"]
    assert x["raw"]["precision"] == 0.5  # the invented c2 signal counts against the model
    assert x["stored"]["precision"] == 1.0  # ...and never reaches the database
    assert x["raw"]["field_accuracy"]["budget"] == 0.0
    assert x["stored"]["field_accuracy"]["budget"] == 1.0  # parser's 3억 5천만원 wins
    assert x["verifier"]["rejected"] == 1
    assert x["verifier"]["budget_replaced_by_parser"] == 1
    # 2 calls × (400 in × $5 + 600 out × $25 + 1400 cache-read × $0.5) / 1M
    assert x["cost_usd"] == pytest.approx(2 * (0.002 + 0.015 + 0.0007), abs=1e-4)
    assert x["tokens"]["cache_read_share"] == pytest.approx(1400 / 1800, abs=1e-3)
    assert "claude-opus-5 · low" in render(result)


async def test_spend_cap_stops_calls() -> None:
    fake = FakeProvider()
    result = await compare(
        [Candidate("claude-opus-5", "low")],
        api_key=None,
        max_usd=0.0001,
        cases=CASES,
        providers={"claude-opus-5 · low": fake},  # type: ignore[dict-item]
    )
    assert fake.calls == 0
    assert result["candidates"][0]["errors"] == {"over_budget": 2}


async def test_a_configuration_error_stops_that_model_only() -> None:
    broken, fine = FakeProvider("claude-sonnet-5"), FakeProvider()
    broken.fail_with = LLMConfigError("anthropic rejected request: effort")
    result = await compare(
        [Candidate("claude-sonnet-5", "low"), Candidate("claude-opus-5", "low")],
        api_key=None,
        max_usd=5,
        cases=CASES,
        concurrency=1,
        providers={"claude-sonnet-5 · low": broken, "claude-opus-5 · low": fine},  # type: ignore[dict-item]
    )
    assert broken.calls == 1  # the second case was not sent
    assert result["candidates"][0]["errors"] == {"config": 2}
    assert result["candidates"][1]["answered"] == 2


def test_titles_are_matched_before_keyword_lists() -> None:
    case = {
        "id": "k",
        "expected": [
            {
                "title_keywords": ["횡단보도"],
                "category": "smart_city",
                "commitment": "committed",
                "budget_krw": None,
                "expected_year": None,
            },
            {
                "title_keywords": ["비상벨"],
                "category": "safety_cctv",
                "commitment": "planned",
                "budget_krw": None,
                "expected_year": None,
            },
        ],
    }
    bell = Prediction(
        "통학로 비상벨 추가", ("비상벨", "횡단보도"), "safety_cctv", "planned", None, None
    )
    crossing = Prediction("스마트 횡단보도 설치", (), "smart_city", "committed", None, None)
    tally = Tally()
    tally.add(case, [bell, crossing])
    assert tally.matched == 2
    assert tally.field_ok["commitment"] == 2  # each paired with its own project


def test_hand_written_set_is_well_formed() -> None:
    cases = load_realistic()
    assert len({c["id"] for c in cases}) == len(cases) >= 50
    for c in cases:
        assert c["doc_type"] in ("council_minutes", "budget_book")
        assert c["doc_type"] != "budget_book" or c.get("fiscal_year")
        for e in c["expected"]:
            assert e["commitment"] in ("committed", "planned", "reviewing", "declined")
            assert e["title_keywords"]
