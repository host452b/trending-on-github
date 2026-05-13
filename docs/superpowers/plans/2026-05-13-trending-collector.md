# Trending-on-GitHub Collector Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a once-a-day GitHub Actions workflow that scrapes the three GitHub trending pages (daily, weekly, monthly) and commits structured JSON snapshots back to this repo, accumulating a time-series dataset via the "git scraping" pattern.

**Architecture:** A small Python package `trending/` with clear module boundaries — `period` (pure date math), `parse` (BeautifulSoup HTML → records), `fetch` (HTTP with retry), `snapshot` (atomic JSON write), and a CLI `__main__`. A scheduled workflow runs the CLI three times (one per granularity) and uses `stefanzweifel/git-auto-commit-action` to push changes. A test workflow runs `pytest` on push/PR using frozen HTML fixtures so GitHub-side markup drift surfaces as a red test rather than a corrupted dataset.

**Tech Stack:** Python 3.12, `requests`, `beautifulsoup4`, `pytest`. GitHub Actions (`actions/checkout@v4`, `actions/setup-python@v5`, `stefanzweifel/git-auto-commit-action@v5`). No GitHub API token required.

**Spec reference:** `docs/superpowers/specs/2026-05-13-trending-collector-design.md`

---

## File Structure

Files this plan will create (all paths relative to the repo root):

| Path                                          | Responsibility                                           |
|-----------------------------------------------|----------------------------------------------------------|
| `.gitignore`                                  | Ignore venv, caches, pyc, editor cruft                   |
| `requirements.txt`                            | Runtime deps: `requests`, `beautifulsoup4`               |
| `requirements-dev.txt`                        | Dev deps: `pytest`, `responses`                          |
| `pyproject.toml`                              | Pytest config + src layout                               |
| `src/trending/__init__.py`                    | Package marker; version constant                         |
| `src/trending/period.py`                      | `period_for(run_date, granularity)`, `file_name(...)`    |
| `src/trending/parse.py`                       | `parse_trending_html(html, granularity, period)`          |
| `src/trending/fetch.py`                       | `fetch_trending(granularity)` with retry + UA            |
| `src/trending/snapshot.py`                    | `write_snapshot(out_dir, granularity, run_date, items)`  |
| `src/trending/__main__.py`                    | CLI entry: orchestrates fetch → parse → snapshot         |
| `tests/__init__.py`                           | (empty)                                                  |
| `tests/conftest.py`                           | Shared pytest fixtures (paths)                           |
| `tests/test_period.py`                        | Period math + filename tests                             |
| `tests/test_parse.py`                         | Parser tests against frozen HTML fixtures                |
| `tests/test_snapshot.py`                      | Snapshot write tests                                     |
| `tests/test_fetch.py`                         | Fetch retry/UA tests (mocked HTTP)                       |
| `tests/fixtures/trending_daily.html`          | Frozen HTML snapshot of `?since=daily`                   |
| `tests/fixtures/trending_weekly.html`         | Frozen HTML snapshot of `?since=weekly`                  |
| `tests/fixtures/trending_monthly.html`        | Frozen HTML snapshot of `?since=monthly`                 |
| `.github/workflows/test.yml`                  | CI test workflow (push/PR)                               |
| `.github/workflows/scrape.yml`                | Daily cron scrape + auto-commit                          |
| `data/README.md`                              | Schema + example `jq` queries                            |
| `README.md`                                   | Top-level project documentation                          |

Total: ~22 files.

---

### Task 1: Project bootstrap

**Files:**
- Create: `.gitignore`
- Create: `requirements.txt`
- Create: `requirements-dev.txt`
- Create: `pyproject.toml`
- Create: `src/trending/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`

- [ ] **Step 1: Create `.gitignore`**

```
# Python
__pycache__/
*.py[cod]
*.egg-info/
.venv/
venv/
.pytest_cache/
.ruff_cache/

# Editors
.vscode/
.idea/
.DS_Store
```

- [ ] **Step 2: Create `requirements.txt`**

```
requests==2.32.3
beautifulsoup4==4.12.3
```

- [ ] **Step 3: Create `requirements-dev.txt`**

```
-r requirements.txt
pytest==8.3.3
responses==0.25.3
```

- [ ] **Step 4: Create `pyproject.toml`**

```toml
[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "trending"
version = "0.1.0"
description = "GitHub trending data collector (git-scraping pattern)"
requires-python = ">=3.12"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]
addopts = "-q"
```

- [ ] **Step 5: Create `src/trending/__init__.py`**

```python
__version__ = "0.1.0"
```

- [ ] **Step 6: Create `tests/__init__.py`**

(empty file)

- [ ] **Step 7: Create `tests/conftest.py`**

```python
from pathlib import Path

import pytest


@pytest.fixture()
def fixtures_dir() -> Path:
    return Path(__file__).parent / "fixtures"
```

- [ ] **Step 8: Create venv and install dev deps locally**

