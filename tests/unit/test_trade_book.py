"""Trade book identity and area observation (AC-01, AC-08, AC-13, AC-15, AC-18)."""

from __future__ import annotations

from datetime import date

import pytest

from app.core import DateInterval, DuplicateTradeIdError, TradeBook
from tests.builders import make_trade

pytestmark = pytest.mark.unit


class TestIdentity:
    def test_unique_trade_ids_are_accepted(self) -> None:
        book = TradeBook((make_trade(trade_id="T001"), make_trade(trade_id="T002")))

        assert len(book) == 2

    def test_duplicate_trade_id_is_rejected_not_deduplicated(self) -> None:
        """AC-15: two rows sharing an id make the book ambiguous. Silently dropping one
        could halve a real position, so the book refuses to exist."""
        with pytest.raises(DuplicateTradeIdError) as exc:
            TradeBook((make_trade(trade_id="T001"), make_trade(trade_id="T001", volume_mw=99)))

        assert "T001" in str(exc.value)

    def test_every_duplicated_id_is_reported_at_once(self) -> None:
        """A user should be able to fix the whole file in one pass (AC-14)."""
        with pytest.raises(DuplicateTradeIdError) as exc:
            TradeBook(
                (
                    make_trade(trade_id="T001"),
                    make_trade(trade_id="T001"),
                    make_trade(trade_id="T002"),
                    make_trade(trade_id="T002"),
                )
            )

        message = str(exc.value)
        assert "T001" in message and "T002" in message

    def test_empty_book_is_valid(self) -> None:
        """An empty book is a legitimate state -- it should produce FLAT rows, not a crash."""
        book = TradeBook(())

        assert len(book) == 0
        assert book.observed_areas == ()
        assert book.horizon is None


class TestObservedAreas:
    def test_areas_are_distinct(self) -> None:
        book = TradeBook(
            (
                make_trade(trade_id="T001", area="Tokyo"),
                make_trade(trade_id="T002", area="Tokyo"),
                make_trade(trade_id="T003", area="Kansai"),
            )
        )

        assert book.observed_areas == ("Tokyo", "Kansai")

    def test_areas_follow_grid_order_not_insertion_or_alphabetical_order(self) -> None:
        """S8.3 requires a stable ordering. Grid order puts Tokyo before Kansai, which is
        also the order the expected results in S9 are presented in."""
        book = TradeBook(
            (
                make_trade(trade_id="T001", area="Kyushu"),
                make_trade(trade_id="T002", area="Kansai"),
                make_trade(trade_id="T003", area="Tokyo"),
                make_trade(trade_id="T004", area="Hokkaido"),
            )
        )

        assert book.observed_areas == ("Hokkaido", "Tokyo", "Kansai", "Kyushu")

    def test_unknown_area_is_accepted_and_sorts_after_known_areas(self) -> None:
        """AC-18: a new area flows through as data. It is not rejected, and it does not
        need a code change -- it simply sorts after the nine configured areas."""
        book = TradeBook(
            (
                make_trade(trade_id="T001", area="Okinawa"),
                make_trade(trade_id="T002", area="Tokyo"),
            )
        )

        assert book.observed_areas == ("Tokyo", "Okinawa")

    def test_area_ordering_is_stable_across_rebuilds(self) -> None:
        """AC-01: repeated runs must produce identical results, which requires the area
        ordering to be deterministic rather than set-iteration order."""
        trades = (
            make_trade(trade_id="T001", area="Kansai"),
            make_trade(trade_id="T002", area="Tokyo"),
            make_trade(trade_id="T003", area="Chubu"),
        )

        orderings = {TradeBook(trades).observed_areas for _ in range(10)}
        assert orderings == {("Tokyo", "Chubu", "Kansai")}


class TestHorizon:
    def test_horizon_spans_the_earliest_start_to_the_latest_end(self) -> None:
        """The supplied book runs 1 January 2026 to 1 April 2028 (S4.2)."""
        book = TradeBook(
            (
                make_trade(trade_id="T001", start=date(2026, 1, 1), end=date(2027, 1, 1)),
                make_trade(trade_id="T009", start=date(2027, 4, 1), end=date(2028, 4, 1)),
            )
        )

        assert book.horizon == DateInterval(date(2026, 1, 1), date(2028, 4, 1))

    def test_horizon_of_a_single_trade_is_its_own_interval(self) -> None:
        trade = make_trade(start=date(2026, 10, 1), end=date(2026, 11, 1))

        assert TradeBook((trade,)).horizon == trade.interval
