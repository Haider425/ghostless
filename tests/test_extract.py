"""Fields read from postings (crawler plan, stage C): places, workplace, job
type, sponsorship, years, seniority, structured source fields, and the
accuracy floor on the labelled test set."""

import os
from datetime import datetime, timezone

import pytest

from tracker import evaluate
from tracker.classify import classify_level, enrich
from tracker.disclosures import parse_salary
from tracker.extract import (
    classify_seniority,
    countries_of,
    level_of,
    parse_employment_type,
    parse_locations,
    parse_min_years,
    parse_sponsorship,
    parse_workplace,
)
from tracker.models import Job
from tracker.sources.boards import parse_ashby, parse_greenhouse, parse_lever
from tracker.sources.workday import parse_workday_job


@pytest.mark.parametrize(
    "location, countries",
    [
        ("Toronto, ON, CAN", ["CA"]),
        ("TORONTO, Ontario, Canada | MONTRÉAL, Quebec, Canada", ["CA"]),
        ("San Francisco, CA", ["US"]),
        ("Toronto, ON, CA", ["CA"]),
        ("Chicago, IL | McLean, VA | Richmond, VA", ["US"]),
        ("GBR-London-5 Canada Square", ["GB"]),  # London's Canada Square is not Canada
        ("United States of America, New York, New York | Canada, Toronto, Ontario", ["US", "CA"]),
        ("Remote (United States | Canada)", ["US", "CA"]),
        ("Remote - Poland", ["PL"]),
        ("Villahermosa, TAB, MX, 86035", ["MX"]),
        ("CA, N5A6S9", ["CA"]),
        ("Bangalore, Karnataka | Chennai, Tamil Nadu", ["IN"]),
        ("Los Angeles, Palo Alto, San Francisco, Toronto", ["US", "CA"]),
        ("Home based - Worldwide", []),
    ],
)
def test_places(location, countries):
    assert countries_of(parse_locations(location)) == countries


def test_a_place_from_the_text_when_the_location_line_has_none():
    places = parse_locations("Main Campus", "University of Ottawa, 120 University, Ottawa, ON, K1N 6N5")
    assert countries_of(places) == ["CA"] and places[0]["city"] == "Ottawa"


@pytest.mark.parametrize(
    "title, location, text, workplace",
    [
        ("Engineer", "Toronto", "Great team. #LI-Hybrid", "hybrid"),
        ("Engineer", "Toronto", "We're in the office 5 days a week. This is not a hybrid role.", "onsite"),
        ("Engineer", "Toronto", "You'll spend three days a week in the office (Tuesday-Thursday).", "hybrid"),
        ("Engineer", "Remote - US", "", "remote"),
        ("Engineer", "Toronto", "Experience with hybrid cloud and hybrid search.", None),
        ("Engineer", "Toronto", "Cohere is remote-friendly, with offices in Toronto.", None),
        ("Platform Engineer (Hybrid)", "San Antonio", "", "hybrid"),
        ("Engineer", "Roanoke", "Must be able to work on-site in Roanoke.", "onsite"),
    ],
)
def test_workplace(title, location, text, workplace):
    assert parse_workplace(title, location, text) == workplace


@pytest.mark.parametrize(
    "title, text, seniority, kind",
    [
        ("Software Engineer Intern", "Full-time, paid internship", "intern", "internship"),
        ("Contract Student Worker", "We want to be transparent: this is not an internship. This is a contract position.", "intern", "contract"),
        ("Generative AI Associate", "It's a part-time, remote, flexible opportunity.", "mid", "part_time"),
        ("Engineer", "Employment Type: Full-Time", "mid", "full_time"),
        ("Engineer", "Salaries for part-time roles will be prorated. Full-time employees get benefits.", "mid", None),
        ("Sr. Engineer (Poland, Remote, B2B)", "", "senior", "contract"),
    ],
)  # fmt: skip
def test_employment_type(title, text, seniority, kind):
    assert parse_employment_type(title, text, seniority) == kind


@pytest.mark.parametrize(
    "text, answer",
    [
        ("Please note: immigration sponsorship is not available for this role.", "not_available"),
        ("Applicants must be authorized to work without the need for current or future sponsorship.", "not_available"),
        ("Active TS/SCI clearance required.", "not_available"),
        ("This position requires access to information subject to the International Traffic in Arms Regulations.", "not_available"),
        ("Certain positions require access to the International Traffic in Arms Regulations.", "unknown"),
        ("Capital One will consider sponsoring a new qualified applicant.", "available"),
        ("Visa sponsorship: Yes, we sponsor visas.", "available"),
        ("You need to be legally eligible to work at the location(s) specified above.", "unknown"),
    ],
)  # fmt: skip
def test_sponsorship(text, answer):
    assert parse_sponsorship(text) == answer


