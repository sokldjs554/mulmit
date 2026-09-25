"""Procurement thesaurus: the same thing, named differently at each stage.

Council members say "스쿨존 카메라", the budget book says "어린이보호구역 지능형 CCTV", the tender
says "스쿨존 AI 안전카메라 설치사업". A multilingual embedding model (Voyage) learns much of this;
the offline hashing embedder cannot. Canonicalising known synonyms before similarity scoring
closes most of that gap at zero cost, and helps the model-based path too.

Groups are curated from how 나라장터 titles and 예산서 세부사업명 name the same purchase. The first
entry of each group is the canonical form. Longest variants are replaced first.
"""

from __future__ import annotations

import re

SYNONYM_GROUPS: tuple[tuple[str, ...], ...] = (
    ("어린이보호구역", "스쿨존", "학교 앞"),
    (
        "스마트쉘터",
        "스마트 쉘터",
        "스마트 버스정류장",
        "스마트버스정류장",
        "스마트정류장",
        "스마트 정류장",
    ),
    ("수요응답형교통", "수요응답형 교통", "수요응답형", "수요응답", "DRT", "부르면 오는 버스"),
    ("태양광", "신재생에너지", "재생에너지", "신재생 에너지"),
    ("인공지능", "AI"),
    ("누리집", "홈페이지"),
    ("예경보", "예·경보", "예측·경보", "예측 경보", "경보"),
    ("CCTV", "안전카메라", "씨씨티비", "단속카메라"),
    ("챗봇", "AI 상담", "상담봇"),
    ("돌봄스피커", "돌봄 스피커", "AI 스피커", "인공지능 스피커", "돌봄서비스", "돌봄 서비스"),
    ("메이커스페이스", "메이커 스페이스"),
    ("미디어파사드", "미디어 파사드"),
    ("주차안내", "주차정보 안내", "주차 안내", "주차정보안내"),
    ("디지털트윈", "디지털 트윈", "3D 디지털트윈", "3차원 디지털트윈"),
    ("리모델링", "개보수", "리노베이션"),
    ("전기차충전", "전기차 충전", "급속충전기", "충전소", "충전기", "충전인프라"),
    ("침수", "하천 수위", "수위"),
    ("클라우드전환", "클라우드 전환", "클라우드 네이티브", "클라우드 이전"),
    ("고독사", "안부확인", "안부 확인"),
    ("상권분석", "상권 분석", "골목상권"),
    ("가로등", "LED 가로등", "스마트 가로등"),
    ("선별관제", "지능형 관제", "지능형 선별관제"),
    ("스마트폴", "스마트 폴", "스마트 기둥"),
)

_REPLACEMENTS: list[tuple[re.Pattern[str], str]] = sorted(
    (
        (re.compile(re.escape(variant), re.IGNORECASE), group[0])
        for group in SYNONYM_GROUPS
        for variant in group[1:]
    ),
    key=lambda pair: len(pair[0].pattern),
    reverse=True,
)


def canonicalize(text: str) -> str:
    """Replace known variants with their canonical form (longest variants first)."""
    out = text
    for pattern, canonical in _REPLACEMENTS:
        out = pattern.sub(canonical, out)
    return out


def canonical_terms(text: str) -> set[str]:
    """Canonical terms present in ``text`` — a compact, synonym-free fingerprint."""
    canon = canonicalize(text)
    return {group[0] for group in SYNONYM_GROUPS if group[0].lower() in canon.lower()}
