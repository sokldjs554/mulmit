"""LLM layer: schema, Anthropic request shape, fallback chain — all without network."""

import json
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import anthropic
import httpx
import pytest

from app.llm.budget import MemorySpendGuard
from app.llm.prompts import EXTRACT_SYSTEM, ChunkContext, extract_user_message
from app.llm.providers.anthropic_provider import AnthropicProvider
from app.llm.providers.heuristic import HeuristicProvider
from app.llm.schemas import ExtractionOutput, strict_json_schema
from app.llm.service import LLMService
from app.llm.types import LLMRefusedError, LLMUnavailableError, Usage

CTX = ChunkContext(
    doc_type="council_minutes",
    title="제301회 임시회",
    institution="서울특별시 강남구의회",
    document_date=date(2025, 11, 20),
    labels=["위원 박지훈", "스마트도시과장 이정민"],
    text=(
        "○위원 박지훈  버스정류장에 냉난방이 되는 스마트쉘터를 더 늘릴 계획이 있습니까?\n"
        "○스마트도시과장 이정민  내년도 본예산에 스마트쉘터 7개소 추가 설치 사업비 3억 5천만원을 "
        "반영하겠습니다."
    ),
)

GOOD_OUTPUT = {
    "signals": [
        {
            "title": "스마트쉘터 설치",
            "summary": "강남구가 스마트쉘터 7개소 추가 설치 예정",
            "category": "smart_city",
            "institution_mention": "강남구",
            "department": "스마트도시과",
            "budget_text": "3억 5천만원",
            "budget_krw": 350000000,
            "timing_text": "내년도 본예산에",
            "expected_year": 2026,
            "expected_half": None,
            "commitment": "committed",
            "procurement_type": "goods",
            "keywords": ["스마트쉘터"],
            "evidence": [
                "내년도 본예산에 스마트쉘터 7개소 추가 설치 사업비 3억 5천만원을 반영하겠습니다."
            ],
            "confidence": 0.9,
        }
    ]
}


def _response(payload: dict[str, Any] | str, stop_reason: str = "end_turn") -> Any:
    text = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
    return SimpleNamespace(
        content=[
            SimpleNamespace(type="thinking", thinking=""),
            SimpleNamespace(type="text", text=text),
        ],
        stop_reason=stop_reason,
        stop_details=None,
        model="claude-opus-5",
        usage=SimpleNamespace(
            input_tokens=420,
            output_tokens=180,
            cache_read_input_tokens=1400,
            cache_creation_input_tokens=0,
        ),
        _request_id="req_test",
    )


class FakeMessages:
    def __init__(self, outcomes: list[Any]) -> None:
        self.outcomes = outcomes
        self.calls: list[dict[str, Any]] = []

    async def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _provider(outcomes: list[Any]) -> tuple[AnthropicProvider, FakeMessages]:
    messages = FakeMessages(outcomes)
    client = SimpleNamespace(beta=SimpleNamespace(messages=messages))
    provider = AnthropicProvider(
        api_key="test",
        extract_model="claude-opus-5",
        extract_effort="low",
        brief_model="claude-opus-5",
        brief_effort="medium",
        client=client,  # type: ignore[arg-type]
    )
    return provider, messages


class FakeSession:
    """Just enough AsyncSession for LLMService (cache miss path + call recording)."""

    def __init__(self) -> None:
        self.added: list[Any] = []
        self.executed = 0

    async def get(self, *_: Any) -> None:
        return None

    async def execute(self, *_: Any) -> None:
        self.executed += 1

    def add(self, obj: Any) -> None:
        self.added.append(obj)


def test_strict_schema_has_no_unsupported_keywords() -> None:
    schema = json.dumps(strict_json_schema(ExtractionOutput))
    for keyword in ('"minimum"', '"maximum"', '"minLength"', '"maxItems"'):
        assert keyword not in schema
    s = strict_json_schema(ExtractionOutput)
    signal = s["$defs"]["ExtractedSignal"]
    assert signal["additionalProperties"] is False
    assert set(signal["required"]) == set(signal["properties"])
    assert "title" in signal["properties"]  # a *property* called title survives


def test_system_prompt_is_frozen_and_cacheable() -> None:
    # No per-request values in the cached prefix, and long enough to cache (≥512 tokens).
    assert "{" not in EXTRACT_SYSTEM.replace('{"signals": []}', "")
    assert len(EXTRACT_SYSTEM) > 2500
    assert "2025-11-20" in extract_user_message(CTX)


