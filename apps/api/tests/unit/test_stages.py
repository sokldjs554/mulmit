from datetime import date

from app.domain.stages import CANCELS_KEY, withdrawn_bids

D1, D2, D3 = date(2026, 9, 1), date(2026, 9, 5), date(2026, 9, 9)


def bid(no: str) -> dict[str, str]:
    return {"bid_notice_no": no}


def cancel(no: str) -> dict[str, str]:
    return {"bid_notice_no": no, CANCELS_KEY: no}


def test_a_cancel_withdraws_its_own_number_only() -> None:
    assert withdrawn_bids([(bid("A"), D1), (cancel("A"), D2), (bid("B"), D1)]) == {"A"}


def test_a_reannouncement_under_the_same_number_puts_it_back() -> None:
    assert withdrawn_bids([(bid("A"), D1), (cancel("A"), D2), (bid("A"), D3)]) == set()


def test_on_the_same_day_the_cancel_wins() -> None:
    assert withdrawn_bids([(cancel("A"), D2), (bid("A"), D2)]) == {"A"}


def test_a_cancel_seen_without_its_notice_still_counts() -> None:
    # The window can cut the original 공고 off; the 취소 carries the number itself.
    assert withdrawn_bids([(cancel("A"), D2)]) == {"A"}


def test_records_without_a_bid_number_are_ignored() -> None:
    assert withdrawn_bids([({"order_plan_no": "P"}, D1)]) == set()
