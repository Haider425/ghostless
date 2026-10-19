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
        # Apple's wording
        (
            "The base pay range for this role is between $119,100 and $230,500, and your base pay will depend on",
            Salary(119100, 230500, "year", None),
        ),
        # a currency code before every symbol
        ("base pay range in the Toronto area is CAD $40 - CAD $45 per hour.", Salary(40, 45, "hour", "CAD")),
        (
            "base pay range is CAD $108,000 - CAD $135,000, not inclusive of equity",
            Salary(108000, 135000, "year", "CAD"),
        ),
        # the currency after the range
        ("base pay range for this position is $34-$36/hour CAD.", Salary(34, 36, "hour", "CAD")),
        ("The base salary range is 224,000 USD - 300,000 USD.", Salary(224000, 300000, "year", "USD")),
        # pounds and euros
        ("Salary: £96,900.00 - £145,300.00", Salary(96900, 145300, "year", "GBP")),
        ("The salary is between €50,000 - €69,000.", Salary(50000, 69000, "year", "EUR")),
        ("Salary range:\u202f £70,000 to £80,000 per annum", Salary(70000, 80000, "year", "GBP")),
        # a stray space before the thousands comma
        (
            "The salary range for this position is $202 ,400 - $231,000 .",
            Salary(202400, 231000, "year", None),
        ),
        # no symbol on the numbers: the heading says what they are
        ("Expected Base Pay Range (USD)\n\n34 - 68, $ per hour.", Salary(34, 68, "hour", "USD")),
        # one stated amount, right after a pay word
        ("Salary: £34k + discretionary 10% bonus", Salary(34000, 34000, "year", "GBP")),
        ("Pay Rate: 19.50 USD/per hour", Salary(19.5, 19.5, "hour", "USD")),
        ("Compensation: $85,000 per year plus benefits.", Salary(85000, 85000, "year", None)),
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
        "We have 3 - 5 open roles and great compensation.",  # bare numbers that aren't pay
        "Compensation includes 401k matching and 10 - 20 days of vacation.",
        "You'll get a $500 home office stipend for equipment.",  # an allowance below any salary
        "Revenue grew to 224,000 USD - 300,000 USD million.",
        "Pay rate: 4.5 USD / hour",  # implausibly low: a different market or a typo
    ],
)
def test_parse_salary_rejects_non_salaries(text):
    assert parse_salary(text) is None


@pytest.mark.parametrize(
    "text, expected",
    [
        (
            "The starting base pay is between USD 168,750 in the lowest geographic market and USD 270,000 in the highest.",
            Salary(168750, 270000, "year", "USD"),
        ),
        (
            "Our typical salary range starts at $130,000 and stretches up to $250,000.",
            Salary(130000, 250000, "year", None),
        ),
    ],
)
def test_parse_salary_reads_ranges_written_as_words(text, expected):
    assert parse_salary(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "Compensation: researchers looking for your profile tend to pay up to $18/hr per study completed.",
        "Pay: a $20,000 signing bonus for this role.",
        "Compensation includes a $25,000 relocation allowance.",
    ],
)
def test_a_ceiling_or_a_perk_is_not_a_salary(text):
    assert parse_salary(text) is None


@pytest.mark.parametrize(
    "text, expected",
    [
        ("€111.800 – €167.600 EUR", Salary(111800, 167600, "year", "EUR")),  # European thousands
        (
            "The salary range for this position is :€43.600,00 - €65.400,00",
            Salary(43600, 65400, "year", "EUR"),
        ),
        ("The anticipated base salary is $33/hour to $40/hour.", Salary(33, 40, "hour", None)),
        (
            "The base salary range is $185,000.00 USD – $230,000.00 USD.",
            Salary(185000, 230000, "year", "USD"),
        ),
    ],
)
def test_parse_salary_number_and_unit_formats(text, expected):
    assert parse_salary(text) == expected


def test_a_labelled_range_beats_a_range_in_words():
    text = (
        "The starting base pay is between USD 142,500 in the lowest geographic market and USD 228,000 in the "
        "highest geographic market.\n\nBase Pay Range\n\n$171,000 – $273,600 USD"
    )
    assert parse_salary(text) == Salary(171000, 273600, "year", "USD")


def test_a_range_later_in_the_text_beats_a_single_amount_before_it():
    text = "Pay: $40,000 is our floor in some markets. The salary range for this role is $90,000 - $110,000."
    assert parse_salary(text) == Salary(90000, 110000, "year", None)


def test_a_single_amount_never_swallows_a_range():
    salary = parse_salary("Salary: $90,000 - $110,000 per year")
    assert (salary.minimum, salary.maximum) == (90000, 110000)


def test_salary_evidence_is_the_whole_sentence():
    salary = parse_salary(
        "About us. At Apple, base pay is one part of our package. The base pay range for this role is between $119,100 and $230,500, and depends on location. More."
    )
    assert salary is not None
    assert salary.text.startswith("The base pay range for this role is between $119,100 and $230,500")


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
