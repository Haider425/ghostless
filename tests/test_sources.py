"""Parser tests run against small fixture payloads shaped like each real API."""

from tracker.sources import parse_ashby, parse_greenhouse, parse_lever
from tracker.text import html_to_text

GREENHOUSE = {
    "jobs": [
        {
            "id": 4012345,
            "title": "Software Engineer, New Grad ",
            "absolute_url": "https://boards.greenhouse.io/example/jobs/4012345",
            "location": {"name": "Toronto, Canada"},
            "departments": [{"name": "Engineering"}],
            "updated_at": "2026-10-01T12:00:00-04:00",
            "content": "&lt;p&gt;Build APIs in &lt;strong&gt;Python&lt;/strong&gt; &amp;amp; Go&lt;/p&gt;",
        }
    ]
}

LEVER = [
    {
        "id": "a1b2c3",
        "text": "Data Engineer",
        "hostedUrl": "https://jobs.lever.co/example/a1b2c3",
        "categories": {"location": "Vancouver, BC", "team": "Data"},
        "descriptionPlain": "Own our Airflow pipelines.",
        "lists": [{"text": "Requirements", "content": "<li>SQL</li><li>Spark</li>"}],
        "createdAt": 1759320000000,
        "workplaceType": "remote",
    }
]

ASHBY = {
    "jobs": [
        {
            "id": "uuid-1",
            "title": "Backend Engineer",
            "jobUrl": "https://jobs.ashbyhq.com/example/uuid-1",
            "location": "Remote",
            "department": "Engineering",
            "isRemote": True,
            "isListed": True,
            "descriptionPlain": "TypeScript and Postgres.",
            "publishedAt": "2026-09-15T00:00:00.000Z",
        },
        {"id": "uuid-2", "title": "Hidden role", "isListed": False},
    ]
}


def test_html_to_text_drops_scripts_styles_and_comments():
    page = (
        "<html><head><title>Job</title><style>.a{color:red}</style></head><body>"
        "<p>Build things.</p><script>var cfg = {'url': 'https://accounts.example.com'};</script>"
        "<!-- tracking --><noscript>Enable JavaScript</noscript><p>Ship them.</p></body></html>"
    )
    assert html_to_text(page) == "Build things.\n\nShip them."


def test_html_to_text_drops_a_double_escaped_script():
    assert html_to_text("&lt;p&gt;Hi&lt;/p&gt;&lt;script&gt;track()&lt;/script&gt;") == "Hi"


def test_html_to_text_handles_double_escaping():
    assert html_to_text("&lt;p&gt;A &amp;amp; B&lt;/p&gt;") == "A & B"


def test_html_to_text_keeps_paragraphs_and_lists():
    raw = "<p>About us</p>\n<h3>What you do</h3><ul><li>Build things</li><li>Ship <b>fast</b></li></ul><p>a<br>b</p>"
    assert html_to_text(raw) == "About us\n\nWhat you do\n• Build things\n• Ship fast\n\na\nb"


def test_parse_greenhouse():
    [job] = parse_greenhouse(GREENHOUSE)
    assert job.external_id == "4012345"
    assert job.title == "Software Engineer, New Grad"
    assert job.location == "Toronto, Canada"
    assert job.department == "Engineering"
    assert job.description == "Build APIs in Python & Go"
    assert job.posted_at.year == 2026


def test_parse_lever():
    [job] = parse_lever(LEVER)
    assert job.external_id == "a1b2c3"
    assert job.department == "Data"
    assert job.source_remote is True
    assert "Airflow" in job.description and "Spark" in job.description
    assert job.posted_at is not None


def test_parse_ashby_skips_unlisted():
    jobs = parse_ashby(ASHBY)
    assert [j.external_id for j in jobs] == ["uuid-1"]
    assert jobs[0].source_remote is True


def test_parsers_tolerate_empty_payloads():
    assert parse_greenhouse({}) == []
    assert parse_lever([]) == []
    assert parse_ashby({}) == []
