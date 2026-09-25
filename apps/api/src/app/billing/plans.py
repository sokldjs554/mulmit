"""Plans and credit prices.

Subscription buys *coverage* (how many watch regions, which alert channels) and a monthly
credit grant; credits pay for the expensive, per-use LLM work (Deep Brief). Credits granted by a
plan expire at the end of the period; purchased credits do not — the ledger keeps them apart via
``reason``.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Plan:
    key: str
    name: str
    monthly_price_krw: int
    monthly_credits: int
    max_regions: int | None
    channels: tuple[str, ...]
    instant_alerts: bool


PLANS: dict[str, Plan] = {
    "free": Plan("free", "Free", 0, 3, 1, ("email",), False),
    "pro": Plan("pro", "Pro", 99_000, 40, 5, ("email", "slack"), True),
    "team": Plan("team", "Team", 290_000, 150, None, ("email", "slack", "kakao"), True),
}

BRIEF_CREDIT_COST = 3

CREDIT_PACKS: dict[str, tuple[int, int]] = {
    # key: (credits, price KRW incl. VAT)
    "pack_30": (30, 33_000),
    "pack_100": (100, 99_000),
}

DUNNING_SCHEDULE_DAYS = (1, 3, 7)  # retry a failed renewal after these many days, then cancel
