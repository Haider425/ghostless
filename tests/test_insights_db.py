"""Ghost signals, hiring calendar and skills gap against a real PostgreSQL.
Skipped unless TEST_DATABASE_URL is set (CI provides one)."""

import os
from datetime import datetime, timedelta, timezone

import pytest

from tests.conftest import reset_database
from tracker import db, insights
from tracker.classify import enrich
from tracker.models import Company, Job
from tracker.skills import extract_skills

DSN = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DSN, reason="TEST_DATABASE_URL not set")

DAY0 = datetime(2026, 9, 1, 10, tzinfo=timezone.utc)


@pytest.fixture
def conn():
    with db.connect(DSN) as c:
        reset_database(c)
        db.apply_schema(c)
        yield c


def job(ext_id, title="Software Engineer", description="Build APIs in Python.", location="Toronto, ON"):
    j = Job(
        external_id=ext_id, title=title, url=f"https://x/{ext_id}", location=location, description=description
    )
    return enrich(j, extract_skills(f"{title} {description}"))


def day(n):
    return DAY0 + timedelta(days=n)


def signals(conn, ext_id):
    return conn.execute(
        """SELECT s.ghost_risk, s.flags, s.age_known, s.days_open, s.times_posted_before
           FROM job_signals s JOIN jobs j ON j.id = s.job_id WHERE j.external_id = %s""",
        (ext_id,),
    ).fetchone()


def test_disclosures_are_stored(conn):
    cid = db.upsert_company(conn, Company("Acme", "greenhouse", "acme"))
    text = "Salary $90,000 - $110,000 per year. This posting is for an existing vacancy."
    db.save_company_jobs(conn, cid, [job("1", description=text)], day(0))
    row = conn.execute(
        "SELECT salary_min, salary_max, salary_period, salary_currency, vacancy FROM jobs"
    ).fetchone()
    assert (float(row[0]), float(row[1]), row[2], row[3], row[4]) == (
        90000,
        110000,
        "year",
        "CAD",
        "existing",
    )


def test_repost_is_linked_and_flagged(conn):
    cid = db.upsert_company(conn, Company("Acme", "greenhouse", "acme"))
    db.save_company_jobs(conn, cid, [job("old"), job("other", title="Data Analyst")], day(0))
    db.save_company_jobs(conn, cid, [job("old"), job("other", title="Data Analyst")], day(1))
    # Day 2: same role taken down and put back up under a new id
    db.save_company_jobs(conn, cid, [job("new"), job("other", title="Data Analyst")], day(2))

    old_id, new_from = conn.execute(
        """SELECT (SELECT id FROM jobs WHERE external_id = 'old'),
                  (SELECT reposted_from FROM jobs WHERE external_id = 'new')"""
    ).fetchone()
    assert new_from == old_id

    risk, flags, age_known, _, before = signals(conn, "new")
    assert risk == "medium" and flags == ["reposted"] and age_known and before == 1


def test_not_existing_vacancy_is_high_risk(conn):
    cid = db.upsert_company(conn, Company("Acme", "greenhouse", "acme"))
    db.save_company_jobs(conn, cid, [job("seed", title="Recruiter")], day(0))
    pool = job("pool", description="This posting is not for an existing vacancy. Python.")
    db.save_company_jobs(conn, cid, [job("seed", title="Recruiter"), pool], day(1))
    risk, flags, *_ = signals(conn, "pool")
    assert risk == "high" and flags == ["not_existing_vacancy"]


def test_duplicate_and_long_open_postings(conn):
    cid = db.upsert_company(conn, Company("Acme", "greenhouse", "acme"))
    # Two live copies of the identical role, open since the first run
    db.save_company_jobs(conn, cid, [job("a"), job("b")], datetime.now(timezone.utc) - timedelta(days=100))
    risk, flags, age_known, days_open, _ = signals(conn, "a")
    assert flags == ["duplicate_posting", "open_unusually_long"]  # same first run: neither is a repost
    assert risk == "high"
    assert age_known is False  # open before tracking began, so 100 days is a lower bound
    assert days_open >= 99


def test_unrelated_roles_with_same_title_are_not_reposts(conn):
    cid = db.upsert_company(conn, Company("Amazon", "amazon", "x"))
    db.save_company_jobs(conn, cid, [job("seed", title="Recruiter")], day(0))
    ads = job("ads", title="Software Development Engineer", description="Ads team. Java.")
    alexa = job("alexa", title="Software Development Engineer", description="Alexa team. Python.")
    db.save_company_jobs(conn, cid, [job("seed", title="Recruiter"), ads, alexa], day(1))
    assert signals(conn, "ads")[:2] == ("low", [])
    assert signals(conn, "alexa")[:2] == ("low", [])


def test_hiring_calendar_ignores_pre_tracking_jobs(conn):
    cid = db.upsert_company(conn, Company("TD", "workday", "td"))
    db.save_company_jobs(conn, cid, [job("existing", title="Software Engineer Intern")], day(0))
    db.save_company_jobs(
        conn,
        cid,
        [job("existing", title="Software Engineer Intern"), job("i1", title="Data Engineer Intern")],
        day(10),
    )
    rows = conn.execute(
        "SELECT company, level, role_type, first_opened, postings FROM hiring_calendar"
    ).fetchall()
    assert rows == [("TD", "intern", "data_eng", day(10).date(), 1)]


