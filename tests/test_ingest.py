"""The pipeline must survive a dropped database connection mid-run."""

import os

import psycopg
import pytest

from tracker import db, ingest
from tracker.models import Company, Job, JobList

COMPANIES = [Company("Alpha", "greenhouse", "alpha"), Company("Beta", "greenhouse", "beta")]


def jobs_for(company, details=True):
    return JobList([Job(external_id=f"{company.board_slug}-1", title="Software Engineer", url="u")])


@pytest.fixture
def pipeline(monkeypatch):
    monkeypatch.setattr(ingest, "load_companies", lambda: COMPANIES)
    monkeypatch.setattr(ingest, "fetch_jobs", jobs_for)


DSN = os.environ.get("TEST_DATABASE_URL")


@pytest.mark.skipif(not DSN, reason="TEST_DATABASE_URL not set")
def test_server_killing_connections_mid_run_is_survived(pipeline, monkeypatch):
    """Reproduces Neon suspending: every connection open while Beta is being
    fetched is terminated by the server, as a real idle timeout would."""
    monkeypatch.setenv("DATABASE_URL", DSN)
    with db.connect(DSN) as c:
        c.execute("DROP VIEW IF EXISTS job_signals, hiring_calendar")
        c.execute("DROP TABLE IF EXISTS job_skills, skills, jobs, companies, ingest_runs CASCADE")

    def fetch_and_kill_connections(company, details=True):
        if company.name == "Beta":
            with psycopg.connect(DSN, autocommit=True) as admin:
                admin.execute(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = current_database() AND pid <> pg_backend_pid()"
                )
        return jobs_for(company)

    monkeypatch.setattr(ingest, "fetch_jobs", fetch_and_kill_connections)
    stats = ingest.run()
    assert stats["companies_ok"] == 2 and stats["companies_failed"] == 0

    with db.connect(DSN) as c:
        assert c.execute("SELECT count(*) FROM jobs").fetchone()[0] == 2
        run = c.execute("SELECT companies_ok, finished_at IS NOT NULL FROM ingest_runs").fetchone()
        assert run == (2, True)


class FakeConn:
    def __init__(self, fail):
        self.fail = fail

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, *a, **k):
        return self


def test_write_retries_once_then_counts_company_as_failed(pipeline, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake")
    attempts = {"Alpha": 0, "Beta": 0}

    monkeypatch.setattr(ingest.db, "connect", lambda dsn: FakeConn(False))
    monkeypatch.setattr(ingest.db, "apply_schema", lambda conn: None)
    monkeypatch.setattr(ingest.db, "start_run", lambda conn, started: 1)
    monkeypatch.setattr(ingest.db, "finish_run", lambda conn, run_id, stats: None)
    monkeypatch.setattr(ingest.db, "upsert_company", lambda conn, company: company.name)

    def save(conn, company_name, jobs, run_started, close_missing=True):
        attempts[company_name] += 1
        if company_name == "Alpha" and attempts["Alpha"] == 1:
            raise psycopg.OperationalError("the connection is lost")  # recovers on retry
        if company_name == "Beta":
            raise psycopg.OperationalError("server closed the connection")  # never recovers
        return (1, 0)

    monkeypatch.setattr(ingest.db, "save_company_jobs", save)
    stats = ingest.run()
    assert attempts == {"Alpha": 2, "Beta": 2}
    assert stats["companies_ok"] == 1 and stats["companies_failed"] == 1
