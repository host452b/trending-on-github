# Trending-on-GitHub Collector — Design Spec

**Date approved**: 2026-05-13
**Repo**: `github.com/host452b/trending-on-github`
**Status**: approved; ready for implementation planning

## 1. Goal

A GitHub Actions workflow that runs once a day, scrapes
`https://github.com/trending?since={daily,weekly,monthly}`, and commits
JSON snapshots back to this repo. The git history serves as a free,
versioned time-series dataset of GitHub trending repositories
("git scraping" pattern — Simon Willison, 2020).

## 2. Non-goals

- No real-time feed, no public API, no UI/dashboard (these are future
  follow-ups).
- No per-language trending breakdowns — only the global "all languages"
  trending pages.
- No true contributor count — we only record the visible avatar count
  from the trending row's "Built by" section, documented honestly.
- No multiple cron ticks per day; no parallel jobs; no extra workflow
  artifacts. Stay frugal with Actions minutes.

## 3. Architecture

### 3.1 Directory layout

```
trending-on-github/
├── .github/workflows/
│   ├── scrape.yml         # cron 30 0 * * *, one job, pip cache, concurrency guard, auto-commit
│   └── test.yml           # pytest on push/PR (parser + period math only, no network)
├── src/trending/
│   ├── __init__.py
│   ├── parse.py           # HTML → list[Record]. All BeautifulSoup selectors live here, isolated.
│   ├── period.py          # Pure: (run_date, granularity) → (start, end, label_iso, label_compact)
│   ├── snapshot.py        # Atomic write of snapshot JSON (write temp + os.replace)
│   ├── fetch.py           # requests.get with retry + User-Agent; thin, easy to mock
│   └── __main__.py        # CLI: `python -m trending --granularity {daily|weekly|monthly} --out data`
├── tests/
│   ├── fixtures/
│   │   ├── trending_daily.html      # frozen snapshot of github.com/trending?since=daily
│   │   ├── trending_weekly.html
│   │   └── trending_monthly.html
│   ├── test_parse.py      # parses each fixture, asserts schema + record count + key fields
│   └── test_period.py     # boundary cases: month-end, leap year, year rollover
├── data/
│   ├── README.md          # schema + example jq queries
│   ├── daily/             # YYYY-MM-DD.json — one new file per day
│   ├── weekly/            # YYYY-Www.json   — one file per ISO week, overwritten daily within that week
│   └── monthly/           # YYYY-MM.json    — one file per calendar month, overwritten daily within that month
├── requirements.txt       # requests, beautifulsoup4 (runtime)
├── requirements-dev.txt   # pytest (dev only)
├── pyproject.toml         # pytest + ruff config
└── README.md              # what it is, schedule, schema, usage
```

### 3.2 Module responsibilities

- **`fetch.py`** is the only network-touching module. It exposes
  `fetch_trending(granularity) -> str` (HTML body) with three retries on
  5xx/timeout and a courteous User-Agent
  `trending-on-github/1.0 (+https://github.com/host452b/trending-on-github)`.
- **`parse.py`** consumes HTML → `list[Record]`. Pure (no I/O). Every
  selector is documented in a single table near the top of the file so
  that future GitHub markup changes can be patched in one place.
- **`period.py`** is pure date math. Given `(run_date, granularity)` it
  returns `(start, end, label_iso, label_compact)`. No imports beyond
  `datetime`.
- **`snapshot.py`** writes the JSON atomically
  (`tempfile.NamedTemporaryFile` in the same directory, then
  `os.replace`) so a crashed run cannot leave a half-written file.
  Named `snapshot` rather than `io` to avoid shadowing Python's stdlib
  `io` module and to describe its purpose plainly.
- **`__main__.py`** is the CLI entry. It wires `fetch → parse → io`
  together, handles logging, and returns a non-zero exit code only when
  *all three* granularities fail — a single transient failure should
  not block the other two.

