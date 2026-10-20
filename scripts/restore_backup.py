"""Put back postings from a backup that today's storage rules keep.

The non-tech cleanup of 19 October 2026 backed up every non-tech posting
before deleting them (backups/2026-10-19-non-tech-postings/). The classifier
has improved since, so some of those postings count as student or tech roles
now. This puts them back as they were: their original ids, first-seen dates,
closures, skills, saved jobs and application events, with today's level and
role labels.

If the crawler stored a posting again after the delete (a new row for the
same board and posting id), the original replaces it. The new row's current
state (last seen, open or closed), and anything attached to it (saved jobs,
reports, application events, repost links), move to the original first.

    python scripts/restore_backup.py                 show what it would do (reads only)
    python scripts/restore_backup.py --apply         restore, in one transaction

Run from the repository root.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import io
from dataclasses import dataclass, field
from pathlib import Path

import psycopg

from tracker.classify import classify_level, classify_role

STUDENT_LEVELS = ("intern", "new_grad")
DEFAULT_DIR = Path("backups/2026-10-19-non-tech-postings")


@dataclass
class Backup:
    """The records to restore, as exact CSV text (Postgres writes NULL as an
    unquoted empty field and an empty string as "", so the text is passed
    through untouched rather than re-written)."""

    labels: dict[int, tuple[str, str]] = field(default_factory=dict)  # id -> (level, role_type)
    csv: dict[str, str] = field(default_factory=dict)  # table -> header + selected records


def _records(text: str):
    """Raw CSV records (a quoted field can span lines), header first."""
    record = ""
    for line in text.splitlines(keepends=True):
        record += line
        if record.count('"') % 2 == 0:
            yield record
            record = ""
    if record:
        yield record


def _filter(path: Path, keep) -> str:
    text = gzip.open(path, "rt", encoding="utf-8", newline="").read() if path.exists() else ""
    records = _records(text)
    header = next(records, "")
    names = next(csv.reader([header])) if header else []
    chosen = [r for r in records if keep(dict(zip(names, next(csv.reader(io.StringIO(r))), strict=True)))]
    return header + "".join(chosen)


def read_backup(directory: Path = DEFAULT_DIR) -> Backup:
    backup = Backup()

    def keep_job(row: dict) -> bool:
        if row["level"] in STUDENT_LEVELS:
            return False  # these were never deleted
        level, role = classify_level(row["title"]), classify_role(row["title"])
        if role == "other" and level not in STUDENT_LEVELS:
            return False
        backup.labels[int(row["id"])] = (level, role)
        return True

    backup.csv["jobs"] = _filter(directory / "jobs.csv.gz", keep_job)
    for table in ("job_skills", "saved_jobs", "application_events"):
        backup.csv[table] = _filter(
            directory / f"{table}.csv.gz", lambda r: int(r["job_id"]) in backup.labels
        )
    return backup


def _load(conn: psycopg.Connection, backup: Backup) -> None:
    """The selected records into temporary tables shaped like the real ones."""
    for table in ("jobs", "job_skills", "saved_jobs", "application_events"):
        conn.execute(f"CREATE TEMP TABLE restore_{table} (LIKE {table}) ON COMMIT DROP")
        text = backup.csv.get(table, "")
        if not text:
            continue
        columns = ", ".join(next(csv.reader([text.split("\n", 1)[0]])))
        with conn.cursor().copy(
            f"COPY restore_{table} ({columns}) FROM STDIN WITH (FORMAT csv, HEADER true)"
        ) as copy:
            copy.write(text)
    ids = list(backup.labels)
    levels = [backup.labels[i][0] for i in ids]
    roles = [backup.labels[i][1] for i in ids]
    conn.execute(
        """UPDATE restore_jobs r SET level = n.level, role_type = n.role
           FROM unnest(%s::bigint[], %s::text[], %s::text[]) AS n(id, level, role) WHERE r.id = n.id""",
        (ids, levels, roles),
    )
    # a row stored again since the delete: same board, same posting id
    conn.execute(
        """CREATE TEMP TABLE restore_copies ON COMMIT DROP AS
           SELECT r.id AS original, j.id AS copy, j.last_seen, j.is_active, j.closed_at
           FROM restore_jobs r JOIN jobs j ON j.company_id = r.company_id AND j.external_id = r.external_id"""
    )


def plan(conn: psycopg.Connection, backup: Backup) -> dict:
    """What `restore` would do. Writes nothing that outlives the transaction:
    the caller rolls back."""
    _load(conn, backup)
    one = lambda sql: conn.execute(sql).fetchone()[0]  # noqa: E731
    return {
        "postings": one("SELECT count(*) FROM restore_jobs"),
        "open_when_backed_up": one("SELECT count(*) FROM restore_jobs WHERE is_active"),
        "company_missing": one(
            "SELECT count(*) FROM restore_jobs r WHERE NOT EXISTS (SELECT 1 FROM companies c WHERE c.id = r.company_id)"
        ),
        "id_in_use": one("SELECT count(*) FROM restore_jobs r JOIN jobs j ON j.id = r.id"),
        "copies": one("SELECT count(*) FROM restore_copies"),
        "saved_on_copies": one(
            "SELECT count(*) FROM saved_jobs s JOIN restore_copies c ON s.job_id = c.copy"
        ),
        "reports_on_copies": one("SELECT count(*) FROM reports s JOIN restore_copies c ON s.job_id = c.copy"),
        "events_on_copies": one(
            "SELECT count(*) FROM application_events s JOIN restore_copies c ON s.job_id = c.copy"
        ),
        "skills": one("SELECT count(*) FROM restore_job_skills"),
        "saved_jobs": one("SELECT count(*) FROM restore_saved_jobs"),
        "application_events": one("SELECT count(*) FROM restore_application_events"),
    }


def restore(conn: psycopg.Connection, backup: Backup) -> dict:
    """Restore in the caller's transaction (commit to keep it). Returns counts."""
    _load(conn, backup)
    blocked = conn.execute(
        """SELECT count(*) FROM restore_jobs r
           WHERE NOT EXISTS (SELECT 1 FROM companies c WHERE c.id = r.company_id)
              OR EXISTS (SELECT 1 FROM jobs j WHERE j.id = r.id)"""
    ).fetchone()[0]
    if blocked:
        raise RuntimeError(f"{blocked} postings can't go back: their company is gone or their id is in use")

    # 1. make room: the copy steps aside so the original can take its posting id
    conn.execute(
        "UPDATE jobs SET external_id = external_id || ' (replaced)' WHERE id IN (SELECT copy FROM restore_copies)"
    )
    columns = [
        r[0]
        for r in conn.execute(
            """SELECT column_name FROM information_schema.columns
               WHERE table_name = 'jobs' AND table_schema = current_schema() ORDER BY ordinal_position"""
        )
    ]
    listed = ", ".join(columns)
    restored = conn.execute(f"INSERT INTO jobs ({listed}) SELECT {listed} FROM restore_jobs").rowcount

    # 2. the copy saw the posting more recently: its open or closed state wins
    conn.execute(
        """UPDATE jobs j SET last_seen = c.last_seen, is_active = c.is_active, closed_at = c.closed_at
           FROM restore_copies c WHERE j.id = c.original AND c.last_seen > j.last_seen"""
    )
    # 3. what people attached to the copy moves to the original
    moved_saved = conn.execute(
        """INSERT INTO saved_jobs (user_id, job_id, saved_at, status, notes, updated_at, applied_at)
           SELECT s.user_id, c.original, s.saved_at, s.status, s.notes, s.updated_at, s.applied_at
           FROM saved_jobs s JOIN restore_copies c ON s.job_id = c.copy
           ON CONFLICT DO NOTHING"""
    ).rowcount
    moved_reports = conn.execute(
        "UPDATE reports r SET job_id = c.original FROM restore_copies c WHERE r.job_id = c.copy"
    ).rowcount
    moved_events = conn.execute(
        "UPDATE application_events e SET job_id = c.original FROM restore_copies c WHERE e.job_id = c.copy"
    ).rowcount
    conn.execute(
        "UPDATE jobs j SET reposted_from = c.original FROM restore_copies c WHERE j.reposted_from = c.copy"
    )
    removed = conn.execute("DELETE FROM jobs WHERE id IN (SELECT copy FROM restore_copies)").rowcount

    # 4. the history from the backup
    skills = conn.execute(
        """INSERT INTO job_skills (job_id, skill_id) SELECT r.job_id, r.skill_id FROM restore_job_skills r
           WHERE EXISTS (SELECT 1 FROM skills s WHERE s.id = r.skill_id) ON CONFLICT DO NOTHING"""
    ).rowcount
    saved = conn.execute(
        """INSERT INTO saved_jobs SELECT r.* FROM restore_saved_jobs r
           WHERE EXISTS (SELECT 1 FROM users u WHERE u.id = r.user_id) ON CONFLICT DO NOTHING"""
    ).rowcount
    events = conn.execute(
        """INSERT INTO application_events SELECT r.* FROM restore_application_events r
           WHERE EXISTS (SELECT 1 FROM users u WHERE u.id = r.user_id) ON CONFLICT DO NOTHING"""
    ).rowcount
    return {
        "postings": restored,
        "copies_replaced": removed,
        "saved_moved": moved_saved,
        "reports_moved": moved_reports,
        "events_moved": moved_events,
        "skills": skills,
        "saved_jobs": saved,
        "application_events": events,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--apply", action="store_true", help="restore (otherwise only show what it would do)")
    parser.add_argument("--dir", type=Path, default=DEFAULT_DIR, help="the backup folder")
    args = parser.parse_args()

    from tracker import db
    from tracker.cli import load_dotenv
    from tracker.config import database_url

    load_dotenv()
    backup = read_backup(args.dir)
    with db.connect(database_url()) as conn:
        if not args.apply:
            conn.read_only = True
            for key, value in plan(conn, backup).items():
                print(f"{key:22s} {value}")
            conn.rollback()
            print("\nNothing written. Run again with --apply to restore.")
            return
        counts = restore(conn, backup)
        conn.commit()
        db.refresh_signals(conn)
    for key, value in counts.items():
        print(f"{key:22s} {value}")


if __name__ == "__main__":
    main()
