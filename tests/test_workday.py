from datetime import datetime, timedelta, timezone

import pytest

from tracker.models import Company
from tracker.sources import (
    FetchError,
    common,
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


def test_fetch_workday_paginates_and_fetches_each_description_once(monkeypatch):
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
    # every posting Ghostless stores gets its description (not the Branch Teller);
    # a failed detail call keeps the job
    assert detail_calls == ["a", "c", "d", "e"]
    assert jobs[0].description == "Python"
    assert jobs[2].description == ""

    # postings already stored with a description are not fetched again
    detail_calls.clear()
    fetch_workday(company, known=frozenset({"/job/a", "/job/b"}))
    assert detail_calls == ["c", "d", "e"]

    # past the per-run cap, the most relevant go first: tech roles in Canada,
    # remote or several cities, then other tech roles, then the rest
    detail_calls.clear()
    monkeypatch.setattr(common, "MAX_DETAILS_PER_RUN", 3)
    fetch_workday(company)
    assert detail_calls == ["a", "c", "e"]

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
    jobs = fetch_jobs(Company("Acme", "workday", "acme.wd3.myworkdayjobs.com/External"), details=False)
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
    jobs = fetch_jobs(Company("Acme", "workday", "acme.wd3.myworkdayjobs.com/External"), details=False)
    assert [j.external_id for j in jobs] == ["/job/1", "/job/2", "/job/3"]
    assert jobs.complete is True


FACETS = [
    {
        "facetParameter": "jobFamilyGroup",
        "values": [
            {"descriptor": "Engineering", "id": "eng", "count": 5},
            {"descriptor": "Sales", "id": "sales", "count": 3},
        ],
    },
    {  # nested group: locations inside a main group
        "facetParameter": "locationMainGroup",
        "values": [
            {
                "facetParameter": "locationCountry",
                "values": [
                    {"descriptor": "Canada", "id": "ca", "count": 2},
                    {"descriptor": "US", "id": "us", "count": 4},
                ],
            }
        ],
    },
    {"facetParameter": "timeType", "values": [{"descriptor": "Full time", "id": "ft", "count": 8}]},
]


def test_flatten_facets_handles_nesting():
    flat = workday.flatten_facets(FACETS)
    assert flat["jobFamilyGroup"] == [("eng", 5), ("sales", 3)]
    assert flat["locationCountry"] == [("ca", 2), ("us", 4)]
    assert flat["timeType"] == [("ft", 8)]


def test_choose_split_covers_everything_with_the_smallest_parts():
    flat = workday.flatten_facets(FACETS)
    # countries cover only 6 of 8 postings, so they'd lose some; one time type can't split
    assert workday.choose_split(flat, 8, {}) == ("jobFamilyGroup", ["eng", "sales"])
    assert workday.choose_split(flat, 8, {"jobFamilyGroup": ["eng"]}) is None


def test_big_listings_are_split_by_facet_past_the_offset_limit(monkeypatch):
    """8 postings, but the API stops after 6: split by job family to get them all."""
    monkeypatch.setattr(workday, "PAGE_SIZE", 2)
    monkeypatch.setattr(workday, "OFFSET_LIMIT", 6)
    families = {"eng": [f"/job/e{i}" for i in range(5)], "sales": [f"/job/s{i}" for i in range(3)]}
    searches = []

    def fake_request(method, url, payload=None):
        applied = payload["appliedFacets"]
        searches.append(applied)
        paths = families.get(applied.get("jobFamilyGroup", [None])[0]) or [
            p for ps in families.values() for p in ps
        ]
        offset = payload["offset"]
        page = [{"title": "Engineer", "externalPath": p} for p in paths[offset : offset + 2]]
        return (
            {"total": len(paths), "facets": FACETS, "jobPostings": page}
            if offset == 0
            else {"total": 0, "jobPostings": page}
        )

    monkeypatch.setattr(http, "request_json", fake_request)
    jobs = fetch_jobs(Company("Nvidia", "workday", "acme.wd3.myworkdayjobs.com/External"), details=False)
    assert len(jobs) == 8
    assert jobs.complete is True
    assert {"jobFamilyGroup": ["eng"]} in searches and {"jobFamilyGroup": ["sales"]} in searches


def test_student_searches_keep_only_student_titles(monkeypatch):
    """Workday's search for "intern" also finds International and Internal Audit."""
    found = [
        {"title": "Software Engineering Intern", "externalPath": "/job/a", "locationsText": "Toronto"},
        {"title": "International Tax Manager", "externalPath": "/job/b", "locationsText": "Toronto"},
        {"title": "Internal Audit Senior", "externalPath": "/job/c", "locationsText": "Toronto"},
        {"title": "Co-op, Data Analyst (Winter 2027)", "externalPath": "/job/d", "locationsText": "Toronto"},
        {"title": "New Grad Software Developer", "externalPath": "/job/e", "locationsText": "Toronto"},
    ]
    details = []

    def fake_request(method, url, payload=None):
        if method == "POST":
            return {"total": len(found), "jobPostings": found if payload["offset"] == 0 else []}
        details.append(url.rsplit("/", 1)[-1])
        return {"jobPostingInfo": {"jobDescription": "x"}}

    monkeypatch.setattr(http, "request_json", fake_request)
    company = Company("Acme", "workday", "acme.wd3.myworkdayjobs.com/External")
    jobs = fetch_workday(company, queries=("intern", "co-op", "new grad"), per_query=100)
    assert [j.external_id for j in jobs] == ["/job/a", "/job/d", "/job/e"]
    assert sorted(details) == ["a", "d", "e"]  # no descriptions fetched for the rest


def test_weekly_full_read_lists_small_boards_and_skips_huge_ones(monkeypatch):
    from tracker.sources.workday import list_workday

    calls = []

    def board(total):
        def fake_request(method, url, payload=None):
            calls.append(payload["offset"])
            start = payload["offset"]
            page = [{"title": "x", "externalPath": f"/job/{i}"} for i in range(start, min(start + 20, total))]
            return {"total": total, "jobPostings": page, "facets": [{"facetParameter": "loc", "values": []}]}

        return fake_request

    company = Company("Acme", "workday", "acme.wd3.myworkdayjobs.com/External")
    monkeypatch.setattr(http, "request_json", board(45))
    listed, complete = list_workday(company)
    assert complete and len(listed) == 45 and len(calls) == 4  # a first look, then 3 pages

    calls.clear()
    monkeypatch.setattr(http, "request_json", board(2733))
    listed, complete = list_workday(company)
    assert not complete and calls == [0]  # one request, then skipped: closes nothing
