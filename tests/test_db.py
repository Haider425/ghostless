"""Integration tests against a real PostgreSQL. Skipped unless TEST_DATABASE_URL is set.

CI provides one through a Postgres service container.
"""

import os
from datetime import datetime, timedelta, timezone

import pytest

from tests.conftest import reset_database
from tracker import db
from tracker.models import Company, Job

DSN = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DSN, reason="TEST_DATABASE_URL not set")


@pytest.fixture
def conn():
    with db.connect(DSN) as c:
        reset_database(c)
        db.apply_schema(c)
        yield c


def _job(ext_id, skills=()):
    return Job(
        external_id=ext_id,
        title=f"Role {ext_id}",
        url=f"https://x/{ext_id}",
        level="new_grad",
        role_type="sde",
        skills=list(skills),
    )


def test_upsert_is_idempotent_and_tracks_closures(conn):
    company_id = db.upsert_company(conn, Company("Example", "greenhouse", "example"))
    day1 = datetime(2026, 10, 1, tzinfo=timezone.utc)
    day2 = day1 + timedelta(days=1)

    new, closed = db.save_company_jobs(conn, company_id, [_job("1", ["Python"]), _job("2")], day1)
    assert (new, closed) == (2, 0)

    # Day 2: job 1 is still posted, job 2 disappeared, job 3 is new
    new, closed = db.save_company_jobs(conn, company_id, [_job("1", ["Python", "SQL"]), _job("3")], day2)
    assert (new, closed) == (1, 1)

    active = conn.execute("SELECT external_id FROM jobs WHERE is_active ORDER BY external_id").fetchall()
    assert [r[0] for r in active] == ["1", "3"]

    first_seen = conn.execute("SELECT first_seen FROM jobs WHERE external_id = '1'").fetchone()[0]
    assert first_seen == day1  # first_seen is never overwritten

    skills = conn.execute(
        """SELECT s.name FROM job_skills js JOIN skills s ON s.id = js.skill_id
           JOIN jobs j ON j.id = js.job_id WHERE j.external_id = '1' ORDER BY s.name"""
    ).fetchall()
    assert [r[0] for r in skills] == ["Python", "SQL"]


def test_partial_listings_never_close_jobs(conn):
    company_id = db.upsert_company(conn, Company("Google", "google", "location=Canada&q=x"))
    day1 = datetime(2026, 10, 1, tzinfo=timezone.utc)
    db.save_company_jobs(conn, company_id, [_job("1"), _job("2")], day1, close_missing=False)

    new, closed = db.save_company_jobs(
        conn, company_id, [_job("1")], day1 + timedelta(days=1), close_missing=False
    )
    assert (new, closed) == (0, 0)
    assert conn.execute("SELECT count(*) FROM jobs WHERE is_active").fetchone()[0] == 2


def test_a_site_that_suddenly_returns_nothing_closes_nothing(conn, caplog):
    company_id = db.upsert_company(conn, Company("Apple", "apple", "en-ca/search"))
    day1 = datetime(2026, 10, 1, tzinfo=timezone.utc)
    db.save_company_jobs(conn, company_id, [_job(str(i)) for i in range(36)], day1)

    # the page changed or came back empty: keep the jobs open, and say so
    assert db.save_company_jobs(conn, company_id, [], day1 + timedelta(days=1)) == (0, 0)
    assert conn.execute("SELECT count(*) FROM jobs WHERE is_active").fetchone()[0] == 36
    assert "nothing was closed" in caplog.text

    # a third of the listings at once is suspicious too
    assert (
        db.save_company_jobs(conn, company_id, [_job(str(i)) for i in range(5)], day1 + timedelta(days=2))[1]
        == 0
    )

    # an ordinary drop still closes jobs
    kept = [_job(str(i)) for i in range(30)]
    assert db.save_company_jobs(conn, company_id, kept, day1 + timedelta(days=3))[1] == 6


def test_a_small_company_can_close_everything(conn):
    company_id = db.upsert_company(conn, Company("Tiny", "lever", "tiny"))
    day1 = datetime(2026, 10, 1, tzinfo=timezone.utc)
    db.save_company_jobs(conn, company_id, [_job("1"), _job("2")], day1)
    assert db.save_company_jobs(conn, company_id, [], day1 + timedelta(days=1)) == (0, 2)


