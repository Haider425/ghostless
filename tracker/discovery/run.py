"""The discovery step of each ingest run.

1. Read the public job lists (tracker.discovery.lists).
2. Register every job board their links lead to (Greenhouse, Lever, Ashby,
   Workday) that companies.yaml doesn't already cover. These "discovered"
   boards then grow the tracker on their own: no one has to add companies.
3. Crawl a rotation of discovered boards, oldest first, so each is visited
   every few days without making the daily run too long. Greenhouse, Lever and
   Ashby boards are read in full. Workday boards are searched for internships,
   co-ops and new grad roles only, since a full crawl of hundreds of large
   employers would take hours.
4. Store list entries whose company isn't covered by a board the tracker
   reads, as they appear in the list (title, link, locations, season). They
   close when they leave the list, or when the company's board is tracked.
"""

from __future__ import annotations

import logging
import os
from collections import defaultdict
from datetime import datetime

import psycopg

from tracker import db
from tracker.classify import enrich
from tracker.discovery.boards import board_from_url, company_key
from tracker.discovery.lists import JobList, ListedJob, clean_url, fetch_list
from tracker.models import Company, Job
from tracker.parallel import run_by_site, site_of
from tracker.skills import extract_skills
from tracker.sources import FetchError
from tracker.sources.boards import fetch_board
from tracker.sources.workday import fetch_workday

log = logging.getLogger("tracker.discovery")

BOARDS_PER_RUN = int(os.environ.get("GHOSTLESS_DISCOVERED_PER_RUN", "120"))
WORKDAY_QUERIES = ("intern", "co-op", "new grad")
WORKDAY_PER_QUERY = 100
WORKDAY_DETAILS = 15
MAX_FAILURES = 5  # after this many failures in a row, a board is retried monthly
STUDENT_LEVELS = ("intern", "new_grad")


def run(
    dsn: str, configured: list[Company], lists: list[JobList], run_started: datetime, stats: dict
) -> None:
    items: list[ListedJob] = []
    all_lists_read = True
    for job_list in lists:
        try:
            found = fetch_list(job_list)
        except FetchError as exc:
            all_lists_read = False
            log.error("list %s: could not read it, skipping (nothing closed): %s", job_list.name, exc)
            continue
        log.info("list %s: %d open entries", job_list.name, len(found))
        items.extend(found)
    if not items:
        return

    configured_boards = {(c.platform, c.board_slug.lower()) for c in configured}
    configured_names = {company_key(c.name) for c in configured}
    registered = register_boards(dsn, items, configured_boards, configured_names)
    if registered:
        log.info("discovered %d new job boards", registered)

    crawl_boards(dsn, run_started, stats)
    save_list_jobs(dsn, items, configured_names, run_started, stats, close=all_lists_read)


# ---------- 2. registering boards ----------


def register_boards(
    dsn: str, items: list[ListedJob], configured_boards: set[tuple[str, str]], configured_names: set[str]
) -> int:
    found: dict[tuple[str, str], tuple[str, str]] = {}
    for item in items:
        board = board_from_url(item.url)
        if board is None or company_key(item.company) in configured_names:
            continue
        if (board[0], board[1].lower()) in configured_boards:
            continue
        found.setdefault(board, (item.company, item.list_name))
    if not found:
        return 0
    with db.connect(dsn) as conn:
        before = conn.execute("SELECT count(*) FROM discovered_boards").fetchone()[0]
        with conn.cursor() as cur:
            cur.executemany(
                """INSERT INTO discovered_boards (platform, board_slug, company_name, found_in)
                   VALUES (%s, %s, %s, %s) ON CONFLICT (platform, board_slug) DO NOTHING""",
                [(p, slug, name, where) for (p, slug), (name, where) in found.items()],
            )
        after = conn.execute("SELECT count(*) FROM discovered_boards").fetchone()[0]
    return after - before


# ---------- 3. crawling a rotation of boards ----------


def _due_boards(conn: psycopg.Connection, limit: int) -> list[tuple[str, str, str]]:
    return conn.execute(
        """SELECT platform, board_slug, company_name FROM discovered_boards
           WHERE failures < %s OR last_crawled < now() - interval '30 days'
           ORDER BY last_crawled NULLS FIRST, first_seen
           LIMIT %s""",
        (MAX_FAILURES, limit),
    ).fetchall()


def crawl_boards(dsn: str, run_started: datetime, stats: dict, limit: int | None = None) -> None:
    with db.connect(dsn) as conn:
        due = _due_boards(conn, BOARDS_PER_RUN if limit is None else limit)
    companies = [
        Company(name=name, platform=platform, board_slug=slug, origin="discovered")
        for platform, slug, name in due
    ]
    for company, result in run_by_site(companies, site_of, lambda c: _crawl_one(dsn, c, run_started)):
        if isinstance(result, BaseException):
            log.error("discovered %s: %s", company.name, result)
            continue
        if result is None:
            continue
        seen, new, closed = result
        stats["discovered_ok"] = stats.get("discovered_ok", 0) + 1
        stats["jobs_seen"] += seen
        stats["jobs_new"] += new
        stats["jobs_closed"] += closed


