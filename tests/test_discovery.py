"""Discovery: public job lists and the job boards their links lead to."""

import os
from datetime import datetime, timedelta, timezone

import pytest

from tests.conftest import reset_database
from tracker import db
from tracker.classify import is_canada, parse_terms
from tracker.discovery import run as discovery
from tracker.discovery.boards import board_from_url, company_key
from tracker.discovery.lists import JobList, ListedJob, parse_simplify
from tracker.models import Company, Job
from tracker.models import JobList as Jobs

DSN = os.environ.get("TEST_DATABASE_URL")
needs_db = pytest.mark.skipif(not DSN, reason="TEST_DATABASE_URL not set")


@pytest.mark.parametrize(
    "url, expected",
    [
        ("https://job-boards.greenhouse.io/figma/jobs/5555", ("greenhouse", "figma")),
        ("https://boards.greenhouse.io/embed/job_app?for=Stripe&token=1", ("greenhouse", "stripe")),
        ("https://jobs.lever.co/palantir/abc?lever-source=x", ("lever", "palantir")),
        ("https://jobs.ashbyhq.com/ramp/uuid/application", ("ashby", "ramp")),
        (
            "https://acme.wd3.myworkdayjobs.com/en-US/External/job/Toronto/SWE_R1",
            ("workday", "acme.wd3.myworkdayjobs.com/External"),
        ),
        ("https://careers.example.com/job/1", None),
        ("not a url", None),
    ],
)
def test_board_from_url(url, expected):
    assert board_from_url(url) == expected


def test_company_names_match_loosely():
    assert company_key("Stripe, Inc.") == company_key("stripe") == "stripe"
    assert company_key("Royal Bank of Canada") != company_key("Bank of Canada")


def test_parse_simplify_keeps_open_visible_entries():
    data = [
        {
            "id": "a",
            "company_name": "Acme",
            "title": "Software Engineer Intern",
            "url": "https://jobs.lever.co/acme/1",
            "locations": ["Toronto, ON"],
            "active": True,
            "is_visible": True,
            "date_posted": 1792281600,
            "terms": ["Summer 2027", "N/A"],
            "category": "Software",
        },
        {"id": "b", "company_name": "Closed", "title": "x", "url": "https://x.example", "active": False},
        {
            "id": "c",
            "company_name": "Hidden",
            "title": "x",
            "url": "https://x.example",
            "active": True,
            "is_visible": False,
        },
        {"id": "d", "company_name": "", "title": "x", "url": "https://x.example", "active": True},
    ]
    [job] = parse_simplify(data, "Test list", level="intern")
    assert (job.company, job.terms, job.level) == ("Acme", ["Summer 2027"], "intern")
    assert job.posted_at.year == 2026


def test_seasons_and_us_namesakes():
    assert parse_terms("Software Engineer Intern (Summer 2027)") == ["Summer 2027"]
    assert parse_terms("Co-op, Winter-27") == ["Winter 2027"]
    assert is_canada("Vancouver, BC") and not is_canada("Vancouver, WA")
    assert is_canada("Seattle, WA | Toronto, ON")


# ---------- the whole step, against a database ----------


def listed(id, company, title, url, level="intern", category="Software"):
    return ListedJob(
        list_name="Test list",
        id=id,
        company=company,
        title=title,
        url=url,
        locations=["Toronto, ON"],
        posted_at=datetime(2026, 10, 1, tzinfo=timezone.utc),
        terms=["Summer 2027"],
        category=category,
        level=level,
    )


@pytest.fixture
def conn():
    with db.connect(DSN) as c:
        reset_database(c)
        db.apply_schema(c)
        c.commit()
        yield c


def fake_sources(monkeypatch, items, boards=None):
    monkeypatch.setattr(discovery, "fetch_list", lambda job_list: list(items))
    boards = boards or {}

    def board(company, details=True):
        if company.board_slug not in boards:
            from tracker.sources import FetchError

            raise FetchError("board unreachable")
        return Jobs(boards[company.board_slug])

    monkeypatch.setattr(discovery, "fetch_board", board)
    monkeypatch.setattr(discovery, "fetch_workday", lambda company, **kw: board(company))


@needs_db
def test_lists_boards_and_dedupe(conn, monkeypatch):
    now = datetime.now(timezone.utc)
    items = [
        listed("1", "Acme", "Software Developer", "https://jobs.lever.co/acme/1", level="new_grad"),
        listed(
            "2", "Iris Robotics", "Hardware Intern", "https://careers.iris.example/2", category="Hardware"
        ),
        listed("3", "Iris Robotics", "Firmware Intern", "https://careers.iris.example/3"),
        listed("4", "Configured Co", "SWE Intern", "https://jobs.lever.co/configuredco/4"),
    ]
    configured = [Company("Configured Co", "lever", "configuredco")]
    lists = [JobList("owner/list")]
    fake_sources(monkeypatch, items)  # Acme's board can't be read yet
    stats = dict(jobs_seen=0, jobs_new=0, jobs_closed=0)
    discovery.run(DSN, configured, lists, now, stats)

    boards = conn.execute("SELECT platform, board_slug, company_name FROM discovered_boards").fetchall()
    assert boards == [("lever", "acme", "Acme")]  # the configured company's board isn't rediscovered
    rows = dict(
        conn.execute(
            """SELECT j.title, j.level || '/' || j.role_type FROM jobs j JOIN companies c ON c.id = j.company_id
               WHERE c.origin = 'list' AND j.is_active"""
        ).fetchall()
    )
    # Acme's board failed, so its list entry is kept; the configured company's isn't duplicated
    assert rows == {
        "Software Developer": "new_grad/sde",  # the new grad list's level and the list's category
        "Hardware Intern": "intern/hardware",
        "Firmware Intern": "intern/hardware",
    }
    terms = conn.execute("SELECT terms, listed_in FROM jobs WHERE title = 'Hardware Intern'").fetchone()
    assert terms == (["Summer 2027"], "Test list")

    # next day: Acme's board is readable, and one Iris entry left the list
    acme_jobs = [
        Job(external_id="a1", title="Software Developer, New Grad", url="https://jobs.lever.co/acme/1")
    ]
    fake_sources(monkeypatch, items[:2] + items[3:], boards={"acme": acme_jobs})
    discovery.run(DSN, configured, lists, now + timedelta(days=1), stats)

    active = conn.execute(
        """SELECT c.origin, j.title FROM jobs j JOIN companies c ON c.id = j.company_id
           WHERE j.is_active ORDER BY c.origin, j.title"""
    ).fetchall()
    assert active == [
        ("discovered", "Software Developer, New Grad"),  # from Acme's own board now
        ("list", "Hardware Intern"),
    ]
    acme = conn.execute("SELECT origin FROM companies WHERE board_slug = 'acme'").fetchone()
    assert acme == ("discovered",)


@needs_db
def test_a_failed_list_closes_nothing(conn, monkeypatch):
    now = datetime.now(timezone.utc)
    items = [listed("1", "Iris Robotics", "Hardware Intern", "https://careers.iris.example/1")]
    fake_sources(monkeypatch, items)
    stats = dict(jobs_seen=0, jobs_new=0, jobs_closed=0)
    discovery.run(DSN, [], [JobList("owner/list")], now, stats)

    from tracker.sources import FetchError

    def down(job_list):
        raise FetchError("GitHub is down")

    monkeypatch.setattr(discovery, "fetch_list", down)
    discovery.run(DSN, [], [JobList("owner/list")], now + timedelta(days=1), stats)
    assert conn.execute("SELECT count(*) FROM jobs WHERE is_active").fetchone()[0] == 1
