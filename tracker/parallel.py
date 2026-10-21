"""Run work for many companies at once without being any less polite.

Companies are grouped by the website they're fetched from (every Greenhouse
board is one site; each Workday employer is its own). Groups run side by
side; within a group, companies run one after another, except on the public
job-board APIs (Greenhouse, Lever, Ashby), where a group is split into as many
lanes as that API allows requests at once. The HTTP layer enforces the real
limits per host and per Workday server cluster (tracker.sources.http), so
this module only decides what can overlap; it can never make a site see more
than its limit.
"""

from __future__ import annotations

import logging
import os
import zlib
from collections import defaultdict
from collections.abc import Callable, Iterable, Iterator
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import TypeVar

from tracker.models import Company

log = logging.getLogger("tracker.parallel")

T = TypeVar("T")
R = TypeVar("R")

DEFAULT_WORKERS = 16  # threads; the per-site limits in the HTTP layer decide the load

# the host behind each shared-API platform, for its request limit
PLATFORM_HOSTS = {
    "greenhouse": "boards-api.greenhouse.io",
    "lever": "api.lever.co",
    "lever-eu": "api.eu.lever.co",
    "ashby": "api.ashbyhq.com",
    "workable": "apply.workable.com",
    "rippling": "api.rippling.com",
    "smartrecruiters": "jobs.smartrecruiters.com",
}


def workers() -> int:
    try:
        return max(1, min(32, int(os.environ.get("GHOSTLESS_WORKERS", DEFAULT_WORKERS))))
    except ValueError:
        return DEFAULT_WORKERS


def site_of(company: Company) -> str:
    """The website a company's postings come from, as far as pacing goes."""
    slug = company.board_slug.lower()
    first = slug.split("/", 1)[0]
    if "." in first:  # slugs that are hosts: Workday, Eightfold, feeds and sitemaps
        return first
    if company.platform == "lever" and first == "eu":  # Lever's EU instance has its own API
        return "lever-eu"
    return company.platform  # one shared API: Greenhouse, Lever, Ashby, Amazon, Google, Apple


def lanes(site: str) -> int:
    """How many companies of one site can be in flight at once."""
    from tracker.sources.http import HOST_CONCURRENCY

    return HOST_CONCURRENCY.get(PLATFORM_HOSTS.get(site, site), 1)


def run_by_site(
    items: Iterable[T], site: Callable[[T], str], work: Callable[[T], R], max_workers: int | None = None
) -> Iterator[tuple[T, R | BaseException]]:
    """(item, result or the exception it raised), as each finishes."""
    by_site: dict[str, list[T]] = defaultdict(list)
    for item in items:
        by_site[site(item)].append(item)
    groups: dict[str, list[T]] = {}
    for name, members in by_site.items():
        count = max(1, min(lanes(name), len(members)))
        for lane in range(count):  # round robin, so each lane gets a mix of big and small boards
            groups[f"{name}#{lane}"] = members[lane::count]

    def run_group(group: list[T]) -> list[tuple[T, R | BaseException]]:
        out: list[tuple[T, R | BaseException]] = []
        for item in group:
            try:
                out.append((item, work(item)))
            except Exception as exc:  # noqa: BLE001 - reported by the caller, per item
                out.append((item, exc))
        return out

    size = max_workers or workers()
    if size == 1 or len(groups) <= 1:
        for group in groups.values():
            yield from run_group(group)
        return
    # biggest groups first, so the longest queue starts right away
    ordered = sorted(groups.values(), key=len, reverse=True)
    with ThreadPoolExecutor(max_workers=size, thread_name_prefix="site") as pool:
        futures = [pool.submit(run_group, group) for group in ordered]
        for future in as_completed(futures):
            yield from future.result()


# ---------- splitting a run across machines ----------


def parse_shard(value: str | None) -> tuple[int, int] | None:
    """ "2/4" -> (2, 4): the second of four machines."""
    if not value:
        return None
    try:
        part, total = (int(x) for x in value.split("/"))
    except ValueError:
        raise SystemExit(f"--shard takes the form 2/4, not {value!r}") from None
    if not 1 <= part <= total <= 64:
        raise SystemExit(f"--shard {value}: the part must be between 1 and the total (at most 64)")
    return part, total


def shard_key(company: Company) -> str:
    """What must stay together on one machine: a site, so its own limits
    hold. The public job-board APIs are built for this traffic, so their boards
    are spread out one by one. Workday employers are spread out too: each
    machine still caps what it sends to each Workday server cluster, and those
    clusters serve thousands of companies."""
    site = site_of(company)
    if site in PLATFORM_HOSTS:
        return f"{site}:{company.board_slug.lower()}"
    return site


def in_shard(company: Company, shard: tuple[int, int] | None) -> bool:
    if shard is None:
        return True
    part, total = shard
    return zlib.crc32(shard_key(company).encode()) % total == part - 1
