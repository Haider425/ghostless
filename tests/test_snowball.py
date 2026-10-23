"""Discovery that grows by itself (stage B1, B4): links to boards, candidates
and their checks, and a company found on two platforms. Database tests run in
CI and skip without TEST_DATABASE_URL."""

import json
import os
from datetime import datetime, timedelta, timezone

import pytest

from tests.conftest import reset_database
from tracker import db
from tracker.discovery import run as discovery
from tracker.discovery import snowball
from tracker.discovery.boards import board_links, career_site
from tracker.discovery.dedupe import merge_duplicates
from tracker.models import Company, Job, JobList
from tracker.sources import http
from tracker.sources.http import FetchError

DSN = os.environ.get("TEST_DATABASE_URL")
needs_db = pytest.mark.skipif(not DSN, reason="TEST_DATABASE_URL not set")


@pytest.fixture(autouse=True)
def fresh(monkeypatch):
    snowball.noted.take()
    for name in ("GHOSTLESS_SNOWBALL", "GHOSTLESS_JSONLD"):
        monkeypatch.delenv(name, raising=False)


# ---------- links ----------


def test_board_links_for_every_platform():
    text = (
        "Apply at https://jobs.lever.co/Acme/123, or https://job-boards.greenhouse.io/acme/jobs/9. "
        "Also (https://jobs.ashbyhq.com/Acme/uuid) and "
        "https://acme.wd3.myworkdayjobs.com/en-US/External/job/Toronto/SWE_R1; "
        "not https://www.linkedin.com/jobs/view/1 or https://careers.acme.example/jobs/1."
    )
    assert board_links(text) == {
        ("lever", "acme"),
        ("greenhouse", "acme"),
        ("ashby", "Acme"),
        ("workday", "acme.wd3.myworkdayjobs.com/External"),
    }
    assert board_links("") == set()


@pytest.mark.parametrize(
    "url, site",
    [
        ("https://careers.acme.example/jobs/123-software-engineer", "careers.acme.example/jobs"),
        ("https://acme.example/en/careers/positions/42?src=list", "acme.example/en/careers/positions"),
        ("https://jobs.acme.example/42", "jobs.acme.example"),
        (
            "https://careers.formlabs.example/job/8196515/software-engineer",
            "careers.formlabs.example/job",
        ),  # not the id
        ("https://acme.example/careers/3f2a9c1e-77aa-4b1e-9d1a-1234567890ab/apply", "acme.example/careers"),
        ("https://acme.example/", None),  # a home page
        ("https://www.linkedin.com/jobs/view/1", None),  # never read
        ("https://ca.indeed.com/viewjob?jk=1", None),
        ("https://acme.icims.com/jobs/1/job", None),  # a shared hiring system
        ("https://jobs.smartrecruiters.com/Acme/1", None),
        ("https://tql.avature.net/en_US/careers/JobDetail/Driver/123", None),
        ("https://xanterra.jibeapply.com/jobs/1234", None),
        (
            "https://apply.deloitte.example/en_US/careers/JobDetail/Government-Services-Delivery-Analyst/300",
            "apply.deloitte.example/en_US/careers/JobDetail",
        ),
        ("http://localhost:8000/jobs/1", None),
    ],
)
def test_career_sites(url, site):
    assert career_site(url) == site


def test_nothing_is_noted_while_switched_off():
    company = Company("Acme", "apple", "x")
    snowball.note_postings(company, [Job("1", "SWE", "https://jobs.lever.co/other/1")])
    snowball.note_list_entry("Acme", "https://careers.acme.example/jobs/1", "List")
    assert snowball.noted.take() == []


def test_postings_note_the_boards_they_link_to(monkeypatch):
    monkeypatch.setenv("GHOSTLESS_SNOWBALL", "1")
    company = Company("Acme", "lever", "acme")
    jobs = [
        Job(
            "1",
            "SWE",
            "https://jobs.lever.co/acme/1",
            description="Our sister company: https://jobs.lever.co/beta-labs",
        ),
        Job("2", "SWE", "https://boards.greenhouse.io/acme/jobs/2"),
    ]
    snowball.note_postings(company, jobs)
    found = {(c.platform, c.board_slug): c for c in snowball.noted.take()}
    assert set(found) == {("lever", "beta-labs"), ("greenhouse", "acme")}  # not its own board
    assert found[("greenhouse", "acme")].company_name == "Acme"  # its own board elsewhere
    assert found[("lever", "beta-labs")].company_name == "Beta Labs"


