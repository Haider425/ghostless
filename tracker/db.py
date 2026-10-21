"""PostgreSQL persistence: idempotent upserts, closure and repost tracking, run stats."""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

import psycopg
from psycopg.types.json import Jsonb

from tracker import health
from tracker.models import Company, Job
from tracker.sources.http import Validators

log = logging.getLogger("tracker.db")

SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"


def connect(dsn: str) -> psycopg.Connection:
    # The timeout covers a serverless database waking from sleep.
    return psycopg.connect(dsn, connect_timeout=30)


def apply_schema(conn: psycopg.Connection) -> None:
    conn.execute(SCHEMA_PATH.read_text())
    conn.commit()


def upsert_company(conn: psycopg.Connection, company: Company) -> int:
    row = conn.execute(
        """
        INSERT INTO companies (name, platform, board_slug, domain, origin)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (platform, board_slug) DO UPDATE SET
            name = EXCLUDED.name,
            domain = coalesce(EXCLUDED.domain, companies.domain),
            origin = EXCLUDED.origin
        RETURNING id
        """,
        (company.name, company.platform, company.board_slug, company.domain, company.origin),
    ).fetchone()
    return row[0]


def stored_details(conn: psycopg.Connection, company: Company) -> dict[str, tuple[str, str]]:
    """{external_id: (description, location)} for this company's postings that
    already have a description, so sources that need a request per posting
    don't fetch them again."""
    rows = conn.execute(
        """
        SELECT j.external_id, j.description, coalesce(j.location, '')
        FROM jobs j JOIN companies c ON c.id = j.company_id
        WHERE c.platform = %s AND c.board_slug = %s AND coalesce(j.description, '') <> ''
        """,
        (company.platform, company.board_slug),
    ).fetchall()
    return {external_id: (description, location) for external_id, description, location in rows}


def stored_versions(
    conn: psycopg.Connection, company: Company
) -> dict[str, tuple[datetime, str, str | None]]:
    """{external_id: (source_updated_at, description, department)} for this
    company's postings stored with a description and a source version, so a
    posting the source hasn't changed since isn't downloaded again."""
    rows = conn.execute(
        """
        SELECT j.external_id, j.source_updated_at, j.description, j.department
        FROM jobs j JOIN companies c ON c.id = j.company_id
        WHERE c.platform = %s AND c.board_slug = %s
          AND j.source_updated_at IS NOT NULL AND coalesce(j.description, '') <> ''
        """,
        (company.platform, company.board_slug),
    ).fetchall()
    return {
        external_id: (updated, description, department)
        for external_id, updated, description, department in rows
    }


# ---------- conditional requests (see http_cache in schema.sql) ----------

FULL_READ_DAYS = 7  # even an unchanged board is read in full once a week


def cached_validators(conn: psycopg.Connection, company: Company, url: str, rules: str) -> Validators | None:
    """What to send to ask whether a board changed, or None to read it in full:
    nothing cached, the code that reads boards has changed since, the last full
    read is a week old, or nothing is stored for the board (so a bad first
    read can't stick)."""
    row = conn.execute(
        """
        SELECT h.etag, h.last_modified FROM http_cache h
        WHERE h.url = %s AND h.rules = %s AND h.fetched_at > now() - make_interval(days => %s)
          AND EXISTS (SELECT 1 FROM jobs j JOIN companies c ON c.id = j.company_id
                      WHERE c.platform = %s AND c.board_slug = %s AND j.is_active)
        """,
        (url, rules, FULL_READ_DAYS, company.platform, company.board_slug),
    ).fetchone()
    return Validators(url, row[0], row[1]) if row else None


def store_validators(conn: psycopg.Connection, url: str, validators: Validators | None, rules: str) -> None:
    """After a full read is saved (same transaction, so the cache never runs
    ahead of the jobs it vouches for)."""
    if validators is None:
        conn.execute("DELETE FROM http_cache WHERE url = %s", (url,))
        return
    conn.execute(
        """
        INSERT INTO http_cache (url, etag, last_modified, rules, fetched_at, checked_at)
        VALUES (%s, %s, %s, %s, now(), now())
        ON CONFLICT (url) DO UPDATE SET etag = EXCLUDED.etag, last_modified = EXCLUDED.last_modified,
            rules = EXCLUDED.rules, fetched_at = now(), checked_at = now()
        """,
        (url, validators.etag, validators.last_modified, rules),
    )


