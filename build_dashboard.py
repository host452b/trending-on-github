#!/usr/bin/env python3
"""Build dashboard.ipynb from the latest data/ snapshots.

Reads the most recent daily/weekly/monthly JSON files plus all prior
daily snapshots for history-based sections, and writes a static
notebook with pre-rendered HTML tables baked into cell outputs.
GitHub renders these directly — no kernel needed.

Re-run after every scrape:
    python build_dashboard.py
"""

from __future__ import annotations

import json
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
DATA_DIR = REPO_ROOT / "data"
OUT_NOTEBOOK = REPO_ROOT / "dashboard.ipynb"

# Match the reference notebook's visual language.
TABLE_STYLE = "border-collapse:collapse;font-size:0.92em;margin-top:8px"
TH_STYLE = (
    "padding:4px 10px;background:#f0f0f0;text-align:left;"
    "border-bottom:2px solid #ccc"
)
TD_STYLE = "padding:4px 10px;border-bottom:1px solid #eee;vertical-align:top"
SUBTITLE_STYLE = "color:#888;font-size:0.85em;margin:4px 0"


def _esc(s: str | None) -> str:
    if s is None:
        return ""
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def latest_snapshot(granularity: str) -> dict | None:
    folder = DATA_DIR / granularity
    if not folder.exists():
        return None
    files = sorted(folder.glob("*.json"))
    if not files:
        return None
    return json.loads(files[-1].read_text(encoding="utf-8"))


def all_daily_snapshots() -> list[dict]:
    folder = DATA_DIR / "daily"
    if not folder.exists():
        return []
    return [
        json.loads(p.read_text(encoding="utf-8"))
        for p in sorted(folder.glob("*.json"))
    ]


# --- HTML builders --------------------------------------------------------


def trending_table_html(snapshot: dict, emoji: str, title: str) -> str:
    items = snapshot["items"]
    label = snapshot["period"]["label_compact"]
    rows = [
        f"<h3>{emoji} {title} — {label}</h3>",
        f'<p style="{SUBTITLE_STYLE}">'
        f"Captured at <code>{snapshot['run_date_utc']}</code> · "
        f"{snapshot['count']} repos · sorted as GitHub ranked them."
        f"</p>",
        f'<table style="{TABLE_STYLE}">',
        "<tr>"
        f'<th style="{TH_STYLE}">#</th>'
        f'<th style="{TH_STYLE}">Repo</th>'
        f'<th style="{TH_STYLE}">Lang</th>'
        f'<th style="{TH_STYLE};text-align:right">⭐ total</th>'
        f'<th style="{TH_STYLE};text-align:right">forks</th>'
        f'<th style="{TH_STYLE};text-align:right">period ⭐</th>'
        f'<th style="{TH_STYLE}">Description</th>'
        "</tr>",
    ]
    for item in items:
        rows.append(
            "<tr>"
            f'<td style="{TD_STYLE};text-align:right">{item["rank"]}</td>'
            f'<td style="{TD_STYLE}"><a href="{_esc(item["url"])}">'
            f'{_esc(item["full_name"])}</a></td>'
            f'<td style="{TD_STYLE}">{_esc(item.get("language") or "—")}</td>'
            f'<td style="{TD_STYLE};text-align:right">'
            f'{item["stars_total"]:,}</td>'
            f'<td style="{TD_STYLE};text-align:right">'
            f'{item["forks_total"]:,}</td>'
            f'<td style="{TD_STYLE};text-align:right"><b>'
            f'{item["period_stars"]:,}</b></td>'
            f'<td style="{TD_STYLE}">{_esc(item.get("description") or "")}</td>'
            "</tr>"
        )
    rows.append("</table>")
    return "".join(rows)


