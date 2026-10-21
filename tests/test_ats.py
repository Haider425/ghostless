"""The hiring systems added in stage E, on recorded responses (trimmed copies
of real ones, 21 October 2026; Recruitee's follows its documented format).
Each is off unless named in GHOSTLESS_SOURCES."""

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pytest

from tracker.classify import enrich
from tracker.discovery import snowball
from tracker.discovery.boards import board_from_url
from tracker.models import Company, Job, JobList
from tracker.sources import FetchError, ats, fetch_jobs, http
from tracker.sources.http import Validators

FIXTURES = Path(__file__).parent / "fixtures" / "sources"


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


@pytest.fixture
def switched_on(monkeypatch):
    monkeypatch.setenv("GHOSTLESS_SOURCES", "all")


# ---------- off by default ----------


def test_every_new_source_is_off_by_default(monkeypatch):
    monkeypatch.delenv("GHOSTLESS_SOURCES", raising=False)
    for platform in ats.PLATFORMS:
        with pytest.raises(FetchError, match="switched off"):
            fetch_jobs(Company("Acme", platform, "acme"))
    assert board_from_url("https://oatly.teamtailor.com/jobs/1-x") is None
    assert snowball.check("teamtailor", "oatly", None).outcome == "failed"


@pytest.mark.parametrize(
    "url, board",
    [
        ("https://apply.workable.com/focusrite/j/E34BD57579/", ("workable", "focusrite")),
        ("https://apply.workable.com/j/E34BD57579", None),  # a job link without the company
        ("https://oatly.teamtailor.com/jobs/8401169-account-manager", ("teamtailor", "oatly")),
        ("https://www.teamtailor.com/careers", None),
        ("https://acme.jobs.personio.de/job/1834171", ("personio", "acme.jobs.personio.de")),
        ("https://forge-nano.breezy.hr/p/ef317746553f-application-engineer-i", ("breezy", "forge-nano")),
        ("https://ats.rippling.com/en-GB/apexanalytix-careers/jobs/e1eab597", ("rippling", "apexanalytix-careers")),
        ("https://acme.recruitee.com/o/backend-developer", ("recruitee", "acme")),
        ("https://jobs.smartrecruiters.com/WesternDigital/744000138191379-intern", ("smartrecruiters", "WesternDigital")),
    ],
)  # fmt: skip
def test_links_to_each_new_source(switched_on, url, board):
    assert board_from_url(url) == board


# ---------- parsing recorded responses ----------


def test_workable(switched_on, monkeypatch):
    monkeypatch.setattr(http, "get_json", lambda url: json.loads(fixture("workable.json")))
    jobs = fetch_jobs(Company("Focusrite", "workable", "focusrite"))
    assert len(jobs) == 2
    job = jobs[0]
    assert job.external_id and job.url.startswith("https://apply.workable.com/j/")
    assert "Germany" in job.location and job.description
    assert (job.employment_type, job.workplace) == ("full_time", "remote")


def test_teamtailor_reads_pages_and_answers_304(switched_on, monkeypatch):
    calls = []

    def send(method, url, payload, accept, extra=None):
        calls.append((url, extra))

        class Resp:
            status_code = 304 if extra else 200
            text = fixture("teamtailor.xml")
            headers = {"ETag": '"v1"'}

        return Resp()

    monkeypatch.setattr(http, "_send", send)
    company = Company("Oatly", "teamtailor", "oatly")
    jobs = fetch_jobs(company)
    assert len(jobs) == 2 and jobs.complete and jobs.validators.etag == '"v1"'
    assert jobs[0].location == "Stockholm, Sweden" and jobs[0].workplace == "onsite"
    assert jobs[0].description and jobs[0].posted_at.year == 2026
    again = fetch_jobs(company, cached=jobs.validators)
    assert again.not_modified and list(again) == []


def test_personio(switched_on, monkeypatch):
    def send(method, url, payload, accept, extra=None):
        class Resp:
            status_code = 200
            text = fixture("personio.xml")
            headers = {}

        return Resp()

    monkeypatch.setattr(http, "_send", send)
    [job] = fetch_jobs(Company("Personio", "personio", "personio.jobs.personio.de"))
    assert job.title == "Staff Software Engineer, Data Platform"
    assert job.url == "https://personio.jobs.personio.de/job/1834171"
    assert job.location == "Munich | Berlin" and job.employment_type == "full_time"
    assert job.min_years_experience == 7 and "The Role" in job.description


def test_breezy_reads_descriptions_from_job_pages(switched_on, monkeypatch):
    pages = []
    monkeypatch.setattr(
        http, "get_json_if_changed", lambda url, cached=None: (json.loads(fixture("breezy.json")), None)
    )
    monkeypatch.setattr(http, "get_text", lambda url: pages.append(url) or fixture("breezy_page.html"))
    jobs = fetch_jobs(Company("Forge Nano", "breezy", "forge-nano"))
    first = enrich(jobs[0], [])  # an unlabelled $ follows the posting's country
    assert (first.title, first.employment_type) == ("Application Engineer I", "full_time")
    assert (first.salary_min, first.salary_max, first.salary_currency) == (70000, 78000, "USD")
    assert first.description and "CO" in first.location
    # descriptions already stored aren't fetched again
    pages.clear()
    fetch_jobs(Company("Forge Nano", "breezy", "forge-nano"), known=frozenset(j.external_id for j in jobs))
    assert pages == []


