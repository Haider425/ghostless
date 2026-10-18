"""The discovery step of each ingest run.

1. Read the public job lists (tracker.discovery.lists).
2. Register every job board their links lead to (Greenhouse, Lever, Ashby,
   Workday) that companies.yaml doesn't already cover. These "discovered"
   boards then grow the tracker on their own: no one has to add companies.
3. Crawl every discovered board that's due. A board whose postings changed
   is read again the next day; one that keeps not changing is read every few
   days, up to weekly (the revisit policy search engines use: spend visits
   where things change). Boards with open student roles are never left more
   than two days, and a failing board waits longer after each failure.
   Greenhouse, Lever and Ashby boards are read in full. Workday boards are
   searched for internships, co-ops and new grad roles only, since a full crawl
   of hundreds of large employers would take hours.
4. Store list entries whose company isn't covered by a board the tracker
   reads, as they appear in the list (title, link, locations, season). They
   close when they leave the list, or when the company's board is tracked.
"""

from __future__ import annotations

import logging
import os
import time
from collections import defaultdict
from datetime import datetime

import psycopg

from tracker import db
from tracker.classify import enrich
from tracker.discovery.boards import board_from_url, company_key
from tracker.discovery.lists import JobList, ListedJob, clean_url, fetch_list
from tracker.models import Company, Job
from tracker.parallel import in_shard, run_by_site, site_of
from tracker.skills import extract_skills
from tracker.sources import FetchError
from tracker.sources.boards import fetch_board
from tracker.sources.workday import fetch_workday

log = logging.getLogger("tracker.discovery")

# a safety cap; normally every due board is read (see next_visit)
BOARDS_PER_RUN = int(os.environ.get("GHOSTLESS_DISCOVERED_PER_RUN", "5000"))
WORKDAY_QUERIES = ("intern", "co-op", "new grad")
WORKDAY_PER_QUERY = 100
WORKDAY_DETAILS = 15
MAX_QUIET_DAYS = 7  # a board that never changes is still read weekly
STUDENT_DAYS = 2  # boards with open internships or new grad roles
MAX_FAILURE_DAYS = 30
STUDENT_LEVELS = ("intern", "new_grad")


def run(
    dsn: str,
    configured: list[Company],
    lists: list[JobList],
    run_started: datetime,
    stats: dict,
    crawl: bool = True,
) -> None:
    """Steps 1 to 4. With crawl=False (after a sharded run, where every part
    crawled its share of boards), only the lists are read and saved."""
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

    if crawl:
        crawl_boards(dsn, run_started, stats)
    save_list_jobs(
        dsn,
        items,
        configured_names,
        run_started,
        stats,
        close=all_lists_read,
        configured_boards=configured_boards,
    )
    from tracker.discovery.dedupe import merge_duplicates

    with db.connect(dsn) as conn:
        merge_duplicates(conn)


# ---------- 2. registering boards ----------


def register_boards(
    dsn: str, items: list[ListedJob], configured_boards: set[tuple[str, str]], configured_names: set[str]
) -> int:
    found: dict[tuple[str, str], tuple[str, str, str]] = {}
    for item in items:
        board = board_from_url(item.url)
        if board is None or company_key(item.company) in configured_names:
            continue
        key = (board[0], board[1].lower())  # "External" and "external" are one Workday board
        if key in configured_boards:
            continue
        found.setdefault(key, (board[1], item.company, item.list_name))
    if not found:
        return 0
    with db.connect(dsn) as conn:
        known = {
            (platform, slug.lower())
            for platform, slug in conn.execute(
                "SELECT platform, board_slug FROM discovered_boards"
            ).fetchall()
        }
        rows = [
            (p, slug, name, where) for (p, _), (slug, name, where) in found.items() if (p, _) not in known
        ]
        before = conn.execute("SELECT count(*) FROM discovered_boards").fetchone()[0]
        with conn.cursor() as cur:
            cur.executemany(
                """INSERT INTO discovered_boards (platform, board_slug, company_name, found_in)
                   VALUES (%s, %s, %s, %s) ON CONFLICT (platform, board_slug) DO NOTHING""",
                rows,
            )
        after = conn.execute("SELECT count(*) FROM discovered_boards").fetchone()[0]
    return after - before


# ---------- 3. crawling a rotation of boards ----------


