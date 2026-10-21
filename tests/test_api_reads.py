"""What the website's API reads from the database (Neon caps it monthly): the
company endpoints read only the rows they return, and the resume endpoints
keep the matching pool and descriptions until an ingest finishes, with the
same answers as before. Against a real PostgreSQL (skipped without
TEST_DATABASE_URL)."""

import os
import unicodedata
from datetime import datetime, timedelta, timezone

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from tests.conftest import reset_database  # noqa: E402
from tracker import db  # noqa: E402
from tracker.api import cache, create_app, queries  # noqa: E402
from tracker.api.deps import limiter  # noqa: E402
from tracker.classify import enrich  # noqa: E402
from tracker.models import Company, Job  # noqa: E402
from tracker.skills import extract_skills  # noqa: E402

DSN = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DSN, reason="TEST_DATABASE_URL not set")

NOW = datetime.now(timezone.utc)
DAY0 = NOW - timedelta(days=10)
DAY1 = NOW - timedelta(days=2)
NAMES = (
    "Alpha Bravo Charlie Delta Echo Foxtrot Golf Hotel India Juliet Kilo Lima Mike "
    "November Oscar Papa Quebec Romeo Sierra Tango Uniform Victor Whiskey Xray"
).split()
PLACES = ["Toronto, ON", "Remote", "Austin, TX"]
TRICKY = ["Café Nouveau", "AT&T", "--Weird  Name!!", "3M", "Ünïcode Labs", "O'Reilly Media"]


def posting(key, title, location, ghost=False):
    text = "Python, SQL and AWS. " + ("This posting is not for an existing vacancy." if ghost else "")
    job = Job(
        external_id=key, title=title, url=f"https://x.example/{key}", location=location, description=text
    )
    return enrich(job, extract_skills(f"{title} {text}"))


def finish_a_run(conn, when):
    run = db.start_run(conn, when)
    db.finish_run(
        conn,
        run,
        dict(companies_ok=1, companies_failed=0, jobs_seen=1, jobs_new=0, jobs_closed=0, duration_seconds=1),
    )


@pytest.fixture
def client():
    with db.connect(DSN) as conn:
        reset_database(conn)
        db.apply_schema(conn)
        for i, name in enumerate(NAMES + TRICKY):
            listed = i % 5 == 4
            company = Company(
                name,
                "list" if listed else "greenhouse",
                f"list:{name.lower()}" if listed else f"b{i}",
                origin="list" if listed else "configured",
            )
            company_id = db.upsert_company(conn, company)
            day0 = [
                posting(f"{i}-t{n}", "Software Engineer", PLACES[(i + n) % 3], ghost=(i + n) % 7 == 0)
                for n in range(i % 4 + 1)
            ] + [posting(f"{i}-o{n}", "Account Manager", "Toronto, ON") for n in range(i % 3)]
            db.save_company_jobs(conn, company_id, day0, DAY0)
            if i % 3 == 0:  # new this week
                more = [posting(f"{i}-n{n}", "Data Engineer", "Remote") for n in range(i % 5)]
                db.save_company_jobs(conn, company_id, day0 + more, DAY1)
        finish_a_run(conn, DAY1)
        db.refresh_signals(conn)
        conn.commit()
    limiter.reset()
    cache.reset()
    with TestClient(create_app(DSN)) as c:
        yield c


# ---------- 1. one company ----------


def test_the_slug_is_matched_in_the_database_exactly_as_slugify_makes_it(client):
    with db.connect(DSN) as conn:
        for name in TRICKY + ["Plain", "a--b", "Ünïcode"]:
            in_sql = conn.execute(
                f"SELECT {queries.SLUG_SQL} FROM (SELECT %s::text AS name) c", (name,)
            ).fetchone()[0]
            assert in_sql == queries.slugify(name), name
    for name in TRICKY:
        company = client.get(f"/companies/{queries.slugify(name)}")
        assert company.status_code == 200 and company.json()["name"] == name
    every = {c["slug"]: c for c in client.get("/companies").json()}
    assert {k: v for k, v in client.get("/companies/golf").json().items() if k in every["golf"]} == every[
        "golf"
    ]
    assert client.get("/companies/nope").status_code == 404


# ---------- 2. the Companies page, search suggestions and sitemap ----------

SORT_KEYS = {  # web/src/app/companies/page.tsx
    "open": lambda c: -c["tech_active_jobs"],
    "new": lambda c: -c["new_last_7_days"],
    "fastest": lambda c: 9999 if c["typical_days_open"] is None else c["typical_days_open"],
    "risk": lambda c: -(c["high_risk_jobs"] / max(1, c["active_jobs"])),
}


def by_name(name):
    """localeCompare's order for these names: accents and case only break ties."""
    plain = "".join(ch for ch in unicodedata.normalize("NFKD", name) if not unicodedata.combining(ch))
    return (plain.casefold(), name.swapcase())