@pytest.mark.parametrize(
    "text, years",
    [
        ("At least 6 years of experience in software engineering. 1+ year of experience leading reviews.", 6),
        ("BS + 5 years, or MS + 4 years, in Electrical Engineering (or equivalent experience)", 4),
        ("Minimum of three (3) years of relevant experience", 3),
        ("0–1 years as a software engineer", 0),
        ("7–10+ years of experience in data engineering, 5+ years of hands-on Informatica", 7),
        ("NVIDIA has been redefining computing for more than 25 years. Must be 18 years of age.", None),
        ("New grad candidates should have no more than 18 months of professional experience", None),
    ],
)
def test_years_of_experience(text, years):
    assert parse_min_years(text) == years


@pytest.mark.parametrize(
    "title, years, seniority, level",
    [
        (
            "Software Development Engineer II, S3 Routing and Blob Placement",
            None,
            "mid",
            "mid",
        ),  # not an intern
        ("Quality Engineer I", 5, "junior", "new_grad"),
        ("Full Stack Engineer 5", None, "senior", "senior"),
        ("Staff Software Engineer", None, "staff", "senior"),
        ("Senior/Staff Software Engineer (Platform)", None, "senior", "senior"),
        ("AI Engineer", 2, "junior", "mid"),  # few years asked for never makes a role a student one
        ("Software Engineer", 8, "senior", "senior"),
        ("Stagiaire en recherche", None, "intern", "intern"),
    ],
)
def test_seniority_and_level(title, years, seniority, level):
    found, from_title = classify_seniority(title, years)
    assert found == seniority and level_of(found, from_title) == level


def test_level_from_a_title_is_unchanged_for_the_site():
    assert classify_level("Software Engineer Intern") == "intern"
    assert classify_level("Senior Software Engineer") == "senior"
    assert classify_level("Software Engineer, New Grad") == "new_grad"
    assert classify_level("Junior Developer") == "new_grad"
    assert classify_level("Software Engineer") == "mid"


# ---------- pay ----------


def test_pay_per_country_and_per_month():
    text = "US: $147000 - $210000 (USD) + 15% bonus. Canada: $150000 - $153000 (CAD) + 15% bonus."
    assert parse_salary(text, "CA").minimum == 150000
    assert parse_salary(text, "US").minimum == 147000
    monthly = parse_salary("Salary Range: $7,000 CAD per month")
    assert (monthly.minimum, monthly.period, monthly.currency) == (7000, "month", "CAD")
    stated = parse_salary("Toronto, ON, CAN - 50,405.00 CAD Annually")
    assert (stated.minimum, stated.period, stated.currency) == (50405, "year", "CAD")
    assert parse_salary("Compensation: researchers tend to pay up to $18/hr per study completed.") is None


def test_unlabelled_dollars_follow_the_posting_country():
    us = enrich(
        Job("1", "Engineer", "u", location="Seattle, WA", description="Base pay: $150,000 - $180,000"), []
    )
    ca = enrich(
        Job("2", "Engineer", "u", location="Toronto, ON", description="Base pay: $150,000 - $180,000"), []
    )
    assert (us.salary_currency, ca.salary_currency) == ("USD", "CAD")


# ---------- structured source fields (C1) ----------


def test_ashby_structured_fields():
    [job] = parse_ashby(
        {
            "jobs": [
                {
                    "id": "1",
                    "title": "Software Engineer",
                    "jobUrl": "u",
                    "location": "New York",
                    "workplaceType": "Hybrid",
                    "employmentType": "FullTime",
                    "compensation": {
                        "summaryComponents": [
                            {"compensationType": "EquityPercentage", "interval": "NONE"},
                            {"compensationType": "Salary", "interval": "1 YEAR", "currencyCode": "USD",
                             "minValue": 211400, "maxValue": 290600},
                        ]
                    },
                }
            ]
        }
    )  # fmt: skip
    job = enrich(job, [])
    assert (job.workplace, job.employment_type) == ("hybrid", "full_time")
    assert (job.salary_min, job.salary_max, job.salary_currency, job.salary_period) == (
        211400,
        290600,
        "USD",
        "year",
    )


def test_greenhouse_pay_ranges_pick_the_postings_country():
    item = {
        "id": 1,
        "title": "Engineer",
        "absolute_url": "u",
        "location": {"name": "Toronto, ON"},
        "content": "",
        "pay_input_ranges": [
            {"min_cents": 13920000, "max_cents": 23520000, "currency_type": "USD", "title": "United States"},
            {"min_cents": 12000000, "max_cents": 15000000, "currency_type": "CAD", "title": "Canada"},
        ],
    }
    [job] = parse_greenhouse({"jobs": [item]})
    assert (job.salary_min, job.salary_max, job.salary_currency) == (120000, 150000, "CAD")


