"""scripts/restore_backup.py: postings from the non-tech backup that today's rules keep."""

import gzip
import importlib.util
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from tests.conftest import reset_database
from tracker import db
from tracker.models import Company, Job

_spec = importlib.util.spec_from_file_location(
    "restore_backup", Path(__file__).resolve().parents[1] / "scripts" / "restore_backup.py"
)
restore_backup = importlib.util.module_from_spec(_spec)
sys.modules["restore_backup"] = restore_backup  # dataclasses look their module up
_spec.loader.exec_module(restore_backup)

DSN = os.environ.get("TEST_DATABASE_URL")
needs_db = pytest.mark.skipif(not DSN, reason="TEST_DATABASE_URL not set")

DAY1 = datetime(2026, 9, 1, tzinfo=timezone.utc)


def test_csv_records_keep_quoted_line_breaks_and_quoting():
    text = 'id,description,department\n1,"two\nlines",\n2,"",Sales\n'
    records = list(restore_backup._records(text))
    assert records == ["id,description,department\n", '1,"two\nlines",\n', '2,"",Sales\n']


@pytest.fixture
def conn():
    with db.connect(DSN) as c:
        reset_database(c)
        db.apply_schema(c)
        c.commit()
        yield c


def export(conn, directory: Path, ids: list[int]) -> None:
    """The backup, written the way the real one was (COPY ... TO CSV)."""
    queries = {
        "jobs": "SELECT * FROM jobs WHERE id = ANY({ids})",
        "job_skills": "SELECT * FROM job_skills WHERE job_id = ANY({ids})",
        "saved_jobs": "SELECT * FROM saved_jobs WHERE job_id = ANY({ids})",
        "application_events": "SELECT * FROM application_events WHERE job_id = ANY({ids})",
    }
    directory.mkdir()
    for name, sql in queries.items():
        query = sql.format(ids=f"ARRAY[{','.join(map(str, ids))}]::bigint[]")  # ints only
        with gzip.open(directory / f"{name}.csv.gz", "wb") as out:
            with conn.cursor().copy(f"COPY ({query}) TO STDOUT WITH (FORMAT csv, HEADER true)") as copy:
                for chunk in copy:
                    out.write(chunk)
    # remove the columns added after the real backup was taken
    path = directory / "jobs.csv.gz"
    lines = gzip.open(path, "rt", encoding="utf-8", newline="").read()
    header, _, body = lines.partition("\n")
    columns = header.split(",")
    keep = [i for i, c in enumerate(columns) if c != "source_updated_at"]
    if len(keep) != len(columns):  # source_updated_at is the last column, and NULL here
        assert columns[-1] == "source_updated_at"
        body = "".join(r[: r.rstrip("\n").rfind(",")] + "\n" for r in restore_backup._records(body))
        header = ",".join(columns[:-1])
    with gzip.open(path, "wt", encoding="utf-8", newline="") as out:
        out.write(header + "\n" + body)


@needs_db
def test_restore_brings_back_postings_with_their_history(conn, tmp_path):
    company_id = db.upsert_company(conn, Company("Maison", "lever", "maison"))
    stage = Job(
        external_id="s1", title="Stagiaire Contrôle de gestion (H/F)", url="https://x/s1", level="mid"
    )
    stage.description, stage.skills = "", ["Excel"]  # an empty description, not NULL
    teller = Job(external_id="t1", title="Branch Teller", url="https://x/t1", level="mid")
    ai = Job(external_id="a1", title="Senior AI Applied Engineer", url="https://x/a1", level="senior")
    db.save_company_jobs(conn, company_id, [stage, teller, ai], DAY1)
    user = conn.execute(
        "INSERT INTO users (email, name) VALUES ('a@example.com', 'A') RETURNING id"
    ).fetchone()[0]
    ids = dict(conn.execute("SELECT external_id, id FROM jobs").fetchall())
    conn.execute(
        "INSERT INTO saved_jobs (user_id, job_id, status) VALUES (%s, %s, 'applied')", (user, ids["s1"])
    )
    conn.execute(
        "INSERT INTO application_events (user_id, job_id, status, source) VALUES (%s, %s, 'applied', 'tracker')",
        (user, ids["s1"]),
    )
    conn.execute("UPDATE jobs SET role_type = 'other'")  # how the old classifier stored them
    conn.commit()
    export(conn, tmp_path / "backup", list(ids.values()))

    # the cleanup deletes them; then the crawler stores the AI role again as a new row
    conn.execute("DELETE FROM application_events")
    conn.execute("DELETE FROM jobs")
    db.save_company_jobs(
        conn, company_id, [Job(external_id="a1", title=ai.title, url=ai.url)], DAY1 + timedelta(days=30)
    )
    copy_id = conn.execute("SELECT id FROM jobs WHERE external_id = 'a1'").fetchone()[0]
    conn.execute("INSERT INTO saved_jobs (user_id, job_id, status) VALUES (%s, %s, 'saved')", (user, copy_id))
    conn.execute(
        "INSERT INTO reports (category, message, job_id, email) VALUES ('other', 'looks fake', %s, 'r@example.com')",
        (copy_id,),
    )
    conn.commit()

    backup = restore_backup.read_backup(tmp_path / "backup")
    assert sorted(backup.labels.values()) == [("intern", "other"), ("senior", "ml")]  # not the teller

    plan = restore_backup.plan(conn, backup)
    conn.rollback()
    assert (plan["postings"], plan["copies"], plan["saved_on_copies"], plan["reports_on_copies"]) == (
        2,
        1,
        1,
        1,
    )
    assert conn.execute("SELECT count(*) FROM jobs").fetchone()[0] == 1  # planning wrote nothing

    counts = restore_backup.restore(conn, backup)
    conn.commit()
    assert counts["postings"] == 2 and counts["copies_replaced"] == 1
    assert (counts["saved_moved"], counts["reports_moved"], counts["skills"]) == (1, 1, 1)
    assert (counts["saved_jobs"], counts["application_events"]) == (1, 1)

    rows = {
        r[0]: r[1:]
        for r in conn.execute("SELECT external_id, id, first_seen, level, role_type, description FROM jobs")
    }
    assert set(rows) == {"s1", "a1"}
    assert rows["s1"] == (ids["s1"], DAY1, "intern", "other", "")  # original id, date; "" stays ""
    assert rows["a1"][:4] == (ids["a1"], DAY1, "senior", "ml")
    assert conn.execute("SELECT department FROM jobs WHERE external_id = 's1'").fetchone()[0] is None
    # the copy's newer sighting wins, and what was attached to it moved over
    assert conn.execute("SELECT last_seen FROM jobs WHERE external_id = 'a1'").fetchone()[
        0
    ] == DAY1 + timedelta(days=30)
    assert conn.execute("SELECT job_id FROM reports").fetchone()[0] == ids["a1"]
    saved = sorted(conn.execute("SELECT job_id, status FROM saved_jobs").fetchall())
    assert saved == sorted([(ids["s1"], "applied"), (ids["a1"], "saved")])
    assert conn.execute("SELECT job_id FROM application_events").fetchone()[0] == ids["s1"]
    skills = conn.execute(
        "SELECT s.name FROM job_skills js JOIN skills s ON s.id = js.skill_id WHERE js.job_id = %s",
        (ids["s1"],),
    ).fetchall()
    assert skills == [("Excel",)]

    # running it again changes nothing
    with pytest.raises(RuntimeError, match="id is in use"):
        restore_backup.restore(conn, backup)
    conn.rollback()
