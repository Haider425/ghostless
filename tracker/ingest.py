"""The ingestion pipeline: fetch, classify, store. Run it with `ghostless ingest`."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

import psycopg

from tracker import db
from tracker.classify import enrich
from tracker.config import database_url, load_companies, select
from tracker.skills import extract_skills
from tracker.sources import FetchError, fetch_jobs

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


def run(only: str | None = None) -> dict:
    companies = select(load_companies(), only)
    dsn = database_url()

    run_started = datetime.now(timezone.utc)
    clock = time.perf_counter()
    stats = dict(companies_ok=0, companies_failed=0, jobs_seen=0, jobs_new=0, jobs_closed=0)

    with db.connect(dsn) as conn:
        db.apply_schema(conn)
        run_id = db.start_run(conn, run_started)

    for company in companies:
        try:
            jobs = fetch_jobs(company)
        except FetchError as exc:
            stats["companies_failed"] += 1
            log.error("%s: fetch failed, skipping (no jobs closed): %s", company.name, exc)
            continue

        for job in jobs:
            enrich(job, extract_skills(f"{job.title} {job.description}"))

        try:
            new, closed = _save(dsn, company, jobs, run_started)
        except Exception:
            stats["companies_failed"] += 1
            log.exception("%s: database write failed, nothing saved for this company", company.name)
            continue

        stats["companies_ok"] += 1
        stats["jobs_seen"] += len(jobs)
        stats["jobs_new"] += new
        stats["jobs_closed"] += closed
        log.info("%s: %d jobs (%d new, %d closed)", company.name, len(jobs), new, closed)

    stats["duration_seconds"] = round(time.perf_counter() - clock, 2)
    with db.connect(dsn) as conn:
        db.finish_run(conn, run_id, stats)

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


if __name__ == "__main__":  # backwards compatible: python -m tracker.ingest
    from tracker.cli import main

    main(["ingest"])