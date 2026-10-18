from datetime import datetime, timedelta, timezone

import pytest
import requests

from tracker.sources import http
from tracker.sources.http import FetchError, Throttle, parse_retry_after
from tracker.sources.robots import RobotsCache


class FakeClock:
    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def clock(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(round(seconds, 2))
        self.now += seconds


class FakeResponse:
    def __init__(self, status, body="{}", headers=None):
        self.status_code = status
        self.text = body
        self.headers = headers or {}

    def json(self):
        import json

        return json.loads(self.text)


@pytest.fixture
def clock(monkeypatch):
    fake = FakeClock()
    monkeypatch.setattr(http, "throttle", Throttle(1.0, {"slow.example.com": 3.0}, fake.clock, fake.sleep))
    monkeypatch.setattr(http, "robots", RobotsCache("t", lambda url: (404, "")))
    monkeypatch.setattr(http.random, "uniform", lambda a, b: 0)
    return fake


def test_throttle_spaces_requests_per_host(clock):
    t = http.throttle
    t.wait("a.com")
    t.wait("a.com")  # immediately again: must wait 1s
    t.wait("b.com")  # different host: no wait
    t.wait("slow.example.com")
    t.wait("slow.example.com")  # overridden host: 3s
    assert clock.sleeps == [1.0, 3.0]


def test_slow_down_doubles_and_caps():
    t = Throttle(0.5, {})
    assert t.slow_down("x") == 1.0
    assert t.slow_down("x") == 2.0
    for _ in range(10):
        t.slow_down("x")
    assert t.interval("x") == http.MAX_INTERVAL_SECONDS


def test_parse_retry_after():
    now = datetime(2026, 10, 17, 12, 0, tzinfo=timezone.utc)
    assert parse_retry_after("7") == 7.0
    assert parse_retry_after("9999") == http.MAX_RETRY_AFTER_SECONDS
    later = (now + timedelta(seconds=30)).strftime("%a, %d %b %Y %H:%M:%S GMT")
    assert parse_retry_after(later, now) == 30.0
    assert parse_retry_after("nonsense") is None
    assert parse_retry_after(None) is None


def test_429_slows_host_and_honours_retry_after(clock, monkeypatch):
    responses = [FakeResponse(429, headers={"Retry-After": "5"}), FakeResponse(200, '{"ok": true}')]
    monkeypatch.setattr(requests, "request", lambda *a, **k: responses.pop(0))
    assert http.get_json("https://api.example.com/jobs") == {"ok": True}
    assert 5.0 in clock.sleeps  # waited as told
    assert http.throttle.interval("api.example.com") == 2.0  # and slowed future requests


def test_gives_up_after_max_attempts(clock, monkeypatch):
    monkeypatch.setattr(requests, "request", lambda *a, **k: FakeResponse(503))
    with pytest.raises(FetchError, match="gave up after 5 attempts"):
        http.get_json("https://api.example.com/jobs")


def test_client_errors_fail_fast(clock, monkeypatch):
    calls = []
    monkeypatch.setattr(requests, "request", lambda *a, **k: calls.append(1) or FakeResponse(403))
    with pytest.raises(FetchError, match="HTTP 403"):
        http.get_json("https://api.example.com/jobs")
    assert len(calls) == 1


def test_dump_saves_responses(clock, monkeypatch, tmp_path):
    monkeypatch.setattr(
        requests,
        "request",
        lambda *a, **k: FakeResponse(200, "<html>hi</html>", {"Content-Type": "text/html"}),
    )
    monkeypatch.setattr(http, "dump_dir", tmp_path)
    http.get_text("https://jobs.example.com/en-ca/search?x=1")
    [saved] = tmp_path.iterdir()
    assert saved.name.endswith("jobs.example.com_en-ca_search.html")
    assert saved.read_text() == "<html>hi</html>"


def test_user_agent_identifies_project():
    assert http.USER_AGENT.startswith("ghostless/")
    assert "+http" in http.USER_AGENT
