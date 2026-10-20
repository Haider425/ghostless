"""Ghostless stores tech roles at any level and student roles in any field, on
every save path. A stored posting the filter would drop is never taken for
closed while its source still lists it.

The database tests run in CI (a Postgres service) and skip without
TEST_DATABASE_URL."""

import os
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from tests.conftest import reset_database
from tracker import db, health, ingest
from tracker.classify import enrich, keep_relevant, title_worth_storing
from tracker.discovery import run as discovery
from tracker.discovery.lists import JobList as ListSource
from tracker.discovery.lists import ListedJob
from tracker.models import Company, Job, JobList
from tracker.sources import boards, common, http
from tracker.sources.http import Validators

DSN = os.environ.get("TEST_DATABASE_URL")
needs_db = pytest.mark.skipif(not DSN, reason="TEST_DATABASE_URL not set")

DAY1 = datetime(2026, 10, 1, tzinfo=timezone.utc)
DAY2 = DAY1 + timedelta(days=1)


def job(external_id, title):
    return enrich(Job(external_id=external_id, title=title, url=f"https://x.example/{external_id}"), [])


TECH = "Software Engineer"
STUDENT = "Finance Intern - Summer 2027"
OTHER = "Branch Teller"


# ---------- without a database ----------


@pytest.mark.parametrize(
    "title, stored",
    [
        (TECH, True),
        ("Senior Data Engineer", True),
        (STUDENT, True),
        ("Co-op, Marketing (Winter 2027)", True),
        ("2027 Leadership Development Program - Supply Chain", True),
        ("Stagiaire Contrôle de gestion (H/F)", True),
        (OTHER, False),
        ("Senior Accountant", False),
    ],
)
def test_title_test_matches_the_full_test(title, stored):
    assert title_worth_storing(title) is stored
    assert (job("1", title).role_type != "other" or job("1", title).level in ("intern", "new_grad")) is stored


def test_keep_relevant_remembers_everything_the_source_listed():
    fetched = JobList([job("a", TECH), job("b", OTHER), job("c", STUDENT)], complete=False, total=9)
    kept = keep_relevant(fetched)
    assert [j.external_id for j in kept] == ["a", "c"]
    assert kept.listed == frozenset({"a", "b", "c"})
    assert (kept.complete, kept.total) == (False, 9)
    assert keep_relevant(kept).listed == kept.listed  # filtering twice changes nothing
    assert keep_relevant([job("x", OTHER)]).listed == frozenset({"x"})  # a plain list works too


def test_sources_skip_descriptions_of_postings_that_wont_be_stored(monkeypatch):
    items = [("a", TECH, "Toronto"), ("b", OTHER, "Toronto"), ("c", STUDENT, "Toronto")]
    assert common.plan_details(items, frozenset()) == {"a", "c"}

    listing = [
        {"id": i, "title": t, "updated_at": "2026-10-01T10:00:00Z", "location": {"name": "Toronto"}}
        for i, t in ((1, TECH), (2, OTHER), (3, STUDENT))
    ]
    asked = []

    def fake_json(url):
        asked.append(url)
        key = int(url.split("/jobs/")[1].split("?")[0])
        return {**next(i for i in listing if i["id"] == key), "content": "&lt;p&gt;text&lt;/p&gt;"}

    monkeypatch.setattr(http, "get_json_if_changed", lambda url, cached=None: ({"jobs": listing}, None))
    monkeypatch.setattr(http, "get_json", fake_json)
    jobs = boards.fetch_greenhouse(Company("Acme", "greenhouse", "acme"))
    assert [u.split("/jobs/")[1].split("?")[0] for u in asked] == ["1", "3"]
    assert [j.external_id for j in jobs] == ["1", "2", "3"]  # still listed, so closure tracking sees it
    assert [bool(j.description) for j in jobs] == [True, False, True]


# ---------- against a database (CI) ----------


@pytest.fixture
def conn():
    with db.connect(DSN) as c:
        reset_database(c)
        db.apply_schema(c)
        c.commit()
        yield c


