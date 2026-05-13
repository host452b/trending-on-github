import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from trending.parse import Record
from trending.snapshot import write_snapshot


def _make_record(rank: int = 1) -> Record:
    return Record(
        rank=rank,
        owner="microsoft",
        name="vscode",
        full_name="microsoft/vscode",
        url="https://github.com/microsoft/vscode",
        description="Visual Studio Code",
        language="TypeScript",
        stars_total=162345,
        forks_total=28901,
        contributors_visible=5,
        period_stars=1273,
        period_stars_label="1,273 stars 2026-05-13",
    )


def test_write_snapshot_creates_expected_path(tmp_path: Path):
    run_dt = datetime(2026, 5, 13, 0, 30, 0, tzinfo=timezone.utc)
    out = write_snapshot(
        out_dir=tmp_path,
        granularity="daily",
        run_dt=run_dt,
        records=[_make_record()],
    )
    assert out == tmp_path / "daily" / "2026-05-13.json"
    assert out.exists()


def test_write_snapshot_content_schema(tmp_path: Path):
    run_dt = datetime(2026, 5, 13, 0, 30, 0, tzinfo=timezone.utc)
    out = write_snapshot(
        out_dir=tmp_path,
        granularity="daily",
        run_dt=run_dt,
        records=[_make_record()],
    )
    data = json.loads(out.read_text())
    assert data["granularity"] == "daily"
    assert data["run_date_utc"] == "2026-05-13T00:30:00Z"
    assert data["period"]["start"] == "2026-05-13"
    assert data["period"]["end"] == "2026-05-13"
    assert data["period"]["label_iso"] == "2026-05-13"
    assert data["period"]["label_compact"] == "2026.05.13"
    assert data["source_url"] == "https://github.com/trending?since=daily"
    assert data["count"] == 1
    assert data["items"][0]["full_name"] == "microsoft/vscode"


def test_write_snapshot_weekly_path_uses_iso_week(tmp_path: Path):
    run_dt = datetime(2026, 5, 13, 0, 30, 0, tzinfo=timezone.utc)
    out = write_snapshot(
        out_dir=tmp_path,
        granularity="weekly",
        run_dt=run_dt,
        records=[_make_record()],
    )
    assert out == tmp_path / "weekly" / "2026-W20.json"


def test_write_snapshot_monthly_path_uses_calendar_month(tmp_path: Path):
    run_dt = datetime(2026, 5, 13, 0, 30, 0, tzinfo=timezone.utc)
    out = write_snapshot(
        out_dir=tmp_path,
        granularity="monthly",
        run_dt=run_dt,
        records=[_make_record()],
    )
    assert out == tmp_path / "monthly" / "2026-05.json"


def test_write_snapshot_is_atomic_on_failure(tmp_path: Path, monkeypatch):
    """If os.replace fails mid-swap, the previous file content must survive
    and no temp file may be left behind in the target directory."""
    target = tmp_path / "daily" / "2026-05-13.json"
    target.parent.mkdir(parents=True)
    target.write_text('{"sentinel": true}')

    def boom(*args, **kwargs):
        raise RuntimeError("rename failed")

    # Patch via the snapshot module's reference so the real os.replace
    # remains available to the rest of the test infrastructure.
    monkeypatch.setattr("trending.snapshot.os.replace", boom)

    run_dt = datetime(2026, 5, 13, 0, 30, 0, tzinfo=timezone.utc)
    with pytest.raises(RuntimeError, match="rename failed"):
        write_snapshot(
            out_dir=tmp_path,
            granularity="daily",
            run_dt=run_dt,
            records=[_make_record()],
        )
    # Previous content is intact
    assert target.read_text() == '{"sentinel": true}'
    # No leftover temp files in the target directory
    leftovers = [p for p in target.parent.iterdir() if p != target]
    assert leftovers == []


def test_write_snapshot_with_empty_records(tmp_path: Path):
    run_dt = datetime(2026, 5, 13, 0, 30, 0, tzinfo=timezone.utc)
    out = write_snapshot(
        out_dir=tmp_path,
        granularity="daily",
        run_dt=run_dt,
        records=[],
    )
    data = json.loads(out.read_text())
    assert data["count"] == 0
    assert data["items"] == []
