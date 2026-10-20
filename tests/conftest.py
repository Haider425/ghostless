import pytest
import requests

from tracker.sources import http


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Tests must never hit real sites: fail loudly if anything tries."""

    def blocked(*args, **kwargs):
        raise AssertionError("a test tried to make a real HTTP request")

    monkeypatch.setattr(requests, "request", blocked)
    monkeypatch.setattr(requests.Session, "request", blocked)
    monkeypatch.setattr(requests, "get", blocked)
    monkeypatch.setattr(http, "throttle", http.Throttle(0, {}, sleep=lambda s: None))


def reset_database(conn) -> None:
    """Drop every Ghostless object (views first, they depend on the tables)."""
    conn.execute("DROP MATERIALIZED VIEW IF EXISTS job_signals_mv")
    conn.execute("DROP VIEW IF EXISTS job_signals, hiring_calendar")
    conn.execute(
        "DROP TABLE IF EXISTS http_cache, application_events, events, reports, resumes, saved_jobs, email_tokens, oauth_accounts, sessions, users, discovered_boards, "
        "job_skills, skills, jobs, companies, ingest_runs CASCADE"
    )
    conn.commit()
