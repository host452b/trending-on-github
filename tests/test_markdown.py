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


def test_build_file_orders_sections_newest_first(md_mod, tmp_path):
    snap_old = _make_snapshot("daily", [_item(1, "a", "b")])
    snap_old["period"]["start"] = "2026-05-12"
    snap_old["run_date_utc"] = "2026-05-12T00:30:00Z"
    snap_new = _make_snapshot("daily", [_item(1, "c", "d")])
    snap_new["period"]["start"] = "2026-05-14"
    snap_new["run_date_utc"] = "2026-05-14T00:30:00Z"

    body = md_mod.build_file(
        granularity="daily",
        title="Daily Trending",
        emoji="🔥",
        pairs=[
            (Path("daily/2026-05-12.json"), snap_old),
            (Path("daily/2026-05-14.json"), snap_new),
        ],
    )
    new_idx = body.find("2026-05-14 — 🔥")
    old_idx = body.find("2026-05-12 — 🔥")
    assert new_idx != -1 and old_idx != -1
    assert new_idx < old_idx  # newer appears earlier in the file


def test_build_file_header_summary_counts_snapshots(md_mod):
    snap_a = _make_snapshot("daily", [_item(1, "a", "b")])
    snap_a["period"]["start"] = "2026-05-12"
    snap_b = _make_snapshot("daily", [_item(1, "c", "d")])
    snap_b["period"]["start"] = "2026-05-14"

    body = md_mod.build_file(
        granularity="daily",
        title="Daily Trending",
        emoji="🔥",
        pairs=[
            (Path("daily/2026-05-12.json"), snap_a),
            (Path("daily/2026-05-14.json"), snap_b),
        ],
    )
    assert body.startswith("# Daily Trending — accumulated snapshots")
    assert "**2 snapshots**" in body
    assert "`2026-05-12` → `2026-05-14`" in body


def test_build_file_handles_empty_input(md_mod):
    body = md_mod.build_file(
        granularity="daily",
        title="Daily Trending",
        emoji="🔥",
        pairs=[],
    )
    assert body.startswith("# Daily Trending — accumulated snapshots")
    assert "**0 snapshots**" in body
    # No section headers when there's no data
    assert "## " not in body


def test_write_file_creates_target(md_mod, tmp_path):
    target = tmp_path / "daily.md"
    md_mod.write_file(target, "# hello\n")
    assert target.read_text(encoding="utf-8") == "# hello\n"


def test_write_file_is_atomic_on_failure(md_mod, tmp_path, monkeypatch):
    target = tmp_path / "daily.md"
    target.write_text("# original\n", encoding="utf-8")

    def boom(*args, **kwargs):
        raise RuntimeError("rename failed")

    # Patch the module-local reference so the real os.replace stays
    # available to the rest of the test infrastructure.
    monkeypatch.setattr("build_markdown.os.replace", boom)
    with pytest.raises(RuntimeError, match="rename failed"):
        md_mod.write_file(target, "# new content\n")
    # Original is intact and no temp file leaked beside it
    assert target.read_text(encoding="utf-8") == "# original\n"
    leftovers = [p for p in target.parent.iterdir() if p != target]
    assert leftovers == []


def test_main_writes_three_files(md_mod, tmp_path, monkeypatch):
    # Lay out a miniature dataset
    for granularity in ("daily", "weekly", "monthly"):
        folder = tmp_path / granularity
        folder.mkdir()
        snap = _make_snapshot(granularity, [_item(1, "a", "b")])
        (folder / f"sample-{granularity}.json").write_text(
            json.dumps(snap), encoding="utf-8"
        )

    monkeypatch.setattr(md_mod, "DATA_DIR", tmp_path)
    code = md_mod.main()
    assert code == 0
    for granularity, name in (
        ("daily", "daily.md"),
        ("weekly", "weekly.md"),
        ("monthly", "monthly.md"),
    ):
        target = tmp_path / name
        assert target.exists()
        body = target.read_text(encoding="utf-8")
        assert "accumulated snapshots" in body
        assert "a/b" in body
        # raw JSON link is relative to data/ — not absolute, not pointing
        # outside the markdown file's directory
        assert f"({granularity}/sample-{granularity}.json)" in body
        assert "/Users/" not in body
        assert str(tmp_path) not in body
