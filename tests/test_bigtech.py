"""Parser and fetch tests for Amazon, Microsoft (Eightfold), Google and Apple.

Fixtures are trimmed copies of each site's real response shape.
"""

from datetime import datetime, timezone

import pytest

from tracker.models import Company
from tracker.sources import (
    FetchError,
    fetch_jobs,
    http,
    listing_is_complete,
    parse_amazon,
    parse_apple_page,
    parse_eightfold_position,
    parse_eightfold_slug,
    parse_google_detail,
    parse_google_listing,
)

# ---------- Amazon ----------

AMAZON_PAGE = {
    "hits": 2,
    "jobs": [
        {
            "id": "b60723a8",
            "id_icims": "10452751",
            "title": "Software Development Engineer ",
            "job_path": "/en/jobs/10452751/software-development-engineer",
            "normalized_location": "Vancouver, British Columbia, CAN",
            "location": "CA, BC, Vancouver",
            "job_category": "Software Development",
            "posted_date": "June 18, 2026",
            "description": "Build services in Java.",
            "basic_qualifications": "- 3+ years of experience<br/>- Python",
            "preferred_qualifications": "- AWS",
        },
        {
            "id": "c2",
            "id_icims": "222",
            "title": "Data Engineer, Ads",
            "job_path": "/en/jobs/222/data-engineer",
            "normalized_location": "Toronto, Ontario, CAN",
            "posted_date": "not a date",
        },
    ],
}


def test_parse_amazon():
    first, second = parse_amazon(AMAZON_PAGE)
    assert first.external_id == "10452751"
    assert first.title == "Software Development Engineer"
    assert first.url == "https://www.amazon.jobs/en/jobs/10452751/software-development-engineer"
    assert first.location == "Vancouver, British Columbia, CAN"
    assert first.posted_at == datetime(2026, 6, 18, tzinfo=timezone.utc)
    assert "Java" in first.description and "AWS" in first.description
    assert second.posted_at is None


def test_fetch_amazon_dedupes_across_queries(monkeypatch):
    urls = []

    def fake(url):
        urls.append(url)
        return AMAZON_PAGE

    monkeypatch.setattr(http, "get_json", fake)
    jobs = fetch_jobs(Company("Amazon", "amazon", "normalized_country_code[]=CAN|base_query=data"))
    assert len(jobs) == 2
    assert len(urls) == 2 and "offset=0" in urls[0]


# ---------- Microsoft / Eightfold ----------


def test_parse_eightfold_slug():
    assert parse_eightfold_slug("apply.careers.microsoft.com/microsoft.com?location=Canada") == (
        "apply.careers.microsoft.com",
        "microsoft.com",
        "location=Canada",
    )
    with pytest.raises(FetchError):
        parse_eightfold_slug("microsoft.com")


POSITION = {
    "id": 1970393556928710,
    "name": "Software Engineer II - Distributed Systems",
    "standardizedLocations": ["Vancouver, BC, CA", "ON,CA"],
    "postedTs": 1787763723,
    "department": "Software Engineering",
    "workLocationOption": "onsite",
    "positionUrl": "/careers/job/1970393556928710",
}


def test_parse_eightfold_position():
    detail = {"jobDescription": "<b>Overview</b><p>C# and Azure</p>", "publicUrl": "https://x/careers/job/1"}
    job = parse_eightfold_position(POSITION, detail, "apply.careers.microsoft.com")
    assert job.external_id == "1970393556928710"
    assert job.location == "Vancouver, BC, CA | ON,CA"
    assert job.description == "Overview C# and Azure"
    assert job.url == "https://x/careers/job/1"
    assert job.posted_at.year == 2026


def test_fetch_eightfold_paginates_by_count(monkeypatch):
    calls = []

    def fake(url):
        calls.append(url)
        if "/search" in url:
            start = int(url.split("start=")[1].split("&")[0])
            ids = range(start, min(start + 10, 15))
            return {
                "data": {
                    "count": 15,
                    "positions": [
                        {**POSITION, "id": i, "name": "Software Engineer" if i == 0 else "Account Executive"}
                        for i in ids
                    ],
                }
            }
        return {"data": {"jobDescription": "Python"}}

    monkeypatch.setattr(http, "get_json", fake)
    jobs = fetch_jobs(
        Company("Microsoft", "eightfold", "apply.careers.microsoft.com/microsoft.com?location=Canada")
    )
    assert len(jobs) == 15
    assert sum("/search" in c for c in calls) == 2
    assert sum("position_details" in c for c in calls) == 1  # only the engineering role
    assert "location=Canada" in calls[0]


# ---------- Google ----------

GOOGLE_LISTING = """
<li><h3>Software Developer, Google Chat iOS</h3>
<a href="jobs/results/115977778800534214-software-developer-google-chat-ios?location=Canada&amp;q=software">Learn more</a></li>
<li><a href="jobs/results/112518690523488966-software-developer-intern-phd-summer-2027?location=Canada">Learn more</a>
<a href="jobs/results/112518690523488966-software-developer-intern-phd-summer-2027">again</a></li>
"""

GOOGLE_DETAIL = """<html><head><title>Software Developer, Google Chat iOS — Google Careers</title></head>
<body><nav>Google Cloud Teams Locations</nav><h2>Software Developer, Google Chat iOS</h2>
<h3>Minimum qualifications:</h3><ul><li>Experience with Swift and Kotlin.</li></ul>
<h3>About the job</h3><p>Build iOS apps.</p></body></html>"""


