"""Every rule scripts/fix_pay.py applied to stored pay also applies to new postings.

Each case is a real posting from the database (its id in the comment), with
the amounts, currency, place and job board it had. It goes through two paths
that must agree:

- new posting: the job board's own parser (Greenhouse pay_input_ranges, Ashby
  compensation, Lever salaryRange) or the description text, then
  classify.enrich, as an ingest run does
- stored posting: scripts/fix_pay.py's decide() on the row as it was stored

The board responses themselves aren't stored, so the payloads are rebuilt in
each board's shape around the real values.
"""

import importlib.util
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

from tracker.classify import enrich
from tracker.sources.boards import _greenhouse_job, parse_ashby, parse_lever

_spec = importlib.util.spec_from_file_location(
    "fix_pay", Path(__file__).resolve().parents[1] / "scripts" / "fix_pay.py"
)
fix = importlib.util.module_from_spec(_spec)
sys.modules["fix_pay"] = fix
_spec.loader.exec_module(fix)

ASHBY_INTERVAL = {"year": "1 YEAR", "month": "1 MONTH", "hour": "1 HOUR"}
LEVER_INTERVAL = {"year": "per-year-salary", "month": "per-month-salary", "hour": "per-hour-wage"}


@dataclass
class Case:
    rule: str
    job_id: int  # the posting in the database
    board: str  # greenhouse | ashby | lever | text
    location: str
    low: float
    high: float
    period: str  # as the board stated it (Greenhouse: from its range title, see _greenhouse_pay)
    currency: str | None  # as the board stated it
    country: str | None  # as stored, from the location
    shown: tuple | None  # (min, max, period, currency) after the check, or None: no pay shown
    text: str = ""  # for board == "text": the sentence in the description


CASES = [
    Case("a range titled hourly is yearly", 120325, "greenhouse", "San Mateo, CA",
         200000, 315000, "hour", "USD", "US", (200000, 315000, "year", "USD")),
    Case("an hourly rate stated as yearly is hourly", 142961, "lever", "Birmingham, AL",
         21, 21, "year", "USD", "US", (21, 21, "hour", "USD")),
    Case("an intern's monthly pay stated as annual is monthly", 229422, "greenhouse", "Santa Clara, CA",
         8500, 10000, "year", "USD", "US", (8500, 10000, "month", "USD")),
    Case("an intern's $10,000 stated as yearly is monthly", 121763, "greenhouse", "Mountain View, CA",
         10000, 10000, "year", "USD", "US", (10000, 10000, "month", "USD")),
    Case("a monthly stipend from Lever stated as yearly is monthly", 235107, "lever", "Arlington, VA",
         5500, 7500, "year", "USD", "US", (5500, 7500, "month", "USD")),
    Case("a weekly stipend is not guessed to be monthly", 160845, "greenhouse", "Hawthorne, CA",
         1925, 1925, "year", "USD", "US", None),
    Case("a low end that lost its k", 75272, "ashby", "New York, NY",
         200, 400000, "year", "USD", "US", (200000, 400000, "year", "USD")),
    Case("a dropped digit", 33374, "greenhouse", "Costa Mesa, California, United States",
         22000, 292000, "year", "USD", "US", None),
    Case("a mistyped high end", 19470, "greenhouse", "New York, NY",
         152405, 179300152, "year", "USD", "US", None),
    Case("a research grant over a million a year", 161149, "ashby", "San Francisco, CA",
         5000000, 5000000, "year", "USD", "US", None),
    Case(
        "gig pay just above the US minimum wage, stated in US dollars abroad",
        243637,
        "greenhouse",
        "Greece",
        9.5,
        9.5,
        "hour",
        "USD",
        "GR",
        (9.5, 9.5, "hour", "USD"),
    ),
    Case("a $1 placeholder", 194021, "ashby", "Austin, TX",
         1, 1, "hour", "USD", "US", None),
    Case("rupees named by the board", 182884, "ashby", "Bengaluru, India",
         5000000, 8000000, "year", "INR", "IN", (5000000, 8000000, "year", "INR")),
    Case("no currency named: the country's, rupees", 182949, "ashby", "Bengaluru, India",
         1500000, 3000000, "year", None, "IN", (1500000, 3000000, "year", "INR")),
    Case("no currency named: Singapore dollars", 153772, "ashby", "Singapore",
         200000, 400000, "year", None, "SG", (200000, 400000, "year", "SGD")),
    Case("zloty stated as yearly that only fit a month", 22039, "ashby", "Warsaw, Poland",
         16000, 24000, "year", None, "PL", (16000, 24000, "month", "PLN")),
    Case("a junior's zloty a month (no weekly guard outside dollars)", 177751, "ashby", "Warsaw, Poland",
         8500, 17042, "year", None, "PL", (8500, 17042, "month", "PLN")),
    Case("65 rupees an hour is under a dollar", 185253, "ashby", "Bengaluru, India",
         65, 65, "hour", None, "IN", None),
    Case("a currency Ghostless doesn't know", 0, "ashby", "Austin, TX",
         100000, 150000, "year", "XYZ", "US", None),
    Case("no currency and no country: unknown, not dollars", 0, "text", "Remote",
         61000, 65000, "year", None, None, (61000, 65000, "year", None),
         text="Salary: 61,000 - 65,000 per year."),
    Case("rupees in the text, in lakhs", 0, "text", "Bengaluru, India",
         3000000, 5000000, "year", "INR", "IN", (3000000, 5000000, "year", "INR"),
         text="Pay: ₹30,00,000 - ₹50,00,000 per annum"),
]  # fmt: skip


