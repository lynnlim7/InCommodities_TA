"""The position engine: net signed MWh per area per reporting period.

This is requirements.md S6 expressed as directly as it can be. For each reporting period
and each area, sum the signed MWh every trade delivers inside that period:

    NetMWh(area, period) = sum over trades in area of signedMW * coveredHours(trade, period)

The per-trade term lives on ``Trade.mwh_in``, so this module is only grouping and
summation. It contains no conditional on area, trade type, load profile, or product --
which is what lets a new area, profile, or trade type arrive without touching it
(S3.2, AC-18, AC-19).

Complexity is O(n*m): n trades by m reporting periods, 23 periods by default. Work is
proportional to trade/period intersections rather than to delivery hours, which is the
property AC-20 asks for. Trades that cannot touch any reported period are discarded once
up front, and trades are bucketed by area once, so the inner loop only visits trades that
could plausibly contribute.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal, localcontext

from app.config import DEFAULT_REPORTING_CONFIG, ReportingConfig
from app.core.interval import DateInterval
from app.core.periods import ReportPeriod, reporting_periods, reporting_window
from app.core.results import PositionRow, PositionView, PositionViews
from app.core.trade import Trade, TradeBook

AVERAGE_MW_PRECISION = 28
"""Significant digits used for the Average MW division.

Net MWh is exact: it is a sum of (decimal volume x integer hours) products. Average MW is
a ratio and can repeat -- 4,656 MWh over 168 hours is 27.714285... -- so it is the one
figure that cannot be represented exactly. It is computed well beyond any plausible
display precision and rounded only for presentation (S5.4).
"""


def calculate_views(
    book: TradeBook,
    as_of: date,
    config: ReportingConfig = DEFAULT_REPORTING_CONFIG,
) -> PositionViews:
    """Calculate every reporting view for a book as at ``as_of``.

    ``as_of`` is a required argument rather than a default of today, so that the result is
    fully determined by its inputs and a run is reproducible (S13.2).
    """
    periods = reporting_periods(as_of, config)
    areas = book.observed_areas
    trades_by_area = _bucket_by_area(book, reporting_window(periods))

    views = tuple(
        PositionView(
            granularity=granularity,
            rows=tuple(
                _row(area, period, trades_by_area[area])
                for period in view_periods
                for area in areas
            ),
        )
        for granularity, view_periods in periods.items()
    )
    return PositionViews(as_of=as_of, areas=areas, views=views)


def net_mwh(trades: tuple[Trade, ...], period: DateInterval) -> Decimal:
    """Net signed MWh delivered by ``trades`` inside ``period``.

    Buys and sells net algebraically, so an offsetting pair cancels to zero rather than
    being reported as two separate exposures (AC-07).
    """
    total = Decimal(0)
    for trade in trades:
        total += trade.mwh_in(period)
    return total


def average_mw(net: Decimal, period: DateInterval) -> Decimal:
    """Time-weighted average MW across the period's wall-clock hours (S6.3)."""
    with localcontext() as ctx:
        ctx.prec = AVERAGE_MW_PRECISION
        return net / period.hours


def _row(area: str, period: ReportPeriod, trades: tuple[Trade, ...]) -> PositionRow:
    net = net_mwh(trades, period.interval)
    return PositionRow(
        area=area,
        period=period,
        net_mwh=net,
        average_mw=average_mw(net, period.interval),
    )


def _bucket_by_area(
    book: TradeBook, window: DateInterval | None
) -> dict[str, tuple[Trade, ...]]:
    """Group trades by area, dropping any that cannot touch the reported window.

    A trade outside the window contributes zero to every period (S6.1), so discarding it
    here cannot change a result -- it only avoids asking the same question 23 times. The
    defaultdict means an area with no surviving trades still yields an empty bucket, which
    is how a zero-exposure area becomes a FLAT row rather than a missing one (AC-13).
    """
    buckets: defaultdict[str, list[Trade]] = defaultdict(list)
    for area in book.observed_areas:
        buckets[area] = []
    for trade in book:
        if window is not None and trade.interval.intersection(window) is None:
            continue
        buckets[trade.area].append(trade)
    return {area: tuple(trades) for area, trades in buckets.items()}