def test_list_entries_note_career_sites(monkeypatch):
    monkeypatch.setenv("GHOSTLESS_JSONLD", "1")
    snowball.note_list_entry("Iris", "https://careers.iris.example/jobs/2", "List")
    snowball.note_list_entry("Acme", "https://jobs.lever.co/acme/1", "List")  # the lists step handles these
    [candidate] = snowball.noted.take()
    assert (candidate.platform, candidate.board_slug, candidate.sample_url) == (
        "jsonld",
        "careers.iris.example/jobs",
        "https://careers.iris.example/jobs/2",
    )


# ---------- checking a candidate: one request ----------


def posting_page(title):
    return (
        f'<script type="application/ld+json">{json.dumps({"@type": "JobPosting", "title": title})}</script>'
    )


@pytest.mark.parametrize(
    "platform, answer, outcome",
    [
        ("greenhouse", {"jobs": [{"title": "Software Engineer", "company_name": "Acme Inc"}]}, "active"),
        ("greenhouse", {"jobs": [{"title": "Branch Teller"}]}, "empty"),  # nothing worth storing
        ("lever", [{"text": "Finance Intern"}], "active"),
        ("ashby", {"jobs": [{"title": "Data Engineer", "isListed": False}]}, "empty"),
        ("lever", FetchError("not found (404)"), "failed"),
    ],
)
def test_checks_of_hiring_system_boards(monkeypatch, platform, answer, outcome):
    def fake(url):
        if isinstance(answer, Exception):
            raise answer
        return answer

    monkeypatch.setattr(http, "get_json", fake)
    result = snowball.check(platform, "acme", None)
    assert result.outcome == outcome
    if outcome == "active" and platform == "greenhouse":
        assert result.name == "Acme Inc"


@pytest.mark.parametrize(
    "page, outcome",
    [
        (posting_page("Software Engineer"), "active"),
        (posting_page("Branch Teller"), "empty"),
        ("<html>no structured data</html>", "failed"),
        (posting_page("SWE") + '<a href="https://jobs.lever.co/acme">Apply</a>', "replaced"),
    ],
)
def test_checks_of_career_sites(monkeypatch, page, outcome):
    monkeypatch.setattr(http, "get_text", lambda url: page)
    result = snowball.check("jsonld", "careers.acme.example/jobs", "https://careers.acme.example/jobs/1")
    assert result.outcome == outcome
    if outcome == "replaced":
        assert result.replaced_by == ("lever", "acme")


# ---------- against a database (CI) ----------


@pytest.fixture
def conn():
    with db.connect(DSN) as c:
        reset_database(c)
        db.apply_schema(c)
        c.commit()
        yield c


def states(conn):
    return dict(conn.execute("SELECT board_slug, state FROM discovered_boards").fetchall())


@needs_db
def test_candidates_are_registered_once_and_never_crawled_before_their_check(conn, monkeypatch):
    conn.execute(
        "INSERT INTO discovered_boards (platform, board_slug, company_name) VALUES ('lever', 'Known', 'Known')"
    )
    db.upsert_company(conn, Company("Gamma", "greenhouse", "gamma"))
    conn.commit()
    for c in (
        snowball.Candidate("lever", "known", "Known", "x"),  # already known, any spelling
        snowball.Candidate("lever", "beta", "Beta", "x", "https://jobs.lever.co/beta/1"),
        snowball.Candidate(
            "jsonld", "careers.gamma.example/jobs", "Gamma", "x", "https://careers.gamma.example/jobs/1"
        ),
        snowball.Candidate(
            "jsonld", "careers.iris.example/jobs", "Iris", "x", "https://careers.iris.example/jobs/1"
        ),
    ):
        snowball.noted.add(c)
    assert snowball.register(DSN) == 2  # Gamma is already read through Greenhouse
    assert states(conn) == {"Known": "active", "beta": "candidate", "careers.iris.example/jobs": "candidate"}

    crawled = []
    monkeypatch.setattr(discovery, "_crawl_one", lambda dsn, c, *a, **k: crawled.append(c.board_slug))
    discovery.crawl_boards(DSN, datetime.now(timezone.utc), dict(jobs_seen=0, jobs_new=0, jobs_closed=0))
    assert crawled == ["Known"]


