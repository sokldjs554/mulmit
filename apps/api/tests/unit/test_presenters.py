from datetime import date

from app.api.presenters import head_start_days
from app.db.models import Opportunity


def _opp(first: date, *, published: date | None = None, window: date | None = None) -> Opportunity:
    return Opportunity(first_seen_at=first, bid_published_at=published, bid_window_start=window)


def test_head_start_runs_to_the_actual_tender_when_there_is_one() -> None:
    opp = _opp(date(2025, 8, 9), published=date(2026, 9, 5), window=date(2026, 9, 5))
    assert head_start_days(opp) == 392


def test_head_start_runs_to_the_forecast_window_before_the_tender() -> None:
    assert head_start_days(_opp(date(2025, 11, 20), window=date(2026, 6, 1))) == 193


def test_no_head_start_when_the_tender_was_the_first_signal_or_nothing_is_forecast() -> None:
    assert head_start_days(_opp(date(2026, 9, 5), published=date(2026, 9, 5))) is None
    assert head_start_days(_opp(date(2026, 1, 5))) is None
