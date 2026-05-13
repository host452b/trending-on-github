"""CLI: python -m trending --granularity {daily|weekly|monthly} --out data"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, datetime, timezone
from pathlib import Path

from trending.fetch import fetch_trending
from trending.parse import parse_trending_html
from trending.period import period_for
from trending.snapshot import write_snapshot

log = logging.getLogger("trending")

_GRANULARITIES = ("daily", "weekly", "monthly")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m trending")
    p.add_argument("--granularity", required=True, choices=_GRANULARITIES)
    p.add_argument("--out", required=True, type=Path,
                   help="Output directory (e.g. ./data)")
    p.add_argument("--run-date", default=None, type=date.fromisoformat,
                   metavar="YYYY-MM-DD",
                   help="UTC date YYYY-MM-DD; defaults to today (UTC)")
    p.add_argument("--verbose", "-v", action="store_true")
    args = p.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    if args.run_date is not None:
        run_dt = datetime(
            args.run_date.year, args.run_date.month, args.run_date.day,
            tzinfo=timezone.utc,
        )
    else:
        run_dt = datetime.now(tz=timezone.utc).replace(microsecond=0)

    period = period_for(run_dt.date(), args.granularity)
    log.info(
        "fetching %s trending (run_date=%s, window=%s)",
        args.granularity, run_dt.date().isoformat(), period.label_compact,
    )
    try:
        html = fetch_trending(args.granularity)
    except Exception as exc:
        log.error("fetch failed for %s: %s", args.granularity, exc)
        return 1

    records = parse_trending_html(html, args.granularity, period)
    if not records:
        log.error("parsed zero records for %s — refusing to write empty snapshot",
                  args.granularity)
        return 1

    target = write_snapshot(
        out_dir=args.out,
        granularity=args.granularity,
        run_dt=run_dt,
        records=records,
    )
    log.info("wrote %d records to %s", len(records), target)
    return 0


if __name__ == "__main__":
    sys.exit(main())