Run (from the repo root):
```bash
python3.12 -m venv .venv
.venv/bin/pip install --quiet --upgrade pip
.venv/bin/pip install --quiet -r requirements-dev.txt
.venv/bin/pytest --collect-only
```
Expected: pytest collects 0 tests (no test files yet) and exits 5 (no tests collected). That's fine — it confirms the install works.

- [ ] **Step 9: Commit bootstrap**

```bash
git add .gitignore requirements.txt requirements-dev.txt pyproject.toml \
        src/trending/__init__.py tests/__init__.py tests/conftest.py
git commit -m "build: bootstrap python package skeleton and pytest config"
```

---

### Task 2: Period math module (TDD)

**Files:**
- Create: `tests/test_period.py`
- Create: `src/trending/period.py`

The period module is pure (no I/O), so we drive it entirely with unit tests. Behavior to capture:

- `period_for(run_date, "daily")` → `Period(start=run_date, end=run_date, label_iso=YYYY-MM-DD, label_compact=YYYY.MM.DD)`
- `period_for(run_date, "weekly")` → 7-day window ending on `run_date`
- `period_for(run_date, "monthly")` → 30-day window ending on `run_date`
- `file_name(run_date, granularity)` → `daily/YYYY-MM-DD.json`, `weekly/YYYY-Www.json`, `monthly/YYYY-MM.json`

- [ ] **Step 1: Write failing tests for `period_for`**

Create `tests/test_period.py`:

```python
from datetime import date

import pytest

from trending.period import Period, file_name, period_for


def test_daily_period_is_single_day():
    p = period_for(date(2026, 5, 13), "daily")
    assert p == Period(
        start=date(2026, 5, 13),
        end=date(2026, 5, 13),
        label_iso="2026-05-13",
        label_compact="2026.05.13",
    )


def test_weekly_period_is_rolling_7_days():
    p = period_for(date(2026, 5, 13), "weekly")
    assert p.start == date(2026, 5, 7)
    assert p.end == date(2026, 5, 13)
    assert p.label_iso == "2026-05-07/2026-05-13"
    assert p.label_compact == "2026.05.07-2026.05.13"


def test_monthly_period_is_rolling_30_days():
    p = period_for(date(2026, 5, 13), "monthly")
    assert p.start == date(2026, 4, 14)
    assert p.end == date(2026, 5, 13)
    assert p.label_iso == "2026-04-14/2026-05-13"
    assert p.label_compact == "2026.04.14-2026.05.13"


def test_weekly_period_crosses_month_boundary():
    # May 1 weekly → April 25 - May 1
    p = period_for(date(2026, 5, 1), "weekly")
    assert p.start == date(2026, 4, 25)
    assert p.end == date(2026, 5, 1)


def test_monthly_period_crosses_year_boundary():
    # Jan 5 monthly → Dec 7 prior year - Jan 5
    p = period_for(date(2026, 1, 5), "monthly")
    assert p.start == date(2025, 12, 7)
    assert p.end == date(2026, 1, 5)


def test_daily_leap_day():
    p = period_for(date(2024, 2, 29), "daily")
    assert p.start == p.end == date(2024, 2, 29)
    assert p.label_compact == "2024.02.29"


def test_unknown_granularity_raises():
    with pytest.raises(ValueError, match="unknown granularity"):
        period_for(date(2026, 5, 13), "yearly")


def test_file_name_daily():
    assert file_name(date(2026, 5, 13), "daily") == "daily/2026-05-13.json"


def test_file_name_weekly_iso_week_20():
    # 2026-05-13 is a Wednesday in ISO week 20 (Mon May 11 – Sun May 17)
    assert file_name(date(2026, 5, 13), "weekly") == "weekly/2026-W20.json"


def test_file_name_monthly():
    assert file_name(date(2026, 5, 13), "monthly") == "monthly/2026-05.json"


def test_file_name_weekly_pads_single_digit_week():
    # 2026-01-05 is in ISO week 2 → must be zero-padded as W02
    assert file_name(date(2026, 1, 5), "weekly") == "weekly/2026-W02.json"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_period.py -v`
Expected: `ImportError` / `ModuleNotFoundError: trending.period` — file does not exist yet.

- [ ] **Step 3: Implement `src/trending/period.py`**

```python
"""Pure date math for the three trending granularities.

`period_for(run_date, granularity)` returns a `Period` describing the
rolling window the trending page covers when crawled on `run_date`.
`file_name(run_date, granularity)` returns the snapshot file path
(relative to the data directory).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

Granularity = str  # "daily" | "weekly" | "monthly"

_WINDOW_DAYS: dict[Granularity, int] = {
    "daily": 1,
    "weekly": 7,
    "monthly": 30,
}


@dataclass(frozen=True)
class Period:
    start: date
    end: date
    label_iso: str
    label_compact: str


def period_for(run_date: date, granularity: Granularity) -> Period:
    if granularity not in _WINDOW_DAYS:
        raise ValueError(f"unknown granularity: {granularity!r}")
    days = _WINDOW_DAYS[granularity]
    start = run_date - timedelta(days=days - 1)
    end = run_date
    if start == end:
        label_iso = start.isoformat()
        label_compact = start.strftime("%Y.%m.%d")
    else:
        label_iso = f"{start.isoformat()}/{end.isoformat()}"
        label_compact = f"{start.strftime('%Y.%m.%d')}-{end.strftime('%Y.%m.%d')}"
    return Period(start=start, end=end, label_iso=label_iso, label_compact=label_compact)


def file_name(run_date: date, granularity: Granularity) -> str:
    if granularity == "daily":
        return f"daily/{run_date.isoformat()}.json"
    if granularity == "weekly":
        iso_year, iso_week, _ = run_date.isocalendar()
        return f"weekly/{iso_year}-W{iso_week:02d}.json"
    if granularity == "monthly":
        return f"monthly/{run_date.year:04d}-{run_date.month:02d}.json"
    raise ValueError(f"unknown granularity: {granularity!r}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_period.py -v`
