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

    def board(company, details=True, **kwargs):
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
    due = conn.execute("SELECT next_due - now() FROM discovered_boards WHERE board_slug = 'acme'").fetchone()[
        0
    ]
    assert timedelta(hours=23) < due <= timedelta(days=1)  # a failed board is retried the next day
    conn.execute("UPDATE discovered_boards SET next_due = now() - interval '1 minute'")  # a day passes
    conn.commit()
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


MARKDOWN = """# Canadian Tech Internships

| Company | Role | Location | Apply | Date Posted |
|--------|------|----------|:-----:|--------------|
| D2L | Software Developer Co-op (Winter 2027) | Kitchener, ON | [![Apply](https://img.shields.io/badge/-Apply-blue)](https://www.d2l.com/careers/jobs/?job_id=1&utm_source=list) | Oct 16, 2026 |
| ↳ | Data Analyst Co-op | Waterloo, ON / Remote, Canada | [Apply](https://www.d2l.com/careers/jobs/?job_id=2) | Oct 15, 2026 |
| Motorola | Embedded Co-op | Vancouver, BC | Closed🔒 | Oct 7, 2026 |
| **Shopify** | Dev Intern | Toronto, ON | <a href="x"><img src="badge.png"></a> https://www.shopify.com/careers/1 | Sep 30, 2026 |

Some other text.
"""


def test_a_markdown_table_list():
    from tracker.discovery.lists import parse_markdown

    jobs = parse_markdown(MARKDOWN, "owner/list", level="intern")
    assert [(j.company, j.title) for j in jobs] == [
        ("D2L", "Software Developer Co-op (Winter 2027)"),
        ("D2L", "Data Analyst Co-op"),  # ↳ repeats the company
        ("Shopify", "Dev Intern"),
    ]  # the closed row is skipped
    assert jobs[0].url == "https://www.d2l.com/careers/jobs/?job_id=1&utm_source=list"
    assert jobs[1].locations == ["Waterloo, ON", "Remote, Canada"]
    assert jobs[0].posted_at.date().isoformat() == "2026-10-16"
    assert jobs[2].url == "https://www.shopify.com/careers/1"
    assert all(j.level == "intern" and j.id.startswith("url:") for j in jobs)


def test_a_jobs_json_list_and_clean_urls():
    from tracker.discovery.lists import clean_url, parse_jobs_json

    data = {
        "jobs": [
            {
                "company": "Waabi",
                "title": "Safety Intern",
                "locationText": "Toronto, ON, Canada",
                "applyUrl": "https://jobs.lever.co/waabi/480d/apply?utm_source=Simplify&ref=Simplify",
                "postedAt": "2026-10-17T01:22:13.113Z",
                "hidden": False,
            },
            {"company": "Hidden", "title": "X", "applyUrl": "https://x.example/1", "hidden": True},
            {"company": "", "title": "No company", "applyUrl": "https://x.example/2"},
        ]
    }
    [job] = parse_jobs_json(data, "owner/list")
    assert (job.company, job.locations) == ("Waabi", ["Toronto, ON, Canada"])
    assert job.posted_at.year == 2026
    assert (
        clean_url(job.url)
        == clean_url("https://jobs.lever.co/waabi/480d")
        == "https://jobs.lever.co/waabi/480d"
    )
    assert clean_url("https://a.example/j?id=3&utm_medium=x") == "https://a.example/j?id=3"


def test_boards_are_revisited_by_how_often_they_change():
    from tracker.discovery.run import next_visit_days

    assert next_visit_days(changed=True, quiet_visits=0, student_roles=0, failures=0) == 1
    # quiet boards back off: a day longer for every two quiet visits, up to a week
    assert [next_visit_days(False, q, 0, 0) for q in (1, 2, 4, 6, 20)] == [1, 2, 3, 4, 7]
    assert (
        next_visit_days(False, 20, student_roles=3, failures=0) == 2
    )  # open student roles: two days at most
    assert [next_visit_days(False, 0, 0, f) for f in (1, 2, 3, 6, 10)] == [1, 2, 4, 30, 30]


