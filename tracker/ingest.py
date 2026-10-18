"""The ingestion pipeline: fetch, classify, store. Run it with `ghostless ingest`."""

from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timezone

import psycopg

from tracker import db
from tracker.accounts.store import purge_expired
from tracker.classify import enrich
from tracker.config import database_url, load_companies, load_lists, select
from tracker.parallel import in_shard, run_by_site, site_of, workers
from tracker.skills import extract_skills
from tracker.sources import INCREMENTAL_DETAILS, FetchError, fetch_jobs

log = logging.getLogger("tracker.ingest")


WRITE_ATTEMPTS = 2


def _save(dsn: str, company, jobs, run_started: datetime) -> tuple[int, int]:
    """Write one company's jobs in its own short-lived connection.

    Fetching a large employer can take many minutes. Holding one connection
    across that idle time fails on serverless databases such as Neon, which
    suspend after a few idle minutes and drop open connections. A fresh
    connection per company avoids that, and a lost connection is retried
    once (the database wakes on the next connect).
    """
    for attempt in range(1, WRITE_ATTEMPTS + 1):
        try:
            with db.connect(dsn) as conn:  # commits on success, rolls back on error
                company_id = db.upsert_company(conn, company)
                return db.save_company_jobs(conn, company_id, jobs, run_started, close_missing=jobs.complete)
        except psycopg.OperationalError as exc:
            if attempt == WRITE_ATTEMPTS:
                raise
            log.warning("%s: database connection lost (%s); retrying", company.name, exc)
    raise AssertionError("unreachable")


_MULTI_LOCATION = re.compile(r"^\s*\d+\s+locations?\s*$", re.I)


def _stored_details(dsn: str, company) -> dict[str, tuple[str, str]]:
    if company.platform not in INCREMENTAL_DETAILS:
        return {}
    try:
        with db.connect(dsn) as conn:
            return db.stored_details(conn, company)
    except psycopg.Error as exc:  # first run, or the database is waking: fetch everything
        log.warning("%s: could not read stored descriptions (%s)", company.name, exc)
        return {}


def reuse_details(jobs, stored: dict[str, tuple[str, str]]) -> None:
    """Give postings whose description was not fetched this run their stored
    description, and their full location when the listing only says
    "3 Locations"."""
    for job in jobs:
        if job.description or job.external_id not in stored:
            continue
        description, location = stored[job.external_id]
        job.description = description
        if location and (not job.location or _MULTI_LOCATION.match(job.location)):
            job.location = location


def run(only: str | None = None, shard: tuple[int, int] | None = None) -> dict:
    """The whole pipeline, or with `shard` (part, total) one machine's share of
    the companies and discovered boards. Sharded runs leave the job lists,
    signals and clean-up to `finish`, run once after every part is done."""
    companies = [c for c in select(load_companies(), only) if in_shard(c, shard)]
    dsn = database_url()

    run_started = datetime.now(timezone.utc)
    clock = time.perf_counter()
    stats = dict(companies_ok=0, companies_failed=0, jobs_seen=0, jobs_new=0, jobs_closed=0)

    with db.connect(dsn) as conn:
        if shard is None:  # sharded runs start after a single `ghostless migrate`, so parts don't race
            db.apply_schema(conn)
        run_id = db.start_run(conn, run_started)
    if shard:
        log.info("part %d of %d: %d configured companies", shard[0], shard[1], len(companies))

    timings: dict[str, float] = {}
    done = {"count": 0}

    def collect(company) -> tuple[int, int, int] | None:
        """Fetch and save one company: (jobs, new, closed), or None if fetching failed."""
        started = time.perf_counter()
        try:
            return _collect(company, started)
        finally:
            timings[company.name] = time.perf_counter() - started

    def _collect(company, started: float) -> tuple[int, int, int] | None:
        stored = _stored_details(dsn, company)
        try:
            jobs = fetch_jobs(company, known=frozenset(stored))
        except FetchError as exc:
            log.error("%s: fetch failed, skipping (no jobs closed): %s", company.name, exc)
            return None
        reuse_details(jobs, stored)
        for job in jobs:
            enrich(job, extract_skills(f"{job.title} {job.description}"))
        new, closed = _save(dsn, company, jobs, run_started)
        done["count"] += 1
        log.info(
            "[%d/%d] %s: %d jobs (%d new, %d closed) in %.0fs",
            done["count"],
            len(companies),
            company.name,
            len(jobs),
            new,
            closed,
            time.perf_counter() - started,
        )
        return len(jobs), new, closed

    log.info("collecting %d companies, %d sites at a time", len(companies), workers())
    for company, result in run_by_site(companies, site_of, collect):
        if isinstance(result, BaseException):
            stats["companies_failed"] += 1
            log.error(
                "%s: database write failed, nothing saved for this company",
                company.name,
                exc_info=(type(result), result, result.__traceback__),
            )
            continue
        if result is None:
            stats["companies_failed"] += 1
            continue
        seen, new, closed = result
        stats["companies_ok"] += 1
        stats["jobs_seen"] += seen
        stats["jobs_new"] += new
        stats["jobs_closed"] += closed

    slowest = sorted(timings.items(), key=lambda kv: -kv[1])[:5]
    if slowest:
        log.info("slowest: %s", ", ".join(f"{name} {seconds:.0f}s" for name, seconds in slowest))
    log.info("companies done in %.0fs", time.perf_counter() - clock)

    if not only:
        # beyond companies.yaml: public job lists and the boards they lead to
        from tracker.discovery import run as discovery

        try:
            if shard:
                discovery.crawl_boards(dsn, run_started, stats, shard=shard)
            else:
                discovery.run(dsn, select(load_companies(), None), load_lists(), run_started, stats)
        except Exception:
            log.exception("discovery failed; the companies above were still saved")

    stats["duration_seconds"] = round(time.perf_counter() - clock, 2)
    with db.connect(dsn) as conn:
        db.finish_run(conn, run_id, stats)
        if shard is None:
            db.refresh_signals(conn)
            purge_expired(conn)  # old sessions, used email links, analytics past retention
        conn.commit()

    log.info(
        "run complete: %d companies ok, %d failed, %d jobs seen, %d new, %d closed in %.0fs",
        stats["companies_ok"],
        stats["companies_failed"],
        stats["jobs_seen"],
        stats["jobs_new"],
        stats["jobs_closed"],
        stats["duration_seconds"],
    )
    return stats


def finish() -> dict:
    """After every part of a sharded run: read the job lists (registering any
    new boards, saving list-only postings), then refresh the signals and clean
    up. Takes seconds."""
    from tracker.discovery import run as discovery

    dsn = database_url()
    run_started = datetime.now(timezone.utc)
    stats = dict(jobs_seen=0, jobs_new=0, jobs_closed=0)
    discovery.run(dsn, load_companies(), load_lists(), run_started, stats, crawl=False)
    with db.connect(dsn) as conn:
        db.refresh_signals(conn)
        purge_expired(conn)
        conn.commit()
    log.info(
        "finished: %d list companies, %d new and %d closed list postings",
        stats.get("list_companies", 0),
        stats["jobs_new"],
        stats["jobs_closed"],
    )
    return stats


if __name__ == "__main__":  # backwards compatible: python -m tracker.ingest
    from tracker.cli import main

    main(["ingest"])
