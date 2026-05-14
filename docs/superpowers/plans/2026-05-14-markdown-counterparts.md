# Markdown Counterparts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- []`) syntax for tracking.

**Goal:** Generate three cumulative Markdown files (`data/daily.md`, `data/weekly.md`, `data/monthly.md`) from the existing JSON snapshots, refreshed on every scrape, so a human can skim every snapshot chronologically without parsing JSON.

**Architecture:** A standalone Python script `build_markdown.py` at the repo root reads every JSON snapshot under `data/{daily,weekly,monthly}/` and atomically writes the three markdown files using pure stdlib (`json`, `tempfile`, `os`). The scrape workflow runs it right after `build_dashboard.py`, and the existing `git-auto-commit-action` step is extended to push the `.md` files alongside the JSON.

**Tech Stack:** Python 3.12 (stdlib only — no extra pip deps). Tests via `pytest` (already in `requirements-dev.txt`). GitHub Actions for the cron integration.

**Spec reference:** `docs/superpowers/specs/2026-05-14-markdown-counterparts-design.md`

---

## File Structure

| Path                                      | Responsibility                                                                 |
|-------------------------------------------|--------------------------------------------------------------------------------|
| `build_markdown.py`                       | Read `data/*/*.json` → emit `data/{daily,weekly,monthly}.md`. Atomic writes.    |
| `tests/test_markdown.py`                  | Unit tests for the helpers and end-to-end build via `tmp_path`.                |
| `data/daily.md` (generated, committed)    | Cumulative log of every daily snapshot, newest first.                          |
| `data/weekly.md` (generated, committed)   | Same for weekly snapshots.                                                     |
| `data/monthly.md` (generated, committed)  | Same for monthly snapshots.                                                    |
| `.github/workflows/scrape.yml` (modify)   | Add "Rebuild cumulative markdown" step; extend auto-commit `file_pattern`.     |
| `data/README.md` (modify)                 | One paragraph pointing at the three new files.                                 |
| `README.md` (modify)                      | List `build_markdown.py` next to `build_dashboard.py` in the layout block.     |

Total: 1 new code file, 1 new test file, 3 generated `.md` files, 3 modified files.

---

### Task 1: `escape_pipe` and `format_int` helpers (TDD)

**Files:**
- Create: `build_markdown.py`
- Create: `tests/test_markdown.py`

Two tiny helpers we'll reuse everywhere: pipe-escaping inside table cells, and thousands-grouped integer formatting.

- [ ] **Step 1: Create `tests/test_markdown.py` with helper tests**

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_markdown.py -v`
Expected: `ImportError: No module named 'build_markdown'` (file does not exist yet).

- [ ] **Step 3: Create `build_markdown.py` with the helpers**

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_markdown.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add build_markdown.py tests/test_markdown.py
git commit -m "feat(markdown): escape_pipe + format_int helpers"
```

---

### Task 2: `read_snapshots` — load JSON files in chronological order (TDD)

**Files:**
- Modify: `build_markdown.py`
- Modify: `tests/test_markdown.py`

A helper that returns `(path, snapshot_dict)` tuples for one granularity, sorted by filename ascending (chronological). Bad files are skipped with a warning to `stderr`, not raised — one corrupt JSON should not block the whole rebuild.

- [ ] **Step 1: Append tests to `tests/test_markdown.py`**

Append (do not replace existing tests):

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_markdown.py::test_read_snapshots_returns_chronological_order -v`
Expected: `AttributeError: module 'build_markdown' has no attribute 'read_snapshots'`.

- [ ] **Step 3: Add `read_snapshots` to `build_markdown.py`**

Append (do not replace existing code):

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_markdown.py -v`
Expected: 6 passed (3 prior + 3 new).

- [ ] **Step 5: Commit**

```bash
git add build_markdown.py tests/test_markdown.py
git commit -m "feat(markdown): read_snapshots loader with skip-on-error semantics"
```

---

### Task 3: `build_section` — render one snapshot as markdown (TDD)

**Files:**
- Modify: `build_markdown.py`
- Modify: `tests/test_markdown.py`

Renders a single snapshot dict (plus its on-disk path for the JSON link) as a markdown section: header, subtitle, pipe-table of items, trailing `---`.

- [ ] **Step 1: Append tests**

Append to `tests/test_markdown.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_markdown.py::test_build_section_includes_header_subtitle_and_table -v`
Expected: `AttributeError: module 'build_markdown' has no attribute 'build_section'`.