def stored_before_the_filter(conn, company: Company, titles: dict[str, str]) -> int:
    """Postings saved by the old code, which stored everything."""
    company_id = db.upsert_company(conn, company)
    db.save_company_jobs(conn, company_id, [job(k, t) for k, t in titles.items()], DAY1)
    conn.commit()
    return company_id


def open_ids(conn, company_id):
    return sorted(
        r[0]
        for r in conn.execute(
            "SELECT external_id FROM jobs WHERE company_id = %s AND is_active", (company_id,)
        )
    )


@needs_db
def test_a_listed_posting_the_filter_drops_stays_open(conn):
    company_id = stored_before_the_filter(
        conn, Company("Bank", "greenhouse", "bank"), {"t": TECH, "o": OTHER, "g": TECH}
    )
    # day 2: the teller is still listed, the second tech role is gone, a new teller is posted
    fetched = keep_relevant(JobList([job("t", TECH), job("o", OTHER), job("o2", OTHER)]))
    new, closed = db.save_company_jobs(conn, company_id, fetched, DAY2)
    assert (new, closed) == (0, 1)
    assert open_ids(conn, company_id) == ["o", "t"]  # o2 isn't stored; o isn't closed
    seen = conn.execute("SELECT last_seen FROM jobs WHERE external_id = 'o'").fetchone()[0]
    assert seen == DAY2  # seen in this run, so not counted as missing later either


@needs_db
def test_a_board_of_mostly_filtered_postings_does_not_trip_the_guard(conn):
    health.current.reset()
    titles = {f"o{i}": OTHER for i in range(30)} | {f"t{i}": TECH for i in range(5)}
    company_id = stored_before_the_filter(conn, Company("Bank", "greenhouse", "bank"), titles)
    # the site still lists all 30 tellers and 4 of the 5 tech roles: only 4 are kept
    fetched = keep_relevant(
        JobList([job(k, OTHER) for k in titles if k.startswith("o")] + [job(f"t{i}", TECH) for i in range(4)])
    )
    new, closed = db.save_company_jobs(conn, company_id, fetched, DAY2)
    assert closed == 1 and health.current.report()["guarded"] == []
    assert len(open_ids(conn, company_id)) == 34


@needs_db
def test_tech_roles_gone_from_a_board_of_filtered_postings_still_close(conn):
    health.current.reset()
    company_id = stored_before_the_filter(
        conn, Company("Bank", "greenhouse", "bank"), {f"t{i}": TECH for i in range(5)}
    )
    fetched = keep_relevant(JobList([job(f"o{i}", OTHER) for i in range(200)]))  # 200 listed, none stored
    assert db.save_company_jobs(conn, company_id, fetched, DAY2) == (0, 5)
    assert health.current.report()["guarded"] == []  # the site answered in full: not a failed load
    assert conn.execute("SELECT count(*) FROM jobs").fetchone()[0] == 5  # no tellers inserted


@needs_db
def test_configured_companies_are_filtered(conn, monkeypatch):
    company = Company("Bank", "greenhouse", "bank")
    company_id = stored_before_the_filter(conn, company, {"o": OTHER})
    monkeypatch.setenv("DATABASE_URL", DSN)
    monkeypatch.setattr(ingest, "load_companies", lambda: [company])
    monkeypatch.setattr(ingest, "board_state", lambda dsn, c: (None, {}))
    monkeypatch.setattr(
        ingest,
        "fetch_jobs",
        lambda c, **kw: JobList([job("t", TECH), job("o", OTHER), job("s", STUDENT), job("o2", OTHER)]),
    )
    ingest.run(only="Bank")
    assert open_ids(conn, company_id) == ["o", "s", "t"]
    assert conn.execute("SELECT count(*) FROM jobs WHERE external_id = 'o2'").fetchone()[0] == 0


