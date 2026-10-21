"""Bulk seeding from Common Crawl's URL index (stage B2), read from the copy on
Hugging Face, which allows crawling. Common Crawl's own hosts are never used.

Monthly, from the discover.yml workflow only (needs the optional `index`
extra, pyarrow; ingest and the API never import this module):

1. find the latest crawl in the mirror;
2. for each of its index files (Parquet, sorted by URL in SURT form, e.g.
   "co,lever,jobs)/acme/123"), read only the footer, whose row-group
   statistics say which slice of URLs each row group holds;
3. download the URL column of the few row groups that can hold job board
   URLs (Greenhouse, Lever, Ashby, Workday), with range requests;
4. turn those URLs into boards, and register the new ones as candidates.
   They're checked (one request each, GHOSTLESS_VERIFY_PER_RUN a run) before
   anything is read from them, like the boards links lead to.

Every request goes through `http`, so robots.txt and the host's pace apply.
"""

from __future__ import annotations

import io
import logging
from collections import Counter
from datetime import datetime, timedelta, timezone

from tracker.discovery.boards import board_from_url
from tracker.sources import http
from tracker.sources.http import FetchError

log = logging.getLogger("tracker.discovery")

MIRROR = "https://huggingface.co/buckets/commoncrawl/commoncrawl/resolve/"
# Index URLs in SURT form: hosts reversed, lowercase. The table is sorted on it,
# so each of these is one contiguous slice.
PREFIXES = (
    "co,lever,jobs)/",
    "com,ashbyhq,jobs)/",
    "com,myworkdayjobs,",
    "io,greenhouse,boards)/",
    "io,greenhouse,job-boards)/",
    "io,greenhouse,eu,boards)/",
    "io,greenhouse,eu,job-boards)/",
)
# the stage E hiring systems, searched for only when switched on (GHOSTLESS_SOURCES)
NEW_SOURCE_PREFIXES = {
    "workable": ("com,workable,",),
    "teamtailor": ("com,teamtailor,",),
    "personio": ("de,personio,jobs,", "com,personio,jobs,"),
    "breezy": ("hr,breezy,",),
    "rippling": ("com,rippling,ats)/",),
    "recruitee": ("com,recruitee,",),
    "smartrecruiters": ("com,smartrecruiters,jobs)/", "com,smartrecruiters,careers)/"),
}


def prefixes() -> tuple[str, ...]:
    from tracker import settings

    extra = [p for name in sorted(settings.sources()) for p in NEW_SOURCE_PREFIXES[name]]
    return PREFIXES + tuple(extra)


READ_BLOCK = 1 << 16  # small reads (footers) are fetched in blocks of this size


def surt_to_url(surt: str) -> str | None:
    """'co,lever,jobs)/acme/123' -> 'https://jobs.lever.co/acme/123'."""
    host, sep, path = surt.partition(")")
    if not sep:
        return None
    host = host.split(":", 1)[0]  # a port, if any
    return "https://" + ".".join(reversed(host.split(","))) + path


def overlaps(low: str | None, high: str | None, prefixes=PREFIXES) -> bool:
    """Can a row group whose keys run from `low` to `high` hold any key with one of these prefixes?"""
    if low is None or high is None:
        return True  # no statistics: read it to be safe
    return any(low <= prefix + "￿" and high >= prefix for prefix in prefixes)


def wanted(surt: str, prefixes=PREFIXES) -> bool:
    return surt.startswith(prefixes)


class RangeFile(io.RawIOBase):
    """A remote file read with range requests, for pyarrow. Small reads are
    rounded up to a block and cached, so a footer costs one or two requests."""

    def __init__(self, url: str):
        super().__init__()
        self.url = url
        self.pos = 0
        self.size = http.get_range(url, 0, 0)[1]
        self._block: tuple[int, bytes] = (-1, b"")

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return True

    def tell(self) -> int:
        return self.pos

    def seek(self, offset: int, whence: int = 0) -> int:
        base = {0: 0, 1: self.pos, 2: self.size}[whence]
        self.pos = max(0, base + offset)
        return self.pos

    def readinto(self, buffer) -> int:
        want = min(len(buffer), self.size - self.pos)
        if want <= 0:
            return 0
        start, block = self._block
        if not (start <= self.pos and self.pos + want <= start + len(block)):
            first = self.pos if want >= READ_BLOCK else max(0, min(self.pos, self.size - READ_BLOCK))
            block, _ = http.get_range(self.url, first, min(self.size, first + max(want, READ_BLOCK)) - 1)
            start = first
            self._block = (start, block)
        chunk = block[self.pos - start : self.pos - start + want]
        buffer[: len(chunk)] = chunk
        self.pos += len(chunk)
        return len(chunk)


def crawl_ids(today: datetime | None = None, weeks: int = 20) -> list[str]:
    """Crawl names to look for, newest first: Common Crawl names crawls CC-MAIN-<year>-<ISO week>."""
    today = today or datetime.now(timezone.utc)
    ids = []
    for back in range(weeks):
        year, week, _ = (today - timedelta(weeks=back)).isocalendar()
        ids.append(f"CC-MAIN-{year}-{week:02d}")
    return ids


def latest_crawl() -> tuple[str, list[str]]:
    """The newest crawl in the mirror, and its index files (the 'warc' subset)."""
    import gzip

    for crawl in crawl_ids():
        try:
            data = http.get_bytes(f"{MIRROR}crawl-data/{crawl}/cc-index-table.paths.gz")
        except FetchError:
            continue
        files = [p for p in gzip.decompress(data).decode().split() if "/subset=warc/" in p]
        if files:
            return crawl, [MIRROR + p for p in files]
    raise FetchError("no recent crawl found in the Common Crawl mirror")


def board_urls_in(url: str, prefixes=PREFIXES) -> tuple[list[str], int, int]:
    """Job board URLs in one index file: (urls, row groups read, row groups in the file)."""
    import pyarrow.parquet as pq  # the optional `index` extra

    source = RangeFile(url)
    parquet = pq.ParquetFile(source)
    names = parquet.schema_arrow.names
    column = names.index("url_surtkey")
    found: list[str] = []
    read = 0
    for group in range(parquet.metadata.num_row_groups):
        stats = parquet.metadata.row_group(group).column(column).statistics
        low = stats.min if stats is not None and stats.has_min_max else None
        high = stats.max if stats is not None and stats.has_min_max else None
        if not overlaps(low, high, prefixes):
            continue
        read += 1
        keys = parquet.read_row_group(group, columns=["url_surtkey"]).column(0).to_pylist()
        for key in keys:
            if key and wanted(key, prefixes):
                link = surt_to_url(key)
                if link:
                    found.append(link)
    return found, read, parquet.metadata.num_row_groups


def find_boards(files: list[str], limit_files: int | None = None) -> tuple[dict[tuple[str, str], str], dict]:
    """{(platform, slug): a job link on it} across the index files, and counts."""
    boards: dict[tuple[str, str], str] = {}
    counts = Counter()
    wanted = prefixes()
    for url in files[:limit_files] if limit_files else files:
        try:
            links, read, groups = board_urls_in(url, wanted)
        except (FetchError, OSError) as exc:
            log.warning("index file %s unreadable: %s", url.rsplit("/", 1)[-1], exc)
            counts["files_failed"] += 1
            continue
        counts["files"] += 1
        counts["row_groups"] += groups
        counts["row_groups_read"] += read
        counts["urls"] += len(links)
        for link in links:
            board = board_from_url(link)
            if board:
                key = (board[0], board[1].lower())
                boards.setdefault(key, link)
    return boards, dict(counts)
