"""Structured-output contract for signal extraction.

The schema is the API between a probabilistic model and a deterministic pipeline, so it is
explicit about *verbatim* fields (``budget_text``, ``timing_text``, ``evidence``) that the
grounding verifier re-checks, versus *derived* fields (``budget_krw``, ``expected_year``) that
the model computes and the verifier refuses to trust blindly.
"""

from __future__ import annotations

import copy
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.domain.taxonomy import Category

Commitment = Literal["committed", "planned", "reviewing", "declined"]
ProcurementType = Literal["service", "goods", "construction", "unknown"]
Half = Literal["H1", "H2"]

EXTRACTION_SCHEMA_VERSION = "signal-v3"


class ExtractedSignal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(description="사업명: short formal noun phrase, e.g. '스마트쉘터 설치'")
    summary: str = Field(description="One Korean sentence: who plans to buy what, and why")
    category: Category
    institution_mention: str | None = Field(
        description="Institution as written in the text, if any (e.g. '강남구')"
    )
    department: str | None = Field(description="Responsible department, e.g. '스마트도시과'")
    budget_text: str | None = Field(description="Amount phrase copied verbatim, e.g. '3억 5천만원'")
    budget_krw: int | None = Field(description="budget_text converted to won")
    timing_text: str | None = Field(
        description="Timing phrase copied verbatim, e.g. '내년도 본예산에'"
    )
    expected_year: int | None = Field(
        description="Year the purchase is expected (resolve 내년 etc.)"
    )
    expected_half: Half | None
    commitment: Commitment
    procurement_type: ProcurementType
    keywords: list[str] = Field(description="2-6 Korean keywords a vendor would search for")
    evidence: list[str] = Field(
        description="1-3 quotes copied EXACTLY from the text that support this signal"
    )
    confidence: float = Field(ge=0.0, le=1.0)


class ExtractionOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    signals: list[ExtractedSignal]


_UNSUPPORTED_KEYS = {
    "minimum",
    "maximum",
    "exclusiveMinimum",
    "exclusiveMaximum",
    "multipleOf",
    "minLength",
    "maxLength",
    "pattern",
    "minItems",
    "maxItems",
    "uniqueItems",
    "default",
    "title",
}


def _clean(node: Any) -> Any:
    if isinstance(node, list):
        return [_clean(n) for n in node]
    if not isinstance(node, dict):
        return node
    out: dict[str, Any] = {}
    for key, value in node.items():
        if key == "properties" and isinstance(value, dict):
            # Property *names* (e.g. a field called "title") are not schema keywords.
            out[key] = {name: _clean(sub) for name, sub in value.items()}
        elif key in _UNSUPPORTED_KEYS:
            continue
        else:
            out[key] = _clean(value)
    if out.get("type") == "object" or "properties" in out:
        out["additionalProperties"] = False
        out["required"] = list(out.get("properties", {}))
    return out


def strict_json_schema(model: type[BaseModel]) -> dict[str, Any]:
    """Pydantic JSON schema → the subset structured outputs accepts.

    * every object gets ``additionalProperties: false`` and all properties ``required``
      (optional fields are expressed as ``anyOf [..., null]``, which Pydantic already emits);
    * numeric/string/array constraints are stripped — Pydantic re-validates them client-side
      after the response arrives.
    """
    cleaned: dict[str, Any] = _clean(copy.deepcopy(model.model_json_schema()))
    return cleaned