def new_posting(case: Case):
    """The posting as an ingest run reads and enriches it."""
    title = "Software Engineer"
    if case.board == "greenhouse":
        range_title = "Base pay (per hour)" if case.period == "hour" else "Base pay"
        job = _greenhouse_job(
            {
                "id": case.job_id,
                "title": title,
                "absolute_url": "",
                "location": {"name": case.location},
                "content": "",
                "pay_input_ranges": [
                    {
                        "min_cents": int(case.low * 100),
                        "max_cents": int(case.high * 100),
                        "currency_type": case.currency,
                        "title": range_title,
                    }
                ],
            }
        )
    elif case.board == "ashby":
        compensation = {
            "summaryComponents": [
                {
                    "compensationType": "Salary",
                    "minValue": case.low,
                    "maxValue": case.high,
                    "currencyCode": case.currency,
                    "interval": ASHBY_INTERVAL[case.period],
                }
            ]
        }
        (job,) = parse_ashby(
            {
                "jobs": [
                    {
                        "id": case.job_id,
                        "title": title,
                        "location": case.location,
                        "compensation": compensation,
                    }
                ]
            }
        )
    elif case.board == "lever":
        (job,) = parse_lever(
            [
                {
                    "id": case.job_id,
                    "text": title,
                    "categories": {"location": case.location},
                    "salaryRange": {
                        "min": case.low,
                        "max": case.high,
                        "currency": case.currency,
                        "interval": LEVER_INTERVAL[case.period],
                    },
                }
            ]
        )
    else:
        from tracker.models import Job

        job = Job(external_id="1", title=title, url="", location=case.location, description=case.text)
    return enrich(job, [])


@pytest.mark.parametrize("case", CASES, ids=[c.rule for c in CASES])
def test_new_postings_get_the_same_pay_as_fix_pay_gives_stored_ones(case):
    job = new_posting(case)
    got = (job.salary_min, job.salary_max, job.salary_period, job.salary_currency)
    want = case.shown or (None, None, None, None)
    assert got == want

    if case.board == "text":
        return  # text pay was always parsed and checked; fix_pay only saw it once stored
    plan = fix.decide([(case.job_id, case.low, case.high, case.period, case.currency, case.country)])
    if case.shown is None:
        assert plan.clear == [case.job_id]
    elif case.shown == (case.low, case.high, case.period, case.currency):
        assert plan.correct == [] and plan.clear == []
    else:
        assert plan.correct == [(case.job_id, *case.shown)]