@needs_db
def test_candidate_states(conn, monkeypatch):
    monkeypatch.setenv("GHOSTLESS_SNOWBALL", "1")
    monkeypatch.setenv("GHOSTLESS_JSONLD", "1")
    rows = [
        ("lever", "good", None),
        ("lever", "quiet", None),
        ("lever", "broken", None),
        ("jsonld", "careers.delta.example/jobs", "https://careers.delta.example/jobs/1"),
    ]
    for platform, slug, sample in rows:
        conn.execute(
            """INSERT INTO discovered_boards (platform, board_slug, company_name, sample_url, state)
               VALUES (%s, %s, %s, %s, 'candidate')""",
            (platform, slug, slug, sample),
        )
    conn.commit()
    answers = {
        "good": snowball.Check("active"),
        "quiet": snowball.Check("empty"),
        "broken": snowball.Check("failed"),
        "careers.delta.example/jobs": snowball.Check("replaced", replaced_by=("greenhouse", "delta")),
    }
    monkeypatch.setattr(snowball, "check", lambda platform, slug, sample: answers[slug])

    counts = snowball.verify(DSN)
    assert (counts["active"], counts["empty"], counts["failed"], counts["replaced"]) == (1, 1, 1, 1)
    assert states(conn) == {
        "good": "active",
        "quiet": "empty",
        "broken": "candidate",
        "careers.delta.example/jobs": "replaced",
        "delta": "candidate",  # the site's hiring system, to be checked next
    }
    due = dict(conn.execute("SELECT board_slug, next_due - now() FROM discovered_boards").fetchall())
    assert due["good"] < timedelta(minutes=1)  # read on this run's crawl
    assert (
        timedelta(days=29) < due["quiet"] <= timedelta(days=30, hours=1)
    )  # in a month (an hour of slack for a clock change)

    for _ in range(2):  # a board that keeps failing is dead after three checks
        conn.execute("UPDATE discovered_boards SET next_due = now() - interval '1 minute'")
        conn.commit()
        snowball.verify(DSN)
    assert states(conn)["broken"] == "dead"


@needs_db
def test_results_are_saved_over_one_connection_in_batches(conn, monkeypatch):
    monkeypatch.setenv("GHOSTLESS_SNOWBALL", "1")
    monkeypatch.setattr(snowball, "RECORD_BATCH", 2)
    for i in range(5):
        conn.execute(
            "INSERT INTO discovered_boards (platform, board_slug, company_name, state)"
            " VALUES ('lever', %s, %s, 'candidate')",
            (f"co{i}", f"co{i}"),
        )
    conn.commit()
    monkeypatch.setattr(snowball, "check", lambda *a: snowball.Check("active"))
    opened = []
    real_connect = db.connect
    monkeypatch.setattr(snowball.db, "connect", lambda dsn: opened.append(dsn) or real_connect(dsn))

    assert snowball.verify(DSN)["active"] == 5
    assert len(opened) == 2  # one to choose the candidates, one for every result
    assert set(states(conn).values()) == {"active"}


@needs_db
def test_candidates_not_checked_in_time_wait_for_the_next_run(conn, monkeypatch):
    monkeypatch.setenv("GHOSTLESS_SNOWBALL", "1")
    for slug in ("one", "two"):
        conn.execute(
            "INSERT INTO discovered_boards (platform, board_slug, company_name, state)"
            " VALUES ('lever', %s, %s, 'candidate')",
            (slug, slug),
        )
    conn.commit()
    monkeypatch.setattr(snowball, "check", lambda *a: pytest.fail("no time left: nothing is checked"))
    monkeypatch.setattr(snowball.settings, "verify_minutes", lambda: 0)  # the budget is already spent

    counts = snowball.verify(DSN)
    assert counts["checked"] == 0 and counts["deferred"] == 2
    assert states(conn) == {"one": "candidate", "two": "candidate"}
    assert (
        conn.execute("SELECT count(*) FROM discovered_boards WHERE next_due IS NOT NULL").fetchone()[0] == 0
    )


