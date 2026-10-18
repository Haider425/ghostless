"""API tests against a real PostgreSQL (skipped unless TEST_DATABASE_URL is set).

The fixture builds a small, realistic history: two daily runs, a closed and
reposted role, an evergreen talent-pool posting, salaries and skills.
"""

import os
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from tests.conftest import reset_database
from tracker import db  # noqa: E402
from tracker.api import create_app  # noqa: E402
from tracker.classify import enrich  # noqa: E402
from tracker.models import Company, Job  # noqa: E402
from tracker.skills import extract_skills  # noqa: E402

DSN = os.environ.get("TEST_DATABASE_URL")
needs_db = pytest.mark.skipif(not DSN, reason="TEST_DATABASE_URL not set")

NOW = datetime.now(timezone.utc)
DAY0 = NOW - timedelta(days=10)  # first run: everything seen here was already open
DAY1 = NOW - timedelta(days=2)  # second run: anything first seen here is genuinely new
TORONTO_DAY1 = DAY1.astimezone(ZoneInfo("America/Toronto")).date()


def job(ext_id, title, location="Toronto, ON", description=""):
    j = Job(
        external_id=ext_id,
        title=title,
        url=f"https://acme.example/{ext_id}",
        location=location,
        description=description,
    )
    return enrich(j, extract_skills(f"{title} {description}"))


INTERN = job("intern", "Software Engineer Intern", description="Python and AWS. Pay: $30 - $38 per hour.")
DATA_OLD = job("data-old", "Data Engineer", description="Build Spark pipelines with Airflow and SQL.")
DATA_NEW = job("data-new", "Data Engineer", description="Build Spark pipelines with Airflow and SQL.")
POOL = job(
    "pool",
    "New Grad Software Engineer",
    location="Vancouver, BC",
    description="This posting is not for an existing vacancy. Java and React. "
    "Salary $85,000 - $105,000 per year.",
)
SENIOR = job("senior", "Senior Software Engineer", location="Austin, TX", description="Go and Kubernetes.")


@pytest.fixture(scope="module")
def client():
    if not DSN:
        pytest.skip("TEST_DATABASE_URL not set")
    with db.connect(DSN) as conn:
        reset_database(conn)
        db.apply_schema(conn)
        acme = db.upsert_company(conn, Company("Acme", "greenhouse", "acme", domain="acme.example"))
        beta = db.upsert_company(conn, Company("Beta", "workday", "beta"))

        run = db.start_run(conn, DAY0)
        db.save_company_jobs(conn, acme, [INTERN, DATA_OLD], DAY0)
        db.save_company_jobs(conn, beta, [SENIOR], DAY0)
        db.finish_run(
            conn,
            run,
            dict(
                companies_ok=2,
                companies_failed=0,
                jobs_seen=3,
                jobs_new=3,
                jobs_closed=0,
                duration_seconds=12.5,
            ),
        )

        run = db.start_run(conn, DAY1)
        db.save_company_jobs(conn, acme, [INTERN, DATA_NEW, POOL], DAY1)  # DATA_OLD closed, reposted
        db.save_company_jobs(conn, beta, [SENIOR], DAY1)
        db.finish_run(
            conn,
            run,
            dict(
                companies_ok=2,
                companies_failed=0,
                jobs_seen=4,
                jobs_new=2,
                jobs_closed=1,
                duration_seconds=10.0,
            ),
        )
        conn.commit()
        db.refresh_signals(conn)

    with TestClient(create_app(DSN)) as test_client:
        yield test_client


def ids(response):
    assert response.status_code == 200, response.text
    return [item["url"].rsplit("/", 1)[-1] for item in response.json()["items"]]


def test_health_does_not_need_a_database():
    with TestClient(create_app("postgresql://nobody@127.0.0.1:1/none")) as c:
        assert c.get("/health").json() == {"status": "ok"}