async def test_anthropic_request_shape_and_parse() -> None:
    provider, messages = _provider([_response(GOOD_OUTPUT)])
    result = await provider.extract(CTX)
    call = messages.calls[0]
    assert call["model"] == "claude-opus-5"
    assert call["output_config"]["effort"] == "low"
    assert call["output_config"]["format"]["type"] == "json_schema"
    assert call["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert call["fallbacks"] == "default"
    assert call["betas"] == ["server-side-fallback-2026-07-01"]
    assert "thinking" not in call  # adaptive by default on Opus 5; effort is the lever
    assert result.value.signals[0].budget_krw == 350_000_000
    assert result.usage.cache_read_tokens == 1400
    assert result.served_by == "claude-opus-5"


async def test_refusal_is_typed() -> None:
    provider, _ = _provider([_response({"signals": []}, stop_reason="refusal")])
    with pytest.raises(LLMRefusedError):
        await provider.extract(CTX)


async def test_rate_limit_maps_to_unavailable() -> None:
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    error = anthropic.RateLimitError(
        "slow down", response=httpx.Response(429, request=request), body=None
    )
    provider, _ = _provider([error])
    with pytest.raises(LLMUnavailableError):
        await provider.extract(CTX)


async def test_service_records_cost_and_uses_primary() -> None:
    provider, _ = _provider([_response(GOOD_OUTPUT)])
    guard = MemorySpendGuard(10)
    service = LLMService(primary=provider, fallback=HeuristicProvider(), guard=guard)
    session = FakeSession()
    attempt = await service.extract(session, CTX)  # type: ignore[arg-type]
    assert not attempt.degraded
    assert attempt.extractor.startswith("anthropic:claude-opus-5")
    assert await guard.spent_today() > 0
    assert session.added[0].status == "ok"


async def test_service_degrades_when_budget_exhausted() -> None:
    provider, messages = _provider([_response(GOOD_OUTPUT)])
    service = LLMService(primary=provider, fallback=HeuristicProvider(), guard=MemorySpendGuard(0))
    session = FakeSession()
    attempt = await service.extract(session, CTX)  # type: ignore[arg-type]
    assert attempt.degraded and attempt.reason == "budget_exceeded"
    assert not messages.calls  # the model was never called
    assert attempt.output.signals[0].title  # heuristic still produced the signal
    assert session.added[0].status == "budget_skip"


async def test_service_propagates_transient_errors_until_final_attempt() -> None:
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    overloaded = anthropic.InternalServerError(
        "overloaded", response=httpx.Response(529, request=request), body=None
    )
    provider, _ = _provider([overloaded, overloaded])
    service = LLMService(primary=provider, fallback=HeuristicProvider(), guard=MemorySpendGuard(10))
    with pytest.raises(LLMUnavailableError):
        await service.extract(FakeSession(), CTX, final_attempt=False)  # type: ignore[arg-type]
    attempt = await service.extract(FakeSession(), CTX, final_attempt=True)  # type: ignore[arg-type]
    assert attempt.degraded and attempt.reason == "provider_unavailable"


async def test_heuristic_extracts_council_commitment() -> None:
    result = await HeuristicProvider().extract(CTX)
    [signal] = result.value.signals
    assert signal.commitment == "committed"
    assert signal.budget_krw == 350_000_000
    assert signal.expected_year == 2026
    assert signal.category.value == "smart_city"
    assert "스마트쉘터" in signal.title


async def test_heuristic_skips_operating_cost_budget_lines() -> None:
    ctx = ChunkContext(
        "budget_book",
        "예산서",
        "강남구",
        date(2025, 12, 18),
        ["부서: 총무과"],
        "세부사업: 업무추진비  51,555  48,977  2,578",
        fiscal_year=2026,
    )
    assert (await HeuristicProvider().extract(ctx)).value.signals == []


def test_usage_cost_accounts_for_cache() -> None:
    usage = Usage(input_tokens=1_000_000, output_tokens=0, cache_read_tokens=1_000_000)
    assert usage.cost_usd("claude-opus-5") == Decimal("5.5")


@pytest.mark.parametrize(
    ("answer", "expected"),
    [
        # circumstance qualifiers are not part of the project name
        (
            "취지는 공감하나 현재 재정 여건상 스마트쉘터 설치는 당분간 추진하기 어렵습니다.",
            "스마트쉘터 설치",
        ),
        # a spoken relative clause is kept whole rather than cut mid-clause
        (
            "AI가 이상행동을 먼저 잡아주는 CCTV는 필요성은 공감합니다만, 효과성 검증이 필요해서 적극 검토하겠습니다.",
            "AI가 이상행동을 먼저 잡아주는 CCTV",
        ),
    ],
)
def test_heuristic_titles_read_like_project_names(answer: str, expected: str) -> None:
    from app.llm.providers.heuristic import _guess_title

    assert _guess_title(answer, "") == expected


def test_template_brief_advice_follows_the_stage_reached() -> None:
    from app.pipeline.brief import template_brief

    def facts(stage: str, last_commitment: str) -> str:
        return "\n".join(
            [
                "# 기회",
                "- 사업명: 스마트쉘터 설치",
                "- 기관: 서울특별시 강남구 / 부서: 교통행정과",
                f"- 현재 단계: {stage} (공고 전)",
                "- 추정 예산: 3억 5,000만원",
                "",
                "# 신호 (시간순, 원문 인용)",
                f"- 2026-03-02 [의회 발언] 스마트쉘터 설치, {last_commitment}: 「…」",
                "",
                "# 이 기관의 최근 발주 이력",
                "- (수집된 이력 없음)",
            ]
        )

    prespec = template_brief(facts("사전규격", "확약(반영·편성)"))
    assert "의견등록 기간" in prespec
    assert "예산에 편성되기 전" not in prespec

    council = template_brief(facts("의회 발언", "검토 중"))
    assert "예산에 편성되기 전" in council
    assert "가장 최근 발언이 확약이 아닙니다" in council
