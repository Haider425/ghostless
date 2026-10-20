"""The JSON-LD career site reader (stage B3)."""

import gzip
import json
from datetime import datetime, timezone

import pytest

from tracker import settings
from tracker.models import Company
from tracker.sources import http, jsonld
from tracker.sources.http import FetchError
from tracker.sources.robots import RobotsCache


def page(*blocks: str) -> str:
    scripts = "".join(f'<script type="application/ld+json">{b}</script>' for b in blocks)
    return f"<html><head>{scripts}</head><body>hi</body></html>"


POSTING = {
    "@context": "https://schema.org",
    "@type": "JobPosting",
    "title": "Software Engineer Intern &amp; Co-op",
    "description": "<p>Build <b>Python</b> services.</p><ul><li>Summer 2027</li></ul>",
    "datePosted": "2026-10-01",
    "validThrough": "2099-01-01T00:00:00Z",
    "hiringOrganization": {"@type": "Organization", "name": "Acme"},
    "jobLocation": [
        {
            "@type": "Place",
            "address": {"addressLocality": "Toronto", "addressRegion": "ON", "addressCountry": "CA"},
        },
        {"@type": "Place", "address": {"addressLocality": "Montreal", "addressCountry": {"name": "Canada"}}},
    ],
    "baseSalary": {
        "@type": "MonetaryAmount",
        "currency": "CAD",
        "value": {"@type": "QuantitativeValue", "minValue": 30, "maxValue": 40, "unitText": "HOUR"},
    },
}


def test_reads_a_job_posting():
    [job], any_posting = jsonld.parse_job_page(
        page(json.dumps(POSTING)), "https://careers.acme.example/jobs/42?src=x"
    )
    assert any_posting
    assert job.title == "Software Engineer Intern & Co-op"
    assert job.external_id == "careers.acme.example/jobs/42"
    assert job.location == "Toronto, ON, CA | Montreal, Canada"
    assert "Build Python services." in job.description and "Summer 2027" in job.description
    assert (job.salary_min, job.salary_max, job.salary_period, job.salary_currency) == (30, 40, "hour", "CAD")
    assert job.posted_at.date().isoformat() == "2026-10-01"


@pytest.mark.parametrize(
    "blocks, titles",
    [
        (
            [json.dumps([POSTING, {**POSTING, "title": "Data Engineer"}])],
            ["Software Engineer Intern & Co-op", "Data Engineer"],
        ),
        (
            [json.dumps({"@context": "https://schema.org", "@graph": [{"@type": "Organization"}, POSTING]})],
            ["Software Engineer Intern & Co-op"],
        ),
        (
            ["{not json", json.dumps({**POSTING, "title": "Backend Developer"})],
            ["Backend Developer"],
        ),  # bad block skipped
        (["<!--" + json.dumps({**POSTING, "title": "SRE"}) + "-->"], ["SRE"]),  # wrapped in a comment
        (
            [json.dumps({**POSTING, "@type": ["JobPosting", "Thing"], "title": "QA Engineer"})],
            ["QA Engineer"],
        ),
        ([json.dumps({"@type": "Organization", "name": "Acme"})], []),
    ],
    ids=["several", "graph", "invalid json", "comment", "type list", "no posting"],
)
def test_finds_postings_wherever_they_sit(blocks, titles):
    assert [p["title"].replace("&amp;", "&") for p in jsonld.find_postings(page(*blocks))] == titles


def test_raw_newlines_in_strings_are_accepted():
    raw = '{"@type": "JobPosting", "title": "Data Analyst", "description": "line one\nline two"}'
    [job], _ = jsonld.parse_job_page(page(raw), "https://x.example/jobs/1")
    assert job.description == "line one\nline two"


def test_expired_and_remote_postings():
    gone = {**POSTING, "validThrough": "2020-01-01"}
    jobs, any_posting = jsonld.parse_job_page(page(json.dumps(gone)), "https://x.example/jobs/1")
    assert jobs == [] and any_posting  # a posting, but closed
    remote = {k: v for k, v in POSTING.items() if k != "jobLocation"} | {
        "jobLocationType": "TELECOMMUTE",
        "applicantLocationRequirements": {"@type": "Country", "name": "Canada"},
    }
    [job], _ = jsonld.parse_job_page(page(json.dumps(remote)), "https://x.example/jobs/2")
    assert job.source_remote and job.location == "Canada"