def _crawl_one(dsn: str, company: Company, run_started: datetime) -> tuple[int, int, int] | None:
    """Fetch and save one discovered board: (jobs, new, closed), or None if it couldn't be read."""
    platform, slug, name = company.platform, company.board_slug, company.name
    try:
        if platform == "workday":
            with db.connect(dsn) as conn:
                known = frozenset(db.stored_details(conn, company))
            jobs = fetch_workday(
                company,
                known=known,
                queries=WORKDAY_QUERIES,
                per_query=WORKDAY_PER_QUERY,
                max_details=WORKDAY_DETAILS,
            )
        else:
            jobs = fetch_board(company)
    except FetchError as exc:
        _mark(dsn, platform, slug, ok=False)
        log.warning("discovered %s (%s %s): fetch failed: %s", name, platform, slug, exc)
        return None
    if platform == "workday":
        # reuse descriptions already stored, as for configured companies
        from tracker.ingest import reuse_details

        with db.connect(dsn) as conn:
            reuse_details(jobs, db.stored_details(conn, company))
    for job in jobs:
        enrich(job, extract_skills(f"{job.title} {job.description}"))
    try:
        with db.connect(dsn) as conn:
            company_id = db.upsert_company(conn, company)
            new, closed = db.save_company_jobs(
                conn,
                company_id,
                jobs,
                run_started,
                close_missing=getattr(jobs, "complete", True),
                # a search for student roles is complete for those levels only
                close_levels=STUDENT_LEVELS if platform == "workday" else None,
            )
    except psycopg.Error:
        log.exception("discovered %s: database write failed", name)
        return None
    _mark(dsn, platform, slug, ok=True, jobs=len(jobs))
    log.info("discovered %s: %d jobs (%d new, %d closed)", name, len(jobs), new, closed)
    return len(jobs), new, closed


def _mark(dsn: str, platform: str, slug: str, ok: bool, jobs: int | None = None) -> None:
    with db.connect(dsn) as conn:
        if ok:
            conn.execute(
                """UPDATE discovered_boards SET last_crawled = now(), last_ok = now(), failures = 0, jobs_last = %s
                   WHERE platform = %s AND board_slug = %s""",
                (jobs, platform, slug),
            )
        else:
            conn.execute(
                """UPDATE discovered_boards SET last_crawled = now(), failures = failures + 1
                   WHERE platform = %s AND board_slug = %s""",
                (platform, slug),
            )


# ---------- 4. list-only jobs ----------


# The list's own category, for titles that don't name the kind of work
CATEGORY_ROLES = {
    "software": "sde",
    "software engineering": "sde",
    "hardware": "hardware",
    "hardware engineering": "hardware",
    "ai/ml/data": "ml",
    "data science, ai & machine learning": "ml",
    "quant": "data",
}


def classify_listed(job: Job, item: ListedJob) -> Job:
    """Fill gaps the title leaves, from what the list says about the entry."""
    if job.level == "mid" and item.level:
        job.level = item.level  # a new grad list's plain "Software Developer"
    if job.role_type == "other":
        job.role_type = CATEGORY_ROLES.get((item.category or "").lower(), "other")
    return job


def to_job(item: ListedJob) -> Job:
    return Job(
        external_id=item.id,
        title=item.title,
        url=item.url,
        location=" | ".join(item.locations),
        department=item.category,
        posted_at=item.posted_at,
        terms=list(item.terms),
        listed_in=item.list_name,
    )


def save_list_jobs(
    dsn: str,
    items: list[ListedJob],
    configured_names: set[str],
    run_started: datetime,
    stats: dict,
    close: bool = True,
) -> None:
    with db.connect(dsn) as conn:
        covered = configured_names | {
            company_key(name)
            for (name,) in conn.execute(
                "SELECT company_name FROM discovered_boards WHERE last_ok IS NOT NULL"
            ).fetchall()
        }
        groups: dict[str, list[ListedJob]] = defaultdict(list)
        names: dict[str, str] = {}
        seen_urls: set[str] = set()
        for item in items:
            link = clean_url(item.url)
            if link in seen_urls:
                continue  # the same posting in another list (lists are read in order, so the first one keeps it)
            seen_urls.add(link)
            key = company_key(item.company)
            if key in covered:
                continue  # the company's own board is tracked: no duplicates from the list
            groups[key].append(item)
            names.setdefault(key, item.company)

        seen_slugs = set()
        new_total = closed_total = 0
        for key, group in groups.items():
            jobs, ids = [], set()
            for item in group:
                if item.id in ids:
                    continue
                ids.add(item.id)
                jobs.append(classify_listed(enrich(to_job(item), extract_skills(item.title)), item))
            company = Company(name=names[key], platform="list", board_slug=f"list:{key}", origin="list")
            company_id = db.upsert_company(conn, company)
            new, closed = db.save_company_jobs(conn, company_id, jobs, run_started, close_missing=close)
            seen_slugs.add(company.board_slug)
            new_total += new
            closed_total += closed
            stats["jobs_seen"] += len(jobs)

        if close:
            # list companies with nothing left in the lists, or now covered by a board
            for company_id, slug in conn.execute(
                "SELECT id, board_slug FROM companies WHERE platform = 'list'"
            ).fetchall():
                if slug not in seen_slugs:
                    closed_total += db.save_company_jobs(
                        conn, company_id, [], run_started, close_missing=True
                    )[1]
        conn.commit()
    stats["jobs_new"] += new_total
    stats["jobs_closed"] += closed_total
    stats["list_companies"] = len(groups)
    log.info(
        "lists: %d companies only known from the lists, %d new and %d closed postings",
        len(groups),
        new_total,
        closed_total,
    )
