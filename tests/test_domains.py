"""Company websites for logos: each source, the name matching, and the database step."""

import os
from collections import Counter
from datetime import datetime, timezone

import pytest

from tests.conftest import reset_database
from tracker import db, domains
from tracker.models import Company, Job
from tracker.sources import http
from tracker.sources.http import FetchError


def test_registrable_keeps_the_part_a_company_owns():
    assert domains.registrable("careers.amd.com") == "amd.com"
    assert domains.registrable("jobs.example.co.uk") == "example.co.uk"
    assert domains.registrable("lifeattiktok.com") == "lifeattiktok.com"


def test_domain_of_reads_websites_and_refuses_job_boards():
    assert domains.domain_of("https://www.voyantphotonics.com/") == "voyantphotonics.com"
    assert domains.domain_of("http:\\/\\/eluv.io") == "eluv.io"
    assert domains.domain_of("withpersona.com") == "withpersona.com"
    assert domains.domain_of("https://jobs.lever.co/acme") is None
    assert domains.domain_of("https://www.linkedin.com/company/acme") is None
    assert domains.domain_of("") is None
    assert domains.domain_of(None) is None


@pytest.mark.parametrize(
    "name, domain",
    [
        ("Klaviyo", "klaviyo.com"),
        ("Pure Storage", "purestorage.com"),
        ("KLA Corporation", "kla.com"),
        ("Vishay Intertechnology", "vishay.com"),
        ("WSFS Bank", "wsfsbank.com"),
        ("Prysmian Cables & Systems", "prysmiangroup.com"),
        ("CHAOS Industries", "chaosinc.com"),
        ("T-Mobile", "t-mobile.com"),
        ("Lowe's", "lowes.com"),
    ],
)
def test_names_match(name, domain):
    assert domains.names_match(name, domain)


@pytest.mark.parametrize(
    "name, domain",
    [
        ("Found Energy", "found-industries.com"),  # a longer name that merely starts the same
        ("Acme", "benefitsplan.com"),
        ("AI", "ai.com"),  # too short to tell
        ("Relay", "re.com"),
    ],
)
def test_names_that_dont_match(name, domain):
    assert not domains.names_match(name, domain)


def test_from_postings_picks_the_matching_domain_most_postings_mention():
    hosts = Counter(
        {
            "www.purestorage.com": 3,
            "purestorage.com": 1,
            "careers.purestorage.com": 2,
            "www.eeoc.gov": 5,
            "linkedin.com": 4,
            "unrelated.com": 9,
        }
    )
    assert domains.from_postings("Pure Storage", hosts) == "purestorage.com"
    assert domains.from_postings("Pure Storage", Counter({"unrelated.com": 9})) is None


def test_hiring_systems_that_several_companies_share_are_not_employers():
    names_by_host = {
        "careers-gdms.icims.com": {"General Dynamics Mission Systems"},
        "acme.hireflow.com": {"Acme"},
        "globex.hireflow.com": {"Globex"},
        "careers.amd.com": {"AMD"},
        "jobs.kla.com": {"KLA", "KLA Corporation"},  # one company stored twice
    }
    shared = domains.shared_domains(names_by_host)
    assert "hireflow.com" in shared
    assert "amd.com" not in shared and "kla.com" not in shared

    assert domains.from_apply_links(Counter({"careers.amd.com": 5}), shared) == "amd.com"
    assert domains.from_apply_links(Counter({"acme.hireflow.com": 5}), shared) is None
    assert domains.from_apply_links(Counter({"careers-gdms.icims.com": 5}), shared) is None  # known system
    assert (
        domains.from_apply_links(Counter({"careers.amd.com": 1, "amd.wd1.myworkdayjobs.com": 9}), shared)
        == "amd.com"
    )


def test_board_lookups_read_the_website_the_employer_entered(monkeypatch):
    pages = []
    monkeypatch.setattr(
        http,
        "get_text",
        lambda url: (
            pages.append(url)
            or '<script>window.__appData = {"organization":{"publicWebsite":"https:\\/\\/voyantphotonics.com\\/"}}</script>'
        ),
    )
    assert domains.from_ashby("voyant-photonics") == "voyantphotonics.com"
    assert pages == ["https://jobs.ashbyhq.com/voyant-photonics"]

    monkeypatch.setattr(http, "get_json", lambda url: {"name": "Eluvio", "url": "http://eluv.io"})
    assert domains.from_workable("eluvio") == "eluv.io"
    monkeypatch.setattr(
        http, "get_json", lambda url: {"name": "Nowhere", "url": "https://apply.workable.com/nowhere"}
    )
    assert domains.from_workable("nowhere") is None