@needs_db
def test_checks_are_switched_off_by_default(conn, monkeypatch):
    conn.execute(
        "INSERT INTO discovered_boards (platform, board_slug, company_name, state) VALUES ('lever', 'x', 'x', 'candidate')"
    )
    conn.commit()
    monkeypatch.setattr(snowball, "check", lambda *a: pytest.fail("nothing is checked while switched off"))
    assert snowball.verify(DSN)["checked"] == 0


@needs_db
def test_a_career_site_is_read_through_the_pipeline(conn, monkeypatch):
    company = Company("Iris", "jsonld", "careers.iris.example/jobs", origin="discovered")
    conn.execute(
        "INSERT INTO discovered_boards (platform, board_slug, company_name) VALUES ('jsonld', %s, 'Iris')",
        (company.board_slug,),
    )
    conn.commit()
    day1 = datetime(2026, 10, 1, tzinfo=timezone.utc)

    def site(read):
        def fetch(c, known=frozenset(), stored=None):
            jobs = JobList([Job(k, t, f"https://{k}") for k, t in read])
            jobs.listed = frozenset(k for k, _ in read) | {"careers.iris.example/jobs/unread"}
            return jobs

        return fetch

    monkeypatch.setattr(
        discovery,
        "fetch_jsonld",
        site(
            [
                ("careers.iris.example/jobs/1", "Firmware Intern"),
                ("careers.iris.example/jobs/2", "Branch Teller"),
            ]
        ),
    )
    assert discovery._crawl_one(DSN, company, day1) == (1, 1, 0)  # the teller isn't stored
    company_id = conn.execute("SELECT id FROM companies WHERE platform = 'jsonld'").fetchone()[0]

    # the next day the intern page left the sitemap: it closes
    monkeypatch.setattr(
        discovery, "fetch_jsonld", site([("careers.iris.example/jobs/3", "Software Engineer")])
    )
    assert discovery._crawl_one(DSN, company, day1 + timedelta(days=1)) == (1, 1, 1)
    open_now = conn.execute(
        "SELECT external_id FROM jobs WHERE company_id = %s AND is_active", (company_id,)
    ).fetchall()
    assert open_now == [("careers.iris.example/jobs/3",)]


@needs_db
def test_a_company_on_a_hiring_system_and_a_career_site_keeps_the_hiring_system(conn):
    day = datetime(2026, 10, 1, tzinfo=timezone.utc)
    ats = db.upsert_company(conn, Company("Iris Robotics", "greenhouse", "iris"))
    site = db.upsert_company(
        conn, Company("Iris Robotics Inc.", "jsonld", "careers.iris.example/jobs", origin="discovered")
    )
    conn.execute(
        "INSERT INTO discovered_boards (platform, board_slug, company_name) VALUES ('jsonld', 'careers.iris.example/jobs', 'Iris')"
    )
    db.save_company_jobs(conn, ats, [Job("g1", "Firmware Intern", "https://g/1")], day)
    db.save_company_jobs(
        conn,
        site,
        [Job("s1", "Firmware intern", "https://s/1"), Job("s2", "Only on the site", "https://s/2")],
        day,
    )
    user = conn.execute(
        "INSERT INTO users (email, name) VALUES ('a@example.com', 'A') RETURNING id"
    ).fetchone()[0]
    site_copy = conn.execute("SELECT id FROM jobs WHERE external_id = 's1'").fetchone()[0]
    conn.execute(
        "INSERT INTO saved_jobs (user_id, job_id, status) VALUES (%s, %s, 'applied')", (user, site_copy)
    )
    conn.commit()

    result = merge_duplicates(conn)
    conn.commit()
    assert result["sites"] == 1
    kept = conn.execute("SELECT external_id, is_active FROM jobs ORDER BY external_id").fetchall()
    assert kept == [("g1", True), ("s2", False)]  # the match removed, the rest closed, not deleted
    assert conn.execute(
        "SELECT j.external_id FROM saved_jobs s JOIN jobs j ON j.id = s.job_id"
    ).fetchone() == ("g1",)
    assert states(conn) == {"careers.iris.example/jobs": "replaced"}
    assert (
        merge_duplicates(conn)["sites"] == 1 and conn.execute("SELECT count(*) FROM jobs").fetchone()[0] == 2
    )