@needs_db
def test_default_listing_is_active_jobs_newest_first(client):
    body = client.get("/jobs").json()
    assert body["total"] == 4
    assert set(ids(client.get("/jobs"))[:2]) == {"pool", "data-new"}  # the newest day first
    first = body["items"][0]
    assert set(first) >= {"company", "title", "url", "signals", "skills", "salary", "first_seen"}


@needs_db
def test_job_shape_salary_skills_and_signals(client):
    intern = next(i for i in client.get("/jobs", params={"level": "intern"}).json()["items"])
    assert intern["salary"] == {"min": 30.0, "max": 38.0, "period": "hour", "currency": "CAD"}
    assert intern["skills"] == ["AWS", "Python"]
    assert intern["signals"]["risk"] == "low"
    assert intern["signals"]["age_known"] is False  # was already open when tracking began
    assert intern["signals"]["days_open"] >= 9


@needs_db
def test_filters(client):
    assert ids(client.get("/jobs", params={"location": "canada", "role": "sde", "sort": "company"})) == [
        "pool",
        "intern",
    ]
    assert ids(client.get("/jobs", params={"risk": "high"})) == ["pool"]
    assert ids(client.get("/jobs", params={"risk": "medium"})) == ["data-new"]
    assert ids(client.get("/jobs", params={"company": "BETA"})) == ["senior"]
    assert ids(client.get("/jobs", params={"skill": "airflow"})) == ["data-new"]
    assert sorted(ids(client.get("/jobs", params={"has_salary": True}))) == ["intern", "pool"]
    assert sorted(ids(client.get("/jobs", params={"new_within_days": 7}))) == ["data-new", "pool"]
    assert ids(client.get("/jobs", params={"q": "intern"})) == ["intern"]
    assert ids(client.get("/jobs", params={"status": "closed"})) == ["data-old"]
    # same first_seen and no date from the site: a stable order mixed across companies
    tied = ids(client.get("/jobs", params={"level": ["intern", "senior"], "sort": "oldest"}))
    assert sorted(tied) == ["intern", "senior"]
    assert ids(client.get("/jobs", params={"level": ["intern", "senior"], "sort": "oldest"})) == tied


@needs_db
def test_search_matches_company_place_and_skills_not_just_titles(client):
    assert ids(client.get("/jobs", params={"q": "beta"})) == ["senior"]  # a company name
    assert ids(client.get("/jobs", params={"q": "jobs at Beta"})) == ["senior"]  # filler words ignored
    assert ids(client.get("/jobs", params={"q": "airflow"})) == ["data-new"]  # a skill
    assert ids(client.get("/jobs", params={"q": "acme intern"})) == ["intern"]  # every word must match
    assert ids(client.get("/jobs", params={"q": "beta intern"})) == []


@needs_db
def test_search_text_is_treated_literally(client):
    for q in ["%", "_", "' OR 1=1 --", "\\"]:
        response = client.get("/jobs", params={"q": q})
        assert response.status_code == 200
        assert response.json()["total"] == 0


@needs_db
def test_pagination_and_validation(client):
    page = client.get("/jobs", params={"limit": 2, "offset": 2}).json()
    assert (page["total"], page["limit"], page["offset"], len(page["items"])) == (4, 2, 2, 2)
    assert client.get("/jobs", params={"limit": 101}).status_code == 422
    assert client.get("/jobs", params={"level": "wizard"}).status_code == 422
    assert client.get("/jobs", params={"sort": "random"}).status_code == 422


@needs_db
def test_job_detail_includes_description_and_repost_history(client):
    data_new = client.get("/jobs", params={"risk": "medium"}).json()["items"][0]
    detail = client.get(f"/jobs/{data_new['id']}").json()
    assert detail["description"].startswith("Build Spark pipelines")
    assert detail["signals"]["flags"] == ["reposted"]
    assert [h["url"].rsplit("/", 1)[-1] for h in detail["posting_history"]] == ["data-old"]
    assert detail["posting_history"][0]["is_active"] is False
    assert client.get("/jobs/999999").status_code == 404


