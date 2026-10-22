"""Pay in the API: monthly pay is a valid period, and sorting by pay compares
yearly amounts, so hourly, monthly and yearly ranges rank together.

Skipped unless TEST_DATABASE_URL is set."""

import os
from datetime import datetime, timedelta, timezone

import pytest

from tests.conftest import reset_database
from tracker import db
from tracker.classify import enrich
from tracker.models import Company, Job
from tracker.skills import extract_skills

DSN = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DSN, reason="TEST_DATABASE_URL not set")


def job(ext_id, pay, location="Toronto, ON"):
    title = "Software Engineer"
    j = Job(
        external_id=ext_id,
        title=title,
        url=f"https://acme.example/{ext_id}",
        location=location,
        description=f"Python. {pay}",
    )
    return enrich(j, extract_skills(title))


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient

    from tracker.api import create_app

    with db.connect(DSN) as conn:
        reset_database(conn)
        db.apply_schema(conn)
        acme = db.upsert_company(conn, Company("Acme", "greenhouse", "acme"))
        when = datetime.now(timezone.utc) - timedelta(days=1)
        run = db.start_run(conn, when)
        db.save_company_jobs(
            conn,
            acme,
            [
                job("hourly", "Pay: $40 - $45 per hour."),  # about $94k a year
                job("monthly", "Salary: $8,000 - $9,000 per month."),  # $108k a year
                job("yearly", "Salary $90,000 - $100,000 per year."),
                # about US$60k a year: rupees sort by what they're worth, not their number
                job("rupees", "Salary: INR 3,000,000 - 5,000,000 per year.", "Bengaluru, India"),
                job("unpaid", "No pay listed."),
                # no currency named and no country to tell: the currency is unknown
                job("unknown", "Salary: 61,000 - 65,000 per year.", "Remote"),
            ],
            when,
        )
        db.finish_run(
            conn,
            run,
            dict(
                companies_ok=1,
                companies_failed=0,
                jobs_seen=6,
                jobs_new=6,
                jobs_closed=0,
                duration_seconds=1.0,
            ),
        )
        conn.commit()
        db.refresh_signals(conn)
    with TestClient(create_app(DSN)) as test_client:
        yield test_client


def test_monthly_pay_is_returned_and_pay_sorts_by_the_yearly_amount(client):
    response = client.get("/jobs", params={"sort": "salary"})
    assert response.status_code == 200, response.text
    items = response.json()["items"]
    assert [item["url"].rsplit("/", 1)[-1] for item in items] == [
        "monthly",
        "yearly",
        "hourly",
        "unknown",  # no currency: sorted as if dollars, shown without one
        "rupees",
        "unpaid",
    ]
    monthly = items[0]["salary"]
    assert monthly["period"] == "month" and (monthly["min"], monthly["max"]) == (8000.0, 9000.0)
    unknown = items[3]["salary"]
    assert unknown["currency"] is None and (unknown["min"], unknown["max"]) == (61000.0, 65000.0)
    rupees = items[4]["salary"]
    assert (rupees["currency"], rupees["period"], rupees["max"]) == ("INR", "year", 5000000.0)
