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
    assert site_of(c("lever", "acme")) == "lever" and site_of(c("lever", "eu/acme")) == "lever-eu"


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

    monkeypatch.setattr(http, "_request", fake_request)
    urls = [f"https://{host}/jobs/{i}" for host in ("a.example", "b.example") for i in range(8)]
    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(http.get_json, urls))
    elapsed = time.perf_counter() - started
    assert most == {"a.example": 1, "b.example": 1}
    # 8 requests per host at 20 ms each: about 0.16 s when the two hosts overlap, 0.32 s if not
    assert elapsed < 0.3


@pytest.mark.parametrize("value, expected", [("4", 4), ("0", 1), ("100", 32), ("x", 16)])
def test_worker_count_comes_from_the_environment(monkeypatch, value, expected):
    from tracker.parallel import workers

    monkeypatch.setenv("GHOSTLESS_WORKERS", value)
    assert workers() == expected


def _count_in_flight(monkeypatch, urls, response_status=200):
    """Send `urls` from 24 threads; return the most requests in flight per host and per Workday cluster."""
    monkeypatch.setattr(http.robots, "allowed", lambda url: True)
    monkeypatch.setattr(http, "throttle", http.Throttle(0.0, {}))
    in_flight: dict[str, int] = {}
    most: dict[str, int] = {}
    lock = threading.Lock()

    class Response:
        status_code = response_status
        headers: dict = {}
        text = "{}"

        def json(self):
            return {}

    def bump(key, by):
        with lock:
            in_flight[key] = in_flight.get(key, 0) + by
            most[key] = max(most.get(key, 0), in_flight[key])

    def fake_request(method, url, **kwargs):
        host = url.split("/")[2]
        cluster = http.cluster_of(host)
        bump(host, 1)
        if cluster:
            bump(cluster, 1)
        time.sleep(0.02)
        bump(host, -1)
        if cluster:
            bump(cluster, -1)
        return Response()

    monkeypatch.setattr(http, "_request", fake_request)
    with ThreadPoolExecutor(max_workers=24) as pool:
        list(pool.map(lambda u: http.get_json(u), urls))
    return most


def test_job_board_apis_get_a_few_requests_at_once_and_other_sites_one(monkeypatch):
    urls = [f"https://boards-api.greenhouse.io/v1/boards/b{i}/jobs" for i in range(20)]
    urls += [f"https://careers.example.com/jobs/{i}" for i in range(8)]
    most = _count_in_flight(monkeypatch, urls)
    assert most["boards-api.greenhouse.io"] == http.HOST_CONCURRENCY["boards-api.greenhouse.io"]
    assert most["careers.example.com"] == 1


def test_workday_employers_on_one_cluster_share_a_limit(monkeypatch):
    tenants = [f"bank{i}.wd3.myworkdayjobs.com" for i in range(10)]
    urls = [f"https://{t}/wday/cxs/{t.split('.')[0]}/site/job/{j}" for t in tenants for j in range(3)]
    most = _count_in_flight(monkeypatch, urls)
    assert most["wd3.myworkdayjobs.com"] == http.WORKDAY_CLUSTER_CONCURRENCY
    assert max(most[t] for t in tenants) == 1  # and still one at a time per employer


def test_a_rate_limit_halves_requests_at_once():
    throttle = http.Throttle(0.0, {}, sleep=lambda s: None)
    gate = throttle.gates_for("boards-api.greenhouse.io")[-1]
    assert gate.limit == 4
    throttle.slow_down("boards-api.greenhouse.io")
    assert gate.limit == 2
    throttle.slow_down("boards-api.greenhouse.io")
    throttle.slow_down("boards-api.greenhouse.io")
    assert gate.limit == 1


def test_shared_api_companies_run_in_lanes():
    from tracker.parallel import lanes

    assert lanes("greenhouse") == 4 and lanes("ashby") == 2 and lanes("td.wd3.myworkdayjobs.com") == 1
    active = {"now": 0, "most": 0}
    lock = threading.Lock()

    def work(item):
        with lock:
            active["now"] += 1
            active["most"] = max(active["most"], active["now"])
        time.sleep(0.03)
        with lock:
            active["now"] -= 1
        return item

    boards = [Company(name=f"b{i}", platform="greenhouse", board_slug=f"b{i}") for i in range(12)]
    results = list(run_by_site(boards, site_of, work, max_workers=16))
    assert len(results) == 12
    assert active["most"] == 4


def test_shards_split_the_work_without_splitting_a_site():
    from tracker.parallel import in_shard, parse_shard

    assert parse_shard("2/4") == (2, 4) and parse_shard(None) is None
    for bad in ("0/4", "5/4", "x", "1/100"):
        with pytest.raises(SystemExit):
            parse_shard(bad)

    companies = [Company(f"gh{i}", "greenhouse", f"gh{i}") for i in range(200)]
    companies += [Company(f"bank{i}", "workday", f"bank{i}.wd3.myworkdayjobs.com/Careers") for i in range(12)]
    companies += [Company("Amazon", "amazon", "x"), Company("Google", "google", "y")]
    parts = [[c for c in companies if in_shard(c, (k, 4))] for k in range(1, 5)]
    assert sorted(c.name for part in parts for c in part) == sorted(c.name for c in companies)  # each once
    # each Workday employer stays on one machine, and they're spread over machines
    assert sum(any(c.platform == "workday" for c in part) for part in parts) > 1
    for c in companies:
        assert sum(in_shard(c, (k, 4)) for k in range(1, 5)) == 1
    # Greenhouse boards are spread over every machine, roughly evenly
    counts = [sum(c.platform == "greenhouse" for c in part) for part in parts]
    assert min(counts) > 30
