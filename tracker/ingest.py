"""The ingestion pipeline: fetch, classify, store. Run it with `ghostless ingest`."""

from __future__ import annotations

import functools
import hashlib
import logging
import re
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import psycopg

from tracker import db, dbtraffic, health
from tracker.accounts.store import purge_expired
from tracker.classify import enrich, keep_relevant
from tracker.config import database_url, load_companies, load_lists, select
from tracker.discovery import snowball
from tracker.models import JobList
from tracker.parallel import in_shard, run_by_site, site_of, workers
from tracker.skills import extract_skills
from tracker.sources import (
    CONDITIONAL,
    INCREMENTAL_DETAILS,
    FetchError,
    complete_descriptions,
    fetch_jobs,
    http,
)
from tracker.sources.boards import board_url
from tracker.sources.http import Validators

log = logging.getLogger("tracker.ingest")


WRITE_ATTEMPTS = 2

# The code that turns a board's response into stored postings. When any of it
# changes, cached validators no longer vouch for what's stored, so every board
# is read in full once (see http_cache in schema.sql).
_RULES_FILES = ("classify.py", "skills.py", "disclosures.py", "text.py", "sources/boards.py")


@functools.cache
def rules_version() -> str:
    digest = hashlib.sha256()
    for name in _RULES_FILES:
        digest.update((Path(__file__).parent / name).read_bytes())
    return digest.hexdigest()[:16]


def board_state(dsn: str, company) -> tuple[Validators | None, dict]:
    """For the public job-board APIs: what to send to ask whether the board
    changed (None reads it in full), and on Greenhouse the stored postings'
    versions, so unchanged ones aren't downloaded again. A full read
    (nothing cached, a week old, or new code) downloads everything."""
    if company.platform == "jsonld":  # career sites: when each page was last read
        try:
            with db.connect(dsn) as conn:
                return None, db.stored_versions(conn, company)
        except psycopg.Error:
            return None, {}
    if company.platform not in CONDITIONAL:
        return None, {}
    try:
        with db.connect(dsn) as conn:
            cached = db.cached_validators(conn, company, board_url(company), rules_version())
            stored = db.stored_versions(conn, company) if cached and company.platform == "greenhouse" else {}
            return cached, stored
    except psycopg.Error as exc:  # first run, or the database is waking: read it in full
        log.warning("%s: could not read the board's cache (%s)", company.name, exc)
        return None, {}


def remember_board(conn: psycopg.Connection, company, jobs, open_before: int) -> None:
    """Store what identifies the version of the board just saved. Not after a
    read that looked wrong (see db.suspicious_drop): that board is read in
    full next time."""
    if company.platform not in CONDITIONAL:
        return
    listed = jobs.listed_ids() if isinstance(jobs, JobList) else {job.external_id for job in jobs}
    trusted = not db.suspicious_drop(open_before, len(listed))
    db.store_validators(conn, board_url(company), jobs.validators if trusted else None, rules_version())


def save_unchanged(dsn: str, company, run_started: datetime) -> int:
    """A board that answered 304: its open postings were seen, nothing else changes."""
    with db.connect(dsn) as conn:
        return db.mark_unchanged(conn, company, board_url(company), run_started)


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
                open_before = db.open_count(conn, company_id)
                saved = db.save_company_jobs(conn, company_id, jobs, run_started, close_missing=jobs.complete)
                remember_board(conn, company, jobs, open_before)
                return saved
        except psycopg.OperationalError as exc:
            if attempt == WRITE_ATTEMPTS:
                raise
            log.warning("%s: database connection lost (%s); retrying", company.name, exc)
    raise AssertionError("unreachable")


def log_traffic(seconds_by_platform: dict[str, float] | None = None) -> None:
    """The run summary's numbers: time per platform, and what each kind of
    site was sent (requests, data received, 304 answers)."""
    if seconds_by_platform:
        log.info(
            "time by platform (summed across workers): %s",
            ", ".join(f"{p} {s:.0f}s" for p, s in sorted(seconds_by_platform.items(), key=lambda kv: -kv[1])),
        )
    groups: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])
    for host, (requests, size, not_modified) in list(http.traffic.by_host.items()):
        kind = (
            "workday"
            if host.endswith("myworkdayjobs.com")
            else {
                "boards-api.greenhouse.io": "greenhouse",
                "api.lever.co": "lever",
                "api.eu.lever.co": "lever",
                "api.ashbyhq.com": "ashby",
            }.get(host, "other")
        )
        row = groups[kind]
        row[0] += requests
        row[1] += size
        row[2] += not_modified
    for kind, (requests, size, not_modified) in sorted(groups.items(), key=lambda kv: -kv[1][1]):
        log.info(
            "traffic %s: %d requests, %.1f MB received, %d not modified",
            kind,
            requests,
            size / 1e6,
            not_modified,
        )


