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
