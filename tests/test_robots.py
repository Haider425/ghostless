import pytest

from tracker.sources import http
from tracker.sources.http import FetchError
from tracker.sources.robots import RobotsCache, parse

AGENT = "job-market-tracker/0.2"

GOOGLE_LIKE = """
User-agent: *
Disallow: /search
Allow: /search/about
Disallow: /about/careers/applications/jobs/results?page=
Disallow: /about/careers/applications/jobs/results/?*&page=
Disallow: /*.php$

User-agent: Yandex
Disallow: /
"""


@pytest.mark.parametrize(
    "path, allowed",
    [
        ("/about/careers/applications/jobs/results/?location=Canada&q=software", True),
        ("/about/careers/applications/jobs/results/?location=Canada&q=x&page=2", False),  # wildcard rule
        ("/about/careers/applications/jobs/results?page=3", False),
        ("/about/careers/applications/jobs/results/123-software-engineer", True),
        ("/search?q=x", False),
        ("/search/about", True),  # longer Allow beats shorter Disallow
        ("/index.php", False),  # $ anchors the end
        ("/index.php?x=1", True),
    ],
)
def test_wildcard_and_longest_match_rules(path, allowed):
    assert parse(GOOGLE_LIKE, AGENT).allowed(path) is allowed


def test_specific_agent_group_overrides_star():
    text = "User-agent: *\nDisallow: /\n\nUser-agent: job-market-tracker\nDisallow: /private\n"
    rules = parse(text, AGENT)
    assert rules.allowed("/jobs")
    assert not rules.allowed("/private/x")


def test_empty_disallow_allows_everything():
    assert parse("User-agent: *\nDisallow:\n", AGENT).allowed("/anything")


def test_grouped_agents_share_rules():
    text = "User-agent: a\nUser-agent: *\nDisallow: /x\n"
    assert not parse(text, AGENT).allowed("/x/y")


def test_meta_style_blanket_disallow():
    assert not parse("User-agent: *\nDisallow: /\n", AGENT).allowed("/jobs")


@pytest.mark.parametrize(
    "status, expected",
    [(200, False), (404, True), (403, True), (500, False), (0, False)],
)
def test_cache_status_handling(status, expected):
    calls = []

    def fetcher(url):
        calls.append(url)
        return status, "User-agent: *\nDisallow: /jobs\n"

    cache = RobotsCache(AGENT, fetcher)
    assert cache.allowed("https://example.com/jobs/1") is expected
    cache.allowed("https://example.com/jobs/2")
    assert calls == ["https://example.com/robots.txt"]  # fetched once per host


def test_http_layer_refuses_disallowed_urls(monkeypatch):
    monkeypatch.setattr(http, "robots", RobotsCache(AGENT, lambda url: (200, "User-agent: *\nDisallow: /\n")))
    with pytest.raises(FetchError, match="robots.txt"):
        http.get_json("https://blocked.example.com/api/jobs")