def test_skills_gap(conn):
    cid = db.upsert_company(conn, Company("Acme", "greenhouse", "acme"))
    jobs = [
        job("1", title="Software Engineer Intern", description="Python and AWS and Docker."),
        job("2", title="Software Engineer Intern", description="Python and AWS."),
        job("3", title="New Grad Software Engineer", description="Go and Kubernetes."),
        job("4", title="Senior Software Engineer", description="Rust."),  # wrong level
        job(
            "5", title="Software Engineer Intern", description="Python.", location="Austin, TX"
        ),  # not Canada
    ]
    db.save_company_jobs(conn, cid, jobs, day(0))
    report = insights.skills_gap(conn, have=["python", "postgres", "underwater basket weaving"])

    assert report.total_postings == 3
    top = {s.skill: (s.postings, s.have) for s in report.skills}
    assert top["Python"] == (2, True)
    assert top["AWS"] == (2, False)
    assert "Rust" not in top
    assert report.recognized == ["PostgreSQL", "Python"]
    assert report.unrecognized == ["underwater basket weaving"]
    text = insights.format_gap(report, "intern/new grad sde")
    assert "Biggest gaps: AWS" in text


def test_duplicates_need_matching_descriptions_and_locations(conn):
    cid = db.upsert_company(conn, Company("Bank", "workday", "bank"))
    text = "Build banking software."
    db.save_company_jobs(
        conn,
        cid,
        [
            # same title and city but no description: can't tell the roles apart
            job("x1", description=""),
            job("x2", description=""),
            # same title and description in different cities: separate roles
            job("y1", title="Data Engineer", description=text, location="Toronto, ON | Montreal, QC"),
            job("y2", title="Data Engineer", description=text, location="Toronto, ON | Vancouver, BC"),
        ],
        day(0),
    )
    for ext_id in ("x1", "x2", "y1", "y2"):
        assert "duplicate_posting" not in signals(conn, ext_id)[1]


def test_reprocess_clears_an_old_false_flag(conn):
    from tracker import reprocess

    cid = db.upsert_company(conn, Company("Stripe", "greenhouse", "stripe"))
    duties = "Build candidate pipelines for current and future hiring needs. Pay $100,000 to $120,000 a year."
    db.save_company_jobs(conn, cid, [job("r", title="Recruiter", description=duties)], day(0))
    conn.execute(
        "UPDATE jobs SET vacancy = 'not_existing', salary_min = NULL, salary_max = NULL"
    )  # as an older version stored it
    conn.commit()

    result = reprocess.run(DSN)
    assert result["postings"] == 1
    vacancy, salary_min = conn.execute("SELECT vacancy, salary_min FROM jobs").fetchone()
    assert vacancy is None and float(salary_min) == 100000


def test_reprocess_reads_seasons_and_keeps_job_list_labels(conn):
    from tracker import reprocess

    cid = db.upsert_company(conn, Company("Shopify", "greenhouse", "shopify"))
    text = "A 4-month work term beginning January 2027."
    db.save_company_jobs(
        conn,
        cid,
        [
            job("t", title="Software Engineering Intern (2027 Summer Internship)"),
            job("d", title="Data Engineering Co-op", description=text),
            job(
                "g", title="Software Engineer, Entry-Level (Graduation Date Winter 2026 - Spring/Summer 2027)"
            ),
            job("l", title="Hardware Intern"),
        ],
        datetime(2026, 10, 1, tzinfo=timezone.utc),
    )
    # as an older version stored them; "Hardware Intern" came from a job list labelled Fall 2027
    conn.execute("UPDATE jobs SET terms = '{}' WHERE external_id <> 'l'")
    conn.execute("UPDATE jobs SET terms = '{Fall 2027}', listed_in = 'Test list' WHERE external_id = 'l'")
    conn.commit()

    reprocess.run(DSN)
    terms = dict(conn.execute("SELECT external_id, terms FROM jobs").fetchall())
    assert terms == {"t": ["Summer 2027"], "d": ["Winter 2027"], "g": [], "l": ["Fall 2027"]}


def test_the_season_filter_lists_only_seasons_ahead_soonest_first(conn):
    from tracker.api import queries

    cid = db.upsert_company(conn, Company("Shopify", "greenhouse", "shopify"))
    titles = [
        "Software Engineering Intern (Fall 2026)",  # under way in October
        "Software Engineering Intern (Summer 2027)",
        "Software Engineering Intern (Summer 2027) Toronto",
        "Software Engineering Intern (Winter 2027)",
        "Data Engineering Intern (Spring 2016)",  # a stale list label
        "Software Engineering Intern (Fall 2027)",
    ]
    db.save_company_jobs(conn, cid, [job(str(i), title=t) for i, t in enumerate(titles)], day(0))
    conn.commit()
    seasons = queries.term_counts(conn, today=datetime(2026, 10, 18).date())
    assert seasons == [
        {"term": "Winter 2027", "jobs": 1},
        {"term": "Summer 2027", "jobs": 2},
        {"term": "Fall 2027", "jobs": 1},
    ]
