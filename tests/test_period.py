from datetime import date

import pytest

from trending.period import Period, file_name, period_for


def test_daily_period_is_single_day():
    p = period_for(date(2026, 5, 13), "daily")
    assert p == Period(
        start=date(2026, 5, 13),
        end=date(2026, 5, 13),
        label_iso="2026-05-13",
        label_compact="2026.05.13",
    )


def test_weekly_period_is_rolling_7_days():
    p = period_for(date(2026, 5, 13), "weekly")
    assert p.start == date(2026, 5, 7)
    assert p.end == date(2026, 5, 13)
    assert p.label_iso == "2026-05-07/2026-05-13"
    assert p.label_compact == "2026.05.07-2026.05.13"


def test_monthly_period_is_rolling_30_days():
    p = period_for(date(2026, 5, 13), "monthly")
    assert p.start == date(2026, 4, 14)
    assert p.end == date(2026, 5, 13)
    assert p.label_iso == "2026-04-14/2026-05-13"
    assert p.label_compact == "2026.04.14-2026.05.13"


def test_weekly_period_crosses_month_boundary():
    p = period_for(date(2026, 5, 1), "weekly")
    assert p.start == date(2026, 4, 25)
    assert p.end == date(2026, 5, 1)


def test_monthly_period_crosses_year_boundary():
    p = period_for(date(2026, 1, 5), "monthly")
    assert p.start == date(2025, 12, 7)
    assert p.end == date(2026, 1, 5)


def test_daily_leap_day():
    p = period_for(date(2024, 2, 29), "daily")
    assert p.start == p.end == date(2024, 2, 29)
    assert p.label_compact == "2024.02.29"


def test_unknown_granularity_raises():
    with pytest.raises(ValueError, match="unknown granularity"):
        period_for(date(2026, 5, 13), "yearly")


def test_file_name_daily():
    assert file_name(date(2026, 5, 13), "daily") == "daily/2026-05-13.json"


def test_file_name_weekly_iso_week_20():
    # 2026-05-13 is a Wednesday in ISO week 20 (Mon May 11 – Sun May 17)
    assert file_name(date(2026, 5, 13), "weekly") == "weekly/2026-W20.json"


def test_file_name_monthly():
    assert file_name(date(2026, 5, 13), "monthly") == "monthly/2026-05.json"


def test_file_name_weekly_pads_single_digit_week():
    # 2026-01-05 is in ISO week 2 → must be zero-padded as W02
    assert file_name(date(2026, 1, 5), "weekly") == "weekly/2026-W02.json"