def test_sitemap_index_and_pages():
    index = """<?xml version="1.0"?><sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
      <sitemap><loc>https://x.example/sitemap-blog.xml</loc></sitemap>
      <sitemap><loc>https://x.example/sitemap-jobs.xml.gz</loc></sitemap></sitemapindex>"""
    assert jsonld.parse_sitemap(index) == (
        [],
        ["https://x.example/sitemap-blog.xml", "https://x.example/sitemap-jobs.xml.gz"],
    )
    urls = """<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
      <url><loc>https://x.example/jobs/1</loc><lastmod>2026-10-02</lastmod></url>
      <url><loc>https://x.example/about</loc></url></urlset>"""
    assert jsonld.parse_sitemap(urls) == (
        [("https://x.example/jobs/1", "2026-10-02"), ("https://x.example/about", None)],
        [],
    )
    assert jsonld.parse_sitemap("not xml") == ([], [])


class FakeSite:
    """A career site: robots.txt naming a sitemap index, a gzipped job sitemap, job pages."""

    def __init__(self, monkeypatch, pages: dict[str, tuple[str | None, str]]):
        self.pages = pages  # path -> (lastmod, html)
        self.read: list[str] = []
        robots = "User-agent: *\nAllow: /\nSitemap: https://careers.acme.example/sitemap.xml\n"
        monkeypatch.setattr(http, "robots", RobotsCache("t", lambda url: (200, robots)))
        monkeypatch.setattr(http, "get_text", self.get_text)
        monkeypatch.setattr(http, "get_bytes", self.get_bytes)

    def get_text(self, url):
        self.read.append(url)
        if url.endswith("/sitemap.xml"):
            return """<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
              <sitemap><loc>https://careers.acme.example/news.xml</loc></sitemap>
              <sitemap><loc>https://careers.acme.example/jobs.xml.gz</loc></sitemap></sitemapindex>"""
        path = url.split("careers.acme.example")[1]
        if path not in self.pages:
            raise FetchError(f"not found (404): {url}")
        return self.pages[path][1]

    def get_bytes(self, url):
        self.read.append(url)
        entries = (
            "".join(
                f"<url><loc>https://careers.acme.example{p}</loc>{f'<lastmod>{m}</lastmod>' if m else ''}</url>"
                for p, (m, _) in self.pages.items()
            )
            + "<url><loc>https://careers.acme.example/about</loc></url>"
        )
        return gzip.compress(
            f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{entries}</urlset>'.encode()
        )


def posting_page(title, **extra):
    return page(json.dumps({**POSTING, "title": title, **extra}))


def test_reads_a_career_site_incrementally(monkeypatch):
    site = FakeSite(
        monkeypatch,
        {
            "/jobs/1": ("2026-10-01", posting_page("Software Engineer")),
            "/jobs/2": ("2026-10-05", posting_page("Data Engineer")),
            "/jobs/3": ("2026-10-03", posting_page("Old Role", validThrough="2020-01-01")),
            "/jobs/4": (None, "<html>no posting here</html>"),
        },
    )
    company = Company("Acme", "jsonld", "careers.acme.example/jobs")
    jobs = jsonld.fetch_jsonld(company)
    assert "https://careers.acme.example/jobs.xml.gz" in site.read  # the job sitemap is read before news
    assert [j.external_id for j in jobs] == [
        "careers.acme.example/jobs/2",
        "careers.acme.example/jobs/1",
    ]  # newest first
    # the expired posting leaves the listing (it closes); a page without a posting stays (never stored)
    assert jobs.listed == frozenset(
        {"careers.acme.example/jobs/1", "careers.acme.example/jobs/2", "careers.acme.example/jobs/4"}
    )
    assert jobs[0].source_updated_at == datetime(2026, 10, 5)

    # next run: stored pages aren't read again unless their lastmod moved on
    site.read.clear()
    stored = {
        "careers.acme.example/jobs/1": (datetime(2026, 10, 1), "x", None),
        "careers.acme.example/jobs/2": (datetime(2026, 10, 1), "x", None),
    }
    jobs = jsonld.fetch_jsonld(company, known=frozenset(stored), stored=stored)
    pages_read = [u for u in site.read if "/jobs/" in u]
    assert sorted(pages_read) == [
        "https://careers.acme.example/jobs/2",
        "https://careers.acme.example/jobs/3",
        "https://careers.acme.example/jobs/4",
    ]
    assert "careers.acme.example/jobs/1" in jobs.listed  # not read again, still open


