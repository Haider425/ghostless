"""Re-derive classification, seasons, disclosures, fingerprints and the fields read
from text (seniority, workplace, job type, sponsorship, years, places) for every
stored posting.

Run `ghostless reprocess` after upgrading, so improved parsing applies to
postings already in the database (including closed ones) right away instead
of only as postings are fetched again. Nothing is fetched from the web.
"""

from __future__ import annotations

import logging

import psycopg
from psycopg.types.json import Jsonb

from tracker import db
from tracker.classify import enrich, parse_terms
from tracker.models import Job
from tracker.skills import extract_skills

log = logging.getLogger(__name__)

BATCH = 1000


def _derive(row: tuple) -> tuple:
    (
        job_id, platform, title, location, description, was_remote, vacancy, first_seen, listed_in, terms,
        salary_min, salary_max, salary_period, salary_currency, workplace, employment_type, stored_level,
        stored_role,
    ) = row  # fmt: skip
    text = description or ""
    # the same steps as a freshly fetched posting; Apple reports its own pipeline status
    job = Job(
        external_id=str(job_id),
        title=title,
        url="",
        location=location or "",
        description=text,
        # the platform's own remote flag isn't stored separately, so a remote job stays remote
        source_remote=bool(was_remote),
        vacancy=vacancy if platform == "apple" else None,
    )
    enrich(job, [])
    if listed_in:
        # a job list's own level and category fill what a plain title doesn't say
        # ("Software Engineer" on a new grad list), as when the list was read
        if job.level == "mid" and stored_level in ("intern", "new_grad"):
            job.level = stored_level
        if job.role_type == "other" and stored_role != "other":
            job.role_type = stored_role
    # a job list's own season labels stay; title and description add to them
    found = parse_terms(title, text, job.level, first_seen.year if first_seen else None)
    seasons = list(dict.fromkeys([*(terms or [])] + found)) if listed_in else found
    if job.salary_min is None and salary_min is not None:
        # pay a source gave in its own fields isn't in the text: keep it
        job.salary_min, job.salary_max = salary_min, salary_max
        job.salary_period, job.salary_currency = salary_period, salary_currency
    return (
        job.level,
        job.role_type,
        job.is_canada,
        job.is_remote,
        job.salary_min,
        job.salary_max,
        job.salary_period,
        job.salary_currency,
        job.vacancy,
        job.ai_screening,
        job.fingerprint,
        seasons,
        job.seniority,
        job.workplace or workplace,  # likewise a source's own workplace and job type
        job.employment_type or employment_type,
        job.sponsorship,
        job.min_years_experience,
        Jsonb(job.locations),
        job.countries,
        job_id,
    )


def run(dsn: str, companies: list | None = None) -> dict:
    with db.connect(dsn) as conn:
        db.apply_schema(conn)
        # names and domains from companies.yaml, for companies already stored
        for company in companies or []:
            conn.execute(
                "UPDATE companies SET name = %s, domain = %s WHERE platform = %s AND board_slug = %s",
                (company.name, company.domain, company.platform, company.board_slug),
            )
        updated = 0
        with conn.cursor(name="reprocess") as read:  # server-side cursor: constant memory
            read.itersize = BATCH
            read.execute(
                """SELECT j.id, c.platform, j.title, j.location, j.description, j.is_remote, j.vacancy,
                          j.first_seen, j.listed_in, j.terms, j.salary_min, j.salary_max, j.salary_period,
                          j.salary_currency, j.workplace, j.employment_type, j.level, j.role_type
                   FROM jobs j JOIN companies c ON c.id = j.company_id ORDER BY j.id"""
            )
            while rows := read.fetchmany(BATCH):
                with conn.cursor() as write:
                    write.executemany(
                        """UPDATE jobs SET level = %s, role_type = %s, is_canada = %s, is_remote = %s,
                                  salary_min = %s, salary_max = %s, salary_period = %s,
                                  salary_currency = %s, vacancy = %s, ai_screening = %s, fingerprint = %s,
                                  terms = %s, seniority = %s, workplace = %s, employment_type = %s,
                                  sponsorship = %s, min_years_experience = %s, locations = %s, countries = %s
                           WHERE id = %s""",
                        [_derive(row) for row in rows],
                    )
                _refresh_skills(conn, rows)
                updated += len(rows)
                log.info("reprocessed %d postings", updated)
        relinked = relink_reposts(conn)
        conn.commit()
        db.refresh_signals(conn)
    return {"postings": updated, "reposts_linked": relinked}


def _refresh_skills(conn: psycopg.Connection, rows: list[tuple]) -> None:
    """Re-extract skills, so new skills in the vocabulary apply to stored postings."""
    found = {row[0]: extract_skills(f"{row[2]} {row[4] or ''}") for row in rows}
    ids = db._skill_ids(conn, {name for names in found.values() for name in names})
    with conn.cursor() as cur:
        cur.execute("DELETE FROM job_skills WHERE job_id = ANY(%s)", (list(found),))
        pairs = [(job_id, ids[name]) for job_id, names in found.items() for name in names]
        if pairs:
            cur.executemany(
                "INSERT INTO job_skills (job_id, skill_id) VALUES (%s, %s) ON CONFLICT DO NOTHING", pairs
            )


def relink_reposts(conn: psycopg.Connection) -> int:
    """Recompute every repost link from the current fingerprints: each posting
    points at the latest posting of the same role that closed in the
    repost window before it appeared."""
    conn.execute("UPDATE jobs SET reposted_from = NULL WHERE reposted_from IS NOT NULL")
    return conn.execute(
        """
        UPDATE jobs AS new SET reposted_from = (
            SELECT old.id FROM jobs AS old
            WHERE old.company_id = new.company_id
              AND old.fingerprint = new.fingerprint
              AND old.id <> new.id
              AND old.closed_at IS NOT NULL
              AND old.closed_at <= new.first_seen
              AND old.closed_at >= new.first_seen - make_interval(days => %s)
            ORDER BY old.closed_at DESC
            LIMIT 1
        )
        WHERE new.fingerprint <> ''
          AND EXISTS (
            SELECT 1 FROM jobs AS old
            WHERE old.company_id = new.company_id AND old.fingerprint = new.fingerprint
              AND old.id <> new.id AND old.closed_at IS NOT NULL
              AND old.closed_at <= new.first_seen
              AND old.closed_at >= new.first_seen - make_interval(days => %s)
          )
        """,
        (db.REPOST_WINDOW_DAYS, db.REPOST_WINDOW_DAYS),
    ).rowcount