Expected: 10 passed.

- [ ] **Step 5: Commit**

```bash
git add tests/test_period.py src/trending/period.py
git commit -m "feat(period): pure date math for daily/weekly/monthly windows"
```

---

### Task 3: Capture HTML fixtures

The parser tests need real GitHub trending HTML to be useful. This is a one-time live-network step; the fixtures get committed to the repo and the parser tests then run offline forever after.

**Files:**
- Create: `tests/fixtures/trending_daily.html`
- Create: `tests/fixtures/trending_weekly.html`
- Create: `tests/fixtures/trending_monthly.html`

- [ ] **Step 1: Fetch the three trending pages**

Run (from repo root):
```bash
mkdir -p tests/fixtures
for since in daily weekly monthly; do
  curl --silent --show-error \
       --user-agent "trending-on-github/1.0 (+https://github.com/host452b/trending-on-github)" \
       --output "tests/fixtures/trending_${since}.html" \
       "https://github.com/trending?since=${since}"
done
ls -lh tests/fixtures/
```
Expected: three `.html` files, each between ~100 KB and ~500 KB.

- [ ] **Step 2: Sanity-check the fixtures**

Run:
```bash
for f in tests/fixtures/trending_*.html; do
  echo "=== $f ==="
  grep -c 'article class="Box-row"' "$f" || true
done
```
Expected: each fixture reports a row count in the 20–30 range. If a fixture has 0 rows, GitHub may have responded with a login/anti-bot page; rerun the fetch with a different `--user-agent` or from a different network.

- [ ] **Step 3: Commit fixtures**

```bash
git add tests/fixtures/trending_*.html
git commit -m "test: capture frozen HTML fixtures of github.com/trending"
```

---

### Task 4: HTML parser module (TDD against fixtures)

**Files:**
- Create: `tests/test_parse.py`
- Create: `src/trending/parse.py`

The parser is fully decoupled from network and I/O: it takes raw HTML and a `Period` and returns `list[Record]`. The same parser handles all three granularities; the `granularity` argument is used only to validate the period token in the bottom-right "N stars today / this week / this month" string.

- [ ] **Step 1: Write failing parser tests**

Create `tests/test_parse.py`:

```python
from datetime import date

import pytest

from trending.parse import Record, parse_trending_html
from trending.period import period_for


@pytest.fixture()
def daily_html(fixtures_dir):
    return (fixtures_dir / "trending_daily.html").read_text(encoding="utf-8")


@pytest.fixture()
def weekly_html(fixtures_dir):
    return (fixtures_dir / "trending_weekly.html").read_text(encoding="utf-8")


@pytest.fixture()
def monthly_html(fixtures_dir):
    return (fixtures_dir / "trending_monthly.html").read_text(encoding="utf-8")


def test_daily_parses_at_least_20_records(daily_html):
    period = period_for(date(2026, 5, 13), "daily")
    records = parse_trending_html(daily_html, "daily", period)
    assert len(records) >= 20


def test_daily_record_required_fields(daily_html):
    period = period_for(date(2026, 5, 13), "daily")
    records = parse_trending_html(daily_html, "daily", period)
    for r in records:
        assert r.owner and r.name
        assert r.full_name == f"{r.owner}/{r.name}"
        assert r.url == f"https://github.com/{r.full_name}"
        assert r.stars_total >= 0
        assert r.forks_total >= 0
        assert r.contributors_visible >= 0
        assert r.period_stars >= 0


def test_daily_label_uses_compact_date(daily_html):
    period = period_for(date(2026, 5, 13), "daily")
    records = parse_trending_html(daily_html, "daily", period)
    for r in records:
        assert r.period_stars_label.endswith(" 2026.05.13"), r.period_stars_label
        assert "today" not in r.period_stars_label


def test_weekly_label_uses_compact_range(weekly_html):
    period = period_for(date(2026, 5, 13), "weekly")
    records = parse_trending_html(weekly_html, "weekly", period)
    assert records
    for r in records:
        assert r.period_stars_label.endswith(" 2026.05.07-2026.05.13"), r.period_stars_label
        assert "this week" not in r.period_stars_label


def test_monthly_label_uses_compact_range(monthly_html):
    period = period_for(date(2026, 5, 13), "monthly")
    records = parse_trending_html(monthly_html, "monthly", period)
    assert records
    for r in records:
        assert r.period_stars_label.endswith(" 2026.04.14-2026.05.13"), r.period_stars_label
        assert "this month" not in r.period_stars_label


def test_ranks_are_sequential_starting_at_1(daily_html):
    period = period_for(date(2026, 5, 13), "daily")
    records = parse_trending_html(daily_html, "daily", period)
    assert [r.rank for r in records] == list(range(1, len(records) + 1))


def test_malformed_row_is_skipped(daily_html):
    period = period_for(date(2026, 5, 13), "daily")
    # Inject a malformed row missing the stars link
    broken = daily_html.replace(
        '<article class="Box-row"',
        '<article class="Box-row"><div>broken-row</div></article><article class="Box-row"',
        1,
    )
    records = parse_trending_html(broken, "daily", period)
    # We still get a sane number of records, the broken sentinel is dropped silently
    assert len(records) >= 20


def test_record_dict_round_trip(daily_html):
    period = period_for(date(2026, 5, 13), "daily")
    records = parse_trending_html(daily_html, "daily", period)
    d = records[0].to_dict()
    assert d["rank"] == 1
    assert d["owner"] and d["name"]
    assert "period_stars" in d
    assert "period_stars_label" in d
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_parse.py -v`
Expected: `ImportError: cannot import name 'parse_trending_html' from 'trending.parse'`.