- [ ] **Step 3: Add `build_section` to `build_markdown.py`**

Append:

```python
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
    # Header: use the period start as the section anchor so a permalink
    # works when scrolling through the cumulative file.
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_markdown.py -v`
Expected: 9 passed (6 prior + 3 new).

- [ ] **Step 5: Commit**

```bash
git add build_markdown.py tests/test_markdown.py
git commit -m "feat(markdown): build_section renders one snapshot as a pipe-table"
```

---

### Task 4: `build_file` — assemble the full cumulative markdown (TDD)

**Files:**
- Modify: `build_markdown.py`
- Modify: `tests/test_markdown.py`

Takes the granularity name, the loaded `(path, snapshot)` pairs, and the human title/emoji, and emits the full file body: title, summary line, then sections newest-first.

- [ ] **Step 1: Append tests**

Append to `tests/test_markdown.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_markdown.py::test_build_file_orders_sections_newest_first -v`
Expected: `AttributeError: module 'build_markdown' has no attribute 'build_file'`.

- [ ] **Step 3: Add `build_file` to `build_markdown.py`**

Append:

```python
def build_file(
    *,
    granularity: str,
    title: str,
    emoji: str,
    pairs: list[tuple[Path, dict]],
) -> str:
    """Assemble the full cumulative markdown body for one granularity.

    `pairs` come in chronological order (oldest first) from
    `read_snapshots`. The output renders them newest-first.
    """
    parts: list[str] = []
    parts.append(f"# {title} — accumulated snapshots")
    parts.append("")
    if pairs:
        oldest = pairs[0][1]["period"]["start"]
        newest = pairs[-1][1]["period"]["start"]
        parts.append(
            f"Auto-generated by `build_markdown.py` from "
            f"`data/{granularity}/*.json` on every scrape. "
            f"**{len(pairs)} snapshots** spanning "
            f"`{oldest}` → `{newest}`. "
            f"Raw JSON: [`data/{granularity}/`]({granularity}/)."
        )
    else:
        parts.append(
            f"Auto-generated by `build_markdown.py` from "
            f"`data/{granularity}/*.json` on every scrape. "
            f"**0 snapshots** so far."
        )
    parts.append("")
    parts.append("---")
    parts.append("")
    # Newest first.
    for json_path, snapshot in reversed(pairs):
        parts.append(
            build_section(
                json_path=json_path,
                snapshot=snapshot,
                emoji=emoji,
                title=title,
            )
        )
    return "\n".join(parts).rstrip() + "\n"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_markdown.py -v`
Expected: 12 passed (9 prior + 3 new).

- [ ] **Step 5: Commit**

```bash
git add build_markdown.py tests/test_markdown.py
git commit -m "feat(markdown): build_file assembles cumulative body newest-first"
```

---

### Task 5: Atomic `write_file` + `main()` orchestrator (TDD)

**Files:**
- Modify: `build_markdown.py`
- Modify: `tests/test_markdown.py`

`write_file(target, body)` writes atomically via `tempfile.mkstemp` + `os.replace`, matching the pattern in `src/trending/snapshot.py`. `main()` is the CLI entry: loads each granularity, builds the body, writes to `data/<granularity>.md`, prints a one-line status. The script ends with `if __name__ == "__main__": raise SystemExit(main())`.

- [ ] **Step 1: Append tests**

Append to `tests/test_markdown.py`:

```python
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
    for name in ("daily.md", "weekly.md", "monthly.md"):
        target = tmp_path / name
        assert target.exists()
        body = target.read_text(encoding="utf-8")
        assert "accumulated snapshots" in body
        assert "a/b" in body
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_markdown.py -v`
Expected: 3 new tests fail with `AttributeError: write_file` / `main`.

- [ ] **Step 3: Add `write_file` and `main` to `build_markdown.py`**

Append:

```python
_GRANULARITIES = (
    ("daily", "Daily Trending", "🔥"),
    ("weekly", "Weekly Trending", "📅"),
    ("monthly", "Monthly Trending", "🗓️"),
)


def write_file(target: Path, body: str) -> None:
    """Atomic write: tempfile + os.replace (same pattern as snapshot.py)."""
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_path = tempfile.mkstemp(
        prefix=".build-markdown-",
        suffix=".md.tmp",
        dir=str(target.parent),
    )
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            f.write(body)
        os.replace(tmp_path, target)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            # Best-effort cleanup; never suppress the original exception.
            pass
        raise


def main() -> int:
    for granularity, title, emoji in _GRANULARITIES:
        pairs = read_snapshots(DATA_DIR, granularity)
        body = build_file(
            granularity=granularity,
            title=title,
            emoji=emoji,
            pairs=pairs,
        )
        target = DATA_DIR / f"{granularity}.md"
        write_file(target, body)
        print(f"wrote {target} ({len(pairs)} snapshots)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_markdown.py -v`
Expected: 15 passed (12 prior + 3 new).

- [ ] **Step 5: End-to-end smoke run**

Run from repo root:
```bash
.venv/bin/python build_markdown.py
ls -lh data/daily.md data/weekly.md data/monthly.md
head -20 data/daily.md
```
Expected:
- Three files written under `data/`.
- `head` shows the title `# Daily Trending — accumulated snapshots`, the summary line with the current snapshot count, the `---` separator, then the first `## 2026-MM-DD — 🔥 Daily Trending` section.

- [ ] **Step 6: Run the full test suite to make sure nothing regressed**

Run: `.venv/bin/pytest -q`
Expected: all tests pass (42 prior + 15 new = 57 — exact count may differ by ±2 if Task 1-4 helper-test counts differ; the important thing is zero failures).

- [ ] **Step 7: Commit**

```bash
git add build_markdown.py tests/test_markdown.py data/daily.md data/weekly.md data/monthly.md
git commit -m "feat(markdown): atomic write_file + main() orchestrator, 3 cumulative .md files committed"
```

---

### Task 6: Wire the script into the scrape workflow

**Files:**
- Modify: `.github/workflows/scrape.yml`

- [ ] **Step 1: Read the current scrape.yml**

Run: `cat .github/workflows/scrape.yml`
Confirm the file currently has a `- name: Rebuild dashboard.ipynb` step followed by a `- uses: stefanzweifel/git-auto-commit-action@v5` step whose `file_pattern` block is:

```yaml
          file_pattern: |
            data/**/*.json
            dashboard.ipynb