## 4. Data schema

### 4.1 Snapshot file

One JSON file per (granularity, period). Example
`data/daily/2026-05-13.json`:

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

### 4.2 Period semantics (rolling windows, matching GitHub trending)

| Granularity | Window                         | `label_compact` example      | File name                  |
|-------------|--------------------------------|------------------------------|----------------------------|
| daily       | `[run_date, run_date]`         | `2026.05.13`                 | `daily/2026-05-13.json`    |
| weekly      | `[run_date - 6d, run_date]`    | `2026.05.07-2026.05.13`      | `weekly/2026-W20.json`     |
| monthly     | `[run_date - 29d, run_date]`   | `2026.04.14-2026.05.13`      | `monthly/2026-05.json`     |

ISO week numbers (`YYYY-Www`) come from `datetime.date.isocalendar()` —
e.g. 2026-05-13 (Wednesday) is in ISO week 20. Calendar months are
`YYYY-MM`. Both are zero-padded.

**Note**: the rolling window may cross the bucket boundary used in the
filename. For example, `weekly/2026-W20.json` written on 2026-05-13
holds `period = [2026-05-07, 2026-05-13]`, which spans ISO weeks 19 and
20. That is intentional — the filename is the bucket key (which day's
ISO week / calendar month the run fell into), while `period.start/end`
inside the JSON is the actual rolling window the data covers.

### 4.3 File cadence

- **Daily**: one new file per day. Never overwritten.
- **Weekly**: one file per ISO week. Each daily run during that week
  overwrites it with the latest rolling-7-day snapshot. By Sunday the
  file holds the freshest weekly view.
- **Monthly**: one file per calendar month. Each daily run during that
  month overwrites it with the latest rolling-30-day snapshot.

Because each run records its own `run_date_utc` inside the JSON, the
git history of `weekly/2026-W20.json` and `monthly/2026-05.json`
preserves every daily snapshot — no information is lost, only the
"latest" view of the file shows the most recent capture.

### 4.4 Label rewriting (per the user's stated requirement)

The trending HTML shows `period_stars` as `"N stars today"`,
`"N stars this week"`, or `"N stars this month"`. We rewrite the
trailing token using `period.label_compact`:

```
"1,273 stars today"        → "1,273 stars 2026-05-13"
"4,521 stars this week"    → "4,521 stars 2026.05.07-2026.05.13"
"12,034 stars this month"  → "12,034 stars 2026.04.14-2026.05.13"
```

Numeric form is preserved with commas so the label reads naturally.

### 4.5 Field reference (parser selectors)

| Field                  | Selector                                                   | Notes                                                   |
|------------------------|------------------------------------------------------------|---------------------------------------------------------|
| Row                    | `article.Box-row`                                          | Each trending repo                                      |
| `owner`, `name`        | `h2 a[href]` → strip `/` → split on `/`                    | From the repo link                                      |
| `description`          | `p.col-9` text, stripped                                   | `null` when missing                                     |
| `language`             | `[itemprop="programmingLanguage"]` text                    | `null` when missing                                     |
| `stars_total`          | `a[href$="/stargazers"]` text → `parse_int()`              | `parse_int` handles `"12.3k"` → `12300`                 |
| `forks_total`          | `a[href$="/forks"]` text → `parse_int()`                   | Same `parse_int`                                        |
| `contributors_visible` | `span.d-inline-block.mr-3 a img.avatar` count              | Honest naming — only the "Built by" tile count (1–5)    |
| `period_stars`         | bottom-right `span.d-inline-block.float-sm-right` text matched by `^(\d[\d,]*)\s+stars?\s+(today|this week|this month)$` | Strip commas, parse to int |

### 4.6 Defensive parsing

If any required field (`owner`, `name`, `stars_total`, `period_stars`)
is missing on a row, the row is **dropped with a warning logged** —
one malformed row must not break the whole snapshot. Fixture tests
guarantee the happy path.