def mark_unchanged(conn: psycopg.Connection, company: Company, url: str, run_started: datetime) -> int:
    """A board answered 304: its open postings were seen in this run. Nothing
    is parsed, rewritten or closed. Returns how many postings are open."""
    seen = conn.execute(
        """
        UPDATE jobs j SET last_seen = %s
        FROM companies c
        WHERE c.id = j.company_id AND c.platform = %s AND c.board_slug = %s AND j.is_active
        """,
        (run_started, company.platform, company.board_slug),
    ).rowcount
    conn.execute("UPDATE http_cache SET checked_at = now() WHERE url = %s", (url,))
    return seen


def _skill_ids(conn: psycopg.Connection, names: set[str]) -> dict[str, int]:
    if not names:
        return {}
    conn.execute(
        "INSERT INTO skills (name) SELECT unnest(%s::text[]) ON CONFLICT (name) DO NOTHING",
        (list(names),),
    )
    rows = conn.execute("SELECT name, id FROM skills WHERE name = ANY(%s)", (list(names),)).fetchall()
    return dict(rows)


def open_count(conn: psycopg.Connection, company_id: int) -> int:
    return conn.execute(
        "SELECT count(*) FROM jobs WHERE company_id = %s AND is_active", (company_id,)
    ).fetchone()[0]


def suspicious_drop(open_before: int, found: int) -> bool:
    """True when a fetch found far fewer postings than were open: all of them
    gone (with 3 or more open), or under a third (with 20 or more open)."""
    if open_before >= 3 and found == 0:
        return True
    return open_before >= 20 and found < open_before / 3