def like_the_website(everyone, sort, q, source, page, per_page):
    """What the Companies page computed from the whole /companies list."""
    needle = q.lower()
    chosen = [
        c
        for c in everyone
        if (source == "all" or (c["origin"] == "list") == (source == "lists")) and needle in c["name"].lower()
    ]
    chosen.sort(key=lambda c: (SORT_KEYS[sort](c), by_name(c["name"])))
    pages = max(1, -(-len(chosen) // per_page))
    page = min(pages, max(1, page))
    return {
        "total": len(chosen),
        "page": page,
        "per_page": per_page,
        "employers": len(everyone),
        "from_lists": sum(c["origin"] == "list" for c in everyone),
        "total_open": sum(c["tech_active_jobs"] for c in everyone),
        "items": chosen[(page - 1) * per_page : page * per_page],
    }


@pytest.mark.parametrize("sort", ["open", "new", "fastest", "risk"])
@pytest.mark.parametrize("source", ["all", "boards", "lists"])
def test_the_company_list_is_the_page_the_website_showed(client, sort, source):
    everyone = client.get("/companies").json()
    for q in ("", "o", "ECHO", "zzz"):
        for page in (1, 2, 3, 99):
            got = client.get(
                "/company-list", params={"sort": sort, "q": q, "source": source, "page": page, "per_page": 5}
            ).json()
            assert got == like_the_website(everyone, sort, q, source, page, 5), (q, page)


def test_company_names_answer_the_suggestions_and_the_sitemap(client):
    everyone = client.get("/companies").json()
    names = client.get("/company-names").json()
    assert [n["slug"] for n in names] == [c["slug"] for c in everyone]  # the sitemap's list, in order
    assert names[0] == {k: everyone[0][k] for k in ("name", "slug", "domain", "tech_active_jobs")}
    for q in ("a", "o", "ec", "Z"):  # web/src/app/api/search/suggest/route.ts
        needle = q.lower()
        expected = sorted(
            (c for c in everyone if c["tech_active_jobs"] > 0 and needle in c["name"].lower()),
            key=lambda c: (not c["name"].lower().startswith(needle), -c["tech_active_jobs"]),
        )[:2]
        got = client.get("/company-names", params={"q": q, "limit": 2}).json()
        assert [n["slug"] for n in got] == [c["slug"] for c in expected], q


# ---------- 3 and 4. the resume endpoints' memory ----------

PROFILE = {"skills": ["Python", "SQL", "AWS"], "level": "new_grad", "top_role": "sde"}


def test_one_pool_serves_every_filter_until_an_ingest_finishes(client, monkeypatch):
    loads = []
    real = queries.matching_pool
    monkeypatch.setattr(
        queries, "matching_pool", lambda conn, *a, **k: loads.append(a) or real(conn, *a, **k)
    )
    with db.connect(DSN) as conn:
        for location in ("any", "canada", "remote", "canada_or_remote"):
            for risky in (False, True):
                shared = [j["id"] for j in cache.job_pool(conn, location, risky)]
                assert shared == [j["id"] for j in real(conn, location, risky)], (location, risky)
    assert len(loads) == 1
    for location in ("any", "remote"):
        page = client.post(
            "/resume/recommendations", json={"profile": PROFILE, "location": location, "limit": 5}
        )
        assert page.status_code == 200 and page.json()["items"]
    assert len(loads) == 1  # the endpoint uses the same copy

    monkeypatch.setattr(cache, "CHECK_SECONDS", 0)
    with db.connect(DSN) as conn:
        cache.job_pool(conn)
        assert len(loads) == 1  # nothing changed
        finish_a_run(conn, NOW)
        conn.commit()
        cache.job_pool(conn)
    assert len(loads) == 2  # a new ingest: read again


def test_pool_skills_are_read_for_the_pool_only(client):
    with db.connect(DSN) as conn:
        pool = queries.matching_pool(conn, "remote")
        assert pool and all(j["skills"] for j in pool)
        assert {j["id"] for j in pool} == {j["id"] for j in cache.job_pool(conn, "remote")}


def test_descriptions_are_read_once_until_an_ingest_finishes(client, monkeypatch):
    asked = []
    real = queries.descriptions
    monkeypatch.setattr(queries, "descriptions", lambda conn, ids: asked.append(list(ids)) or real(conn, ids))
    ids = [j["id"] for j in client.get("/jobs", params={"limit": 10}).json()["items"]]
    first = client.post("/resume/match", json={"profile": PROFILE, "job_ids": ids})
    again = client.post("/resume/match", json={"profile": PROFILE, "job_ids": ids})
    assert first.status_code == 200 and first.json() == again.json()
    assert asked == [ids]  # the second request read nothing
    with db.connect(DSN) as conn:
        assert cache.descriptions(conn, ids + [999_999]) == real(conn, ids)
        assert asked[-1] == [999_999]  # a posting without text is remembered too
        cache.descriptions(conn, [999_999])
        assert asked[-1] == [999_999] and len(asked) == 2

        monkeypatch.setattr(cache, "CHECK_SECONDS", 0)
        finish_a_run(conn, NOW)
        conn.commit()
        cache.descriptions(conn, ids[:3])
    assert asked[-1] == ids[:3]  # read again after an ingest
