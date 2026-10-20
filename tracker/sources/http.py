"""Shared HTTP layer for every adapter.

Every request goes through `_send`, so every adapter automatically gets:

  * a robots.txt check: requests a site disallows are never sent, and a
    site's Crawl-delay becomes its minimum gap, one request at a time
  * per-host throttling: a minimum gap between requests to the same host,
    and a cap on requests in flight at once: one for most sites, a few for
    the public job-board APIs built for this (Greenhouse, Lever, Ashby), and a
    shared cap for Workday employers on the same Workday server cluster
  * rate-limit handling: on HTTP 429 the host's gap doubles, and the
    server's Retry-After header is honoured when present
  * retries with exponential backoff and jitter on network errors and 5xx
  * an identifying User-Agent with a contact URL (set GHOSTLESS_CONTACT)
  * one pooled connection per thread and host (keep-alive), so repeated
    requests to a site skip the TCP and TLS handshake
  * conditional requests (`get_json_if_changed`): a site that answers 304
    Not Modified sends no body, and the caller knows nothing changed
  * optional dumping of raw responses for debugging parsers (`--dump`)
"""

from __future__ import annotations

import email.utils
import logging
import os
import random
import re
import threading
import time
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import requests

from tracker import __version__
from tracker.sources.robots import RobotsCache

log = logging.getLogger(__name__)

TIMEOUT_SECONDS = 20
MAX_ATTEMPTS = 5
BACKOFF_BASE_SECONDS = 2.0
MAX_RETRY_AFTER_SECONDS = 120.0

DEFAULT_INTERVAL_SECONDS = 0.5  # minimum gap between requests to one host
MAX_INTERVAL_SECONDS = 30.0
HOST_INTERVALS = {  # slower hosts, set from observed rate limits
    "apply.careers.microsoft.com": 2.0,
    "jobs.apple.com": 1.0,
    "www.google.com": 1.0,
    # public job-board APIs: several requests at once, each answer can take seconds
    "boards-api.greenhouse.io": 0.25,
    "api.lever.co": 1.0,  # its robots.txt asks for Crawl-delay: 1
    "api.ashbyhq.com": 0.5,
}
# Requests in flight at once per host (default 1). These are the public APIs
# ATS vendors publish for job boards; aggregators covering 20,000+ companies
# run tens of requests at once against them. A few is still very gentle.
HOST_CONCURRENCY = {
    "boards-api.greenhouse.io": 4,
    "api.lever.co": 1,  # Crawl-delay means one at a time
    "api.ashbyhq.com": 2,
}
# A site asking for more than this between requests is skipped for the run:
# honouring it would hold a worker for hours.
MAX_CRAWL_DELAY_SECONDS = 30.0
# Each Workday employer has its own host, but they share a few server clusters
# (the wd1, wd3, wd5 ... in the address). Cap what's in flight per cluster too.
_WORKDAY_CLUSTER = re.compile(r"^[^.]+\.(wd\d+\.myworkdayjobs\.com)$", re.I)
WORKDAY_CLUSTER_CONCURRENCY = 4

DEFAULT_CONTACT = "https://github.com/Haider425/ghostless"


class FetchError(Exception):
    pass


def _build_user_agent() -> str:
    # JOB_TRACKER_CONTACT is the pre-rename name, still honoured.
    contact = (
        os.environ.get("GHOSTLESS_CONTACT", "").strip()
        or os.environ.get("JOB_TRACKER_CONTACT", "").strip()
        or DEFAULT_CONTACT
    )
    return f"ghostless/{__version__} (+{contact})"


USER_AGENT = _build_user_agent()


RECOVER_AFTER_SUCCESSES = 10


