"""
Reporting windows: the daily, weekly, and monthly reporting periods for
position views using calendar weeks.
"""

from __future__ import annotations

from datetime import date, timedelta

from app.core.models import DeliveryPeriod, ReportingPeriod


def daily_periods(
        as_of: date, # 1 October 2026, Thursday
        count: int = 7,
) -> tuple[ReportingPeriod, ...]:

    return tuple(
        ReportingPeriod(
            label=(as_of + timedelta(days=offset)).isoformat(),
            delivery=DeliveryPeriod(
                start=as_of + timedelta(days=offset),
                end=as_of + timedelta(days=offset + 1),
            ),
        )
        for offset in range(count)
    )

def weekly_periods(
        as_of: date, 
        count: int=4, 
) -> tuple[ReportingPeriod, ...]:
    """Forward looking Monday to Sunday calendar week periods."""

    periods: list[ReportingPeriod] = []

    days_until_next_monday = 7 - as_of.weekday()

    start = as_of
    end = as_of + timedelta(days=days_until_next_monday)

    for _ in range(count):
        periods.append(
            ReportingPeriod(
                label=(
                    f"{start.isoformat()} to "
                    f"{(end - timedelta(days=1)).isoformat()}"
                ),
                delivery=DeliveryPeriod(
                    start=start,
                    end=end,
                ),
            )
        )

        start = end
        end = start + timedelta(weeks=1)

    return tuple(periods)

def monthly_periods(
        as_of: date, 
        count: int=12,
) -> tuple[ReportingPeriod, ...]:

    periods: list[ReportingPeriod] = []

    year = as_of.year
    month = as_of.month

    for offset in range(count):
        current_year, current_month = _shift_month(
            year, 
            month, 
            offset,
        )

        next_year, next_month = _shift_month(
            current_year, 
            current_month,
            1,
        )

        start = (
            as_of if offset == 0 else date(current_year, current_month, 1)
        )

        end = date(
            next_year,
            next_month,
            1
        )

        periods.append(
            ReportingPeriod(
                label=date(
                    current_year,
                    current_month,
                    1,
                ).strftime("%b-%y"),
                delivery=DeliveryPeriod(
                    start=start,
                    end=end,
                ),
            )
        )

    return tuple(periods)

def _shift_month(
        year: int, 
        month: int, 
        offset: int, 
) -> tuple[int, int]:

    zero_based = (year * 12 + month - 1) + offset

    shifted_year, shifted_month = divmod(
        zero_based, 
        12,
    )

    return shifted_year, shifted_month + 1