def test_reading_is_capped_per_run_and_failures_keep_postings_listed(monkeypatch):
    site = FakeSite(
        monkeypatch,
        {f"/jobs/{i}": (f"2026-10-{i + 1:02d}", posting_page(f"Engineer {i}")) for i in range(1, 9)},
    )
    monkeypatch.setenv("GHOSTLESS_JSONLD_PAGES_PER_SITE", "3")
    del site.pages["/jobs/8"]  # in the sitemap, but the page fails to load
    site.pages["/jobs/8"] = ("2026-10-09", None)  # keep it in the sitemap

    def flaky(url):
        if url.endswith("/jobs/8"):
            raise FetchError("server error (503)")
        return FakeSite.get_text(site, url)

    monkeypatch.setattr(http, "get_text", flaky)
    jobs = jsonld.fetch_jsonld(Company("Acme", "jsonld", "careers.acme.example/jobs"))
    assert (
        len(jobs) == 2 and "careers.acme.example/jobs/8" in jobs.listed
    )  # 3 tried, 1 failed, nothing closed


def test_a_site_without_job_pages_fails(monkeypatch):
    FakeSite(monkeypatch, {})
    with pytest.raises(FetchError, match="no job pages"):
        jsonld.fetch_jsonld(Company("Acme", "jsonld", "careers.acme.example/jobs"))


def test_settings_are_off_by_default_and_bounded(monkeypatch):
    for name in (
        "GHOSTLESS_SNOWBALL",
        "GHOSTLESS_JSONLD",
        "GHOSTLESS_VERIFY_PER_RUN",
        "GHOSTLESS_JSONLD_PAGES_PER_SITE",
    ):
        monkeypatch.delenv(name, raising=False)
    assert not settings.snowball() and not settings.jsonld()
    assert settings.verify_per_run() == 100 and settings.jsonld_pages_per_site() == 25
    monkeypatch.setenv("GHOSTLESS_SNOWBALL", "1")
    monkeypatch.setenv("GHOSTLESS_VERIFY_PER_RUN", "999999")
    monkeypatch.setenv("GHOSTLESS_JSONLD_PAGES_PER_SITE", "lots")
    assert (
        settings.snowball() and settings.verify_per_run() == 1000 and settings.jsonld_pages_per_site() == 25
    )


def test_robots_sitemaps():
    from tracker.sources.robots import parse

    rules = parse(
        "Sitemap: https://x.example/a.xml\nUser-agent: *\nDisallow: /p\nSitemap: https://x.example/b.xml\n",
        "g",
    )
    assert rules.sitemaps == ["https://x.example/a.xml", "https://x.example/b.xml"]


def test_job_ids_ignore_query_and_scheme():
    assert jsonld.job_id("HTTPS://Careers.Acme.example/jobs/42/?utm=x#top") == "careers.acme.example/jobs/42"
    assert datetime.now(timezone.utc)  # keeps the timezone import used


def test_job_pages_under_a_parent_path_are_found(monkeypatch):
    """A job link's path can be more specific than where the site lists its jobs."""
    site = FakeSite(monkeypatch, {"/jobs/1": ("2026-10-01", posting_page("Software Engineer"))})
    pages = jsonld.list_job_pages("careers.acme.example/jobs/engineering")
    assert list(pages) == ["careers.acme.example/jobs/1"]
    assert jsonld.list_job_pages("careers.acme.example/other") == {}  # never widened to the whole site
    assert site.read
