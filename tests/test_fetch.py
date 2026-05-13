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
