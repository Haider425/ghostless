"""Re-derive classification, disclosures and fingerprints for every stored posting.

Run `ghostless reprocess` after upgrading, so improved parsing applies to
postings already in the database (including closed ones) right away instead
of only as postings are fetched again. Nothing is fetched from the web.
"""

from __future__ import annotations

import logging

import psycopg

from tracker import db
from tracker.classify import classify_level, classify_role, is_canada, is_remote
from tracker.disclosures import fingerprint, parse_ai_screening, parse_salary, parse_vacancy
from tracker.skills import extract_skills

log = logging.getLogger(__name__)

BATCH = 1000


def _derive(row: tuple) -> tuple:
    job_id, platform, title, location, description, was_remote, vacancy = row
    text = description or ""
    canada = is_canada(location or "")
    # the platform's own remote flag isn't stored separately, so a remote job stays remote
    remote = is_remote(location or "") or bool(was_remote)
    salary = parse_salary(text)
    currency = None
    if salary:
        currency = salary.currency or ("CAD" if canada and not remote else None)
    # Apple reports its own pipeline status, which the text may not repeat
    new_vacancy = parse_vacancy(text) or (vacancy if platform == "apple" else None)
    return (
        classify_level(title),
        classify_role(title),
        canada,
        remote,
        salary.minimum if salary else None,
        salary.maximum if salary else None,
        salary.period if salary else None,
        currency,
        new_vacancy,
        parse_ai_screening(text),
        fingerprint(title, location or "", text),
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
                """SELECT j.id, c.platform, j.title, j.location, j.description, j.is_remote, j.vacancy
                   FROM jobs j JOIN companies c ON c.id = j.company_id ORDER BY j.id"""
            )
            while rows := read.fetchmany(BATCH):
                with conn.cursor() as write:
                    write.executemany(
                        """UPDATE jobs SET level = %s, role_type = %s, is_canada = %s, is_remote = %s,
                                  salary_min = %s, salary_max = %s, salary_period = %s,
                                  salary_currency = %s, vacancy = %s, ai_screening = %s, fingerprint = %s
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