@needs_db
@pytest.mark.parametrize("registered", [True, False], ids=["existing board", "new board"])
def test_discovered_boards_are_filtered(conn, monkeypatch, registered):
    company = Company("Startup", "lever", "startup", origin="discovered")
    conn.execute(
        "INSERT INTO discovered_boards (platform, board_slug, company_name, last_ok) VALUES ('lever', 'startup', 'Startup', %s)",
        (DAY1 if registered else None,),
    )
    conn.commit()
    if registered:
        stored_before_the_filter(conn, company, {"o": OTHER})
    monkeypatch.setattr(ingest, "board_state", lambda dsn, c: (None, {}))
    monkeypatch.setattr(
        discovery, "fetch_board", lambda c, **kw: JobList([job("t", TECH), job("o", OTHER), job("o2", OTHER)])
    )
    assert discovery._crawl_one(DSN, company, DAY2) == (1, 1, 0)  # one posting kept and new, none closed
    company_id = conn.execute("SELECT id FROM companies WHERE board_slug = 'startup'").fetchone()[0]
    assert open_ids(conn, company_id) == (["o", "t"] if registered else ["t"])


@needs_db
def test_the_weekly_full_read_never_closes_listed_filtered_postings(conn):
    company_id = stored_before_the_filter(
        conn,
        Company("Bank", "workday", "bank.wd3.myworkdayjobs.com/External", origin="discovered"),
        {"/job/o": OTHER, "/job/t": TECH, "/job/s": STUDENT},
    )
    # the full listing has the teller and the intern; the tech role has gone
    closed = db.close_missing_postings(conn, company_id, {"/job/o", "/job/s", "/job/new-teller"}, DAY2)
    assert closed == 1 and open_ids(conn, company_id) == ["/job/o", "/job/s"]
    assert conn.execute("SELECT count(*) FROM jobs").fetchone()[0] == 3  # nothing inserted


def entry(id, title, level=None, category=None):
    return ListedJob(
        list_name="Test list",
        id=id,
        company="Listed Co",
        title=title,
        url=f"https://careers.listed.example/{id}",
        locations=["Toronto, ON"],
        posted_at=DAY1,
        terms=[],
        category=category,
        level=level,
    )


@needs_db
def test_list_only_postings_are_filtered(conn, monkeypatch):
    lists = [ListSource("owner/list")]
    company = Company("Listed Co", "list", "list:listed", origin="list")
    company_id = stored_before_the_filter(conn, company, {"2": OTHER})
    monkeypatch.setattr(
        discovery,
        "fetch_list",
        lambda job_list: [
            entry("1", TECH),
            entry("2", OTHER),
            entry("3", OTHER),
            entry("4", "Analyst", level="new_grad"),
        ],
    )
    stats = dict(jobs_seen=0, jobs_new=0, jobs_closed=0)
    discovery.run(DSN, [], lists, DAY2, stats, crawl=False)
    assert open_ids(conn, company_id) == ["1", "2", "4"]  # 3 not stored; 2 still listed, so open

    # a company whose entries are all filtered out isn't created
    monkeypatch.setattr(
        discovery,
        "fetch_list",
        lambda job_list: [
            entry("1", TECH),
            entry("2", OTHER),
            replace(entry("9", OTHER), company="Shop Co", url="https://shop.example/9"),
        ],
    )
    discovery.run(DSN, [], lists, DAY2 + timedelta(days=1), stats, crawl=False)
    assert conn.execute("SELECT count(*) FROM companies WHERE name = 'Shop Co'").fetchone()[0] == 0


@needs_db
def test_an_unchanged_board_keeps_its_filtered_postings_open(conn):
    company = Company("Bank", "greenhouse", "bank")
    company_id = stored_before_the_filter(conn, company, {"o": OTHER, "t": TECH})
    url = boards.board_url(company)
    db.store_validators(conn, url, Validators(url, '"v1"'), "r")
    assert db.mark_unchanged(conn, company, url, DAY2) == 2
    assert open_ids(conn, company_id) == ["o", "t"]
