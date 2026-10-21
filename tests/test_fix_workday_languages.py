"""scripts/fix_workday_languages.py: Workday boards stored under a bare language."""

import importlib.util
import os
import sys
from pathlib import Path

import pytest

from tests.conftest import reset_database
from tracker import db
from tracker.models import Company

_spec = importlib.util.spec_from_file_location(
    "fix_workday_languages", Path(__file__).resolve().parents[1] / "scripts" / "fix_workday_languages.py"
)
fix = importlib.util.module_from_spec(_spec)
sys.modules["fix_workday_languages"] = fix  # dataclasses look their module up
_spec.loader.exec_module(fix)

DSN = os.environ.get("TEST_DATABASE_URL")
needs_db = pytest.mark.skipif(not DSN, reason="TEST_DATABASE_URL not set")

# real boards and links from the Common Crawl dry run (CC-MAIN-2026-39)
ROWS = [
    ("3m.wd1.myworkdayjobs.com/en", "candidate", "https://3m.wd1.myworkdayjobs.com/en/search"),
    ("3m.wd1.myworkdayjobs.com/es", "candidate", "https://3m.wd1.myworkdayjobs.com/es/search"),
    ("axalta.wd1.myworkdayjobs.com/es", "candidate", "https://axalta.wd1.myworkdayjobs.com/es/axalta"),
    ("amgen.wd1.myworkdayjobs.com/es", "dead", "https://amgen.wd1.myworkdayjobs.com/es/careers/job/india/x_r-221779"),
    ("howard.wd1.myworkdayjobs.com/hu", "candidate", "https://howard.wd1.myworkdayjobs.com/en-us/hu/job/program-manager_jr108293"),
    ("acme.wd1.myworkdayjobs.com/es", "candidate", None),
]  # fmt: skip


def test_decide():
    plan = fix.decide(ROWS, registered={"amgen.wd1.myworkdayjobs.com/careers"}, with_postings=set())
    assert plan.rewrite == {
        "3m.wd1.myworkdayjobs.com/en": "3m.wd1.myworkdayjobs.com/search",
        "axalta.wd1.myworkdayjobs.com/es": "axalta.wd1.myworkdayjobs.com/axalta",
    }
    # 3M's second link is the board just rewritten; Amgen's real board is already known
    assert plan.remove == ["3m.wd1.myworkdayjobs.com/es", "amgen.wd1.myworkdayjobs.com/es"]
    assert plan.keep == ["acme.wd1.myworkdayjobs.com/es", "howard.wd1.myworkdayjobs.com/hu"]


def test_boards_with_postings_are_left_alone():
    plan = fix.decide(ROWS[:1], registered=set(), with_postings={"3m.wd1.myworkdayjobs.com/en"})
    assert plan.has_postings == ["3m.wd1.myworkdayjobs.com/en"] and not plan.rewrite


@needs_db
def test_dry_run_reads_and_apply_repairs():
    with db.connect(DSN) as conn:
        reset_database(conn)
        db.apply_schema(conn)
        for slug, state, url in ROWS:
            conn.execute(
                "INSERT INTO discovered_boards (platform, board_slug, company_name, state, sample_url, failures)"
                " VALUES ('workday', %s, 'X', %s, %s, 3)",
                (slug, state, url),
            )
        conn.execute(
            "INSERT INTO discovered_boards (platform, board_slug, company_name)"
            " VALUES ('workday', 'amgen.wd1.myworkdayjobs.com/careers', 'Amgen')"
        )
        # a company with postings under a bad slug stays as it is
        company_id = db.upsert_company(conn, Company("Acme", "workday", "acme.wd1.myworkdayjobs.com/es"))
        conn.execute(
            "INSERT INTO jobs (company_id, external_id, title, url, level, role_type)"
            " VALUES (%s, '1', 'SWE', 'u', 'mid', 'sde')",
            (company_id,),
        )
        conn.commit()

        plan = fix.plan_for(conn)
        assert plan.has_postings == ["acme.wd1.myworkdayjobs.com/es"]
        assert len(plan.rewrite) == 2 and len(plan.remove) == 2
        fix.apply(conn, plan)
        conn.commit()

        boards = dict(
            conn.execute(
                "SELECT board_slug, state FROM discovered_boards WHERE platform = 'workday'"
            ).fetchall()
        )
        assert boards == {
            "3m.wd1.myworkdayjobs.com/search": "candidate",
            "axalta.wd1.myworkdayjobs.com/axalta": "candidate",
            "amgen.wd1.myworkdayjobs.com/careers": "active",
            "howard.wd1.myworkdayjobs.com/hu": "candidate",
            "acme.wd1.myworkdayjobs.com/es": "candidate",
        }
        name, failures = conn.execute(
            "SELECT company_name, failures FROM discovered_boards WHERE board_slug = 'axalta.wd1.myworkdayjobs.com/axalta'"
        ).fetchone()
        assert failures == 0 and name == "Axalta"
        # a second run finds nothing more to do
        again = fix.plan_for(conn)
        assert not again.rewrite and not again.remove