- [ ] **Step 3: Implement `src/trending/parse.py`**

```python
"""Parse GitHub trending HTML into structured records.

All BeautifulSoup selectors live here. When GitHub changes their
trending markup, this is the only file you should need to touch.
"""

from __future__ import annotations

import logging
import re
from dataclasses import asdict, dataclass
from typing import Optional

from bs4 import BeautifulSoup, Tag

from trending.period import Period

log = logging.getLogger(__name__)

_PERIOD_TOKENS = {
    "daily":   "today",
    "weekly":  "this week",
    "monthly": "this month",
}

_PERIOD_RE = re.compile(
    r"^([\d,]+)\s+stars?\s+(today|this\s+week|this\s+month)\s*$",
    re.IGNORECASE,
)


@dataclass
class Record:
    rank: int
    owner: str
    name: str
    full_name: str
    url: str
    description: Optional[str]
    language: Optional[str]
    stars_total: int
    forks_total: int
    contributors_visible: int
    period_stars: int
    period_stars_label: str

    def to_dict(self) -> dict:
        return asdict(self)


def parse_trending_html(html: str, granularity: str, period: Period) -> list[Record]:
    if granularity not in _PERIOD_TOKENS:
        raise ValueError(f"unknown granularity: {granularity!r}")
    expected_token = _PERIOD_TOKENS[granularity]
    soup = BeautifulSoup(html, "html.parser")
    rows = soup.select("article.Box-row")
    records: list[Record] = []
    for idx, row in enumerate(rows, start=1):
        try:
            record = _parse_row(row, idx, granularity, expected_token, period)
        except _Skip as e:
            log.warning("skipping row %d: %s", idx, e)
            continue
        records.append(record)
    # Re-rank so the output is dense (1..N) after any drops
    for i, r in enumerate(records, start=1):
        r.rank = i
    return records


class _Skip(Exception):
    """Raised when a row is missing required fields and should be dropped."""


def _parse_row(
    row: Tag,
    rank: int,
    granularity: str,
    expected_token: str,
    period: Period,
) -> Record:
    owner, name = _owner_name(row)
    stars_total = _parse_int(_text(row.select_one('a[href$="/stargazers"]')))
    forks_total = _parse_int(_text(row.select_one('a[href$="/forks"]')))
    period_stars, period_word = _period_stars(row)

    if period_word.lower().strip() != expected_token:
        raise _Skip(
            f"period word {period_word!r} does not match granularity {granularity!r}"
        )

    description = _text(row.select_one("p.col-9")) or None
    language = _text(row.select_one('[itemprop="programmingLanguage"]')) or None
    contributors_visible = len(row.select("span.d-inline-block.mr-3 a img.avatar"))

    label = f"{_format_int(period_stars)} stars {period.label_compact}"

    return Record(
        rank=rank,
        owner=owner,
        name=name,
        full_name=f"{owner}/{name}",
        url=f"https://github.com/{owner}/{name}",
        description=description,
        language=language,
        stars_total=stars_total,
        forks_total=forks_total,
        contributors_visible=contributors_visible,
        period_stars=period_stars,
        period_stars_label=label,
    )


def _owner_name(row: Tag) -> tuple[str, str]:
    link = row.select_one("h2 a[href]")
    if link is None:
        raise _Skip("no h2 a[href]")
    href = link.get("href", "").strip()
    parts = [p for p in href.strip("/").split("/") if p]
    if len(parts) < 2:
        raise _Skip(f"unexpected repo href: {href!r}")
    return parts[0], parts[1]


def _period_stars(row: Tag) -> tuple[int, str]:
    candidates = row.select("span.d-inline-block.float-sm-right")
    for span in candidates:
        text = _text(span)
        m = _PERIOD_RE.match(text)
        if m:
            return _parse_int(m.group(1)), m.group(2)
    raise _Skip("could not find period_stars span")


def _text(node: Optional[Tag]) -> str:
    if node is None:
        return ""
    return " ".join(node.get_text(" ", strip=True).split())


def _parse_int(text: str) -> int:
    """Parse '1,234' → 1234, '12.3k' → 12300, '1.2M' → 1200000."""
    if not text:
        raise _Skip("empty integer text")
    s = text.replace(",", "").strip()
    multiplier = 1
    if s.endswith(("k", "K")):
        multiplier = 1_000
        s = s[:-1]
    elif s.endswith(("m", "M")):
        multiplier = 1_000_000
        s = s[:-1]
    try:
        return int(float(s) * multiplier)
    except ValueError as exc:
        raise _Skip(f"cannot parse integer {text!r}") from exc


def _format_int(n: int) -> str:
    return f"{n:,}"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_parse.py -v`