def save_company_jobs(
    conn: psycopg.Connection,
    company_id: int,
    jobs: list[Job],
    run_started: datetime,
    close_missing: bool = True,
    close_levels: tuple[str, ...] | None = None,
    guard: bool = True,
) -> tuple[int, int]:
    """Upsert one company's postings and close the ones that disappeared.

    Only call this after a SUCCESSFUL fetch. If the fetch failed we must not
    run the closure step, or every job at that company would be wrongly closed.
    Pass close_missing=False for sources that only return part of the
    listings (e.g. Google), where a missing job is not necessarily closed.
    close_levels limits closing to jobs at those levels, for fetches that are
    complete for a scope only (a search for internships and new grad roles).

    guard: a site that suddenly returns nothing, or a small fraction of what
    it had, has more likely changed or failed to load than closed its jobs,
    so nothing is closed (see `suspicious_drop`). Off for job lists, whose
    companies really can leave the list.

    Returns (new_jobs, closed_jobs).
    """
    new_count = 0
    skill_ids = _skill_ids(conn, {s for job in jobs for s in job.skills})

    for job in jobs:
        job_id, inserted = conn.execute(
            """
            INSERT INTO jobs (company_id, external_id, title, location, department, url,
                              description, level, role_type, is_canada, is_remote, posted_at,
                              salary_min, salary_max, salary_period, salary_currency,
                              vacancy, ai_screening, fingerprint, terms, listed_in, source_updated_at,
                              seniority, workplace, employment_type, sponsorship, min_years_experience,
                              locations, countries, first_seen, last_seen)
            VALUES (%(company_id)s, %(external_id)s, %(title)s, %(location)s, %(department)s,
                    %(url)s, %(description)s, %(level)s, %(role_type)s, %(is_canada)s,
                    %(is_remote)s, %(posted_at)s, %(salary_min)s, %(salary_max)s,
                    %(salary_period)s, %(salary_currency)s, %(vacancy)s, %(ai_screening)s,
                    %(fingerprint)s, %(terms)s, %(listed_in)s, %(source_updated_at)s,
                    %(seniority)s, %(workplace)s, %(employment_type)s, %(sponsorship)s,
                    %(min_years_experience)s, %(locations)s, %(countries)s, %(run)s, %(run)s)
            ON CONFLICT (company_id, external_id) DO UPDATE SET
                title = EXCLUDED.title,
                location = EXCLUDED.location,
                department = EXCLUDED.department,
                url = EXCLUDED.url,
                description = EXCLUDED.description,
                level = EXCLUDED.level,
                role_type = EXCLUDED.role_type,
                is_canada = EXCLUDED.is_canada,
                is_remote = EXCLUDED.is_remote,
                salary_min = EXCLUDED.salary_min,
                salary_max = EXCLUDED.salary_max,
                salary_period = EXCLUDED.salary_period,
                salary_currency = EXCLUDED.salary_currency,
                vacancy = EXCLUDED.vacancy,
                ai_screening = EXCLUDED.ai_screening,
                fingerprint = EXCLUDED.fingerprint,
                terms = EXCLUDED.terms,
                listed_in = EXCLUDED.listed_in,
                source_updated_at = EXCLUDED.source_updated_at,
                seniority = EXCLUDED.seniority,
                workplace = EXCLUDED.workplace,
                employment_type = EXCLUDED.employment_type,
                sponsorship = EXCLUDED.sponsorship,
                min_years_experience = EXCLUDED.min_years_experience,
                locations = EXCLUDED.locations,
                countries = EXCLUDED.countries,
                last_seen = EXCLUDED.last_seen,
                is_active = true,
                closed_at = NULL
            RETURNING id, (xmax = 0) AS inserted
            """,
            {
                "company_id": company_id,
                "external_id": job.external_id,
                "title": job.title,
                "location": job.location,
                "department": job.department,
                "url": job.url,
                "description": job.description,
                "level": job.level,
                "role_type": job.role_type,
                "is_canada": job.is_canada,
                "is_remote": job.is_remote,
                "posted_at": job.posted_at,
                "salary_min": job.salary_min,
                "salary_max": job.salary_max,
                "salary_period": job.salary_period,
                "salary_currency": job.salary_currency,
                "vacancy": job.vacancy,
                "ai_screening": job.ai_screening,
                "fingerprint": job.fingerprint,
                "terms": job.terms,
                "listed_in": job.listed_in,
                "source_updated_at": job.source_updated_at,
                "seniority": job.seniority,
                "workplace": job.workplace,
                "employment_type": job.employment_type,
                "sponsorship": job.sponsorship,
                "min_years_experience": job.min_years_experience,
                "locations": Jsonb(job.locations),
                "countries": job.countries,
                "run": run_started,
            },
        ).fetchone()
        new_count += int(inserted)

        conn.execute("DELETE FROM job_skills WHERE job_id = %s", (job_id,))
        if job.skills:
            conn.execute(
                """
                INSERT INTO job_skills (job_id, skill_id)
                SELECT %s, unnest(%s::int[]) ON CONFLICT DO NOTHING
                """,
                (job_id, [skill_ids[s] for s in job.skills]),
            )

    # Postings the source still lists that the storage filter left out (see
    # classify.keep_relevant). One stored before the filter is still open: it's
    # marked seen, so it's never closed or counted as missing while it's listed.
    saved_ids = {job.external_id for job in jobs}
    filtered = sorted(i for i in (getattr(jobs, "listed", None) or ()) if i not in saved_ids)
    if filtered:
        conn.execute(
            "UPDATE jobs SET last_seen = %s WHERE company_id = %s AND is_active AND external_id = ANY(%s)",
            (run_started, company_id, filtered),
        )

    closed = 0
    if close_missing and guard:
        levels = list(close_levels) if close_levels else None
        open_before = conn.execute(
            """SELECT count(*) FROM jobs WHERE company_id = %s AND is_active AND last_seen < %s
                 AND (%s::text[] IS NULL OR level = ANY(%s::text[]))""",
            (company_id, run_started, levels, levels),
        ).fetchone()[0]
        # what the site listed, stored or not: a board of mostly non-tech
        # postings isn't a board that suddenly returned almost nothing
        still_open = sum(1 for job in jobs if not close_levels or job.level in close_levels) + len(filtered)
        if suspicious_drop(open_before + still_open, still_open):
            _report_guard(conn, company_id, still_open, open_before + still_open)
            close_missing = False
    if close_missing:
        closed = conn.execute(
            """
            UPDATE jobs SET is_active = false, closed_at = %s
            WHERE company_id = %s AND is_active AND last_seen < %s
              AND (%s::text[] IS NULL OR level = ANY(%s::text[]))
            """,
            (
                run_started,
                company_id,
                run_started,
                list(close_levels) if close_levels else None,
                list(close_levels) if close_levels else None,
            ),
        ).rowcount

    _link_reposts(conn, company_id, run_started)
    return new_count, closed


