"""Run work for many companies at once without being any less polite.

Companies are grouped by the website they're fetched from (every Greenhouse
board is one site; each Workday employer is its own). Groups run side by
side; within a group, companies run one after another. On top of that the
HTTP layer allows one request at a time per host, so no site ever sees more
than it did when everything ran in sequence. Only the waiting overlaps.
"""

from __future__ import annotations

import logging
import os
from collections import defaultdict
from collections.abc import Callable, Iterable, Iterator
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import TypeVar

from tracker.models import Company

log = logging.getLogger("tracker.parallel")

T = TypeVar("T")
R = TypeVar("R")

DEFAULT_WORKERS = 8


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
    return company.platform  # one shared API: Greenhouse, Lever, Ashby, Amazon, Google, Apple


def run_by_site(
    items: Iterable[T], site: Callable[[T], str], work: Callable[[T], R], max_workers: int | None = None
) -> Iterator[tuple[T, R | BaseException]]:
    """(item, result or the exception it raised), as each finishes."""
    groups: dict[str, list[T]] = defaultdict(list)
    for item in items:
        groups[site(item)].append(item)

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