def movers_table_html(daily_snapshots: list[dict]) -> str:
    if len(daily_snapshots) < 2:
        return (
            "<h3>📈 Day-over-day Movers</h3>"
            f'<p style="{SUBTITLE_STYLE}">'
            "Comes online once a second daily snapshot lands "
            f"(currently have {len(daily_snapshots)}).</p>"
        )
    today, yesterday = daily_snapshots[-1], daily_snapshots[-2]
    today_by = {i["full_name"]: i for i in today["items"]}
    yest_by = {i["full_name"]: i for i in yesterday["items"]}

    moved = []
    for name, item in today_by.items():
        if name in yest_by:
            delta = yest_by[name]["rank"] - item["rank"]
            moved.append((delta, item, yest_by[name]))
    new_arrivals = [today_by[n] for n in today_by if n not in yest_by]
    dropouts = [yest_by[n] for n in yest_by if n not in today_by]

    moved.sort(key=lambda t: -t[0])  # biggest gains first
    biggest_gainers = [m for m in moved if m[0] > 0][:5]
    biggest_losers = sorted([m for m in moved if m[0] < 0], key=lambda t: t[0])[:5]

    today_label = today["period"]["label_compact"]
    yest_label = yesterday["period"]["label_compact"]
    parts = [
        f"<h3>📈 Day-over-day Movers — {yest_label} → {today_label}</h3>",
        f'<p style="{SUBTITLE_STYLE}">Daily-trending rank shifts. '
        f"{len(new_arrivals)} new arrivals, {len(dropouts)} dropouts.</p>",
    ]

    def _move_table(title: str, rows: list, color: str) -> str:
        body = [
            f"<h4 style=\"margin:8px 0 4px 0\">{title}</h4>",
            f'<table style="{TABLE_STYLE}">',
            "<tr>"
            f'<th style="{TH_STYLE}">Repo</th>'
            f'<th style="{TH_STYLE};text-align:right">Yesterday</th>'
            f'<th style="{TH_STYLE};text-align:right">Today</th>'
            f'<th style="{TH_STYLE};text-align:right">Δ</th>'
            "</tr>",
        ]
        for delta, today_item, yest_item in rows:
            sign = "+" if delta > 0 else ""
            body.append(
                "<tr>"
                f'<td style="{TD_STYLE}"><a href="{_esc(today_item["url"])}">'
                f'{_esc(today_item["full_name"])}</a></td>'
                f'<td style="{TD_STYLE};text-align:right">'
                f'{yest_item["rank"]}</td>'
                f'<td style="{TD_STYLE};text-align:right">'
                f'{today_item["rank"]}</td>'
                f'<td style="{TD_STYLE};text-align:right;color:{color};'
                f'font-weight:bold">{sign}{delta}</td>'
                "</tr>"
            )
        body.append("</table>")
        return "".join(body)

    if biggest_gainers:
        parts.append(_move_table("🚀 Biggest gainers", biggest_gainers, "#1a7f37"))
    if biggest_losers:
        parts.append(_move_table("🪂 Biggest losers", biggest_losers, "#cf222e"))

    def _arrival_table(title: str, items: list[dict], emoji: str) -> str:
        body = [
            f"<h4 style=\"margin:8px 0 4px 0\">{emoji} {title}</h4>",
            f'<table style="{TABLE_STYLE}">',
            "<tr>"
            f'<th style="{TH_STYLE}">Repo</th>'
            f'<th style="{TH_STYLE}">Lang</th>'
            f'<th style="{TH_STYLE};text-align:right">period ⭐</th>'
            "</tr>",
        ]
        for it in items:
            body.append(
                "<tr>"
                f'<td style="{TD_STYLE}"><a href="{_esc(it["url"])}">'
                f'{_esc(it["full_name"])}</a></td>'
                f'<td style="{TD_STYLE}">{_esc(it.get("language") or "—")}</td>'
                f'<td style="{TD_STYLE};text-align:right">'
                f'{it["period_stars"]:,}</td>'
                "</tr>"
            )
        body.append("</table>")
        return "".join(body)

    if new_arrivals:
        parts.append(_arrival_table("New arrivals", new_arrivals, "🆕"))
    if dropouts:
        parts.append(_arrival_table("Dropouts", dropouts, "🪦"))

    return "".join(parts)