class Gate:
    """A counting semaphore whose limit can shrink (after rate limits)."""

    def __init__(self, limit: int):
        self.limit = max(1, limit)
        self.in_use = 0
        self._cond = threading.Condition()

    def acquire(self) -> None:
        with self._cond:
            while self.in_use >= self.limit:
                self._cond.wait()
            self.in_use += 1

    def release(self) -> None:
        with self._cond:
            self.in_use -= 1
            self._cond.notify_all()

    def shrink(self) -> None:
        with self._cond:
            self.limit = max(1, self.limit // 2)

    def cap(self, limit: int) -> None:
        with self._cond:
            self.limit = max(1, min(self.limit, limit))


def cluster_of(host: str) -> str | None:
    match = _WORKDAY_CLUSTER.match(host)
    return match.group(1).lower() if match else None


class Throttle:
    """Keeps a minimum interval between requests to the same host.

    Rate limits push a host's interval up fast (doubling on each 429) and
    successes bring it back down slowly (halving after every 10 successful
    requests in a row, never below the host's configured base). This is the
    usual "back off fast, recover slowly" pattern, so one burst of 429s does
    not slow a host down for the rest of the run.
    """

    def __init__(
        self,
        default: float,
        overrides: dict[str, float],
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.default = default
        self.base = dict(overrides)
        self.intervals = dict(overrides)
        self.clock = clock
        self.sleep = sleep
        self._last: dict[str, float] = {}
        self._successes: dict[str, int] = {}
        self._gates: dict[str, Gate] = {}
        self._crawl_delays: dict[str, float] = {}
        self._guard = threading.Lock()

    def gate(self, key: str, limit: int) -> Gate:
        with self._guard:
            gate = self._gates.get(key)
            if gate is None:
                gate = self._gates[key] = Gate(limit)
            return gate

    def gates_for(self, host: str) -> list[Gate]:
        """The gates a request to `host` must pass, always in the same order (no deadlocks)."""
        gates = []
        cluster = cluster_of(host)
        if cluster:
            gates.append(self.gate(f"cluster:{cluster}", WORKDAY_CLUSTER_CONCURRENCY))
        gates.append(self.gate(f"host:{host}", HOST_CONCURRENCY.get(host, 1)))
        return gates

    def interval(self, host: str) -> float:
        return self.intervals.get(host, self.default)

    def respect_crawl_delay(self, host: str, delay: float | None) -> None:
        """A robots.txt Crawl-delay: at least that gap between requests, one at a time."""
        if not delay or host in self._crawl_delays:
            return
        with self._guard:
            if host in self._crawl_delays:
                return
            self._crawl_delays[host] = delay
            self.base[host] = max(self.base.get(host, self.default), delay)
            self.intervals[host] = max(self.intervals.get(host, self.default), delay)
        self.gates_for(host)[-1].cap(1)  # the host's own gate, not its Workday cluster's

    def wait(self, host: str) -> None:
        """Wait for this host's next start slot. Slots are handed out under a
        lock, so requests running at once still keep the minimum gap."""
        with self._guard:
            now = self.clock()
            last = self._last.get(host)
            start = now if last is None else max(now, last + self.interval(host))
            self._last[host] = start
        if start > now:
            self.sleep(start - now)

    def slow_down(self, host: str) -> float:
        """Double the host's interval after a rate limit, and return it."""
        ceiling = max(MAX_INTERVAL_SECONDS, self.base.get(host, 0.0))  # never below a Crawl-delay
        new = min(max(self.interval(host) * 2, 1.0), ceiling)
        self.intervals[host] = new
        self._successes[host] = 0
        for gate in self.gates_for(host):  # and fewer requests at once, for the rest of the run
            gate.shrink()
        return new

    def recover(self, host: str) -> None:
        """Record a successful request; ease off a raised interval over time."""
        base = self.base.get(host, self.default)
        current = self.interval(host)
        if current <= base:
            return
        self._successes[host] = self._successes.get(host, 0) + 1
        if self._successes[host] >= RECOVER_AFTER_SUCCESSES:
            self.intervals[host] = max(base, current / 2)
            self._successes[host] = 0


throttle = Throttle(DEFAULT_INTERVAL_SECONDS, HOST_INTERVALS)

# Set by the CLI's --dump flag: every successful response body is saved here.
dump_dir: Path | None = None
_dump_count = 0


_local = threading.local()


def _session() -> requests.Session:
    """This thread's session: pooled keep-alive connections. Its own retries
    stay off (requests' default); `_send_locked` does the retrying."""
    session = getattr(_local, "session", None)
    if session is None:
        session = _local.session = requests.Session()
    return session


def _request(method: str, url: str, **kwargs: Any) -> requests.Response:
    return _session().request(method, url, **kwargs)


class Traffic:
    """Requests, bytes received and 304 answers per host, for the run summary."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.by_host: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])

    def record(self, host: str, resp: requests.Response) -> None:
        with self._lock:
            row = self.by_host[host]
            row[0] += 1
            row[1] += len(getattr(resp, "content", None) or b"")
            row[2] += int(resp.status_code == 304)


traffic = Traffic()


def _fetch_robots(url: str) -> tuple[int, str]:
    try:
        resp = _request("GET", url, timeout=TIMEOUT_SECONDS, headers={"User-Agent": USER_AGENT})
        return resp.status_code, resp.text
    except requests.RequestException:
        return 0, ""


robots = RobotsCache(USER_AGENT, _fetch_robots)


def parse_retry_after(value: str | None, now: datetime | None = None) -> float | None:
    """Retry-After is either a number of seconds or an HTTP date."""
    if not value:
        return None
    value = value.strip()
    if value.isdigit():
        return min(float(value), MAX_RETRY_AFTER_SECONDS)
    try:
        when = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    seconds = (when - (now or datetime.now(timezone.utc))).total_seconds()
    return min(max(seconds, 0.0), MAX_RETRY_AFTER_SECONDS)


def _backoff(attempt: int) -> float:
    return BACKOFF_BASE_SECONDS * 2 ** (attempt - 1) + random.uniform(0, 1)


def _dump(url: str, resp: requests.Response) -> None:
    global _dump_count
    if dump_dir is None:
        return
    _dump_count += 1
    parts = urlsplit(url)
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", f"{parts.netloc}{parts.path}")[:120].strip("_")
    kind = resp.headers.get("Content-Type", "")
    ext = "json" if "json" in kind else "xml" if "xml" in kind else "html"
    dump_dir.mkdir(parents=True, exist_ok=True)
    path = dump_dir / f"{_dump_count:04d}_{name}.{ext}"
    path.write_text(resp.text, encoding="utf-8")
    log.info("saved response to %s", path)


def _send(
    method: str, url: str, payload: dict | None, accept: str, extra: dict[str, str] | None = None
) -> requests.Response:
    host = urlsplit(url).netloc
    gates = throttle.gates_for(host)
    for gate in gates:
        gate.acquire()
    try:
        return _send_locked(method, url, payload, {"Accept": accept, **(extra or {})}, host)
    finally:
        for gate in reversed(gates):
            gate.release()


def _send_locked(
    method: str, url: str, payload: dict | None, extra: dict[str, str], host: str
) -> requests.Response:
    # inside the gates, so even robots.txt fetches respect the host and cluster limits
    if not robots.allowed(url):
        raise FetchError(f"blocked by robots.txt: {url}")
    delay = robots.crawl_delay(url)
    if delay and delay > MAX_CRAWL_DELAY_SECONDS:
        raise FetchError(f"robots.txt asks for {delay:.0f}s between requests, skipping {host} this run")
    throttle.respect_crawl_delay(host, delay)  # start slots are spaced by it from here on
    headers = {"User-Agent": USER_AGENT, **extra}
    conditional = "If-None-Match" in headers or "If-Modified-Since" in headers

    for attempt in range(1, MAX_ATTEMPTS + 1):
        throttle.wait(host)
        try:
            resp = _request(method, url, json=payload, timeout=TIMEOUT_SECONDS, headers=headers)
        except requests.RequestException as exc:
            reason, wait = f"network error: {exc}", _backoff(attempt)
        else:
            traffic.record(host, resp)
            status = resp.status_code
            if status == 304 and conditional:
                throttle.recover(host)
                return resp
            if 200 <= status < 300:
                throttle.recover(host)
                _dump(url, resp)
                return resp
            if status == 404:
                raise FetchError(f"not found (404): {url}")
            if status == 429:
                interval = throttle.slow_down(host)
                wait = parse_retry_after(resp.headers.get("Retry-After")) or _backoff(attempt)
                reason = f"rate limited (429); now pacing {host} at {interval:.0f}s per request"
            elif status >= 500:
                reason, wait = f"server error ({status})", _backoff(attempt)
            else:
                raise FetchError(f"HTTP {status}: {url}")

        if attempt == MAX_ATTEMPTS:
            raise FetchError(f"{reason}, gave up after {attempt} attempts: {url}")
        log.warning("%s; retrying in %.0fs (attempt %d of %d)", reason, wait, attempt + 1, MAX_ATTEMPTS)
        throttle.sleep(wait)

    raise FetchError(url)  # unreachable


def request_json(method: str, url: str, payload: dict | None = None) -> Any:
    resp = _send(method, url, payload, "application/json")
    try:
        return resp.json()
    except ValueError as exc:
        raise FetchError(f"invalid JSON from {url}") from exc


def get_json(url: str) -> Any:
    return request_json("GET", url)


def get_text(url: str) -> str:
    return _send("GET", url, None, "text/html,application/xml;q=0.9,*/*;q=0.8").text


# ---------- conditional requests ----------


@dataclass(frozen=True)
class Validators:
    """What a server said identifies the version it sent. Sent back, they let
    an unchanged resource come back as an empty 304."""

    url: str
    etag: str | None = None
    last_modified: str | None = None

    @classmethod
    def of(cls, url: str, resp: requests.Response) -> Validators | None:
        etag, modified = resp.headers.get("ETag"), resp.headers.get("Last-Modified")
        return cls(url, etag, modified) if etag or modified else None

    def headers(self) -> dict[str, str]:
        out = {}
        if self.etag:
            out["If-None-Match"] = self.etag
        if self.last_modified:
            out["If-Modified-Since"] = self.last_modified
        return out


class _NotModified:
    def __repr__(self) -> str:
        return "NOT_MODIFIED"


NOT_MODIFIED: Any = _NotModified()


def get_json_if_changed(url: str, cached: Validators | None = None) -> tuple[Any, Validators | None]:
    """(data, validators to store for next time), or (NOT_MODIFIED, cached)
    when the server says nothing changed since `cached` was stored."""
    extra = cached.headers() if cached and cached.url == url else None
    resp = _send("GET", url, None, "application/json", extra)
    if resp.status_code == 304:
        return NOT_MODIFIED, cached
    try:
        return resp.json(), Validators.of(url, resp)
    except ValueError as exc:
        raise FetchError(f"invalid JSON from {url}") from exc
