"""Smoke tests for build_dashboard.py.

We import the module directly via importlib because it lives at the
repo root (not inside the `trending` package).
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def dashboard_mod():
    path = REPO_ROOT / "build_dashboard.py"
    spec = importlib.util.spec_from_file_location("build_dashboard", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _make_snapshot(granularity: str, items: list[dict]) -> dict:
    return {
        "granularity": granularity,
        "run_date_utc": "2026-05-13T00:30:00Z",
        "period": {
            "start": "2026-05-13",
            "end": "2026-05-13",
            "label_iso": "2026-05-13",
            "label_compact": "2026.05.13",
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
        "description": "a test repo",
        "language": "Python",
        "stars_total": 1000,
        "forks_total": 100,
        "contributors_visible": 3,
        "period_stars": 50,
        "period_stars_label": "50 stars 2026.05.13",
    }
    base.update(overrides)
    return base


def test_esc_escapes_html_specials(dashboard_mod):
    assert dashboard_mod._esc("<script>") == "&lt;script&gt;"
    assert dashboard_mod._esc('A & "B"') == "A &amp; &quot;B&quot;"
    assert dashboard_mod._esc(None) == ""


def test_trending_table_includes_every_item(dashboard_mod):
    snap = _make_snapshot(
        "daily",
        [_item(1, "alice", "repo-a"), _item(2, "bob", "repo-b")],
    )
    html = dashboard_mod.trending_table_html(snap, "🔥", "Daily")
    assert "<h3>🔥 Daily — 2026.05.13</h3>" in html
    assert "alice/repo-a" in html
    assert "bob/repo-b" in html
    assert "<table" in html and "</table>" in html


def test_gradient_bg_endpoints_and_midpoint(dashboard_mod):
    # min → red
    low = dashboard_mod._gradient_bg(0, 0, 100)
    assert "rgba(220,60,60" in low
    # max → green
    high = dashboard_mod._gradient_bg(100, 0, 100)
    assert "rgba(60,180,75" in high
    # midpoint → transparent (alpha approaches 0)
    mid = dashboard_mod._gradient_bg(50, 0, 100)
    assert "0.00" in mid or mid == ""
    # no variation → no gradient
    flat = dashboard_mod._gradient_bg(5, 5, 5)
    assert flat == ""


def test_trending_table_applies_heat_gradient(dashboard_mod):
    snap = _make_snapshot(
        "daily",
        [
            _item(1, "a", "b", stars_total=10, forks_total=1, period_stars=5),
            _item(2, "c", "d", stars_total=1000, forks_total=999, period_stars=500),
        ],
    )
    html = dashboard_mod.trending_table_html(snap, "🔥", "Daily")
    # Both endpoints of the heat gradient should appear in the rendered table.
    assert "rgba(220,60,60" in html  # the low row gets red
    assert "rgba(60,180,75" in html  # the high row gets green


def test_trending_table_escapes_dangerous_strings(dashboard_mod):
    snap = _make_snapshot(
        "daily",
        [_item(1, "x", "y", description="<script>alert(1)</script>")],
    )
    html = dashboard_mod.trending_table_html(snap, "🔥", "Daily")
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_movers_placeholder_when_insufficient_history(dashboard_mod):
    html = dashboard_mod.movers_table_html([])
    assert "Comes online" in html
    one = [_make_snapshot("daily", [_item(1, "a", "b")])]
    html = dashboard_mod.movers_table_html(one)
    assert "Comes online" in html


def test_movers_renders_with_two_days(dashboard_mod):
    yest = _make_snapshot("daily", [_item(1, "a", "b"), _item(2, "c", "d")])
    today = _make_snapshot("daily", [_item(1, "c", "d"), _item(2, "a", "b")])
    html = dashboard_mod.movers_table_html([yest, today])
    # Either gainers or losers section appears (depending on sign of delta).
    assert "Day-over-day Movers" in html
    assert "Biggest gainers" in html or "Biggest losers" in html


def test_language_breakdown_counts_by_granularity(dashboard_mod):
    d = _make_snapshot(
        "daily",
        [_item(1, "a", "b", language="Python"), _item(2, "c", "d", language="Rust")],
    )
    w = _make_snapshot(
        "weekly",
        [_item(1, "e", "f", language="Python"), _item(2, "g", "h", language="Python")],
    )
    m = _make_snapshot("monthly", [_item(1, "i", "j", language="Go")])
    html = dashboard_mod.language_breakdown_html(
        {"daily": d, "weekly": w, "monthly": m}
    )
    assert "Python" in html
    assert "Rust" in html
    assert "Go" in html
    # Python row total = 1 (daily) + 2 (weekly) + 0 (monthly) = 3
    assert "<b>3</b>" in html


def test_persistent_trenders_placeholder_for_short_history(dashboard_mod):
    html = dashboard_mod.persistent_trenders_html([])
    assert "Comes online" in html


def test_persistent_trenders_counts_multi_day_appearances(dashboard_mod):
    day1 = _make_snapshot("daily", [_item(1, "a", "b"), _item(2, "c", "d")])
    day2 = _make_snapshot("daily", [_item(1, "a", "b"), _item(2, "e", "f")])
    day3 = _make_snapshot("daily", [_item(1, "a", "b"), _item(2, "g", "h")])
    html = dashboard_mod.persistent_trenders_html([day1, day2, day3])
    assert "Persistent Trenders" in html
    assert "a/b" in html
    # a/b appeared in all 3 → "<b>3</b>" should be in the count column
    assert "<b>3</b>" in html


def test_build_notebook_with_no_data_still_produces_valid_structure(
    dashboard_mod, tmp_path, monkeypatch
):
    """If data/ is empty, the build still emits intro + maintenance + placeholders."""
    empty = tmp_path / "data"
    empty.mkdir()
    monkeypatch.setattr(dashboard_mod, "DATA_DIR", empty)
    nb = dashboard_mod.build_notebook()
    assert nb["nbformat"] == 4
    assert nb["cells"][0]["cell_type"] == "markdown"  # intro
    assert nb["cells"][-1]["cell_type"] == "markdown"  # maintenance
    # placeholder cells for movers/language/persistent still exist
    code_cells = [c for c in nb["cells"] if c["cell_type"] == "code"]
    assert len(code_cells) == 3  # only the always-on cells (movers, lang, persistent)
