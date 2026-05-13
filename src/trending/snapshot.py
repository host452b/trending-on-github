"""Atomic JSON snapshot writer.

Why atomic: a crashed run mid-write must not leave a half-written
.json file in the dataset. We use tempfile.mkstemp() to create a
temp file in the same directory as the target (so os.replace is
atomic on the same filesystem) and swap it into place only after
a successful serialisation.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from trending.parse import Record
from trending.period import file_name, period_for

_SOURCE_URLS = {
    "daily":   "https://github.com/trending?since=daily",
    "weekly":  "https://github.com/trending?since=weekly",
    "monthly": "https://github.com/trending?since=monthly",
}


def write_snapshot(
    out_dir: Path,
    granularity: str,
    run_dt: datetime,
    records: list[Record],
) -> Path:
    if granularity not in _SOURCE_URLS:
        raise ValueError(f"unknown granularity: {granularity!r}")
    run_date = run_dt.date()
    period = period_for(run_date, granularity)
    target = out_dir / file_name(run_date, granularity)
    target.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "granularity": granularity,
        "run_date_utc": _format_run_dt(run_dt),
        "period": {
            "start": period.start.isoformat(),
            "end":   period.end.isoformat(),
            "label_iso":     period.label_iso,
            "label_compact": period.label_compact,
        },
        "source_url": _SOURCE_URLS[granularity],
        "count": len(records),
        "items": [r.to_dict() for r in records],
    }

    body = json.dumps(payload, ensure_ascii=False, indent=2)

    tmp_fd, tmp_path = tempfile.mkstemp(
        prefix=".trending-",
        suffix=".json.tmp",
        dir=str(target.parent),
    )
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            f.write(body)
            f.write("\n")
        os.replace(tmp_path, target)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            # Best-effort cleanup; never suppress the original exception.
            pass
        raise
    return target


def _format_run_dt(run_dt: datetime) -> str:
    """ISO 8601 UTC with trailing 'Z' instead of '+00:00'."""
    if run_dt.tzinfo is None:
        # Treat naive datetimes as already being in UTC
        return run_dt.replace(microsecond=0).isoformat() + "Z"
    iso = run_dt.astimezone(timezone.utc).replace(microsecond=0).isoformat()
    # Python emits "+00:00"; normalize to the more conventional "Z"
    if iso.endswith("+00:00"):
        iso = iso[:-6] + "Z"
    return iso
