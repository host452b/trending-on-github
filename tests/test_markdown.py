"""Smoke tests for build_markdown.py.

build_markdown.py lives at the repo root (not inside the trending
package), so we import it via importlib.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def md_mod():
    path = REPO_ROOT / "build_markdown.py"
    spec = importlib.util.spec_from_file_location("build_markdown", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_escape_pipe_replaces_only_pipes(md_mod):
    assert md_mod.escape_pipe("a|b|c") == "a\\|b\\|c"
    assert md_mod.escape_pipe("nothing-special") == "nothing-special"
    assert md_mod.escape_pipe("") == ""
    # None passes through as empty string
    assert md_mod.escape_pipe(None) == ""


def test_escape_pipe_is_idempotent(md_mod):
    once = md_mod.escape_pipe("a|b")
    twice = md_mod.escape_pipe(once)
    assert twice == once == "a\\|b"


def test_format_int_groups_thousands(md_mod):
    assert md_mod.format_int(1234) == "1,234"
    assert md_mod.format_int(0) == "0"
    assert md_mod.format_int(1_000_000) == "1,000,000"


import json


def test_read_snapshots_returns_chronological_order(md_mod, tmp_path):
    daily = tmp_path / "daily"
    daily.mkdir()
    (daily / "2026-05-12.json").write_text(json.dumps({"count": 1, "items": []}))
    (daily / "2026-05-13.json").write_text(json.dumps({"count": 2, "items": []}))
    (daily / "2026-05-14.json").write_text(json.dumps({"count": 3, "items": []}))
    pairs = md_mod.read_snapshots(tmp_path, "daily")
    names = [p.name for p, _ in pairs]
    assert names == ["2026-05-12.json", "2026-05-13.json", "2026-05-14.json"]


def test_read_snapshots_returns_empty_when_folder_missing(md_mod, tmp_path):
    # tmp_path has no "daily" subfolder
    pairs = md_mod.read_snapshots(tmp_path, "daily")
    assert pairs == []


def test_read_snapshots_skips_unreadable_json(md_mod, tmp_path, capsys):
    daily = tmp_path / "daily"
    daily.mkdir()
    (daily / "good.json").write_text(json.dumps({"count": 1, "items": []}))
    (daily / "broken.json").write_text("not json {")
    pairs = md_mod.read_snapshots(tmp_path, "daily")
    names = [p.name for p, _ in pairs]
    assert names == ["good.json"]
    err = capsys.readouterr().err
    assert "broken.json" in err


def _make_snapshot(granularity: str, items: list[dict]) -> dict:
    return {
        "granularity": granularity,
        "run_date_utc": "2026-05-14T00:30:00Z",
        "period": {
            "start": "2026-05-14",
            "end": "2026-05-14",
            "label_iso": "2026-05-14",
            "label_compact": "2026.05.14",
        },
        "source_url": f"https://github.com/trending?since={granularity}",
        "count": len(items),
        "items": items,
    }


def _item(rank: int, owner: str, name: str, **overrides) -> dict:
    base = {
        "rank": rank,
        "owner": owner,
        "name": name,
        "full_name": f"{owner}/{name}",
        "url": f"https://github.com/{owner}/{name}",
        "description": "demo repo",
        "language": "Python",
        "stars_total": 1234,
        "forks_total": 56,
        "contributors_visible": 3,
        "period_stars": 78,
        "period_stars_label": "78 stars 2026.05.14",
    }
    base.update(overrides)
    return base


def test_build_section_includes_header_subtitle_and_table(md_mod):
    snap = _make_snapshot("daily", [_item(1, "alice", "repo-a")])
    section = md_mod.build_section(
        json_path=Path("daily/2026-05-14.json"),
        snapshot=snap,
        emoji="🔥",
        title="Daily Trending",
    )
    # Header line with date, emoji, title and window
    assert "## 2026-05-14 — 🔥 Daily Trending" in section
    assert "`2026.05.14`" in section
    # Subtitle with run timestamp and a link back to the raw JSON
    assert "`2026-05-14T00:30:00Z`" in section
    assert "[raw JSON](daily/2026-05-14.json)" in section
    # Table header and one row
    assert "| # | Repo | Lang | ⭐ total | Forks | Period ⭐ | Description |" in section
    assert "alice/repo-a" in section
    # Trailing separator
    assert section.rstrip().endswith("---")


def test_build_section_escapes_pipes_in_description(md_mod):
    snap = _make_snapshot(
        "daily",
        [_item(1, "x", "y", description="weird | repo | name")],
    )
    section = md_mod.build_section(
        json_path=Path("daily/2026-05-14.json"),
        snapshot=snap,
        emoji="🔥",
        title="Daily Trending",
    )
    # Pipes must be escaped so the markdown table isn't broken
    assert "weird \\| repo \\| name" in section
    # And there must be no raw " | " inside the description cell
    assert "weird | repo" not in section


def test_build_section_renders_null_language_and_description(md_mod):
    snap = _make_snapshot(
        "daily",
        [_item(1, "x", "y", language=None, description=None)],
    )
    section = md_mod.build_section(
        json_path=Path("daily/2026-05-14.json"),
        snapshot=snap,
        emoji="🔥",
        title="Daily Trending",
    )
    # Empty cells render cleanly (just spaces between pipes)
    assert "| — |" in section  # language placeholder
