"""The hand-written set (``golden/realistic.jsonl``) and how a prediction is scored against it.

Each case is one council exchange or budget-book excerpt with the signals a person expects.
A prediction matches an expected signal when one of its ``title_keywords`` appears in the
predicted title (or, failing that, its keywords; spaces ignored); each side matches at most once. Matched
pairs are then scored field by field. Predictions that match nothing count against precision.

Used by ``manage eval all`` (the configured extractor) and ``manage eval llm`` (a model/effort
comparison), so both report the same numbers for the same predictions.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from importlib import resources
from typing import Any

from app.domain.krw import amounts_agree, detect_table_unit
from app.llm.prompts import ChunkContext
from app.llm.schemas import ExtractedSignal
from app.pipeline.process import CheckedSignal, check_signal

FIELDS = ("category", "commitment", "budget", "expected_year")


def load_realistic() -> list[dict[str, Any]]:
    text = (
        resources.files("app.eval").joinpath("golden/realistic.jsonl").read_text(encoding="utf-8")
    )
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def context_for(case: dict[str, Any]) -> ChunkContext:
    return ChunkContext(
        doc_type=case["doc_type"],
        title=case["id"],
        institution=case.get("institution"),
        document_date=date.fromisoformat(case["date"]),
        labels=case.get("labels", []),
        text=case["text"],
        fiscal_year=case.get("fiscal_year"),
    )


def verify(case: dict[str, Any], sig: ExtractedSignal, *, min_score: float = 88.0) -> CheckedSignal:
    """Run the same grounding verifier the pipeline runs before storing a signal."""
    return check_signal(
        sig,
        text=case["text"],
        doc_type=case["doc_type"],
        reference_date=date.fromisoformat(case["date"]),
        fiscal_year=case.get("fiscal_year"),
        table_unit=detect_table_unit(case["text"]) or 1000,
        min_score=min_score,
    )


@dataclass(frozen=True, slots=True)
class Prediction:
    title: str
    keywords: tuple[str, ...]
    category: str
    commitment: str
    budget_krw: int | None
    expected_year: int | None

    @classmethod
    def of(cls, sig: ExtractedSignal, checked: CheckedSignal | None = None) -> Prediction:
        """The model's answer as-is, or — given ``checked`` — as the pipeline would store it."""
        return cls(
            title=sig.title,
            keywords=tuple(sig.keywords),
            category=getattr(sig.category, "value", str(sig.category)),
            commitment=sig.commitment,
            budget_krw=checked.budget_krw if checked else sig.budget_krw,
            expected_year=checked.expected_year if checked else sig.expected_year,
        )


def _squash(s: str) -> str:
    return s.replace(" ", "")


@dataclass(slots=True)
class Tally:
    expected: int = 0
    predicted: int = 0
    matched: int = 0
    field_ok: dict[str, int] = field(default_factory=lambda: dict.fromkeys(FIELDS, 0))
    failures: list[dict[str, Any]] = field(default_factory=list)

    def add(self, case: dict[str, Any], preds: list[Prediction]) -> None:
        expected = case["expected"]
        self.expected += len(expected)
        self.predicted += len(preds)
        pairs = _pair(expected, preds)
        for e, exp in enumerate(expected):
            hit = pairs.get(e)
            if hit is None:
                self.failures.append({"case": case["id"], "missing": exp["title_keywords"][0]})
                continue
            self.matched += 1
            p = preds[hit]
            ok = {
                "category": p.category == exp["category"],
                "commitment": p.commitment == exp["commitment"],
                "expected_year": p.expected_year == exp["expected_year"],
                "budget": (exp["budget_krw"] is None and p.budget_krw is None)
                or (
                    exp["budget_krw"] is not None
                    and p.budget_krw is not None
                    and amounts_agree(exp["budget_krw"], p.budget_krw, tolerance=0.02)
                ),
            }
            for k, v in ok.items():
                self.field_ok[k] += v
            wrong = [k for k, v in ok.items() if not v]
            if wrong:
                self.failures.append(
                    {
                        "case": case["id"],
                        "title": p.title,
                        "wrong": {
                            k: {
                                "got": _field(p, k),
                                "expected": exp["budget_krw" if k == "budget" else k],
                            }
                            for k in wrong
                        },
                    }
                )
        used = set(pairs.values())
        for i, p in enumerate(preds):
            if i not in used:
                self.failures.append({"case": case["id"], "unexpected": p.title})

    def summary(self) -> dict[str, Any]:
        precision = _ratio(self.matched, self.predicted)
        recall = _ratio(self.matched, self.expected)
        f1 = (
            round(2 * precision * recall / (precision + recall), 3)
            if precision and recall
            else None
        )
        return {
            "expected": self.expected,
            "predicted": self.predicted,
            "matched": self.matched,
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "field_accuracy": {k: _ratio(v, self.matched) for k, v in self.field_ok.items()},
        }


def _title(p: Prediction) -> str:
    return p.title


def _title_and_keywords(p: Prediction) -> str:
    return p.title + " ".join(p.keywords)


def _pair(expected: list[dict[str, Any]], preds: list[Prediction]) -> dict[int, int]:
    """expected index → prediction index. Titles first, keywords only for what is left, so a
    prediction whose keyword list happens to mention another project cannot take its match."""
    pairs: dict[int, int] = {}
    for text_of in (_title, _title_and_keywords):
        for e, exp in enumerate(expected):
            if e in pairs:
                continue
            taken = set(pairs.values())
            hit = next(
                (
                    i
                    for i, p in enumerate(preds)
                    if i not in taken
                    and any(_squash(k) in _squash(text_of(p)) for k in exp["title_keywords"])
                ),
                None,
            )
            if hit is not None:
                pairs[e] = hit
    return pairs


def _field(p: Prediction, name: str) -> Any:
    return p.budget_krw if name == "budget" else getattr(p, name)


def _ratio(num: int, den: int) -> float | None:
    return round(num / den, 3) if den else None