def test_parse_google_listing_dedupes():
    assert parse_google_listing(GOOGLE_LISTING) == [
        ("115977778800534214", "software-developer-google-chat-ios"),
        ("112518690523488966", "software-developer-intern-phd-summer-2027"),
    ]


def test_parse_google_detail_skips_navigation():
    title, description = parse_google_detail(GOOGLE_DETAIL)
    assert title == "Software Developer, Google Chat iOS"
    assert description.startswith("Minimum qualifications")
    assert "Swift" in description and "Google Cloud" not in description


def test_fetch_google(monkeypatch):
    def fake(url):
        return GOOGLE_LISTING if "?" in url else GOOGLE_DETAIL

    monkeypatch.setattr(http, "get_text", fake)
    company = Company("Google", "google", "location=Canada&q=software", region="Canada")
    jobs = fetch_jobs(company)
    assert [j.title for j in jobs] == ["Software Developer, Google Chat iOS"] * 2  # detail title wins
    assert all(j.location == "Canada" for j in jobs)  # region fallback
    assert not listing_is_complete(company)


def test_google_query_encoding(monkeypatch):
    urls = []
    monkeypatch.setattr(http, "get_text", lambda url: urls.append(url) or "")
    fetch_jobs(Company("Google", "google", "location=Canada&q=data engineer"))
    assert urls == [
        "https://www.google.com/about/careers/applications/jobs/results/?location=Canada&q=data%20engineer"
    ]


# ---------- Apple ----------

APPLE_PAGE = """
<h2>36 Result(s)</h2>
<a class="link" href="/en-ca/details/200688653-2494/bring-up-engineer-core-os?team=SFTWR">Bring Up Engineer, Core OS</a>
<a href="/en-ca/details/200607536/ca-manager?team=APPST"><span>CA-Manager</span></a>
<a href="/en-ca/details/200688653-2494/bring-up-engineer-core-os?team=SFTWR">duplicate</a>
"""


def test_parse_apple_page():
    jobs, total = parse_apple_page(APPLE_PAGE)
    assert total == 36
    assert [j.external_id for j in jobs] == ["200688653-2494", "200607536"]
    assert jobs[0].title == "Bring Up Engineer, Core OS"
    assert jobs[0].department == "SFTWR"
    assert jobs[1].title == "CA-Manager"
    assert (
        jobs[0].url
        == "https://jobs.apple.com/en-ca/details/200688653-2494/bring-up-engineer-core-os?team=SFTWR"
    )


def test_fetch_apple_stops_when_no_new_jobs(monkeypatch):
    urls = []

    def fake(url):
        urls.append(url)
        return APPLE_PAGE  # every page repeats: must stop after page 2

    monkeypatch.setattr(http, "get_text", fake)
    jobs = fetch_jobs(Company("Apple", "apple", "en-ca/search?location=canada-CANC", region="Canada"))
    assert len(jobs) == 2
    assert urls[0].endswith("location=canada-CANC&page=1")
    assert len(urls) == 2
    assert jobs[0].location == "Canada"


def _hydration_page(payload: dict) -> str:
    import json

    literal = json.dumps(json.dumps(payload))  # JSON inside a JS string literal
    return f"<html><script>window.__staticRouterHydrationData = JSON.parse({literal});</script></html>"


APPLE_DATA = {
    "loaderData": {
        "search": {
            "totalRecords": 2,
            "searchResults": [
                {
                    "positionId": "200688653-2494",
                    "postingTitle": "Bring Up Engineer, Core OS",
                    "transformedPostingTitle": "bring-up-engineer-core-os",
                    "jobSummary": "Work with <b>C++</b> and Python on silicon bring up.",
                    "locations": [{"name": "Ottawa", "countryName": "Canada"}],
                    "team": {"teamName": "Software and Services", "teamCode": "SFTWR"},
                    "homeOffice": False,
                },
                {
                    "positionId": "200607536",
                    "postingTitle": "CA-Manager",
                    "transformedPostingTitle": "ca-manager",
                    "locations": [],
                    "team": {"teamName": "Apple Retail", "teamCode": "APPST"},
                },
            ],
        }
    },
}


def test_parse_apple_embedded_json():
    jobs, total = parse_apple_page(_hydration_page(APPLE_DATA), "en-ca")
    assert total == 2
    first, second = jobs
    assert first.external_id == "200688653-2494"
    assert (
        first.url
        == "https://jobs.apple.com/en-ca/details/200688653-2494/bring-up-engineer-core-os?team=SFTWR"
    )
    assert first.location == "Ottawa"
    assert first.department == "Software and Services"
    assert first.description == "Work with C++ and Python on silicon bring up."
    assert second.location == ""


def test_parse_apple_escaped_links_fallback():
    page = '<script>var x = "\\/en-ca\\/details\\/200607536\\/ca-manager?team=APPST";</script>'
    jobs, total = parse_apple_page(page, "en-ca")
    assert [(j.external_id, j.title) for j in jobs] == [("200607536", "Ca Manager")]
    assert total is None


def test_parse_apple_page_with_nothing_returns_empty():
    assert parse_apple_page("<html>Please enable JavaScript</html>") == ([], None)
