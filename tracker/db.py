"""PostgreSQL persistence: idempotent upserts, closure and repost tracking, run stats."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import psycopg

from tracker.models import Company, Job

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
        INSERT INTO companies (name, platform, board_slug)
        VALUES (%s, %s, %s)
        ON CONFLICT (platform, board_slug) DO UPDATE SET name = EXCLUDED.name
        RETURNING id
        """,
        (company.name, company.platform, company.board_slug),
    ).fetchone()
    return row[0]


def _skill_ids(conn: psycopg.Connection, names: set[str]) -> dict[str, int]:
    if not names:
        return {}
    conn.execute(
        "INSERT INTO skills (name) SELECT unnest(%s::text[]) ON CONFLICT (name) DO NOTHING",
        (list(names),),
    )
    rows = conn.execute("SELECT name, id FROM skills WHERE name = ANY(%s)", (list(names),)).fetchall()
    return dict(rows)


def save_company_jobs(
    conn: psycopg.Connection,
    company_id: int,
    jobs: list[Job],
    run_started: datetime,
    close_missing: bool = True,
) -> tuple[int, int]:
    """Upsert one company's postings and close the ones that disappeared.

    Only call this after a SUCCESSFUL fetch. If the fetch failed we must not
    run the closure step, or every job at that company would be wrongly closed.
    Pass close_missing=False for sources that only return part of the
    listings (e.g. Google), where a missing job is not necessarily closed.

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
                              vacancy, ai_screening, fingerprint, first_seen, last_seen)
            VALUES (%(company_id)s, %(external_id)s, %(title)s, %(location)s, %(department)s,
                    %(url)s, %(description)s, %(level)s, %(role_type)s, %(is_canada)s,
                    %(is_remote)s, %(posted_at)s, %(salary_min)s, %(salary_max)s,
                    %(salary_period)s, %(salary_currency)s, %(vacancy)s, %(ai_screening)s,
                    %(fingerprint)s, %(run)s, %(run)s)
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

    closed = 0
    if close_missing:
        closed = conn.execute(
            """
            UPDATE jobs SET is_active = false, closed_at = %s
            WHERE company_id = %s AND is_active AND last_seen < %s
            """,
            (run_started, company_id, run_started),
        ).rowcount

    _link_reposts(conn, company_id, run_started)
    return new_count, closed


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


def start_run(conn: psycopg.Connection, started_at: datetime) -> int:
    row = conn.execute(
        "INSERT INTO ingest_runs (started_at) VALUES (%s) RETURNING id", (started_at,)
    ).fetchone()
    conn.commit()
    return row[0]


def finish_run(conn: psycopg.Connection, run_id: int, stats: dict) -> None:
    conn.execute(
        """
        UPDATE ingest_runs SET finished_at = now(), companies_ok = %(companies_ok)s,
            companies_failed = %(companies_failed)s, jobs_seen = %(jobs_seen)s,
            jobs_new = %(jobs_new)s, jobs_closed = %(jobs_closed)s,
            duration_seconds = %(duration_seconds)s
        WHERE id = %(run_id)s
        """,
        {**stats, "run_id": run_id},
    )
    conn.commit()