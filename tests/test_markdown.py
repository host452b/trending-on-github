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
