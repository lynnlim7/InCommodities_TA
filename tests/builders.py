"""Test data builders.

A builder with sensible defaults keeps each test focused on the one field it is about,
which matters when there are a dozen trade fields and only five of them affect a position.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.core import BASE, DateInterval, Direction, LoadProfile, Trade, TradeBook


def make_trade(
    *,
    trade_id: str = "T001",
    trade_date: date = date(2026, 9, 1),
    counterparty: str = "Sakura Power Trading",
    area: str = "Tokyo",
    trade_type: str = "Futures",
    direction: Direction = Direction.BUY,
    product: str = "Oct-26 Base",
    profile: LoadProfile = BASE,
    start: date = date(2026, 10, 1),
    end: date = date(2026, 11, 1),
    volume_mw: Decimal | int = 10,
    price_jpy_kwh: Decimal | str = "14.00",
) -> Trade:
    return Trade(
        trade_id=trade_id,
        trade_date=trade_date,
        counterparty=counterparty,
        area=area,
        trade_type=trade_type,
        direction=direction,
        product=product,
        profile=profile,
        interval=DateInterval(start, end),
        volume_mw=Decimal(volume_mw),
        price_jpy_kwh=Decimal(price_jpy_kwh),
    )


# The twelve supplied trades, transcribed from src/app/data/trades.csv.
#
# Held in code so the core can be verified without a filesystem or a CSV parser, which is
# what requirements.md S13.3 asks for. M4 closes the loop by asserting that reading the
# CSV produces exactly this book, so the transcription cannot silently drift.
#
# (trade_id, trade_date, counterparty, area, buy_sell, product, start, end, mw, price)
_SUPPLIED_ROWS: tuple[tuple[str, str, str, str, str, str, str, str, int, str], ...] = (
    ("T001", "2025-09-10", "Sakura Power Trading", "Tokyo", "Buy", "Cal-26 Base", "2026-01-01", "2027-01-01", 20, "13.50"),
    ("T002", "2026-06-12", "Kanto Energy Partners", "Tokyo", "Buy", "Q4-26 Base", "2026-10-01", "2027-01-01", 15, "14.20"),
    ("T003", "2026-09-03", "Fuji Utility Services", "Tokyo", "Sell", "Oct-26 Base", "2026-10-01", "2026-11-01", 5, "15.10"),
    ("T004", "2026-09-30", "Sakura Power Trading", "Tokyo", "Buy", "Week 42-26 Base", "2026-10-12", "2026-10-19", 10, "13.80"),
    ("T005", "2026-10-01", "Minato Hedge Co", "Tokyo", "Sell", "Weekend 10-11 Oct-26 Base", "2026-10-10", "2026-10-12", 8, "12.40"),
    ("T006", "2026-09-15", "Kanto Energy Partners", "Tokyo", "Buy", "Nov-26 Base", "2026-11-01", "2026-12-01", 10, "14.60"),
    ("T007", "2026-09-22", "Fuji Utility Services", "Tokyo", "Sell", "Dec-26 Base", "2026-12-01", "2027-01-01", 5, "15.30"),
    ("T008", "2026-07-08", "Minato Hedge Co", "Tokyo", "Buy", "Q1-27 Base", "2027-01-01", "2027-04-01", 25, "16.00"),
    ("T009", "2026-08-20", "Sakura Power Trading", "Tokyo", "Buy", "FY-27 Base", "2027-04-01", "2028-04-01", 15, "13.20"),
    ("T010", "2026-09-29", "Kanto Energy Partners", "Tokyo", "Sell", "Q2-27 Base", "2027-04-01", "2027-07-01", 5, "12.90"),
    ("T011", "2026-09-08", "Osaka Grid Trading", "Kansai", "Buy", "Q4-26 Base", "2026-10-01", "2027-01-01", 12, "13.10"),
    ("T012", "2026-09-25", "Osaka Grid Trading", "Kansai", "Sell", "Week 41-26 Base", "2026-10-05", "2026-10-12", 6, "12.80"),
)


def supplied_book() -> TradeBook:
    """The trade book from the supplied CSV, built without reading the file."""
    return TradeBook(
        tuple(
            make_trade(
                trade_id=trade_id,
                trade_date=date.fromisoformat(trade_date),
                counterparty=counterparty,
                area=area,
                direction=Direction.parse(buy_sell),
                product=product,
                start=date.fromisoformat(start),
                end=date.fromisoformat(end),
                volume_mw=volume_mw,
                price_jpy_kwh=price,
            )
            for (
                trade_id,
                trade_date,
                counterparty,
                area,
                buy_sell,
                product,
                start,
                end,
                volume_mw,
                price,
            ) in _SUPPLIED_ROWS
        )
    )


AS_OF = date(2026, 10, 1)
"""The as-of date the assessment specifies (requirements.md S3.1)."""