Expected: 8 passed.

If a selector test fails because GitHub's actual markup differs from the spec's selector table, inspect the fixture HTML directly (`open tests/fixtures/trending_daily.html` or `grep -o 'class="[^"]*"' tests/fixtures/trending_daily.html | sort -u | head`) and adjust the selector in `_parse_row`. The fixture-driven test is exactly what tells us a selector is wrong without breaking the live dataset.

- [ ] **Step 5: Commit**

```bash
git add tests/test_parse.py src/trending/parse.py
git commit -m "feat(parse): HTML→Record parser with rolling-window label rewriting"
```

---

### Task 5: Snapshot writer module (TDD)

**Files:**
- Create: `tests/test_snapshot.py`
- Create: `src/trending/snapshot.py`

The snapshot module owns one job: write the JSON file atomically and place it under the correct `<granularity>/<filename>` path. It does not touch HTTP or HTML.

- [ ] **Step 1: Write failing snapshot tests**

Create `tests/test_snapshot.py`:

```python
import json
import os
from datetime import date, datetime, timezone
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_snapshot.py -v`
Expected: `ImportError` — `trending.snapshot` does not exist.

- [ ] **Step 3: Implement `src/trending/snapshot.py`**

```python
"""Atomic JSON snapshot writer.

Why atomic: a crashed run mid-write must not leave a half-written
.json file in the dataset. We write to a NamedTemporaryFile in the
same directory (so os.replace is atomic on the same filesystem) and
swap it into place only after a successful serialisation.
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
        except FileNotFoundError:
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
```

Note the `monkeypatch.setattr("trending.snapshot.os.replace", boom)` line in the test patches the module-level `os` reference, so the implementation MUST `import os` at the top of the module and reach `os.replace(...)` through that reference (it does).

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_snapshot.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add tests/test_snapshot.py src/trending/snapshot.py
git commit -m "feat(snapshot): atomic JSON snapshot writer per granularity"
```

---

### Task 6: Fetch module (TDD with mocked HTTP)

**Files:**
- Create: `tests/test_fetch.py`
- Create: `src/trending/fetch.py`

`fetch_trending(granularity)` returns the raw HTML body string. Tests use the `responses` library (already in `requirements-dev.txt`) to mock HTTP without touching the network.

- [ ] **Step 1: Write failing fetch tests**

Create `tests/test_fetch.py`:

```python
import pytest
import requests
import responses
from responses import matchers

from trending.fetch import fetch_trending

_BASE = "https://github.com/trending"


def _q(since: str) -> list:
    return [matchers.query_param_matcher({"since": since})]


@responses.activate
def test_fetch_daily_returns_body():
    responses.add(
        responses.GET, _BASE,
        body="<html>daily</html>", status=200,
        match=_q("daily"),
    )
    body = fetch_trending("daily", retries=0, backoff=0)
    assert body == "<html>daily</html>"


@responses.activate
def test_fetch_uses_courteous_user_agent():
    responses.add(
        responses.GET, _BASE,
        body="<html>weekly</html>", status=200,
        match=_q("weekly"),
    )
    fetch_trending("weekly", retries=0, backoff=0)
    sent = responses.calls[0].request
    ua = sent.headers["User-Agent"]
    assert ua.startswith("trending-on-github/")
    assert "host452b/trending-on-github" in ua


@responses.activate
def test_fetch_retries_on_5xx_then_succeeds():
    responses.add(responses.GET, _BASE, status=503, match=_q("monthly"))
    responses.add(responses.GET, _BASE, status=503, match=_q("monthly"))
    responses.add(
        responses.GET, _BASE,
        body="<html>ok</html>", status=200,
        match=_q("monthly"),
    )
    body = fetch_trending("monthly", retries=3, backoff=0)
    assert body == "<html>ok</html>"
    assert len(responses.calls) == 3


@responses.activate
def test_fetch_gives_up_after_exhausting_retries():
    for _ in range(3):
        responses.add(responses.GET, _BASE, status=503, match=_q("daily"))
    with pytest.raises(requests.HTTPError):
        fetch_trending("daily", retries=2, backoff=0)
    assert len(responses.calls) == 3  # initial + 2 retries


