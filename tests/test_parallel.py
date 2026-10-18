"""Running companies in parallel must never mean more than one request at a time to a site."""

import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from tracker.models import Company
from tracker.parallel import run_by_site, site_of
from tracker.sources import http


def test_companies_are_grouped_by_the_site_they_come_from():
    def c(platform, slug):
        return Company(name=slug, platform=platform, board_slug=slug)

    assert site_of(c("greenhouse", "stripe")) == site_of(c("greenhouse", "airbnb")) == "greenhouse"
    assert site_of(c("workday", "td.wd3.myworkdayjobs.com/TD_Bank_Careers")) == "td.wd3.myworkdayjobs.com"
    assert site_of(c("workday", "rbc.wd3.myworkdayjobs.com/RBC")) != site_of(
        c("workday", "td.wd3.myworkdayjobs.com/x")
    )


def test_groups_run_side_by_side_and_items_in_a_group_one_by_one():
    active: dict[str, int] = {}
    most: dict[str, int] = {}
    overall = {"now": 0, "most": 0}
    lock = threading.Lock()

    def work(item):
        site, _ = item
        with lock:
            active[site] = active.get(site, 0) + 1
            most[site] = max(most.get(site, 0), active[site])
            overall["now"] += 1
            overall["most"] = max(overall["most"], overall["now"])
        time.sleep(0.05)
        with lock:
            active[site] -= 1
            overall["now"] -= 1
        if item == ("b", 1):
            raise ValueError("boom")
        return item[1] * 10

    items = [(site, i) for site in "abcd" for i in range(3)]
    results = dict(run_by_site(items, lambda item: item[0], work, max_workers=4))
    assert len(results) == 12
    assert isinstance(results[("b", 1)], ValueError)  # one failure doesn't stop the rest
    assert results[("c", 2)] == 20
    assert max(most.values()) == 1  # never two items of one site at once
    assert overall["most"] > 1  # but different sites did overlap


def test_one_host_never_gets_two_requests_at_once(monkeypatch):
    monkeypatch.setattr(http.robots, "allowed", lambda url: True)
    monkeypatch.setattr(http, "throttle", http.Throttle(0.0, {}))
    in_flight: dict[str, int] = {}
    most: dict[str, int] = {}
    lock = threading.Lock()

    class Response:
        status_code = 200
        headers: dict = {}
        text = "{}"

        def json(self):
            return {}

    def fake_request(method, url, **kwargs):
        host = url.split("/")[2]
        with lock:
            in_flight[host] = in_flight.get(host, 0) + 1
            most[host] = max(most.get(host, 0), in_flight[host])
        time.sleep(0.02)
        with lock:
            in_flight[host] -= 1
        return Response()

    monkeypatch.setattr(http.requests, "request", fake_request)
    urls = [f"https://{host}/jobs/{i}" for host in ("a.example", "b.example") for i in range(8)]
    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(http.get_json, urls))
    elapsed = time.perf_counter() - started
    assert most == {"a.example": 1, "b.example": 1}
    # 8 requests per host at 20 ms each: about 0.16 s when the two hosts overlap, 0.32 s if not
    assert elapsed < 0.3


@pytest.mark.parametrize("value, expected", [("4", 4), ("0", 1), ("100", 32), ("x", 8)])
def test_worker_count_comes_from_the_environment(monkeypatch, value, expected):
    from tracker.parallel import workers

    monkeypatch.setenv("GHOSTLESS_WORKERS", value)
    assert workers() == expected
