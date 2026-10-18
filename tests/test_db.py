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