DSN = os.environ.get("TEST_DATABASE_URL")


@pytest.fixture
def conn():
    if not DSN:
        pytest.skip("TEST_DATABASE_URL not set")
    with db.connect(DSN) as c:
        reset_database(c)
        db.apply_schema(c)
        yield c


def _company(conn, name, platform, slug, urls, description=None):
    company_id = db.upsert_company(conn, Company(name, platform, slug))
    jobs = [
        Job(
            external_id=str(i),
            title=f"Engineer {i}",
            url=url,
            level="new_grad",
            role_type="sde",
            description=description,
        )
        for i, url in enumerate(urls)
    ]
    db.save_company_jobs(conn, company_id, jobs, datetime(2026, 10, 1, tzinfo=timezone.utc))
    conn.commit()
    return company_id


def test_fill_finds_websites_once_and_never_replaces_one(conn, monkeypatch):
    voyant = _company(
        conn, "Voyant Photonics", "list", "voyant", ["https://jobs.ashbyhq.com/voyant-photonics/1"]
    )
    amd = _company(
        conn, "AMD", "list", "amd", ["https://careers.amd.com/jobs/1", "https://careers.amd.com/jobs/2"]
    )
    pure = _company(
        conn,
        "Pure Storage",
        "list",
        "pure",
        ["https://job-boards.greenhouse.io/purestorage/jobs/1"],
        description="Learn more at www.purestorage.com. Questions: careers@purestorage.com",
    )
    nobody = _company(conn, "Quiet Co", "list", "quiet", ["https://job-boards.greenhouse.io/quiet/jobs/1"])
    known = _company(conn, "Known", "list", "known", ["https://jobs.ashbyhq.com/known/1"])
    conn.execute("UPDATE companies SET domain = 'known.example' WHERE id = %s", (known,))
    conn.commit()

    lookups = []
    monkeypatch.setattr(
        domains,
        "BOARDS",
        {
            "ashby": lambda slug: lookups.append(slug) or "voyantphotonics.com",
            "workable": lambda slug: None,
        },
    )

    preview = domains.fill(DSN, dry_run=True)
    assert conn.execute("SELECT count(*) FROM companies WHERE domain IS NOT NULL").fetchone()[0] == 1
    assert (preview.from_board, preview.from_careers_site, preview.from_postings, preview.not_found) == (
        1,
        1,
        1,
        1,
    )

    domains.fill(DSN)
    got = dict(conn.execute("SELECT id, domain FROM companies").fetchall())
    assert got[voyant] == "voyantphotonics.com"
    assert got[amd] == "amd.com"
    assert got[pure] == "purestorage.com"
    assert got[nobody] is None
    assert got[known] == "known.example"  # filled in elsewhere: left alone, never looked up
    assert "known" not in lookups

    # everything was looked at: the next run asks nothing until the recheck is due
    lookups.clear()
    again = domains.fill(DSN)
    assert again.looked_at == 0 and lookups == []


def test_a_failed_board_lookup_is_tried_again_next_run(conn, monkeypatch):
    company = _company(
        conn, "Voyant Photonics", "list", "voyant", ["https://jobs.ashbyhq.com/voyant-photonics/1"]
    )

    def down(slug):
        raise FetchError("503")

    monkeypatch.setattr(domains, "BOARDS", {"ashby": down, "workable": down})
    report = domains.fill(DSN)
    assert report.failed_lookups == 1 and report.looked_at == 0
    assert (
        conn.execute("SELECT domain_checked_at FROM companies WHERE id = %s", (company,)).fetchone()[0]
        is None
    )

    monkeypatch.setattr(domains, "BOARDS", {"ashby": lambda slug: "voyantphotonics.com", "workable": down})
    domains.fill(DSN)
    assert (
        conn.execute("SELECT domain FROM companies WHERE id = %s", (company,)).fetchone()[0]
        == "voyantphotonics.com"
    )