def test_lever_and_workday_structured_fields():
    [lever] = parse_lever(
        [
            {
                "id": "1",
                "text": "Engineer",
                "hostedUrl": "u",
                "categories": {"location": "Toronto", "commitment": "Full-time"},
                "workplaceType": "on-site",
                "salaryRange": {
                    "min": 100000,
                    "max": 120000,
                    "currency": "CAD",
                    "interval": "per-year-salary",
                },
            }
        ]
    )
    assert (lever.workplace, lever.employment_type, lever.salary_min, lever.salary_period) == (
        "onsite",
        "full_time",
        100000,
        "year",
    )
    workday = parse_workday_job(
        {"externalPath": "/job/a", "title": "Engineer"},
        {"jobPostingInfo": {"remoteType": "Hybrid", "timeType": "Part time"}},
        "https://x",
        "Site",
    )
    assert (workday.workplace, workday.employment_type) == ("hybrid", "part_time")


def test_json_ld_structured_fields():
    import json

    from tracker.sources.jsonld import parse_job_page

    page = '<script type="application/ld+json">' + json.dumps(
        {
            "@type": "JobPosting",
            "title": "Data Engineer",
            "employmentType": ["CONTRACTOR"],
            "experienceRequirements": {"@type": "OccupationalExperienceRequirements", "monthsOfExperience": 36},
        }
    ) + "</script>"  # fmt: skip
    [job], _ = parse_job_page(page, "https://x.example/jobs/1")
    job = enrich(job, [])
    assert (job.employment_type, job.min_years_experience, job.seniority) == ("contract", 3.0, "mid")


# ---------- accuracy on the labelled postings (CI) ----------

# Measured on 21 October 2026 (see docs/crawler-plan.md, stage C results). A
# change that makes the extractors worse on the committed excerpts fails here.
FLOORS = {
    "level": 0.97,
    "seniority": 0.95,
    "role_type": 0.92,
    "employment_type": 0.93,
    "workplace": 0.95,
    "countries": 0.95,
    "sponsorship": 0.96,
    "min_years_experience": 0.91,
    "pay": 0.93,
}


def test_accuracy_does_not_drop():
    scores = evaluate.evaluate(evaluate.load())
    below = {
        name: round(scores[name].accuracy, 3)
        for name, floor in FLOORS.items()
        if scores[name].accuracy < floor
    }
    assert not below, f"accuracy fell below its floor: {below}"


def test_labelled_sets_are_well_formed():
    for name in ("labels.jsonl", "holdout.jsonl"):
        records = evaluate.load(evaluate.LABELLED / name)
        assert records and len({r["id"] for r in records}) == len(records)
        for record in records:
            assert set(record["expected"]) >= {"seniority", "level", "role_type", "countries", "salary_min"}
            assert record["reviewed"] in (True, False)
            assert record["excerpt"] is not None
    assert not {r["id"] for r in evaluate.load()} & {
        r["id"] for r in evaluate.load(evaluate.LABELLED / "holdout.jsonl")
    }


# ---------- stored (CI database) ----------

DSN = os.environ.get("TEST_DATABASE_URL")


@pytest.mark.skipif(not DSN, reason="TEST_DATABASE_URL not set")
def test_new_fields_are_stored_and_reprocess_fills_them():
    from tests.conftest import reset_database
    from tracker import db, reprocess
    from tracker.models import Company

    with db.connect(DSN) as conn:
        reset_database(conn)
        db.apply_schema(conn)
        company_id = db.upsert_company(conn, Company("Acme", "lever", "acme"))
        text = "Hybrid: 3 days a week in the office. 5+ years of experience. We are unable to sponsor visas."
        job = enrich(Job("1", "Software Engineer", "u", location="Toronto, ON", description=text), [])
        db.save_company_jobs(conn, company_id, [job], datetime(2026, 10, 1, tzinfo=timezone.utc))
        conn.execute("UPDATE jobs SET seniority = NULL, workplace = NULL, countries = '{}'")  # as before C
        conn.commit()
        reprocess.run(DSN)
        row = conn.execute(
            "SELECT seniority, level, workplace, sponsorship, min_years_experience, countries, locations FROM jobs"
        ).fetchone()
    assert row[:6] == ("senior", "senior", "hybrid", "not_available", 5, ["CA"])
    assert row[6][0]["city"] == "Toronto"


@pytest.mark.skipif(not DSN, reason="TEST_DATABASE_URL not set")
def test_reprocess_keeps_a_job_lists_level_for_a_plain_title():
    from tests.conftest import reset_database
    from tracker import db, reprocess
    from tracker.models import Company

    with db.connect(DSN) as conn:
        reset_database(conn)
        db.apply_schema(conn)
        company_id = db.upsert_company(conn, Company("Listed", "list", "list:listed", origin="list"))
        job = Job("1", "Software Engineer", "u", location="Toronto, ON", listed_in="New grad list")
        job.level, job.role_type = "new_grad", "sde"  # from the list, as classify_listed sets them
        db.save_company_jobs(conn, company_id, [job], datetime(2026, 10, 1, tzinfo=timezone.utc), guard=False)
        conn.commit()
        reprocess.run(DSN)
        assert conn.execute("SELECT level, role_type FROM jobs").fetchone() == ("new_grad", "sde")