```

- [ ] **Step 2: Add the rebuild step and extend file_pattern**

Edit `.github/workflows/scrape.yml`:

Find:
```yaml
      - name: Rebuild dashboard.ipynb
        run: python build_dashboard.py
      - uses: stefanzweifel/git-auto-commit-action@v5
        with:
          commit_message: "data: trending snapshot ${{ github.run_id }}"
          file_pattern: |
            data/**/*.json
            dashboard.ipynb
          commit_user_name: host452b
          commit_user_email: 32806348+host452b@users.noreply.github.com
```

Replace with:
```yaml
      - name: Rebuild dashboard.ipynb
        run: python build_dashboard.py
      - name: Rebuild cumulative markdown
        run: python build_markdown.py
      - uses: stefanzweifel/git-auto-commit-action@v5
        with:
          commit_message: "data: trending snapshot ${{ github.run_id }}"
          file_pattern: |
            data/**/*.json
            dashboard.ipynb
            data/*.md
          commit_user_name: host452b
          commit_user_email: 32806348+host452b@users.noreply.github.com
```

- [ ] **Step 3: Validate YAML**

Run: `.venv/bin/python -c "import yaml; yaml.safe_load(open('.github/workflows/scrape.yml'))"`
Expected: no output, exit 0.

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/scrape.yml
git commit -m "ci: rebuild data/{daily,weekly,monthly}.md after each scrape"
```

---

### Task 7: Update READMEs

**Files:**
- Modify: `data/README.md`
- Modify: `README.md`

- [ ] **Step 1: Append the new paragraph to `data/README.md`**

Right after the layout block at the top, before the existing schema discussion, add this section. (Use Edit to insert the block after the closing ```` ``` ```` of the layout block; do not duplicate or remove anything else.)

Add:

```markdown
## Human-readable view

Alongside the per-snapshot JSON files, three cumulative Markdown files
at this directory's root collect every snapshot chronologically (newest
first):

- [`daily.md`](daily.md) — every daily snapshot ever captured.
- [`weekly.md`](weekly.md) — one entry per ISO week.
- [`monthly.md`](monthly.md) — one entry per calendar month.

Regenerated by `build_markdown.py` on every scrape; each section links
back to the raw `.json` file it was rendered from.

```

- [ ] **Step 2: Update the layout block in the top-level `README.md`**

Find:
```
src/trending/         # package: fetch, parse, period, snapshot, __main__
tests/                # pytest + frozen HTML fixtures
data/                 # accumulated snapshots (the dataset)
build_dashboard.py    # static-notebook generator
dashboard.ipynb       # auto-regenerated rendered overview
```

Replace with:
```
src/trending/         # package: fetch, parse, period, snapshot, __main__
tests/                # pytest + frozen HTML fixtures
data/                 # accumulated snapshots (the dataset)
build_dashboard.py    # static-notebook generator
build_markdown.py     # cumulative human-readable markdown generator
dashboard.ipynb       # auto-regenerated rendered overview
```

- [ ] **Step 3: Commit**

```bash
git add data/README.md README.md
git commit -m "docs: point readers at the new data/{daily,weekly,monthly}.md files"
```

---

### Task 8: Final verification + PR

**Files:** (none — verification only)

- [ ] **Step 1: Full test suite**

Run: `.venv/bin/pytest -q`
Expected: all tests pass; the new `tests/test_markdown.py` contributes 15 tests.

- [ ] **Step 2: Confirm the dataset markdown looks reasonable**

Run:
```bash
wc -l data/daily.md data/weekly.md data/monthly.md
head -15 data/daily.md
```
Expected:
- Each file is non-empty; daily.md is shortest (one section per day; we have very few days of history right now), monthly.md is even shorter (one section per calendar month).
- `head` shows a clean title, the summary line, a `---`, then the newest snapshot's `## YYYY-MM-DD — 🔥 Daily Trending (window …)` header.

- [ ] **Step 3: Confirm git log is clean**

Run: `git log --oneline main..HEAD`
Expected: a tight commit series — six or seven feat/ci/docs commits, all authored as `host452b <…@users.noreply.github.com>`.

- [ ] **Step 4: Push branch**

```bash
git push -u origin feat/markdown-counterparts
```

- [ ] **Step 5: Open PR**

```bash
gh pr create --base main --head feat/markdown-counterparts \
  --title "Add cumulative markdown counterparts (data/{daily,weekly,monthly}.md)" \
  --body "$(cat <<'EOF'
## Summary

Adds three cumulative human-readable markdown files at the dataset root, refreshed each scrape by a new \`build_markdown.py\`. Each section corresponds to one JSON snapshot, newest first, with a pipe-table of items and a link back to the raw JSON.

- \`data/daily.md\` — one section per UTC day, newest first
- \`data/weekly.md\` — one section per ISO week
- \`data/monthly.md\` — one section per calendar month

Workflow integration: \`scrape.yml\` runs \`python build_markdown.py\` right after \`build_dashboard.py\`; the auto-commit \`file_pattern\` is extended to include \`data/*.md\`. ~+0.5 s per cron run.

## Test plan

- [x] \`pytest -q\` → all tests pass (incl. 15 new in \`tests/test_markdown.py\`).
- [x] Local end-to-end run of \`build_markdown.py\` produces three valid markdown files; pipes inside descriptions escaped; chronological order newest-first.
- [x] Atomic write verified by patching \`os.replace\` to raise: the previous \`.md\` survives and no temp file is leaked.
- [ ] After merge, manually dispatch the scrape workflow to confirm the auto-commit picks up \`data/*.md\` alongside the JSON and the rebuilt notebook.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

Expected: outputs a PR URL.

- [ ] **Step 6: Watch CI**

Run: `gh pr checks <number> --repo host452b/trending-on-github` (replace `<number>` with the PR number returned by Step 5).
Expected: `test pass` within ~15 s.

---

## Notes for the implementer

- **Identity**: this repo lives under `github.com/host452b/`. Repo-local git config is already set to `user.name=host452b`, `user.email=32806348+host452b@users.noreply.github.com`. Don't modify it.
- **No new pip deps**: the build script is pure stdlib. `requirements.txt` and `requirements-dev.txt` are unchanged.
- **The first generated `data/daily.md` will be tiny**: at the moment of this plan being executed, there's only one daily snapshot in the repo. `daily.md` will have one section; `weekly.md` and `monthly.md` will each have one section too. The files will grow automatically as the cron accumulates more snapshots.
- **Why aggregated, not sidecars**: explicitly chosen during brainstorming (2026-05-14). Sidecar `.md` files next to each `.json` would mean hundreds of small files; the cumulative-file approach gives a single chronological view that GitHub renders nicely.
