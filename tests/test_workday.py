from datetime import datetime, timedelta, timezone

import pytest

from tracker.models import Company
from tracker.sources import (
    FetchError,
    fetch_jobs,
    fetch_workday,
    http,
    parse_workday_age,
    parse_workday_job,
    parse_workday_slug,
    workday,
)

BASE = "https://acme.wd3.myworkdayjobs.com"


@pytest.mark.parametrize(
    "slug",
    [
        "acme.wd3.myworkdayjobs.com/External",
        "https://acme.wd3.myworkdayjobs.com/en-US/External",
        "acme.wd3.myworkdayjobs.com/en-US/External/",
    ],
)
def test_parse_workday_slug(slug):
    assert parse_workday_slug(slug) == (BASE, "acme", "External")


def test_parse_workday_slug_rejects_bad_input():
    with pytest.raises(FetchError):
        parse_workday_slug("acme.com/careers")


def test_parse_workday_age():
    now = datetime(2026, 10, 17, tzinfo=timezone.utc)
    assert parse_workday_age("Posted Today", now) == now
    assert parse_workday_age("Posted Yesterday", now) == now - timedelta(days=1)
    assert parse_workday_age("Posted 3 Days Ago", now) == now - timedelta(days=3)
    assert parse_workday_age("Posted 30+ Days Ago", now) == now - timedelta(days=30)
    assert parse_workday_age("", now) is None


def test_parse_workday_job_with_detail():
    item = {
        "title": "Software Engineer",
        "externalPath": "/job/Toronto/SE_R1",
        "locationsText": "2 Locations",
    }
    detail = {
        "jobPostingInfo": {
            "title": "Software Engineer",
            "location": "Toronto, ON",
            "additionalLocations": ["Remote - Canada"],
            "jobDescription": "<p>Java &amp; SQL</p>",
            "externalUrl": "https://acme.wd3.myworkdayjobs.com/External/job/Toronto/SE_R1",
        }
    }
    job = parse_workday_job(item, detail, BASE, "External")
    assert job.external_id == "/job/Toronto/SE_R1"
    assert job.location == "Toronto, ON | Remote - Canada"
    assert job.description == "Java & SQL"


def test_parse_workday_job_without_detail():
    item = {"title": "Teller", "externalPath": "/job/Ottawa/T_R2", "locationsText": "Ottawa, ON"}
    job = parse_workday_job(item, None, BASE, "External")
    assert job.location == "Ottawa, ON"
    assert job.url == f"{BASE}/en-US/External/job/Ottawa/T_R2"
    assert job.description == ""


def test_fetch_workday_paginates_and_only_details_relevant_roles(monkeypatch):
    monkeypatch.setattr(workday, "PAGE_SIZE", 2)
    pages = {
        # Workday quirk: total only on the first page
        0: {
            "total": 5,
            "jobPostings": [
                {"title": "Software Engineer", "externalPath": "/job/a", "locationsText": "Toronto, ON"},
                {"title": "Branch Teller", "externalPath": "/job/b", "locationsText": "Toronto, ON"},
            ],
        },
        2: {
            "total": 0,
            "jobPostings": [
                {"title": "Data Engineer", "externalPath": "/job/c", "locationsText": "3 Locations"},
                {"title": "Software Engineer", "externalPath": "/job/d", "locationsText": "Austin, TX"},
            ],
        },
        4: {
            "total": 0,
            "jobPostings": [
                {"title": "Backend Developer", "externalPath": "/job/e", "locationsText": "Remote"},
            ],
        },
    }
    detail_calls = []

    def fake_request(method, url, payload=None):
        if method == "POST":
            return pages[payload["offset"]]
        detail_calls.append(url.rsplit("/", 1)[-1])
        if url.endswith("/job/c"):
            raise FetchError("simulated detail failure")
        return {"jobPostingInfo": {"jobDescription": "Python"}}

    monkeypatch.setattr(http, "request_json", fake_request)
    company = Company("Acme", "workday", "acme.wd3.myworkdayjobs.com/External")
    jobs = fetch_workday(company)

    assert [j.external_id for j in jobs] == ["/job/a", "/job/b", "/job/c", "/job/d", "/job/e"]
    # teller (not tech) and Austin (not Canada/remote) skipped; failed detail keeps the job
    assert detail_calls == ["a", "c", "e"]
    assert jobs[0].description == "Python"

    detail_calls.clear()
    fetch_workday(company, details=False)
    assert detail_calls == []


def test_truncated_workday_listing_is_marked_partial(monkeypatch):
    """Workday stops paging at an offset limit: 2,000 jobs back when 2,500 exist."""
    monkeypatch.setattr(workday, "PAGE_SIZE", 2)

    def fake_request(method, url, payload=None):
        offset = payload["offset"]
        if offset >= 4:  # the API's offset limit in this fake
            return {"total": 0, "jobPostings": []}
        return {
            "total": 10 if offset == 0 else 0,
            "jobPostings": [
                {"title": "Teller", "externalPath": f"/job/{offset + i}", "locationsText": "Ottawa"}
                for i in range(2)
            ],
        }

    monkeypatch.setattr(http, "request_json", fake_request)
    jobs = fetch_jobs(Company("Acme", "workday", "acme.wd3.myworkdayjobs.com/External"))
    assert len(jobs) == 4
    assert jobs.complete is False
    assert jobs.total == 10


def test_complete_workday_listing_and_duplicate_pages(monkeypatch):
    monkeypatch.setattr(workday, "PAGE_SIZE", 2)
    pages = {
        0: {
            "total": 3,
            "jobPostings": [
                {"title": "T", "externalPath": "/job/1"},
                {"title": "T", "externalPath": "/job/2"},
            ],
        },
        # a posting shifted between pages and shows up twice
        2: {
            "total": 0,
            "jobPostings": [
                {"title": "T", "externalPath": "/job/2"},
                {"title": "T", "externalPath": "/job/3"},
            ],
        },
    }
    monkeypatch.setattr(http, "request_json", lambda method, url, payload=None: pages[payload["offset"]])
    jobs = fetch_jobs(Company("Acme", "workday", "acme.wd3.myworkdayjobs.com/External"))
    assert [j.external_id for j in jobs] == ["/job/1", "/job/2", "/job/3"]
    assert jobs.complete is True