def next_visit_days(changed: bool, quiet_visits: int, student_roles: int, failures: int) -> float:
    """Days until a board's next visit.

    Failing: 1, 2, 4, 8 ... days, up to a month. Changed: tomorrow. Unchanged:
    one more day for every two quiet visits in a row, up to a week, or two days
    while it has open student roles. (Ghostless runs daily, so "1" means the
    next run.)
    """
    if failures:
        return float(min(MAX_FAILURE_DAYS, 2 ** (failures - 1)))
    if changed:
        return 1.0
    days = min(MAX_QUIET_DAYS, 1 + quiet_visits // 2)
    return float(min(days, STUDENT_DAYS) if student_roles else days)


def _due_boards(conn: psycopg.Connection, limit: int) -> list[tuple[str, str, str]]:
    # an hour of slack: a run that starts a little early still reads yesterday's boards
    return conn.execute(
        """SELECT platform, board_slug, company_name FROM discovered_boards
           WHERE next_due IS NULL OR next_due <= now() + interval '1 hour'
           ORDER BY next_due NULLS FIRST, first_seen
           LIMIT %s""",
        (limit,),
    ).fetchall()


def crawl_boards(
    dsn: str,
    run_started: datetime,
    stats: dict,
    limit: int | None = None,
    shard: tuple[int, int] | None = None,
) -> None:
    started = time.perf_counter()
    with db.connect(dsn) as conn:
        due = _due_boards(conn, BOARDS_PER_RUN if limit is None else limit)
    companies = [
        Company(name=name, platform=platform, board_slug=slug, origin="discovered")
        for platform, slug, name in due
    ]
    companies = [c for c in companies if in_shard(c, shard)]
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
    log.info("discovered boards: %d crawled in %.0fs", len(companies), time.perf_counter() - started)


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
    students = sum(1 for job in jobs if job.level in STUDENT_LEVELS)
    _mark(dsn, platform, slug, ok=True, jobs=len(jobs), changed=bool(new or closed), students=students)
    log.info("discovered %s: %d jobs (%d new, %d closed)", name, len(jobs), new, closed)
    return len(jobs), new, closed


def _mark(
    dsn: str,
    platform: str,
    slug: str,
    ok: bool,
    jobs: int | None = None,
    changed: bool = False,
    students: int = 0,
) -> None:
    with db.connect(dsn) as conn:
        if ok:
            quiet = conn.execute(
                "SELECT quiet_visits FROM discovered_boards WHERE platform = %s AND board_slug = %s",
                (platform, slug),
            ).fetchone()
            quiet_visits = 0 if changed or quiet is None else quiet[0] + 1
            days = next_visit_days(changed, quiet_visits, students, failures=0)
            conn.execute(
                """UPDATE discovered_boards SET last_crawled = now(), last_ok = now(), failures = 0,
                          jobs_last = %s, quiet_visits = %s,
                          last_changed = CASE WHEN %s THEN now() ELSE last_changed END,
                          next_due = now() + make_interval(secs => %s)
                   WHERE platform = %s AND board_slug = %s""",
                (jobs, quiet_visits, changed, days * 86400, platform, slug),
            )
        else:
            failures = conn.execute(
                """UPDATE discovered_boards SET last_crawled = now(), failures = failures + 1
                   WHERE platform = %s AND board_slug = %s RETURNING failures""",
                (platform, slug),
            ).fetchone()
            days = next_visit_days(False, 0, 0, failures[0] if failures else 1)
            conn.execute(
                "UPDATE discovered_boards SET next_due = now() + make_interval(secs => %s) "
                "WHERE platform = %s AND board_slug = %s",
                (days * 86400, platform, slug),
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
    configured_boards: set[tuple[str, str]] = frozenset(),
) -> None:
    with db.connect(dsn) as conn:
        read_boards = conn.execute(
            "SELECT platform, board_slug, company_name FROM discovered_boards WHERE last_ok IS NOT NULL"
        ).fetchall()
        covered = configured_names | {company_key(name) for _, _, name in read_boards}
        # a link to a board the tracker reads is covered whatever the list calls the company
        tracked = set(configured_boards) | {(p, slug.lower()) for p, slug, _ in read_boards}
        groups: dict[str, list[ListedJob]] = defaultdict(list)
        names: dict[str, str] = {}
        seen_urls: set[str] = set()
        for item in items:
            link = clean_url(item.url)
            if link in seen_urls:
                continue  # the same posting in another list (lists are read in order, so the first one keeps it)
            seen_urls.add(link)
            key = company_key(item.company)
            board = board_from_url(item.url)
            if key in covered or (board and (board[0], board[1].lower()) in tracked):
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
            # a list company really can drop to nothing: no guard
            new, closed = db.save_company_jobs(
                conn, company_id, jobs, run_started, close_missing=close, guard=False
            )
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
                        conn, company_id, [], run_started, close_missing=True, guard=False
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