def _report_guard(conn: psycopg.Connection, company_id: int, found: int, open_before: int) -> None:
    row = conn.execute("SELECT name FROM companies WHERE id = %s", (company_id,)).fetchone()
    name = row[0] if row else str(company_id)
    log.warning(
        "%s: the site returned %d postings but %d were open, so nothing was closed "
        "(the site may have changed or failed to load; closures resume on a normal fetch)",
        name,
        found,
        open_before,
    )
    health.current.guard_caught(name, found, open_before)


def close_missing_postings(
    conn: psycopg.Connection, company_id: int, listed: set[str], run_started: datetime
) -> int:
    """After reading a board's complete listing without saving it (the weekly
    Workday full read): close open postings, at any level, that aren't listed,
    and mark the listed ones as seen. Nothing is inserted. The suspicious-drop
    guard applies. Returns how many closed."""
    rows = conn.execute(
        "SELECT id, external_id FROM jobs WHERE company_id = %s AND is_active", (company_id,)
    ).fetchall()
    present = [job_id for job_id, external_id in rows if external_id in listed]
    gone = [job_id for job_id, external_id in rows if external_id not in listed]
    if present:
        conn.execute("UPDATE jobs SET last_seen = %s WHERE id = ANY(%s)", (run_started, present))
    if not gone:
        return 0
    if suspicious_drop(len(rows), len(present)):
        _report_guard(conn, company_id, len(present), len(rows))
        return 0
    return conn.execute(
        "UPDATE jobs SET is_active = false, closed_at = %s WHERE id = ANY(%s)", (run_started, gone)
    ).rowcount


REPOST_WINDOW_DAYS = 120


def _link_reposts(conn: psycopg.Connection, company_id: int, run_started: datetime) -> None:
    """Point each job first seen in this run at the most recent earlier posting
    of the same role (same fingerprint) that has since closed.

    Runs after the closure step, so a role taken down and reposted under a new
    id in the same run is still linked.
    """
    conn.execute(
        """
        UPDATE jobs AS new SET reposted_from = (
            SELECT old.id FROM jobs AS old
            WHERE old.company_id = new.company_id
              AND old.fingerprint = new.fingerprint
              AND old.id <> new.id
              AND old.closed_at IS NOT NULL
              AND old.closed_at >= %(run)s - make_interval(days => %(window)s)
            ORDER BY old.closed_at DESC
            LIMIT 1
        )
        WHERE new.company_id = %(company)s
          AND new.first_seen = %(run)s
          AND new.fingerprint <> ''
          AND new.reposted_from IS NULL
        """,
        {"company": company_id, "run": run_started, "window": REPOST_WINDOW_DAYS},
    )


def refresh_signals(conn: psycopg.Connection) -> None:
    """Recompute the cached ghost signals the API reads."""
    conn.execute("REFRESH MATERIALIZED VIEW CONCURRENTLY job_signals_mv")
    conn.commit()


def start_run(conn: psycopg.Connection, started_at: datetime) -> int:
    row = conn.execute(
        "INSERT INTO ingest_runs (started_at) VALUES (%s) RETURNING id", (started_at,)
    ).fetchone()
    conn.commit()
    return row[0]


def finish_run(conn: psycopg.Connection, run_id: int, stats: dict, report: dict | None = None) -> None:
    conn.execute(
        """
        UPDATE ingest_runs SET finished_at = now(), companies_ok = %(companies_ok)s,
            companies_failed = %(companies_failed)s, jobs_seen = %(jobs_seen)s,
            jobs_new = %(jobs_new)s, jobs_closed = %(jobs_closed)s,
            duration_seconds = %(duration_seconds)s, health = %(health)s
        WHERE id = %(run_id)s
        """,
        {**stats, "run_id": run_id, "health": Jsonb(report) if report is not None else None},
    )
    conn.commit()
