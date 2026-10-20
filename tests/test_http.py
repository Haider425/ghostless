from datetime import datetime, timedelta, timezone

import pytest

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
    monkeypatch.setattr(http, "_request", lambda *a, **k: responses.pop(0))
    assert http.get_json("https://api.example.com/jobs") == {"ok": True}
    assert 5.0 in clock.sleeps  # waited as told
    assert http.throttle.interval("api.example.com") == 2.0  # and slowed future requests


def test_gives_up_after_max_attempts(clock, monkeypatch):
    monkeypatch.setattr(http, "_request", lambda *a, **k: FakeResponse(503))
    with pytest.raises(FetchError, match="gave up after 5 attempts"):
        http.get_json("https://api.example.com/jobs")


def test_client_errors_fail_fast(clock, monkeypatch):
    calls = []
    monkeypatch.setattr(http, "_request", lambda *a, **k: calls.append(1) or FakeResponse(403))
    with pytest.raises(FetchError, match="HTTP 403"):
        http.get_json("https://api.example.com/jobs")
    assert len(calls) == 1


def test_dump_saves_responses(clock, monkeypatch, tmp_path):
    monkeypatch.setattr(
        http,
        "_request",
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


def test_throttle_recovers_slowly_after_rate_limit():
    t = Throttle(0.5, {"ms.example.com": 2.0}, clock=lambda: 0, sleep=lambda s: None)
    for _ in range(4):
        t.slow_down("ms.example.com")
    assert t.interval("ms.example.com") == 30.0  # capped
    for _ in range(9):
        t.recover("ms.example.com")
    assert t.interval("ms.example.com") == 30.0  # not yet: needs 10 in a row
    t.recover("ms.example.com")
    assert t.interval("ms.example.com") == 15.0
    for _ in range(100):
        t.recover("ms.example.com")
    assert t.interval("ms.example.com") == 2.0  # never below the host's base


def test_rate_limit_resets_recovery_progress():
    t = Throttle(1.0, {}, clock=lambda: 0, sleep=lambda s: None)
    t.slow_down("a")
    t.slow_down("a")  # 4s
    for _ in range(9):
        t.recover("a")
    t.slow_down("a")  # 8s, and the 9 successes no longer count
    t.recover("a")
    assert t.interval("a") == 8.0


# ---------- connections, Crawl-delay, conditional requests ----------


def test_each_thread_reuses_one_session():
    import threading

    first, again = http._session(), http._session()
    other = []
    t = threading.Thread(target=lambda: other.append(http._session()))
    t.start()
    t.join()
    assert first is again and other[0] is not first


def test_crawl_delay_sets_the_gap_and_one_request_at_a_time(clock, monkeypatch):
    monkeypatch.setattr(
        http, "robots", RobotsCache("t", lambda url: (200, "User-agent: *\nCrawl-delay: 2\n"))
    )
    monkeypatch.setattr(http, "_request", lambda *a, **k: FakeResponse(200))
    for _ in range(3):
        http.get_json("https://api.lever.co/v0/postings/x")
    assert clock.sleeps == [2.0, 2.0]
    assert http.throttle.gates_for("api.lever.co")[-1].limit == 1
    http.throttle.slow_down("api.lever.co")  # a 429 can't bring the gap under the Crawl-delay later
    assert http.throttle.interval("api.lever.co") >= 2.0


def test_a_huge_crawl_delay_skips_the_site(clock, monkeypatch):
    monkeypatch.setattr(
        http, "robots", RobotsCache("t", lambda url: (200, "User-agent: *\nCrawl-delay: 600\n"))
    )
    monkeypatch.setattr(http, "_request", lambda *a, **k: pytest.fail("no request should be sent"))
    with pytest.raises(FetchError, match="600s"):
        http.get_json("https://slow-site.example/jobs")


def test_conditional_request_sends_validators_and_understands_304(clock, monkeypatch):
    sent = []

    def fake(method, url, **kwargs):
        sent.append(kwargs["headers"])
        if kwargs["headers"].get("If-None-Match") == '"v1"':
            return FakeResponse(304, "")
        return FakeResponse(200, '{"jobs": []}', {"ETag": '"v1"'})

    monkeypatch.setattr(http, "_request", fake)
    url = "https://boards-api.greenhouse.io/v1/boards/x/jobs"
    data, validators = http.get_json_if_changed(url)
    assert data == {"jobs": []} and validators == http.Validators(url, '"v1"', None)
    assert "If-None-Match" not in sent[0]

    data, again = http.get_json_if_changed(url, validators)
    assert data is http.NOT_MODIFIED and again == validators
    assert sent[1]["If-None-Match"] == '"v1"'
    assert http.traffic.by_host["boards-api.greenhouse.io"][2] >= 1  # counted as not modified

    # validators for another URL are never sent
    http.get_json_if_changed(url + "?x=1", validators)
    assert "If-None-Match" not in sent[2]


def test_304_without_asking_is_an_error(clock, monkeypatch):
    monkeypatch.setattr(http, "_request", lambda *a, **k: FakeResponse(304, ""))
    with pytest.raises(FetchError, match="304"):
        http.get_json("https://a.example/jobs")
