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
  in the trending row's *Built by* section (typically 1–5). It is
  **not** the project's full contributor count.
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
