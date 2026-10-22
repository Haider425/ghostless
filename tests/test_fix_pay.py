"""scripts/fix_pay.py: stored pay that can't be right is corrected or cleared."""

import importlib.util
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

from tests.conftest import reset_database
from tracker import db
from tracker.models import Company, Job

_spec = importlib.util.spec_from_file_location(
    "fix_pay", Path(__file__).resolve().parents[1] / "scripts" / "fix_pay.py"
)
fix = importlib.util.module_from_spec(_spec)
sys.modules["fix_pay"] = fix  # dataclasses look their module up
_spec.loader.exec_module(fix)

DSN = os.environ.get("TEST_DATABASE_URL")

# real rows from a copy of the database
ROWS = [
    (9898, 200000, 315000, "hour", "USD", "US"),  # Verkada: a range titled hourly
    (10275, 21, 21, "year", "USD", "US"),  # Protective Life: $21 an hour
    (15822, 200, 400000, "year", "USD", "US"),  # Normal Computing: "$200 - $400,000"
    (11628, 5000000, 5000000, "year", "USD", "US"),  # Mercor: a research grant
    (13384, 3000000, 5000000, "year", None, "IN"),  # AiPrise: rupees with no currency named
    (2, 65, 65, "hour", None, "IN"),  # 65 rupees an hour can't be right
    (1, 90000, 110000, "year", "CAD", "CA"),  # fine: left alone
]


def test_decide():
    plan = fix.decide(ROWS)
    assert plan.checked == 7
    assert plan.correct == [
        (9898, 200000, 315000, "year", "USD"),
        (10275, 21, 21, "hour", "USD"),
        (15822, 200000, 400000, "year", "USD"),
        (13384, 3000000, 5000000, "year", "INR"),
    ]
    assert plan.clear == [11628, 2]


def test_apply_changes_only_what_it_plans_and_a_second_run_finds_nothing():
    if not DSN:
        pytest.skip("TEST_DATABASE_URL not set")
    with db.connect(DSN) as conn:
        reset_database(conn)
        db.apply_schema(conn)
        acme = db.upsert_company(conn, Company("Acme", "greenhouse", "acme"))
        jobs = []
        for ext, (low, high, period) in {"grant": (5e6, 5e6, "year"), "hourly": (2e5, 3e5, "hour"),
                                         "fine": (9e4, 1.1e5, "year")}.items():  # fmt: skip
            job = Job(external_id=ext, title="Software Engineer", url=f"https://acme.example/{ext}",
                      location="Austin, TX", countries=["US"])  # fmt: skip
            job.salary_min, job.salary_max, job.salary_period, job.salary_currency = low, high, period, "USD"
            jobs.append(job)
        db.save_company_jobs(conn, acme, jobs, datetime.now(timezone.utc))
        conn.commit()

        fix.apply(conn, fix.plan_for(conn))
        conn.commit()
        stored = dict(
            (ext, (lo and float(lo), hi and float(hi), per))
            for ext, lo, hi, per in conn.execute(
                "SELECT external_id, salary_min, salary_max, salary_period FROM jobs"
            ).fetchall()
        )
        assert stored == {
            "grant": (None, None, None),
            "hourly": (200000.0, 300000.0, "year"),
            "fine": (90000.0, 110000.0, "year"),
        }
        again = fix.plan_for(conn)
        assert again.correct == [] and again.clear == []