def test_suspicious_drop():
    assert db.suspicious_drop(36, 0) and db.suspicious_drop(30, 9)
    assert not db.suspicious_drop(2, 0) and not db.suspicious_drop(30, 10) and not db.suspicious_drop(10, 2)


# ---------- conditional reads (http_cache) ----------

from tracker.sources.http import Validators  # noqa: E402

BOARD = Company("Example", "greenhouse", "example")
URL = "https://boards-api.greenhouse.io/v1/boards/example/jobs"


def test_migrate_runs_twice(conn):
    db.apply_schema(conn)
    db.apply_schema(conn)
    assert conn.execute("SELECT count(*) FROM http_cache").fetchone()[0] == 0


def test_validators_are_used_only_while_they_vouch_for_what_is_stored(conn):
    day1 = datetime(2026, 10, 1, tzinfo=timezone.utc)
    company_id = db.upsert_company(conn, BOARD)
    db.store_validators(conn, URL, Validators(URL, '"v1"'), "rules-a")
    assert db.cached_validators(conn, BOARD, URL, "rules-a") is None  # nothing stored for the board yet

    db.save_company_jobs(conn, company_id, [_job("1")], day1)
    assert db.cached_validators(conn, BOARD, URL, "rules-a") == Validators(URL, '"v1"')
    assert db.cached_validators(conn, BOARD, URL, "rules-b") is None  # the reading code changed

    conn.execute("UPDATE http_cache SET fetched_at = now() - interval '8 days'")
    assert db.cached_validators(conn, BOARD, URL, "rules-a") is None  # a full read is due

    db.store_validators(conn, URL, None, "rules-a")  # a response without validators
    assert conn.execute("SELECT count(*) FROM http_cache").fetchone()[0] == 0


def test_an_unchanged_board_is_seen_and_nothing_closes(conn):
    day1 = datetime(2026, 10, 1, tzinfo=timezone.utc)
    day2 = day1 + timedelta(days=1)
    company_id = db.upsert_company(conn, BOARD)
    db.save_company_jobs(conn, company_id, [_job("1"), _job("2")], day1)
    db.store_validators(conn, URL, Validators(URL, '"v1"'), "r")

    assert db.mark_unchanged(conn, BOARD, URL, day2) == 2
    rows = conn.execute("SELECT is_active, last_seen, closed_at FROM jobs ORDER BY external_id").fetchall()
    assert rows == [(True, day2, None), (True, day2, None)]

    # the next full read still closes normally: job 2 is gone on day 3
    new, closed = db.save_company_jobs(conn, company_id, [_job("1")], day2 + timedelta(days=1))
    assert (new, closed) == (0, 1)


def test_stored_versions_feed_the_greenhouse_two_step_read(conn):
    company_id = db.upsert_company(conn, BOARD)
    when = datetime(2026, 10, 15, 19, 24, 46, tzinfo=timezone.utc)
    job = _job("1")
    job.description, job.department, job.source_updated_at = "Build things.", "Engineering", when
    db.save_company_jobs(conn, company_id, [job, _job("2")], when)  # job 2 has no description: not reusable
    assert db.stored_versions(conn, BOARD) == {"1": when}  # the version only, never the text
    conn.execute("UPDATE jobs SET is_active = false WHERE external_id = '1'")
    assert db.stored_versions(conn, BOARD) == {}  # a closed posting listed again is read again


def test_stored_postings_carry_no_text_and_descriptions_are_read_only_when_asked(conn):
    company_id = db.upsert_company(conn, BOARD)
    full, summary = _job("full"), _job("summary")
    full.description = "Summary.\n\nDescription\nBuild things."
    summary.description = "Just the search summary."
    day1 = datetime(2026, 10, 1, tzinfo=timezone.utc)
    db.save_company_jobs(conn, company_id, [full, summary, _job("none")], day1)

    stored = db.stored_postings(conn, BOARD)
    assert set(stored) == {"full", "summary", "none"}
    assert stored["full"] == db.StoredPosting(full.title, full.location, True, True, True)
    assert (stored["none"].described, stored["none"].full) == (False, False)
    # Apple: a description is only full with one of its headings, checked in the database
    apple = db.stored_postings(conn, BOARD, ["\n\nDescription\n"])
    assert {k for k, s in apple.items() if s.full} == {"full"}

    assert db.stored_descriptions(conn, BOARD, ["summary", "none", "missing"]) == {
        "summary": ("Just the search summary.", summary.location)
    }
    assert db.stored_descriptions(conn, BOARD, []) == {}