def test_rippling_reads_each_posting_once(switched_on, monkeypatch):
    listing = json.loads(fixture("rippling.json"))
    detail = json.loads(fixture("rippling_detail.json"))
    asked = []

    def get_json(url):
        asked.append(url)
        return (
            detail if url.rsplit("/", 1)[-1] == detail["uuid"] else listing if url.endswith("/jobs") else {}
        )

    monkeypatch.setattr(http, "get_json", get_json)
    jobs = fetch_jobs(Company("apexanalytix", "rippling", "apexanalytix-careers"))
    by_id = {j.external_id: j for j in jobs}
    job = by_id[detail["uuid"]]
    assert (
        job.title == "AI Engineer" and job.location == "Noida, India" and job.employment_type == "full_time"
    )
    assert job.description and job.department
    asked.clear()
    fetch_jobs(Company("apexanalytix", "rippling", "apexanalytix-careers"), known=frozenset(by_id))
    assert asked == ["https://api.rippling.com/platform/api/ats/v1/board/apexanalytix-careers/jobs"]


def test_recruitee_documented_format(switched_on, monkeypatch):
    data = {
        "offers": [
            {
                "id": 7,
                "slug": "backend-developer",
                "title": "Backend Developer",
                "description": "<p>Build APIs.</p>",
                "requirements": "<ul><li>3+ years of experience</li></ul>",
                "location": "Amsterdam, Netherlands",
                "remote": False,
                "employment_type_code": "fulltime",
                "careers_url": "https://acme.recruitee.com/o/backend-developer",
                "published_at": "2026-10-01 10:00:00 UTC",
            }
        ]
    }
    monkeypatch.setattr(http, "get_json", lambda url: data)
    [job] = fetch_jobs(Company("Acme", "recruitee", "acme"))
    assert (job.title, job.employment_type, job.location) == (
        "Backend Developer",
        "full_time",
        "Amsterdam, Netherlands",
    )
    assert "Build APIs." in job.description and "3+ years" in job.description


SR_PAGE = """<html><body>
<a href="https://jobs.smartrecruiters.com/Acme/111-software-engineer-intern" class="link--block"><h4 class="title">Software Engineer Intern</h4></a>
<a href="https://jobs.smartrecruiters.com/Acme/222-data-engineer"><h4 class="title">Data Engineer</h4></a>
</body></html>"""


def test_smartrecruiters_job_page_microdata():
    job = ats.parse_smartrecruiters_job(fixture("smartrecruiters_job.html"), "https://x", "1")
    assert job is not None
    assert job.location == "Fremont, California, United States"
    assert job.employment_type == "internship" and job.workplace == "onsite"
    assert job.description and job.posted_at.year == 2026
    assert ats.parse_smartrecruiters_job("<html>gone</html>", "u", "1") is None


def test_smartrecruiters_closes_a_missing_posting_only_when_its_page_is_gone(switched_on, monkeypatch):
    job_page = fixture("smartrecruiters_job.html")

    def get_text(url):
        if url == "https://jobs.smartrecruiters.com/Acme":
            return SR_PAGE
        if url.endswith("/333"):
            raise FetchError(f"not found (404): {url}")  # gone
        if url.endswith("/444"):
            raise FetchError(f"server error (503), gave up: {url}")  # can't tell
        return job_page  # 555 is still up, beyond the first page

    monkeypatch.setattr(http, "get_text", get_text)
    jobs = fetch_jobs(
        Company("Acme", "smartrecruiters", "Acme"), known=frozenset({"111", "333", "444", "555"})
    )
    assert sorted(j.external_id for j in jobs) == ["111", "222"]
    assert jobs.listed == frozenset({"111", "222", "444", "555"})  # 333 closes; the rest stay open


def test_smartrecruiters_api_host_is_never_used():
    import inspect

    assert "api.smartrecruiters.com" not in inspect.getsource(ats).split('"""', 2)[2]


def test_candidates_on_new_sources_are_checked_with_one_listing(switched_on, monkeypatch):
    monkeypatch.setattr(
        ats,
        "FETCHERS",
        {
            **ats.FETCHERS,
            "workable": lambda c, details=True, **k: JobList([Job("1", "Software Engineer", "u")]),
        },
    )
    assert snowball.check("workable", "acme", None).outcome == "active"


# ---------- through the pipeline (CI database) ----------

DSN = os.environ.get("TEST_DATABASE_URL")


@pytest.mark.skipif(not DSN, reason="TEST_DATABASE_URL not set")
def test_a_discovered_board_on_a_new_source_is_read_and_filtered(switched_on, monkeypatch):
    from tests.conftest import reset_database
    from tracker import db
    from tracker.discovery import run as discovery

    with db.connect(DSN) as conn:
        reset_database(conn)
        db.apply_schema(conn)
        conn.execute(
            "INSERT INTO discovered_boards (platform, board_slug, company_name) VALUES ('teamtailor', 'oatly', 'Oatly')"
        )
        conn.commit()
    monkeypatch.setattr(
        discovery,
        "fetch_jobs",
        lambda c, **k: JobList(
            [Job("a", "Software Engineer", "u"), Job("b", "Account Manager", "u")],
            validators=Validators("u", '"e"'),
        ),
    )
    company = Company("Oatly", "teamtailor", "oatly", origin="discovered")
    assert discovery._crawl_one(DSN, company, datetime(2026, 10, 1, tzinfo=timezone.utc)) == (1, 1, 0)
    with db.connect(DSN) as conn:
        assert conn.execute("SELECT external_id FROM jobs").fetchall() == [("a",)]