## 5. Workflows

### 5.1 `.github/workflows/scrape.yml`

```yaml
name: scrape-trending
on:
  schedule:
    - cron: "30 0 * * *"        # 00:30 UTC daily
  workflow_dispatch:             # manual trigger
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
      - run: pip install -r requirements.txt
      - run: |
          python -m trending --granularity daily   --out data
          python -m trending --granularity weekly  --out data
          python -m trending --granularity monthly --out data
      - uses: stefanzweifel/git-auto-commit-action@v5
        with:
          commit_message: "data: trending snapshot ${{ github.run_id }}"
          file_pattern: "data/**/*.json"
          commit_user_name: host452b
          commit_user_email: 32806348+host452b@users.noreply.github.com
```

### 5.2 `.github/workflows/test.yml`

```yaml
name: test
on: [push, pull_request]
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
      - run: pip install -r requirements.txt -r requirements-dev.txt
      - run: pytest -q
```

### 5.3 Quota estimate

≈ 25 s wall-clock per scrape run (10 s job startup + 3 s setup-python
with cache + 2 s pip install with cache + ~8 s scrape + ~2 s commit).
25 s × 31 days ≈ **13 min/month**. Test workflow only runs on push/PR,
adds negligible quota. Well under any GitHub free tier.

## 6. Testing strategy

- **`test_parse.py`** parses each of three frozen HTML fixtures and
  asserts: ≥ 20 records present, every record has `owner`, `name`,
  `stars_total > 0`, `period_stars >= 0`, and `granularity`-matching
  `period_stars_label` token style. Catches GitHub-side markup drift in
  seconds rather than corrupting the live dataset.
- **`test_period.py`** covers boundary math: leap-year Feb 28 → 29,
  month rollover (e.g. May 1 weekly window starts April 25), year
  rollover (Jan 5 monthly window starts prior December 7).
- **No network in tests.** Fast (< 1 s) and deterministic. The fetch
  module is only exercised by the live scrape workflow.

## 7. Error handling & idempotency

- Atomic write via `tempfile + os.replace`. A crashed run leaves the
  previous file intact, never a partial write.
- `git-auto-commit-action` is a no-op when nothing changed — re-running
  within minutes produces zero commits, zero noise.
- Per-granularity isolation: a 503 on one URL logs and continues with
  the other two. Process exits non-zero only when **all three** fail,
  so transient errors don't paper over real outages.
- `timeout-minutes: 5` is a hard wall — if anything hangs, the run is
  killed and CI minutes aren't burned.
- `concurrency.group: scrape-trending` with
  `cancel-in-progress: false` prevents two runs from racing on
  `git push`.

## 8. Industry references

1. **Simon Willison — Git scraping (2020)**:
   <https://simonwillison.net/2020/Oct/9/git-scraping/>. Canonical
   pattern for this project.
2. **`stefanzweifel/git-auto-commit-action`** (de facto auto-commit
   Action; no-op on no-change; configurable identity).
3. **Frozen-HTML fixture testing for scrapers** (used by Internet
   Archive, news aggregators). Pairs with `actions/cache` for pip and
   a workflow-level `concurrency:` group.

## 9. Open questions

All resolved during the brainstorming phase on 2026-05-13:

- ✅ Storage layout: per-run JSON snapshots, folder per granularity.
- ✅ Crawl scope: "all languages" global trending only (3 URLs / run).
- ✅ Contributor count: approximate from trending page visible
  avatars; honest naming.
- ✅ Schedule: 00:30 UTC daily; single cron tick.
- ✅ Language: Python 3.12 + `requests` + `beautifulsoup4`.
- ✅ Weekly window: rolling 7 days ending on `run_date`.
- ✅ Label form: both `label_iso` and `label_compact` in JSON.
- ✅ File cadence: one daily file per day; weekly/monthly overwritten
  daily within the period (git history preserves all intermediate
  snapshots).
