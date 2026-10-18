import pytest

from tracker.classify import enrich
from tracker.disclosures import (
    Salary,
    fingerprint,
    has_description_hash,
    parse_ai_screening,
    parse_salary,
    parse_vacancy,
    vacancy_evidence,
)
from tracker.models import Job


@pytest.mark.parametrize(
    "text, expected",
    [
        ("The base salary range is $95,000 – $120,000.", Salary(95000, 120000, "year", None)),
        ("Pay: $95K-$120K CAD per year", Salary(95000, 120000, "year", "CAD")),
        ("Salary range: CAD 80,000 to 100,000", Salary(80000, 100000, "year", "CAD")),
        ("US$140,000 - US$180,000 annually", Salary(140000, 180000, "year", "USD")),
        ("Hourly rate: $25.50 - $32 per hour", Salary(25.5, 32, "hour", None)),
        ("$28 to $34/hr for this co-op term", Salary(28, 34, "hour", None)),
        ("Expected compensation $72 000 – $90 000 (CAD)", Salary(72000, 90000, "year", "CAD")),
    ],
)
def test_parse_salary(text, expected):
    assert parse_salary(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "We manage $5 to $10 billion in assets.",
        "Join 200 - 300 engineers.",  # no currency
        "Ranges from $1 - $2 for snacks.",  # implausible
        "Salary from $50,000 to $400,000.",  # wider than 3x: not a real range
        "",
    ],
)
def test_parse_salary_rejects_non_salaries(text):
    assert parse_salary(text) is None


def test_parse_salary_skips_false_match_and_finds_real_one():
    text = "We raised $5 to $10 billion. The salary range is $90,000 - $110,000."
    assert parse_salary(text) == Salary(90000, 110000, "year", None)


@pytest.mark.parametrize(
    "text, expected",
    [
        ("This posting is for an existing vacancy.", "existing"),
        ("Existing vacancy: Yes", "existing"),
        ("This role fills an existing position on our team.", "existing"),
        ("This posting is not for an existing vacancy.", "not_existing"),
        ("This is not an existing vacancy; we are building a talent pool.", "not_existing"),
        ("We are collecting applications for future opportunities.", "not_existing"),
        ("Existing vacancy: No", "not_existing"),
        ("This job posting is intended to build a talent pool for future openings.", "not_existing"),
        ("This posting is for an anticipated vacancy.", "not_existing"),
        ("This is an evergreen requisition.", "not_existing"),
        ("Join our team of engineers.", None),
        # job duties and boilerplate that mention the future are not disclosures
        (
            "Develop and execute sourcing strategies that build broad, qualified candidate "
            "pipelines for current and future hiring needs.",
            None,
        ),
        ("We may keep your information to consider you for future opportunities.", None),
        ("Join our talent community to hear about new roles.", None),
        ("Own a data pipeline role in our analytics platform.", None),
        ("Advise hiring teams on talent-market conditions.", None),
        ("", None),
    ],
)
def test_parse_vacancy(text, expected):
    assert parse_vacancy(text) == expected


def test_vacancy_evidence_quotes_the_sentence():
    text = "Great team.\nThis posting is not for an existing vacancy. Apply today."
    assert vacancy_evidence(text) == ("not_existing", "This posting is not for an existing vacancy.")


def test_salary_keeps_its_sentence():
    salary = parse_salary("Benefits are great. The base range is $90,000 to $110,000 per year. Apply now.")
    assert salary is not None
    assert salary.text == "The base range is $90,000 to $110,000 per year."


@pytest.mark.parametrize(
    "text, expected",
    [
        ("We use artificial intelligence to screen applications.", True),
        ("AI-powered tools may be used to assess candidates during recruitment.", True),
        ("We do not use AI to screen or select applicants.", False),
        ("Artificial intelligence is not used in our hiring or screening process.", False),
        ("You will build AI products that review customer data.", None),  # product, not hiring
        ("Great benefits and a hybrid schedule.", None),
    ],
)
def test_parse_ai_screening(text, expected):
    assert parse_ai_screening(text) is expected


def test_fingerprint_ignores_ids_and_punctuation():
    a = fingerprint("Software Engineer, Payments (R12345)", "Toronto, ON | Remote")
    b = fingerprint("Software Engineer - Payments", "Remote | Toronto ON")
    assert a == b == "software engineer payments|remote,toronto on"


def test_fingerprint_keeps_seasons_distinct():
    assert fingerprint("SWE Intern (Summer 2027)") != fingerprint("SWE Intern (Fall 2027)")


def test_fingerprint_matches_a_plain_repost():
    original = fingerprint(
        "Data Engineer", "Toronto", "Posted Oct 1, 2026. Req #48213. Build Spark pipelines."
    )
    repost = fingerprint(
        "Data Engineer", "Toronto", "Posted Nov 14, 2026. Req #51177. Build Spark pipelines."
    )
    assert original == repost


def test_fingerprint_separates_same_title_different_role():
    ads = fingerprint("Software Development Engineer", "Toronto", "Join the Ads team building bidding.")
    alexa = fingerprint("Software Development Engineer", "Toronto", "Join Alexa building speech models.")
    assert ads != alexa


def test_enrich_fills_disclosures_and_infers_cad():
    job = Job(
        external_id="1",
        title="Data Engineer",
        url="u",
        location="Toronto, ON",
        description="Salary: $90,000 - $110,000 per year. This posting is for an existing vacancy. "
        "We do not use AI to screen applicants.",
    )
    enrich(job, [])
    assert (job.salary_min, job.salary_max, job.salary_period, job.salary_currency) == (
        90000,
        110000,
        "year",
        "CAD",
    )
    assert job.vacancy == "existing"
    assert job.ai_screening is False
    assert job.fingerprint.startswith("data engineer|toronto on|")


def test_fingerprint_separates_the_same_role_in_other_cities():
    text = "Build banking software for our customers."
    toronto = fingerprint("Software Engineer II", "Toronto, ON | Montreal, QC", text)
    vancouver = fingerprint("Software Engineer II", "Toronto, ON | Vancouver, BC", text)
    assert toronto != vancouver


def test_only_description_fingerprints_can_be_duplicates():
    assert has_description_hash(fingerprint("Analyst", "Toronto", "Some description"))
    assert not has_description_hash(fingerprint("Analyst", "Toronto"))
