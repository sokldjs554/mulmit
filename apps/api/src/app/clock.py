"""Time helpers. Business dates (fiscal years, bid windows, digest days) are KST dates, while
containers run in UTC — ``date.today()`` would be wrong for nine hours every day."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))


def now_utc() -> datetime:
    return datetime.now(UTC)


def today_kst() -> date:
    return datetime.now(KST).date()
