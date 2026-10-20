"""The pipeline must survive a dropped database connection mid-run."""

import os

import psycopg
import pytest

from tests.conftest import reset_database
from tracker import db, ingest
from tracker.models import Company, Job, JobList

COMPANIES = [Company("Alpha", "greenhouse", "alpha"), Company("Beta", "greenhouse", "beta")]


def jobs_for(company, details=True, known=frozenset(), **kwargs):
    return JobList([Job(external_id=f"{company.board_slug}-1", title="Software Engineer", url="u")])


@pytest.fixture
def pipeline(monkeypatch):
    monkeypatch.setattr(ingest, "load_companies", lambda: COMPANIES)
    monkeypatch.setattr(ingest, "fetch_jobs", jobs_for)
    monkeypatch.setattr(ingest, "board_state", lambda dsn, company: (None, {}))


DSN = os.environ.get("TEST_DATABASE_URL")


@pytest.mark.skipif(not DSN, reason="TEST_DATABASE_URL not set")
def test_server_killing_connections_mid_run_is_survived(pipeline, monkeypatch):
    """Reproduces Neon suspending: every connection open while Beta is being
    fetched is terminated by the server, as a real idle timeout would."""
    monkeypatch.setenv("DATABASE_URL", DSN)
    with db.connect(DSN) as c:
        reset_database(c)

    def fetch_and_kill_connections(company, details=True, known=frozenset(), **kwargs):
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

    def commit(self):
        pass


def test_write_retries_once_then_counts_company_as_failed(pipeline, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake")
    attempts = {"Alpha": 0, "Beta": 0}

    monkeypatch.setattr(ingest.db, "connect", lambda dsn: FakeConn(False))
    monkeypatch.setattr(ingest.db, "apply_schema", lambda conn: None)
    monkeypatch.setattr(ingest.db, "start_run", lambda conn, started: 1)
    monkeypatch.setattr(ingest.db, "finish_run", lambda conn, run_id, stats, report=None: None)
    monkeypatch.setattr(ingest.db, "refresh_signals", lambda conn: None)
    monkeypatch.setattr(ingest.db, "upsert_company", lambda conn, company: company.name)
    monkeypatch.setattr(ingest.db, "open_count", lambda conn, company_id: 0)

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


def test_stored_descriptions_are_reused():
    jobs = JobList(
        [
            Job(external_id="a", title="Engineer", url="u", location="2 Locations"),
            Job(external_id="b", title="Engineer", url="u", location="Toronto", description="fresh"),
            Job(external_id="c", title="Engineer", url="u", location="Ottawa"),
        ]
    )
    ingest.reuse_details(jobs, {"a": ("stored", "Toronto | Montreal"), "b": ("old", "Toronto")})
    assert (jobs[0].description, jobs[0].location) == ("stored", "Toronto | Montreal")
    assert jobs[1].description == "fresh"  # fetched this run: the new text wins
    assert jobs[2].description == ""


@pytest.mark.skipif(not DSN, reason="TEST_DATABASE_URL not set")
def test_a_sharded_run_collects_its_part_and_finish_does_the_rest(monkeypatch):
    from tracker.discovery import run as discovery

    companies = [Company(f"Co{i}", "greenhouse", f"co{i}") for i in range(12)]
    monkeypatch.setattr(ingest, "load_companies", lambda: companies)
    monkeypatch.setattr(ingest, "fetch_jobs", jobs_for)
    monkeypatch.setenv("DATABASE_URL", DSN)
    with db.connect(DSN) as c:
        reset_database(c)
        db.apply_schema(c)
        c.commit()
    calls = []
    monkeypatch.setattr(discovery, "crawl_boards", lambda *a, **k: calls.append(("crawl", k.get("shard"))))
    monkeypatch.setattr(discovery, "run", lambda *a, **k: calls.append(("lists", k.get("crawl"))))
    refreshed = []
    real_refresh = db.refresh_signals
    monkeypatch.setattr(db, "refresh_signals", lambda conn: refreshed.append(1) or real_refresh(conn))

    seen = [ingest.run(shard=(k, 3))["companies_ok"] for k in (1, 2, 3)]
    assert sum(seen) == 12 and all(seen)  # every company once, spread over the parts
    assert calls == [("crawl", (1, 3)), ("crawl", (2, 3)), ("crawl", (3, 3))]  # each part crawls its boards
    assert refreshed == []  # signals wait for finish

    ingest.finish()
    assert calls[-1] == ("lists", False) and refreshed == [1]
    with db.connect(DSN) as c:
        assert c.execute("SELECT count(*) FROM jobs").fetchone()[0] == 12
