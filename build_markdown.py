#!/usr/bin/env python3
"""Build cumulative human-readable markdown counterparts for data/.

Reads every JSON snapshot under data/{daily,weekly,monthly}/ and writes
three aggregated markdown files at the dataset root, refreshed each
scrape:

    data/daily.md    - one section per daily snapshot, newest first
    data/weekly.md   - one section per weekly snapshot, newest first
    data/monthly.md  - one section per monthly snapshot, newest first

Pure stdlib; intentionally writeable from any Python 3.12 environment
without installing the trending package.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
DATA_DIR = REPO_ROOT / "data"


def escape_pipe(text: str | None) -> str:
    """Escape `|` so it doesn't break a markdown pipe-table cell.

    Idempotent: an already-escaped string is returned unchanged.
    """
    if text is None:
        return ""
    out: list[str] = []
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == "\\" and i + 1 < len(text) and text[i + 1] == "|":
            out.append("\\|")
            i += 2
            continue
        if ch == "|":
            out.append("\\|")
        else:
            out.append(ch)
        i += 1
    return "".join(out)


def format_int(n: int) -> str:
    """Render integers with comma thousands separators."""
    return f"{n:,}"


def build_section(
    *,
    json_path: Path,
    snapshot: dict,
    emoji: str,
    title: str,
) -> str:
    """Render a single snapshot as a markdown section.

    `json_path` is expressed relative to the markdown file's directory
    (i.e. `daily/2026-05-14.json`, NOT an absolute path) so the link
    works on GitHub.
    """
    period = snapshot["period"]
    items = snapshot["items"]

    lines: list[str] = []
    lines.append(
        f"## {period['start']} — {emoji} {title} "
        f"(window `{period['label_compact']}`)"
    )
    lines.append("")
    lines.append(
        f"Captured at `{snapshot['run_date_utc']}` · "
        f"{snapshot['count']} repos · "
        f"[raw JSON]({json_path.as_posix()})"
    )
    lines.append("")
    lines.append(
        "| # | Repo | Lang | ⭐ total | Forks | Period ⭐ | Description |"
    )
    lines.append(
        "|--:|------|------|-------:|------:|---------:|-------------|"
    )
    for item in items:
        repo_link = (
            f"[{escape_pipe(item['full_name'])}]"
            f"({item['url']})"
        )
        lang = escape_pipe(item.get("language") or "—")
        desc = escape_pipe(item.get("description") or "")
        lines.append(
            f"| {item['rank']} | {repo_link} | {lang} | "
            f"{format_int(item['stars_total'])} | "
            f"{format_int(item['forks_total'])} | "
            f"**{format_int(item['period_stars'])}** | {desc} |"
        )
    lines.append("")
    lines.append("---")
    lines.append("")
    return "\n".join(lines)


def read_snapshots(data_dir: Path, granularity: str) -> list[tuple[Path, dict]]:
    """Load all `<data_dir>/<granularity>/*.json` files in chronological order.

    A file that fails to parse is logged to stderr and skipped — one
    corrupt JSON should not block rebuilding the markdown for the
    remaining snapshots.
    """
    folder = data_dir / granularity
    if not folder.exists():
        return []
    pairs: list[tuple[Path, dict]] = []
    for path in sorted(folder.glob("*.json")):
        try:
            pairs.append((path, json.loads(path.read_text(encoding="utf-8"))))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"warn: skipping unreadable {path}: {exc}", file=sys.stderr)
    return pairs
