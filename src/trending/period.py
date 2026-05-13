"""Pure date math for the three trending granularities.

`period_for(run_date, granularity)` returns a `Period` describing the
rolling window the trending page covers when crawled on `run_date`.
`file_name(run_date, granularity)` returns the snapshot file path
(relative to the data directory).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

Granularity = str  # "daily" | "weekly" | "monthly"

_WINDOW_DAYS: dict[Granularity, int] = {
    "daily": 1,
    "weekly": 7,
    "monthly": 30,
}


@dataclass(frozen=True)
class Period:
    start: date
    end: date
    label_iso: str
    label_compact: str


def period_for(run_date: date, granularity: Granularity) -> Period:
    if granularity not in _WINDOW_DAYS:
        raise ValueError(f"unknown granularity: {granularity!r}")
    days = _WINDOW_DAYS[granularity]
    start = run_date - timedelta(days=days - 1)
    end = run_date
    if start == end:
        label_iso = start.isoformat()
        label_compact = start.strftime("%Y.%m.%d")
    else:
        label_iso = f"{start.isoformat()}/{end.isoformat()}"
        label_compact = f"{start.strftime('%Y.%m.%d')}-{end.strftime('%Y.%m.%d')}"
    return Period(start=start, end=end, label_iso=label_iso, label_compact=label_compact)


def file_name(run_date: date, granularity: Granularity) -> str:
    if granularity == "daily":
        return f"daily/{run_date.isoformat()}.json"
    if granularity == "weekly":
        iso_year, iso_week, _ = run_date.isocalendar()
        return f"weekly/{iso_year}-W{iso_week:02d}.json"
    if granularity == "monthly":
        return f"monthly/{run_date.year:04d}-{run_date.month:02d}.json"
    raise ValueError(f"unknown granularity: {granularity!r}")
