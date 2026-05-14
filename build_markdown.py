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