def language_breakdown_html(snapshots: dict) -> str:
    """`snapshots` is {granularity: snapshot}."""
    counters = {g: Counter() for g in ("daily", "weekly", "monthly")}
    for g, snap in snapshots.items():
        if snap is None:
            continue
        for it in snap["items"]:
            counters[g][it.get("language") or "—"] += 1

    all_langs = sorted(
        set().union(*[c.keys() for c in counters.values()]),
        key=lambda l: -sum(c[l] for c in counters.values()),
    )

    parts = [
        "<h3>🗣️ Language Breakdown</h3>",
        f'<p style="{SUBTITLE_STYLE}">Count of trending repos per language, '
        "per granularity. Sorted by overall frequency.</p>",
        f'<table style="{TABLE_STYLE}">',
        "<tr>"
        f'<th style="{TH_STYLE}">Language</th>'
        f'<th style="{TH_STYLE};text-align:right">Daily</th>'
        f'<th style="{TH_STYLE};text-align:right">Weekly</th>'
        f'<th style="{TH_STYLE};text-align:right">Monthly</th>'
        f'<th style="{TH_STYLE};text-align:right">Total</th>'
        "</tr>",
    ]
    for lang in all_langs:
        d = counters["daily"][lang]
        w = counters["weekly"][lang]
        m = counters["monthly"][lang]
        total = d + w + m
        parts.append(
            "<tr>"
            f'<td style="{TD_STYLE}">{_esc(lang)}</td>'
            f'<td style="{TD_STYLE};text-align:right">{d or ""}</td>'
            f'<td style="{TD_STYLE};text-align:right">{w or ""}</td>'
            f'<td style="{TD_STYLE};text-align:right">{m or ""}</td>'
            f'<td style="{TD_STYLE};text-align:right"><b>{total}</b></td>'
            "</tr>"
        )
    parts.append("</table>")
    return "".join(parts)


def persistent_trenders_html(daily_snapshots: list[dict]) -> str:
    if len(daily_snapshots) < 3:
        return (
            "<h3>🔁 Persistent Trenders</h3>"
            f'<p style="{SUBTITLE_STYLE}">'
            "Comes online once a third daily snapshot lands "
            f"(currently have {len(daily_snapshots)}).</p>"
        )
    appearances: Counter = Counter()
    last_seen: dict[str, dict] = {}
    for snap in daily_snapshots:
        for it in snap["items"]:
            appearances[it["full_name"]] += 1
            last_seen[it["full_name"]] = it
    multi = [
        (count, last_seen[name])
        for name, count in appearances.most_common()
        if count >= 2
    ][:20]
    if not multi:
        return (
            "<h3>🔁 Persistent Trenders</h3>"
            f'<p style="{SUBTITLE_STYLE}">No repo has appeared on daily '
            "trending more than once yet.</p>"
        )
    parts = [
        "<h3>🔁 Persistent Trenders</h3>",
        f'<p style="{SUBTITLE_STYLE}">'
        f"Repos that appeared on daily trending across the most days "
        f"(of {len(daily_snapshots)} snapshots).</p>",
        f'<table style="{TABLE_STYLE}">',
        "<tr>"
        f'<th style="{TH_STYLE}">Repo</th>'
        f'<th style="{TH_STYLE}">Lang</th>'
        f'<th style="{TH_STYLE};text-align:right">⭐ total</th>'
        f'<th style="{TH_STYLE};text-align:right">Days trending</th>'
        "</tr>",
    ]
    for count, it in multi:
        parts.append(
            "<tr>"
            f'<td style="{TD_STYLE}"><a href="{_esc(it["url"])}">'
            f'{_esc(it["full_name"])}</a></td>'
            f'<td style="{TD_STYLE}">{_esc(it.get("language") or "—")}</td>'
            f'<td style="{TD_STYLE};text-align:right">'
            f'{it["stars_total"]:,}</td>'
            f'<td style="{TD_STYLE};text-align:right"><b>{count}</b></td>'
            "</tr>"
        )
    parts.append("</table>")
    return "".join(parts)