@needs_db
def test_companies_and_stats(client):
    companies = {c["name"]: c for c in client.get("/companies").json()}
    assert companies["Acme"] == {
        "name": "Acme",
        "slug": "acme",
        "domain": "acme.example",
        "platform": "greenhouse",
        "origin": "configured",
        "active_jobs": 3,
        "tech_active_jobs": 3,
        "high_risk_jobs": 1,
        "new_last_7_days": 2,
        "typical_days_open": None,
    }
    stats = client.get("/stats").json()
    assert stats["active_jobs"] == 4
    assert stats["companies"] == 2
    assert stats["new_last_7_days"] == 2
    assert stats["canada_active_jobs"] == 3
    assert stats["high_risk_active_jobs"] == 1
    assert stats["with_salary_active_jobs"] == 2
    assert stats["signals_computed_at"] is not None
    assert stats["last_run"]["jobs_closed"] == 1
    assert stats["tech_active_jobs"] == 4


@needs_db
def test_company_detail(client):
    acme = client.get("/companies/acme").json()
    assert acme["name"] == "Acme" and acme["domain"] == "acme.example"
    assert {r["key"]: r["count"] for r in acme["roles"]} == {"sde": 2, "data_eng": 1}
    assert len(acme["weekly"]) == 12
    assert sum(w["new"] for w in acme["weekly"]) == 2
    assert sum(w["closed"] for w in acme["weekly"]) == 1
    assert acme["top_skills"][0]["postings"] >= 1
    assert client.get("/companies/nope").status_code == 404


@needs_db
def test_weekly_trend(client):
    weeks = client.get("/trends/weekly", params={"weeks": 4}).json()
    assert len(weeks) == 4
    assert weeks[0]["week_start"] < weeks[-1]["week_start"]


@needs_db
def test_job_detail_quotes_its_evidence(client):
    pool = client.get("/jobs", params={"risk": "high"}).json()["items"][0]
    assert pool["company_slug"] == "acme"
    detail = client.get(f"/jobs/{pool['id']}").json()
    assert detail["evidence"]["vacancy"] == "This posting is not for an existing vacancy."
    assert detail["evidence"]["salary"] == "Salary $85,000 - $105,000 per year."
    assert detail["evidence"]["ai_screening"] is None


@needs_db
def test_skills_endpoints(client):
    top = client.get(
        "/skills/top", params={"role": ["sde", "data_eng"], "level": ["intern", "new_grad", "mid"]}
    )
    names = [s["skill"] for s in top.json()]
    assert {"Python", "AWS", "Java", "React", "Spark"} <= set(names)
    assert "Go" not in names  # Austin senior role is excluded by level and location

    gap = client.get("/skills/gap", params={"have": "python, postgres, juggling"}).json()
    assert gap["recognized"] == ["PostgreSQL", "Python"]
    assert gap["unrecognized"] == ["juggling"]
    assert "AWS" in gap["missing_top_10"]
    assert client.get("/skills/gap").status_code == 422


@needs_db
def test_calendar(client):
    rows = client.get("/calendar").json()
    assert rows == [
        {
            "company": "Acme",
            "level": "new_grad",
            "role_type": "sde",
            "year": TORONTO_DAY1.year,
            "first_opened": TORONTO_DAY1.isoformat(),
            "last_opened": TORONTO_DAY1.isoformat(),
            "postings": 1,
        }
    ]


@needs_db
def test_cache_headers_and_cors(client):
    response = client.get("/stats", headers={"Origin": "https://ghostless.example"})
    assert response.headers["cache-control"] == "public, max-age=300"
    assert response.headers["access-control-allow-origin"] == "*"
    assert "cache-control" not in client.get("/health").headers


@needs_db
def test_clear_error_before_first_ingest():
    with db.connect(DSN) as conn:
        conn.execute("DROP MATERIALIZED VIEW IF EXISTS job_signals_mv")
        conn.commit()
    try:
        with TestClient(create_app(DSN)) as c:
            response = c.get("/jobs")
        assert response.status_code == 503
        assert "ghostless ingest" in response.json()["detail"]
    finally:
        with db.connect(DSN) as conn:
            db.apply_schema(conn)