@needs_db
def test_postings_stored_twice_are_merged_and_nothing_a_person_saved_is_lost(conn):
    from tracker.discovery.boards import board_from_url
    from tracker.discovery.dedupe import merge_duplicates

    # links as the lists write them
    assert board_from_url("https://leidos.wd5.myworkdayjobs.com/en-us/External/job/x_R1") == (
        "workday",
        "leidos.wd5.myworkdayjobs.com/External",
    )
    run = datetime(2026, 10, 18, tzinfo=timezone.utc)
    url = "https://leidos.wd5.myworkdayjobs.com/External/job/Tucson-AZ/Jr-Software-Engineer-Intern_R-1"
    ids = {}
    for slug in ("External", "external", "en-us"):  # one board registered three ways
        conn.execute(
            "INSERT INTO discovered_boards (platform, board_slug, company_name, last_ok) VALUES ('workday', %s, 'Leidos', now())",
            (f"leidos.wd5.myworkdayjobs.com/{slug}",),
        )
        cid = db.upsert_company(
            conn, Company("Leidos", "workday", f"leidos.wd5.myworkdayjobs.com/{slug}", origin="discovered")
        )
        db.save_company_jobs(
            conn, cid, [Job(external_id="R-1", title="Jr Software Engineer Intern", url=url)], run
        )
        ids[slug] = conn.execute("SELECT id FROM jobs WHERE company_id = %s", (cid,)).fetchone()[0]
    listed_id = db.upsert_company(conn, Company("Leidos Inc", "list", "list:leidos", origin="list"))
    db.save_company_jobs(
        conn,
        listed_id,
        [
            Job(external_id="l1", title="Jr Software Engineer Intern", url=url + "?utm_source=Simplify"),
            Job(external_id="l2", title="Only in the list", url="https://leidos.example/careers/2"),
        ],
        run,
        guard=False,
    )
    user = conn.execute(
        "INSERT INTO users (email, name) VALUES ('a@example.com', 'A') RETURNING id"
    ).fetchone()[0]
    conn.execute(
        "INSERT INTO saved_jobs (user_id, job_id, status, notes) VALUES (%s, %s, 'applied', 'phone screen')",
        (user, ids["external"]),  # saved the copy that's about to be removed
    )
    conn.commit()

    result = merge_duplicates(conn)
    conn.commit()
    assert result["boards"] == 2 and result["companies"] == 2
    boards = conn.execute("SELECT board_slug FROM discovered_boards").fetchall()
    assert boards == [("leidos.wd5.myworkdayjobs.com/External",)]
    urls = sorted(r[0] for r in conn.execute("SELECT url FROM jobs").fetchall())
    assert urls == ["https://leidos.example/careers/2", url]  # one copy each
    saved = conn.execute("SELECT job_id, status, notes FROM saved_jobs").fetchall()
    assert saved == [(ids["External"], "applied", "phone screen")]
    assert merge_duplicates(conn) == {"boards": 0, "companies": 0, "jobs": 0, "sites": 0}  # safe to run again


@needs_db
def test_one_workday_board_is_registered_once_however_lists_spell_it(conn):
    items = [
        listed("1", "Leidos", "Intern A", "https://leidos.wd5.myworkdayjobs.com/External/job/a_R1"),
        listed("2", "Leidos", "Intern B", "https://leidos.wd5.myworkdayjobs.com/external/job/b_R2"),
        listed("3", "Leidos", "Intern C", "https://leidos.wd5.myworkdayjobs.com/en-us/EXTERNAL/job/c_R3"),
    ]
    assert discovery.register_boards(DSN, items, set(), set()) == 1
    assert discovery.register_boards(DSN, items[1:], set(), set()) == 0  # and not again on the next run
