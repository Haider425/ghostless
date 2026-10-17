"""The ingestion pipeline: fetch, classify, store. Run it with `jobtracker ingest`."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

from tracker import db
from tracker.classify import enrich
from tracker.config import database_url, load_companies, select
from tracker.skills import extract_skills
from tracker.sources import FetchError, fetch_jobs, listing_is_complete

log = logging.getLogger("tracker.ingest")


def run(only: str | None = None) -> dict:
    companies = select(load_companies(), only)

    run_started = datetime.now(timezone.utc)
    clock = time.perf_counter()
    stats = dict(companies_ok=0, companies_failed=0, jobs_seen=0, jobs_new=0, jobs_closed=0)

    with db.connect(database_url()) as conn:
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
                company_id = db.upsert_company(conn, company)
                new, closed = db.save_company_jobs(
                    conn, company_id, jobs, run_started, close_missing=listing_is_complete(company)
                )
                conn.commit()  # one transaction per company
            except Exception:
                conn.rollback()
                stats["companies_failed"] += 1
                log.exception("%s: database write failed, rolled back", company.name)
                continue

            stats["companies_ok"] += 1
            stats["jobs_seen"] += len(jobs)
            stats["jobs_new"] += new
            stats["jobs_closed"] += closed
            log.info("%s: %d jobs (%d new, %d closed)", company.name, len(jobs), new, closed)

        stats["duration_seconds"] = round(time.perf_counter() - clock, 2)
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
