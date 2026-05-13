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
    """Parse '1,234' -> 1234, '12.3k' -> 12300, '1.2M' -> 1200000."""
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