def log_database_reads() -> dict:
    """Log what this run read from the database (Neon caps it monthly), by
    step and the biggest queries; returned for the run's health report."""
    report = dbtraffic.traffic.report()
    log.info(
        "read from the database: about %.1f MB (%.1f MB of results, %d connections)",
        report["bytes"] / 1e6,
        report["result_bytes"] / 1e6,
        report["connections"],
    )
    for name, row in sorted(report["steps"].items(), key=lambda kv: -kv[1]["bytes"]):
        log.info(
            "  %s: %.2f MB, %d connections, %d queries, %d rows",
            name,
            row["bytes"] / 1e6,
            row["connections"],
            row["queries"],
            row["rows"],
        )
    for row in report["queries"]:
        log.info(
            "  query %s (%s): %.2f MB in %d queries, %d rows",
            row["query"],
            row["step"],
            row["bytes"] / 1e6,
            row["queries"],
            row["rows"],
        )
    return report


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
    dbtraffic.traffic.reset()

    with db.connect(dsn) as conn:
        if shard is None:  # sharded runs start after a single `ghostless migrate`, so parts don't race
            db.apply_schema(conn)
        run_id = db.start_run(conn, run_started)
    if shard:
        log.info("part %d of %d: %d configured companies", shard[0], shard[1], len(companies))

    timings: dict[str, float] = {}
    unchanged: set[str] = set()
    done = {"count": 0}
    health.current.reset()

    def collect(company) -> tuple[int, int, int] | None:
        """Fetch and save one company: (jobs, new, closed), or None if fetching failed."""
        started = time.perf_counter()
        try:
            return _collect(company, started)
        finally:
            timings[company.name] = time.perf_counter() - started

    def _collect(company, started: float) -> tuple[int, int, int] | None:
        stored = _stored_details(dsn, company)
        cached, versions = board_state(dsn, company)
        try:
            jobs = fetch_jobs(
                company, known=complete_descriptions(company.platform, stored), cached=cached, stored=versions
            )
        except FetchError as exc:
            log.error("%s: fetch failed, skipping (no jobs closed): %s", company.name, exc)
            return None
        if jobs.not_modified:
            seen = save_unchanged(dsn, company, run_started)
            stats["boards_not_modified"] = stats.get("boards_not_modified", 0) + 1
            unchanged.add(company.name)
            done["count"] += 1
            log.info(
                "[%d/%d] %s: unchanged (%d open jobs)", done["count"], len(companies), company.name, seen
            )
            return seen, 0, 0
        reuse_details(jobs, stored)
        snowball.note_postings(company, jobs)  # boards they link to (GHOSTLESS_SNOWBALL)
        for job in jobs:
            enrich(job, extract_skills(f"{job.title} {job.description}"))
        jobs = keep_relevant(jobs)  # tech roles and student roles only
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
    with dbtraffic.step("configured companies"):
        results = list(run_by_site(companies, site_of, collect))
    for company, result in results:
        source, seconds = f"configured {company.platform}", timings.get(company.name, 0.0)
        if isinstance(result, BaseException) or result is None:
            health.current.record(source, ok=False, seconds=seconds)
        else:
            health.current.record(
                source,
                not_modified=company.name in unchanged,
                seconds=seconds,
                seen=result[0],
                new=result[1],
                closed=result[2],
            )
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
    by_platform: dict[str, float] = defaultdict(float)
    for company in companies:
        by_platform[company.platform] += timings.get(company.name, 0.0)
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

    with dbtraffic.step("register boards"):
        snowball.register(dsn)  # boards linked from postings, checked on the next run
    stats["duration_seconds"] = round(time.perf_counter() - clock, 2)
    log_traffic(by_platform)
    if stats.get("boards_not_modified") or stats.get("discovered_not_modified"):
        log.info(
            "unchanged since the last read (304): %d configured boards, %d discovered boards",
            stats.get("boards_not_modified", 0),
            stats.get("discovered_not_modified", 0),
        )
    if shard is None:
        with dbtraffic.step("signals and clean-up"), db.connect(dsn) as conn:
            db.refresh_signals(conn)
            purge_expired(conn)  # old sessions, used email links, analytics past retention
    report = health.current.report()
    report["database"] = log_database_reads()
    health.write_step_summary(
        report, f"Ingest health, part {shard[0]} of {shard[1]}" if shard else "Ingest health"
    )
    with db.connect(dsn) as conn:
        db.finish_run(conn, run_id, stats, report)

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
    health.current.reset()
    dbtraffic.traffic.reset()
    discovery.run(dsn, load_companies(), load_lists(), run_started, stats, crawl=False)
    with dbtraffic.step("signals and clean-up"), db.connect(dsn) as conn:
        db.refresh_signals(conn)
        purge_expired(conn)
    report = health.current.report()
    report["database"] = log_database_reads()
    health.write_step_summary(report, "Job lists")
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