# --- Notebook assembly ----------------------------------------------------


def _mk_markdown(text: str) -> dict:
    return {
        "cell_type": "markdown",
        "id": uuid.uuid4().hex[:8],
        "metadata": {},
        "source": [text],
    }


def _mk_code_with_html(source_comment: str, html: str) -> dict:
    return {
        "cell_type": "code",
        "id": uuid.uuid4().hex[:8],
        "execution_count": None,
        "metadata": {},
        "source": [source_comment],
        "outputs": [
            {
                "output_type": "display_data",
                "data": {"text/html": [html]},
                "metadata": {},
            }
        ],
    }


def build_notebook() -> dict:
    daily = latest_snapshot("daily")
    weekly = latest_snapshot("weekly")
    monthly = latest_snapshot("monthly")
    daily_history = all_daily_snapshots()

    latest_run = max(
        (s["run_date_utc"] for s in (daily, weekly, monthly) if s),
        default="(no data yet)",
    )
    counts = {
        g: (snap["count"] if snap else 0)
        for g, snap in (("daily", daily), ("weekly", weekly), ("monthly", monthly))
    }

    intro = (
        "<!-- Pre-rendered HTML tables baked into outputs[].data[\"text/html\"]. "
        "GitHub renders directly; no kernel needed. To update, re-run "
        "`python build_dashboard.py` after a scrape. -->\n"
        "\n"
        "# trending-on-github — Dashboard\n"
        "\n"
        f"**Latest snapshot**: `{latest_run}` · "
        f"`daily={counts['daily']}` · `weekly={counts['weekly']}` · "
        f"`monthly={counts['monthly']}`\n"
        "\n"
        "Auto-generated each day at 00:30 UTC by "
        "[`.github/workflows/scrape.yml`](.github/workflows/scrape.yml). "
        "Raw data lives under [`data/`](data/); schema documented in "
        "[`data/README.md`](data/README.md).\n"
    )

    cells = [_mk_markdown(intro)]

    if daily:
        cells.append(
            _mk_code_with_html(
                "# Daily trending\n",
                trending_table_html(daily, "🔥", "Daily Trending"),
            )
        )
    if weekly:
        cells.append(
            _mk_code_with_html(
                "# Weekly trending\n",
                trending_table_html(weekly, "📅", "Weekly Trending"),
            )
        )
    if monthly:
        cells.append(
            _mk_code_with_html(
                "# Monthly trending\n",
                trending_table_html(monthly, "🗓️", "Monthly Trending"),
            )
        )

    cells.append(
        _mk_code_with_html("# Movers\n", movers_table_html(daily_history))
    )
    cells.append(
        _mk_code_with_html(
            "# Language breakdown\n",
            language_breakdown_html(
                {"daily": daily, "weekly": weekly, "monthly": monthly}
            ),
        )
    )
    cells.append(
        _mk_code_with_html(
            "# Persistent trenders\n",
            persistent_trenders_html(daily_history),
        )
    )

    maintenance = (
        "## 📝 Long-term maintenance / 长期维护\n"
        "\n"
        "This notebook is generated by `build_dashboard.py` from the JSON "
        "snapshots under `data/`. The scrape workflow runs the build script "
        "after each daily crawl, so `dashboard.ipynb` is always one cron tick "
        "behind the live data on GitHub.\n"
        "\n"
        "To regenerate locally:\n"
        "\n"
        "```bash\n"
        ".venv/bin/python build_dashboard.py\n"
        "```\n"
        "\n"
        "No kernel state is preserved between runs — the build script "
        "produces a fully self-contained notebook with HTML tables baked "
        "into the cell outputs. GitHub renders these directly.\n"
    )
    cells.append(_mk_markdown(maintenance))

    return {
        "cells": cells,
        "metadata": {
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3",
            },
            "language_info": {"name": "python", "version": "3.12"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }


def main() -> int:
    nb = build_notebook()
    OUT_NOTEBOOK.write_text(
        json.dumps(nb, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {OUT_NOTEBOOK} ({len(nb['cells'])} cells)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
