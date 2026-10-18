"""Shared HTTP layer for every adapter.

Every request goes through `_send`, so every adapter automatically gets:

  * a robots.txt check: requests a site disallows are never sent
  * per-host throttling: a minimum gap between requests to the same host
  * rate-limit handling: on HTTP 429 the host's gap doubles, and the
    server's Retry-After header is honoured when present
  * retries with exponential backoff and jitter on network errors and 5xx
  * an identifying User-Agent with a contact URL (set GHOSTLESS_CONTACT)
  * optional dumping of raw responses for debugging parsers (`--dump`)
"""

from __future__ import annotations

import email.utils
import logging
import os
import random
import re
import time
from collections.abc import Callable
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
}

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

    def interval(self, host: str) -> float:
        return self.intervals.get(host, self.default)

    def wait(self, host: str) -> None:
        last = self._last.get(host)
        if last is not None:
            remaining = self.interval(host) - (self.clock() - last)
            if remaining > 0:
                self.sleep(remaining)
        self._last[host] = self.clock()

    def slow_down(self, host: str) -> float:
        """Double the host's interval after a rate limit, and return it."""
        new = min(max(self.interval(host) * 2, 1.0), MAX_INTERVAL_SECONDS)
        self.intervals[host] = new
        self._successes[host] = 0
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


def _fetch_robots(url: str) -> tuple[int, str]:
    try:
        resp = requests.get(url, timeout=TIMEOUT_SECONDS, headers={"User-Agent": USER_AGENT})
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


def _send(method: str, url: str, payload: dict | None, accept: str) -> requests.Response:
    if not robots.allowed(url):
        raise FetchError(f"blocked by robots.txt: {url}")
    host = urlsplit(url).netloc
    headers = {"User-Agent": USER_AGENT, "Accept": accept}

    for attempt in range(1, MAX_ATTEMPTS + 1):
        throttle.wait(host)
        try:
            resp = requests.request(method, url, json=payload, timeout=TIMEOUT_SECONDS, headers=headers)
        except requests.RequestException as exc:
            reason, wait = f"network error: {exc}", _backoff(attempt)
        else:
            status = resp.status_code
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
