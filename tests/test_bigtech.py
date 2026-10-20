"""Parser and fetch tests for Amazon, Microsoft (Eightfold), Google and Apple.

Fixtures are trimmed copies of each site's real response shape.
"""

from datetime import datetime, timezone

import pytest

from tracker.models import Company
from tracker.sources import (
    FetchError,
    complete_descriptions,
    fetch_jobs,
    http,
    is_full_description,
    listing_is_complete,
    parse_amazon,
    parse_apple_detail,
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
    microsoft = Company("Microsoft", "eightfold", "apply.careers.microsoft.com/microsoft.com?location=Canada")
    jobs = fetch_jobs(microsoft)
    assert len(jobs) == 15
    assert sum("/search" in c for c in calls) == 2
    # descriptions only for postings Ghostless stores: the Account Executives are left out
    assert sum("position_details" in c for c in calls) == 1
    assert "location=Canada" in calls[0]

    # descriptions already stored are not fetched again
    calls.clear()
    fetch_jobs(microsoft, known=frozenset(str(i) for i in range(1, 15)))
    assert [c for c in calls if "position_details" in c] == [calls[-1]]
    assert "position_id=0" in calls[-1]


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


def test_parse_google_detail_ends_before_the_privacy_notice_and_page_scripts():
    page = (
        "<html><body><h3>Minimum qualifications:</h3><ul><li>Experience with C++.</li></ul>"
        "<p>Canada: $182000 - $186000 (CAD) + bonus</p><h3>Responsibilities</h3><ul><li>Build it.</li></ul>"
        "<p>Information collected and processed as part of your Google Careers profile is subject to the policy.</p>"
        "<p>Google is proud to be an equal opportunity employer.</p>"
        "<script>AF_initDataCallback({key: 'ds:0', data: ['https://accounts.google.com/AccountChooser']});</script>"
        "</body></html>"
    )
    _, description = parse_google_detail(page)
    assert description.endswith("• Build it.")
    assert "accounts.google.com" not in description and "Information collected" not in description


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
    searches = [u for u in urls if "/search" in u]  # the rest are the postings' own pages
    assert searches[0].endswith("location=canada-CANC&page=1")
    assert len(searches) == 2
    assert jobs[0].location == "Canada"


def _hydration_page(payload: dict) -> str:
    import json

    literal = json.dumps(json.dumps(payload))  # JSON inside a JS string literal
    return f"<html><script>window.__staticRouterHydrationData = JSON.parse({literal});</script></html>"


# Shape copied from jobs.apple.com's embedded search data (trimmed).
APPLE_DATA = {
    "loaderData": {
        "search": {
            "totalRecords": 3,
            "searchResults": [
                {
                    "id": "200679759-3350",
                    "positionId": "200679759",
                    "reqId": "200679759-3350",
                    "postingTitle": "Machine Learning Engineer, Software QA",
                    "transformedPostingTitle": "machine-learning-engineer-software-qa",
                    "postDateInGMT": "2026-10-16T22:54:37.862Z",
                    "jobSummary": "Work with <b>Python</b> and PyTorch on model quality.",
                    "locations": [{"name": "Vancouver", "countryName": "Canada", "level": 5}],
                    "team": {"teamName": "Software and Services", "teamCode": "SFTWR"},
                    "homeOffice": False,
                    "managedPipelineRole": False,
                },
                {
                    # same positionId as the next row: one role, two store locations
                    "id": "200607536-3250",
                    "positionId": "200607536",
                    "postingTitle": "CA-Manager",
                    "transformedPostingTitle": "ca-manager",
                    "locations": [{"name": "Coquitlam Centre", "countryName": "Canada", "level": 6}],
                    "team": {"teamName": "Apple Retail", "teamCode": "APPST"},
                },
                {
                    "id": "PIPE-114438004",
                    "positionId": "114438004",
                    "postingTitle": "CA - Specialist: Seasonal, Part-time",
                    "transformedPostingTitle": "ca-specialist-seasonal-part-time",
                    "postDateInGMT": "2026-10-17T23:23:04.639Z",
                    "locations": [{"name": "Canada", "countryName": "Canada", "level": 1}],
                    "team": {"teamName": "Apple Retail", "teamCode": "APPST"},
                    "managedPipelineRole": True,
                },
            ],
        }
    },
}


def test_parse_apple_embedded_json():
    jobs, total = parse_apple_page(_hydration_page(APPLE_DATA), "en-ca")
    assert total == 3
    ml, manager, pipeline = jobs
    assert ml.external_id == "200679759-3350"
    assert ml.url == (
        "https://jobs.apple.com/en-ca/details/200679759-3350/machine-learning-engineer-software-qa?team=SFTWR"
    )
    assert ml.location == "Vancouver, Canada"
    assert ml.department == "Software and Services"
    assert ml.description == "Work with Python and PyTorch on model quality."
    assert ml.posted_at.isoformat().startswith("2026-10-16T22:54:37")
    assert ml.vacancy is None
    assert manager.location == "Coquitlam Centre, Canada"  # store name plus country
    assert pipeline.location == "Canada"
    assert pipeline.url.startswith("https://jobs.apple.com/en-ca/details/114438004/")  # PIPE- prefix dropped
    assert pipeline.vacancy == "not_existing"


def test_apple_same_role_at_two_stores_stays_two_postings():
    second_store = {
        **APPLE_DATA["loaderData"]["search"]["searchResults"][1],
        "id": "200607536-3055",
        "locations": [{"name": "Place Ste-Foy", "countryName": "Canada"}],
    }
    data = {
        "loaderData": {
            "search": {
                "searchResults": [APPLE_DATA["loaderData"]["search"]["searchResults"][1], second_store]
            }
        }
    }
    jobs, _ = parse_apple_page(_hydration_page(data), "en-ca")
    assert [j.external_id for j in jobs] == ["200607536-3250", "200607536-3055"]


def test_apple_pipeline_flag_survives_enrich():
    from tracker.classify import enrich

    jobs, _ = parse_apple_page(_hydration_page(APPLE_DATA), "en-ca")
    pipeline = enrich(jobs[2], [])
    assert pipeline.vacancy == "not_existing"
    assert pipeline.is_canada


# Shape copied from a jobs.apple.com posting page's embedded data (trimmed).
APPLE_DETAIL_DATA = {
    "loaderData": {
        "jobDetails": {
            "jobsData": {
                "id": "200682548-3350",
                "postingTitle": "Software Development Engineer in Test, Full Stack, Creativity Apps",
                "jobSummary": "Imagine what you could do here. The Creativity Applications team is looking for an SDET.",
                "description": "In this role, you will plan and execute test strategy.\nYou will drive quality.",
                "minimumQualifications": "Minimum of 3 years of experience as an SDET.\nFluent in Python, Swift, and/or JavaScript.",
                "preferredQualifications": "Experience with video editing workflows.",
                "postingFooters": [
                    {
                        "postLocationId": "postLocation-VAC",
                        "localizations": {
                            "en_US": [
                                {
                                    "displayOrder": 1,
                                    "name": "Pay & Benefits",
                                    "content": "At Apple, base pay is one part of our total compensation package. "
                                    "The base pay range for this role is between $119,100 and $230,500, and your "
                                    "base pay will depend on your skills.<br><br>Apple employees also have stock programs.",
                                }
                            ]
                        },
                    }
                ],
            }
        }
    }
}


def test_parse_apple_detail_reads_the_whole_posting():
    from tracker.disclosures import parse_salary

    text = parse_apple_detail(_hydration_page(APPLE_DETAIL_DATA))
    assert text.startswith("Imagine what you could do here.")
    assert (
        "\n\nDescription\nIn this role, you will plan and execute test strategy.\nYou will drive quality."
        in text
    )
    assert (
        "\n\nMinimum Qualifications\n• Minimum of 3 years of experience as an SDET.\n• Fluent in Python"
        in text
    )
    assert "\n\nPreferred Qualifications\n• Experience with video editing workflows." in text
    assert "\n\nPay & Benefits\nAt Apple, base pay" in text
    assert is_full_description(text)
    salary = parse_salary(text)
    assert (salary.minimum, salary.maximum, salary.period) == (119100, 230500, "year")


def test_parse_apple_detail_without_posting_data_is_empty():
    assert parse_apple_detail("<html><body>Something went wrong</body></html>") == ""
    assert not is_full_description("Imagine what you could do here.")  # a search-results summary


def test_fetch_apple_fetches_each_posting_page_once(monkeypatch):
    urls = []
    search = _hydration_page(APPLE_DATA)
    detail = _hydration_page(APPLE_DETAIL_DATA)

    def fake(url):
        urls.append(url)
        return search if "/search" in url else detail

    monkeypatch.setattr(http, "get_text", fake)
    apple = Company("Apple", "apple", "en-ca/search?location=canada-CANC", region="Canada")
    jobs = {j.external_id: j for j in fetch_jobs(apple)}
    # only the posting Ghostless stores is read in full, not the two retail roles
    assert sum("/details/" in u for u in urls) == 1
    assert is_full_description(jobs["200679759-3350"].description)

    # stored in full: not fetched again, and no summary to overwrite the stored text
    urls.clear()
    jobs = {j.external_id: j for j in fetch_jobs(apple, known=frozenset({"200679759-3350"}))}
    assert sum("/details/" in u for u in urls) == 0
    assert jobs["200679759-3350"].description == ""


def test_only_full_apple_descriptions_count_as_known():
    stored = {
        "a": ("Just the search summary.", ""),
        "b": (parse_apple_detail(_hydration_page(APPLE_DETAIL_DATA)), ""),
    }
    assert complete_descriptions("apple", stored) == frozenset({"b"})
    assert complete_descriptions("workday", stored) == frozenset({"a", "b"})


def test_parse_apple_escaped_links_fallback():
    page = '<script>var x = "\\/en-ca\\/details\\/200607536\\/ca-manager?team=APPST";</script>'
    jobs, total = parse_apple_page(page, "en-ca")
    assert [(j.external_id, j.title) for j in jobs] == [("200607536", "Ca Manager")]
    assert total is None


def test_parse_apple_page_with_nothing_returns_empty():
    assert parse_apple_page("<html>Please enable JavaScript</html>") == ([], None)