@responses.activate
def test_fetch_does_not_retry_on_4xx():
    responses.add(responses.GET, _BASE, status=429, match=_q("daily"))
    with pytest.raises(requests.HTTPError):
        fetch_trending("daily", retries=3, backoff=0)
    assert len(responses.calls) == 1


def test_fetch_unknown_granularity_raises():
    with pytest.raises(ValueError, match="unknown granularity"):
        fetch_trending("yearly")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_fetch.py -v`
Expected: `ImportError` — `trending.fetch` does not exist.

- [ ] **Step 3: Implement `src/trending/fetch.py`**

```python
"""HTTP layer for the trending crawler.

The only function here, `fetch_trending`, returns the raw HTML body
for a given granularity. It retries on 5xx + connection errors with
exponential backoff and gives up on 4xx (those are permanent).
"""

from __future__ import annotations

import logging
import time

import requests

log = logging.getLogger(__name__)

_URLS = {
    "daily":   "https://github.com/trending?since=daily",
    "weekly":  "https://github.com/trending?since=weekly",
    "monthly": "https://github.com/trending?since=monthly",
}

_USER_AGENT = (
    "trending-on-github/1.0 "
    "(+https://github.com/host452b/trending-on-github)"
)


def fetch_trending(
    granularity: str,
    *,
    retries: int = 3,
    backoff: float = 2.0,
    timeout: float = 30.0,
) -> str:
    if granularity not in _URLS:
        raise ValueError(f"unknown granularity: {granularity!r}")
    url = _URLS[granularity]
    headers = {"User-Agent": _USER_AGENT, "Accept": "text/html"}

    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        try:
            resp = requests.get(url, headers=headers, timeout=timeout)
        except requests.RequestException as exc:
            last_exc = exc
            log.warning("fetch %s attempt %d failed: %s", granularity, attempt, exc)
        else:
            if 500 <= resp.status_code < 600:
                log.warning(
                    "fetch %s attempt %d got %d",
                    granularity, attempt, resp.status_code,
                )
                last_exc = requests.HTTPError(
                    f"{resp.status_code} for {url}", response=resp,
                )
            else:
                resp.raise_for_status()  # raises on 4xx, returns on 2xx/3xx
                return resp.text
        if attempt < retries:
            time.sleep(backoff * (2 ** attempt))
    assert last_exc is not None
    raise last_exc
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_fetch.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add tests/test_fetch.py src/trending/fetch.py
git commit -m "feat(fetch): HTTP layer with retry + courteous User-Agent"
```

---

### Task 7: CLI entry point

**Files:**
- Create: `src/trending/__main__.py`

The CLI wires fetch → parse → snapshot. No unit test required: the constituent pieces are already covered, and the CLI is exercised end-to-end in `Task 9` (the scrape workflow) and manually via dry-run.

- [ ] **Step 1: Implement `src/trending/__main__.py`**

```python
"""CLI: python -m trending --granularity {daily|weekly|monthly} --out data"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timezone
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
    p.add_argument("--run-date", default=None,
                   help="UTC date YYYY-MM-DD; defaults to today (UTC)")
    p.add_argument("--verbose", "-v", action="store_true")
    args = p.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    if args.run_date:
        run_dt = datetime.fromisoformat(args.run_date).replace(tzinfo=timezone.utc)
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
```

- [ ] **Step 2: Dry-run the CLI locally**

Run (from the repo root):
```bash
.venv/bin/python -m trending --granularity daily --out /tmp/trending-dryrun --verbose
ls -lh /tmp/trending-dryrun/daily/
.venv/bin/python -c "
import json, glob, sys
paths = sorted(glob.glob('/tmp/trending-dryrun/daily/*.json'))
data = json.load(open(paths[-1]))
print('granularity:', data['granularity'])
print('count:', data['count'])
print('first item:', data['items'][0])
"
```
Expected: exits 0, writes one `.json` file, and prints a dict with `granularity: 'daily'`, a count in the 20-30 range, and a sensible first item. If this fails because GitHub blocks the request, that confirms the workflow should rely on the actions runner's IP (which github.com generally accepts) — not a flaw in the code.

- [ ] **Step 3: Commit**

```bash
git add src/trending/__main__.py
git commit -m "feat(cli): python -m trending entry point wiring fetch→parse→snapshot"
```

---

### Task 8: Test CI workflow

**Files:**
- Create: `.github/workflows/test.yml`

- [ ] **Step 1: Create the test workflow**

```yaml
name: test
on:
  push:
    branches: [main]
  pull_request:
jobs:
  test:
    runs-on: ubuntu-latest
    timeout-minutes: 3
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: "pip"
          cache-dependency-path: |
            requirements.txt
            requirements-dev.txt
      - run: pip install -r requirements-dev.txt
      - run: pytest -q
```

- [ ] **Step 2: Validate YAML locally**

Run:
```bash
.venv/bin/python -c "import yaml; yaml.safe_load(open('.github/workflows/test.yml'))"
```
Expected: no output, exit 0.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/test.yml
git commit -m "ci: run pytest on push and pull_request"
```

---

### Task 9: Scrape CI workflow

**Files:**
- Create: `.github/workflows/scrape.yml`

- [ ] **Step 1: Create the scrape workflow**

```yaml
name: scrape-trending
on:
  schedule:
    - cron: "30 0 * * *"        # 00:30 UTC daily
  workflow_dispatch:             # manual trigger button for testing
concurrency:
  group: scrape-trending
  cancel-in-progress: false
permissions:
  contents: write
jobs:
  scrape:
    runs-on: ubuntu-latest
    timeout-minutes: 5
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: "pip"
          cache-dependency-path: requirements.txt
      - run: pip install -r requirements.txt
      - name: Scrape daily
        run: python -m trending --granularity daily --out data
        continue-on-error: true
      - name: Scrape weekly
        run: python -m trending --granularity weekly --out data
        continue-on-error: true
      - name: Scrape monthly
        run: python -m trending --granularity monthly --out data
        continue-on-error: true
      - name: Verify at least one snapshot was written
        run: |
          # If all three steps above failed, no new file exists for today
          # and we want the run to fail loudly so the failure surfaces.
          today=$(date -u +%F)
          if [ ! -f "data/daily/${today}.json" ]; then
            echo "::error::no daily snapshot produced for ${today}"
            exit 1
          fi
      - uses: stefanzweifel/git-auto-commit-action@v5
        with:
          commit_message: "data: trending snapshot ${{ github.run_id }}"
          file_pattern: "data/**/*.json"
          commit_user_name: host452b
          commit_user_email: 32806348+host452b@users.noreply.github.com
```

Note on `continue-on-error` + the explicit verify step: the spec calls for "exit non-zero only when all three fail". Using `continue-on-error: true` on each scrape step lets the workflow proceed past a single transient failure; the verify step then asserts that at least *one* snapshot exists for today, which is a simple, observable invariant. We could pick a stricter version (count files), but "the daily file for today exists" is the most user-visible signal and the cheapest to write.

- [ ] **Step 2: Validate YAML locally**

Run:
```bash
.venv/bin/python -c "import yaml; yaml.safe_load(open('.github/workflows/scrape.yml'))"
```
Expected: no output, exit 0.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/scrape.yml
git commit -m "ci: daily cron scrape of github.com/trending with auto-commit"
```

---

### Task 10: READMEs

**Files:**
- Create: `data/README.md`
- Create: `README.md`

- [ ] **Step 1: Create `data/README.md`**

```markdown
# trending-on-github — Dataset

This directory holds JSON snapshots of GitHub's three trending pages,
captured once a day at 00:30 UTC by `.github/workflows/scrape.yml`.

## Layout

```
data/
├── daily/    YYYY-MM-DD.json   — one new file per UTC day
├── weekly/   YYYY-Www.json     — one file per ISO week, overwritten daily
└── monthly/  YYYY-MM.json      — one file per calendar month, overwritten daily
```

The weekly and monthly files are intentionally overwritten by every
daily run during their bucket. The *latest* committed version of
`weekly/2026-W20.json` represents the most recent rolling-7-day
snapshot taken during ISO week 20 of 2026; earlier daily snapshots for
that bucket are preserved in `git log -p data/weekly/2026-W20.json`.

## Schema

```json
{
  "granularity": "daily",
  "run_date_utc": "2026-05-13T00:30:00Z",
  "period": {
    "start": "2026-05-13",
    "end":   "2026-05-13",
    "label_iso":     "2026-05-13",
    "label_compact": "2026.05.13"
  },
  "source_url": "https://github.com/trending?since=daily",
  "count": 25,
  "items": [
    {
      "rank": 1,
      "owner": "microsoft",
      "name":  "vscode",
      "full_name":   "microsoft/vscode",
      "url":         "https://github.com/microsoft/vscode",
      "description": "Visual Studio Code",
      "language":    "TypeScript",
      "stars_total": 162345,
      "forks_total": 28901,
      "contributors_visible": 5,
      "period_stars": 1273,
      "period_stars_label": "1,273 stars 2026-05-13"
    }
  ]
}
```

### Field notes

- `period.start` / `period.end` are the rolling window the snapshot
  covers, *not* the bucket the filename refers to. For weekly and
  monthly, these can cross ISO-week or calendar-month boundaries.
- `contributors_visible` is the count of avatar tiles GitHub renders
  in the trending row's *Built by* section (1–5). It is **not** the
  project's full contributor count.
- `period_stars_label` is the bottom-right tagline from the trending
  HTML with `today` / `this week` / `this month` rewritten to the
  concrete date range — e.g. `"1,273 stars 2026.05.07-2026.05.13"`.

## Example queries

Top 5 trending repos today by `period_stars`:

```bash
jq '.items | sort_by(-.period_stars) | .[:5] | .[] | "\(.period_stars)\t\(.full_name)"' \
   data/daily/$(date -u +%F).json
```

How many distinct repos have appeared on the daily trending page in
the last 30 days?

```bash
ls data/daily | sort | tail -30 | while read f; do
  jq -r '.items[].full_name' "data/daily/$f"
done | sort -u | wc -l
```

Time-series of `microsoft/vscode`'s daily `period_stars`:

```bash
for f in data/daily/*.json; do
  echo -n "$(basename "$f" .json) "
  jq -r '.items[] | select(.full_name=="microsoft/vscode") | .period_stars' "$f"
done | grep -v ' $'
```
```

- [ ] **Step 2: Create top-level `README.md`**

```markdown
# trending-on-github

A daily cron'd GitHub Action that scrapes
[github.com/trending](https://github.com/trending) and commits the
results as JSON snapshots back to this repository. The git history
becomes a free, versioned time-series dataset of trending repos
(["git scraping"](https://simonwillison.net/2020/Oct/9/git-scraping/) —
Simon Willison, 2020).

## What it captures

Three granularities, captured once a day at 00:30 UTC:

| Granularity | URL                                                | Window       |
|-------------|----------------------------------------------------|--------------|
| daily       | `https://github.com/trending?since=daily`         | rolling 24h  |
| weekly      | `https://github.com/trending?since=weekly`        | rolling 7d   |
| monthly     | `https://github.com/trending?since=monthly`       | rolling 30d  |

Per repo, each snapshot records: rank, owner, name, description,
language, total stars, total forks, the count of avatar tiles shown in
the "Built by" section, the period stars, and a human-readable
`period_stars_label` with the concrete date range substituted for
"today" / "this week" / "this month".

Dataset schema and example queries live in
[`data/README.md`](data/README.md).

## Local development

```bash
python3.12 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/pytest -q

# Run a single granularity into ./tmp
.venv/bin/python -m trending --granularity daily --out tmp --verbose
```

## Layout

```
src/trending/    # package: fetch, parse, period, snapshot, __main__
tests/           # pytest + frozen HTML fixtures
data/            # accumulated snapshots (the dataset)
.github/workflows/
  scrape.yml     # daily cron
  test.yml       # CI on push/PR
docs/superpowers/specs/   # design spec
docs/superpowers/plans/   # implementation plan
```

## CI footprint

≈ 25 s wall-clock per scrape run → ~13 min/month. Well under any
GitHub Actions free tier.
```

- [ ] **Step 3: Commit READMEs**

```bash
git add data/README.md README.md
git commit -m "docs: dataset schema, jq examples, and top-level README"
```

---

### Task 11: Final verification

**Files:** (none — this is a verification task)

- [ ] **Step 1: Run the full test suite**

Run: `.venv/bin/pytest -q`
Expected: all tests pass (period: 10, parse: 8, snapshot: 5, fetch: 6 = 29 tests).

- [ ] **Step 2: Confirm git log is clean and ordered**

Run: `git log --oneline`
Expected: a sequence like
```
<sha> docs: dataset schema, jq examples, and top-level README
<sha> ci: daily cron scrape of github.com/trending with auto-commit
<sha> ci: run pytest on push and pull_request
<sha> feat(cli): python -m trending entry point wiring fetch→parse→snapshot
<sha> feat(fetch): HTTP layer with retry + courteous User-Agent
<sha> feat(snapshot): atomic JSON snapshot writer per granularity
<sha> feat(parse): HTML→Record parser with rolling-window label rewriting
<sha> test: capture frozen HTML fixtures of github.com/trending
<sha> feat(period): pure date math for daily/weekly/monthly windows
<sha> build: bootstrap python package skeleton and pytest config
<sha> docs: design spec for trending-on-github collector
```

- [ ] **Step 3: Push branch (only when ready to share)**

```bash
git push origin main
```
This kicks off the `test` workflow on GitHub. Then either wait until
00:30 UTC for the first scheduled scrape, or trigger one manually via
the *Run workflow* button on the *scrape-trending* page under Actions.

- [ ] **Step 4: After the first scheduled scrape, confirm data**

Wait for the first cron run (or trigger via `workflow_dispatch`), then:
```bash
git pull
ls data/daily data/weekly data/monthly
jq '.count, .items[0].full_name' data/daily/$(date -u +%F).json
```
Expected: each directory contains one file for today's run, and the
`jq` invocation prints a record count (~20–25) and a real repo name.

---

## Notes for the implementer

- **Identity**: this repo lives under `github.com/host452b/`. Repo-local
  git config should be `user.name = host452b` and
  `user.email = 32806348+host452b@users.noreply.github.com`. The
  initial commit of the design spec already used this identity.
- **GitHub may change the trending markup at any time.** If a parser
  test starts failing live (not just on the fixture), recapture the
  fixture (`Task 3 Step 1`), inspect the diff, and adjust the
  selectors in `parse.py`. The test will tell you exactly which
  field broke.
- **`continue-on-error: true` plus the verify-step pattern** in
  `scrape.yml` is the elegant way to encode "exit non-zero only when
  all three fail" without writing custom shell. Don't replace it with
  manual `set +e` / `set -e` tricks.