# ---------- stage D: weekly full read, health ----------


def test_full_read_closes_missing_postings_at_every_level_and_adds_none(conn):
    day1 = datetime(2026, 10, 1, tzinfo=timezone.utc)
    day8 = day1 + timedelta(days=7)
    company_id = db.upsert_company(conn, Company("Bank", "workday", "bank.wd3.myworkdayjobs.com/External"))
    jobs = [_job("/job/a"), _job("/job/b"), _job("/job/c"), _job("/job/d")]
    jobs[1].level = jobs[2].level = (
        "mid"  # stored by the old broad search: a student search never closes them
    )
    db.save_company_jobs(conn, company_id, jobs, day1)

    closed = db.close_missing_postings(conn, company_id, {"/job/a", "/job/c", "/job/d", "/job/new"}, day8)
    assert closed == 1
    rows = dict(conn.execute("SELECT external_id, is_active FROM jobs").fetchall())
    assert rows == {"/job/a": True, "/job/b": False, "/job/c": True, "/job/d": True}  # /job/new not inserted
    assert conn.execute("SELECT last_seen FROM jobs WHERE external_id = '/job/a'").fetchone()[0] == day8


def test_full_read_that_looks_wrong_closes_nothing(conn):
    from tracker import health

    health.current.reset()
    day1 = datetime(2026, 10, 1, tzinfo=timezone.utc)
    company_id = db.upsert_company(conn, Company("Bank", "workday", "bank.wd3.myworkdayjobs.com/External"))
    db.save_company_jobs(conn, company_id, [_job(str(i)) for i in range(5)], day1)
    assert db.close_missing_postings(conn, company_id, set(), day1 + timedelta(days=7)) == 0
    assert conn.execute("SELECT count(*) FROM jobs WHERE is_active").fetchone()[0] == 5
    assert health.current.report()["guarded"] == [{"board": "Bank", "found": 0, "open": 5}]
    # an empty listing stays guarded even when it claims to be the whole board
    assert (
        db.close_missing_postings(conn, company_id, set(), day1 + timedelta(days=7), whole_listing=True) == 0
    )


def test_a_whole_listing_closes_a_real_drop(conn):
    """A university board whose season ended (Autodesk's /uni: 26 open, 1 listed):
    the board listed every posting it says it has, so the drop is real."""
    from tracker import health

    health.current.reset()
    day1 = datetime(2026, 10, 1, tzinfo=timezone.utc)
    company_id = db.upsert_company(conn, Company("Autodesk", "workday", "autodesk.wd1.myworkdayjobs.com/uni"))
    db.save_company_jobs(conn, company_id, [_job(f"/job/{i}") for i in range(26)], day1)
    week = day1 + timedelta(days=7)
    assert db.close_missing_postings(conn, company_id, {"/job/0"}, week) == 0  # a search's view: guarded
    assert db.close_missing_postings(conn, company_id, {"/job/0"}, week, whole_listing=True) == 25
    assert conn.execute("SELECT external_id FROM jobs WHERE is_active").fetchall() == [("/job/0",)]


def test_finish_run_stores_the_health_report(conn):
    run_id = db.start_run(conn, datetime(2026, 10, 1, tzinfo=timezone.utc))
    stats = dict(
        companies_ok=1, companies_failed=0, jobs_seen=3, jobs_new=1, jobs_closed=0, duration_seconds=2
    )
    report = {"sources": {"configured lever": {"read": 1}}, "guarded": [], "registered": 0}
    db.finish_run(conn, run_id, stats, report)
    assert conn.execute("SELECT health FROM ingest_runs WHERE id = %s", (run_id,)).fetchone()[0] == report
