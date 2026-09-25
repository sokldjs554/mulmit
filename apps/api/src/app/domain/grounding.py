"""Grounding verifier — the deterministic referee between the LLM and the database.

An extraction is only as trustworthy as the text it can point at. For every signal the LLM (or
the heuristic extractor) proposes, we check, without any model in the loop:

1. **Evidence** — each quote must be locatable in the source chunk: exact after whitespace/NFKC
   normalisation, or fuzzy (partial-ratio alignment) above a threshold that tolerates OCR noise.
   Offsets are mapped back to the original document for UI highlighting.
2. **Budget** — ``budget_krw`` must agree (±1%) with an amount parsed by :mod:`app.domain.krw`
   from the located evidence or the quoted budget phrase. The model never gets the last word on
   a number.
3. **Timing** — ``expected_year`` must follow from the quoted timing phrase and the meeting date.

The verdict routes the signal: ``accepted`` goes straight to linking, ``needs_review`` lands in
the admin review queue, ``rejected`` is stored for eval but never shown to customers.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any, Literal

from rapidfuzz import fuzz

from app.domain.krw import amounts_agree, find_amounts
from app.domain.text import collapse_ws, normalize_with_map
from app.domain.timing import resolve_timing

Verdict = Literal["accepted", "needs_review", "rejected"]


@dataclass(frozen=True, slots=True)
class EvidenceCheck:
    quote: str
    found: bool
    score: float
    start: int | None
    end: int | None
    method: Literal["exact", "fuzzy", "missing"]


def locate_quote(source: str, quote: str, *, min_score: float = 88.0) -> EvidenceCheck:
    norm_src, index_map = normalize_with_map(source)
    norm_q = collapse_ws(quote).strip(" \"'“”‘’…")
    if len(norm_q) < 4 or not norm_src:
        return EvidenceCheck(quote, False, 0.0, None, None, "missing")
    pos = norm_src.find(norm_q)
    if pos >= 0:
        end = pos + len(norm_q) - 1
        return EvidenceCheck(quote, True, 100.0, index_map[pos], index_map[end] + 1, "exact")
    alignment = fuzz.partial_ratio_alignment(norm_q, norm_src, score_cutoff=min_score)
    if alignment is not None and alignment.dest_end > alignment.dest_start:
        start = index_map[alignment.dest_start]
        end_idx = index_map[min(alignment.dest_end, len(index_map)) - 1] + 1
        return EvidenceCheck(quote, True, round(alignment.score, 1), start, end_idx, "fuzzy")
    return EvidenceCheck(quote, False, 0.0, None, None, "missing")


@dataclass(slots=True)
class GroundingReport:
    evidence: list[EvidenceCheck]
    budget_claimed: int | None
    budget_parsed: int | None
    budget_grounded: bool | None
    year_claimed: int | None
    year_resolved: int | None
    year_grounded: bool | None
    issues: list[str] = field(default_factory=list)
    verdict: Verdict = "accepted"

    @property
    def evidence_ratio(self) -> float:
        if not self.evidence:
            return 0.0
        return sum(e.found for e in self.evidence) / len(self.evidence)

    def to_json(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["evidence_ratio"] = round(self.evidence_ratio, 3)
        return payload


def verify_extraction(
    *,
    source: str,
    evidence_quotes: list[str],
    budget_krw: int | None,
    budget_text: str | None,
    expected_year: int | None,
    timing_text: str | None,
    reference_date: date,
    confidence: float,
    min_score: float = 88.0,
    default_unit: int = 1,
) -> GroundingReport:
    checks = [locate_quote(source, q, min_score=min_score) for q in evidence_quotes]
    report = GroundingReport(
        evidence=checks,
        budget_claimed=budget_krw,
        budget_parsed=None,
        budget_grounded=None,
        year_claimed=expected_year,
        year_resolved=None,
        year_grounded=None,
    )

    found_spans = [source[c.start : c.end] for c in checks if c.found and c.start is not None]
    if not checks or not any(c.found for c in checks):
        report.issues.append("evidence_not_found")
    elif report.evidence_ratio < 1.0:
        report.issues.append("partial_evidence")

    if budget_krw is not None:
        candidates: list[int] = []
        table = default_unit != 1  # budget-book context: bare "352,000" cells are amounts
        for span in found_spans:
            candidates += [
                a.value for a in find_amounts(span, default_unit=default_unit, bare_numbers=table)
            ]
        if budget_text and locate_quote(source, budget_text, min_score=min_score).found:
            candidates += [
                a.value
                for a in find_amounts(budget_text, default_unit=default_unit, bare_numbers=table)
            ]
        report.budget_parsed = max(candidates) if candidates else None
        report.budget_grounded = any(amounts_agree(budget_krw, c) for c in candidates)
        if not report.budget_grounded:
            report.issues.append("budget_mismatch" if candidates else "budget_unsupported")

    if expected_year is not None:
        timing_sources = [timing_text] if timing_text else []
        timing_sources += found_spans
        for phrase in timing_sources:
            if phrase and (t := resolve_timing(phrase, reference_date)) is not None:
                report.year_resolved = t.year
                break
        report.year_grounded = report.year_resolved == expected_year
        if not report.year_grounded:
            report.issues.append("year_unverified")

    if confidence < 0.4:
        report.issues.append("low_confidence")

    if "evidence_not_found" in report.issues:
        report.verdict = "rejected"
    elif report.issues:
        report.verdict = "needs_review"
    return report
