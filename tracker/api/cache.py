"""What the resume endpoints keep in memory between requests.

Neon caps how much is read out of the database each month, and the postings
only change when an ingest runs. So each API process keeps:

- one copy of the matching pool (every open tech posting), narrowed per
  request by location and ghost risk (queries.in_pool);
- the descriptions it has read, by job id, up to MAX_DESCRIPTIONS.

Both are dropped when the data changes: a part of the ingest finishes
(ingest_runs) or the signals are refreshed, which `finish` does after saving
the job lists' postings. That's checked at most every CHECK_SECONDS, with a
query that returns one row.
"""

from __future__ import annotations

import threading
import time
from collections import OrderedDict

import psycopg

from tracker.api import queries

CHECK_SECONDS = 60
MAX_DESCRIPTIONS = 4000  # about 15 MB of text at Ghostless's average posting

_lock = threading.Lock()
_load = threading.Lock()  # one pool load at a time
_version: tuple | None = None
_checked = 0.0
_pool: list[dict] | None = None
_texts: OrderedDict[int, str | None] = OrderedDict()


def reset() -> None:
    global _version, _checked, _pool
    with _lock:
        _version, _checked, _pool = None, 0.0, None
        _texts.clear()


def _refresh(conn: psycopg.Connection) -> None:
    """Drop everything cached if an ingest has finished since it was read."""
    global _version, _checked, _pool
    now = time.monotonic()
    if _version is not None and now - _checked < CHECK_SECONDS:
        return
    version = tuple(
        conn.execute(
            "SELECT (SELECT max(finished_at) FROM ingest_runs), (SELECT max(computed_at) FROM job_signals_mv)"
        ).fetchone()
    )
    with _lock:
        if version != _version:
            _pool = None
            _texts.clear()
            _version = version
        _checked = now


def job_pool(conn: psycopg.Connection, location: str = "any", include_high_risk: bool = False) -> list[dict]:
    """The open tech postings for resume matching, from the shared copy."""
    global _pool
    _refresh(conn)
    pool = _pool
    if pool is None:
        with _load:
            pool = _pool
            if pool is None:  # nobody loaded it while this request waited
                pool = queries.matching_pool(conn, "any", include_high_risk=True)
                with _lock:
                    _pool = pool
    return [job for job in pool if queries.in_pool(job, location, include_high_risk)]


def descriptions(conn: psycopg.Connection, job_ids: list[int]) -> dict[int, str]:
    """queries.descriptions, reading only the ones not read since the last ingest."""
    _refresh(conn)
    result: dict[int, str] = {}
    missing: list[int] = []
    with _lock:
        for job_id in dict.fromkeys(job_ids):
            if job_id in _texts:
                _texts.move_to_end(job_id)  # recently used: kept longest
                if _texts[job_id] is not None:
                    result[job_id] = _texts[job_id]
            else:
                missing.append(job_id)
    if missing:
        found = queries.descriptions(conn, missing)
        result.update(found)
        with _lock:
            for job_id in missing:
                _texts[job_id] = found.get(job_id)  # None: no description, remembered too
            while len(_texts) > MAX_DESCRIPTIONS:
                _texts.popitem(last=False)
    return result
