from datetime import date

import pytest

from trending.parse import Record, parse_trending_html
from trending.period import period_for


@pytest.fixture()
def daily_html(fixtures_dir):
    return (fixtures_dir / "trending_daily.html").read_text(encoding="utf-8")


@pytest.fixture()
def weekly_html(fixtures_dir):
    return (fixtures_dir / "trending_weekly.html").read_text(encoding="utf-8")


@pytest.fixture()
def monthly_html(fixtures_dir):
    return (fixtures_dir / "trending_monthly.html").read_text(encoding="utf-8")


def test_daily_parses_at_least_10_records(daily_html):
    period = period_for(date(2026, 5, 13), "daily")
    records = parse_trending_html(daily_html, "daily", period)
    assert len(records) >= 10


def test_daily_record_required_fields(daily_html):
    period = period_for(date(2026, 5, 13), "daily")
    records = parse_trending_html(daily_html, "daily", period)
    for r in records:
        assert r.owner and r.name
        assert r.full_name == f"{r.owner}/{r.name}"
        assert r.url == f"https://github.com/{r.full_name}"
        assert r.stars_total >= 0
        assert r.forks_total >= 0
        assert r.contributors_visible >= 0
        assert r.period_stars >= 0


def test_daily_label_uses_compact_date(daily_html):
    period = period_for(date(2026, 5, 13), "daily")
    records = parse_trending_html(daily_html, "daily", period)
    for r in records:
        assert r.period_stars_label.endswith(" 2026.05.13"), r.period_stars_label
        assert "today" not in r.period_stars_label


def test_weekly_label_uses_compact_range(weekly_html):
    period = period_for(date(2026, 5, 13), "weekly")
    records = parse_trending_html(weekly_html, "weekly", period)
    assert records
    for r in records:
        assert r.period_stars_label.endswith(" 2026.05.07-2026.05.13"), r.period_stars_label
        assert "this week" not in r.period_stars_label


def test_monthly_label_uses_compact_range(monthly_html):
    period = period_for(date(2026, 5, 13), "monthly")
    records = parse_trending_html(monthly_html, "monthly", period)
    assert records
    for r in records:
        assert r.period_stars_label.endswith(" 2026.04.14-2026.05.13"), r.period_stars_label
        assert "this month" not in r.period_stars_label


def test_ranks_are_sequential_starting_at_1(daily_html):
    period = period_for(date(2026, 5, 13), "daily")
    records = parse_trending_html(daily_html, "daily", period)
    assert [r.rank for r in records] == list(range(1, len(records) + 1))


def test_malformed_row_is_skipped(daily_html):
    period = period_for(date(2026, 5, 13), "daily")
    # Inject a malformed row missing the stars link before the first real row
    broken = daily_html.replace(
        '<article class="Box-row"',
        '<article class="Box-row"><div>broken-row</div></article><article class="Box-row"',
        1,
    )
    records = parse_trending_html(broken, "daily", period)
    # We still get a sane number of records, the broken sentinel is dropped silently
    assert len(records) >= 10


def test_record_dict_round_trip(daily_html):
    period = period_for(date(2026, 5, 13), "daily")
    records = parse_trending_html(daily_html, "daily", period)
    d = records[0].to_dict()
    assert d["rank"] == 1
    assert d["owner"] and d["name"]
    assert "period_stars" in d
    assert "period_stars_label" in d
