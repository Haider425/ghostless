"""Correct or clear stored pay that can't be right.

Pay a job board states in its own fields used to be stored as given, so some
postings show $200,000 an hour, $21 a year, research grants of $5M, or rupee
and zloty amounts as dollars. New postings now go through
tracker.disclosures.checked_pay; this applies the same check to stored ones:

    correct   the period, a lost "k" or the currency is fixed ($200,000 an hour
              -> a year; 3,000,000 with no currency in India -> rupees)
    clear     the pay can't be trusted, so the posting shows "Pay not listed"

    python scripts/fix_pay.py            show what it would do (reads only)
    python scripts/fix_pay.py --apply    make the changes, in one transaction

Run from the repository root. It reads only the pay columns of postings with
pay (a few hundred kB), never descriptions.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field

import psycopg

from tracker.config import database_url
from tracker.disclosures import checked_pay


@dataclass
class Plan:
    # (id, min, max, period, currency)
    correct: list[tuple[int, float, float, str, str | None]] = field(default_factory=list)
    clear: list[int] = field(default_factory=list)
    examples: list[str] = field(default_factory=list)
    checked: int = 0


def decide(rows) -> Plan:
    """rows: (id, min, max, period, currency, first country)."""
    plan = Plan()
    for job_id, low, high, period, currency, country in rows:
        plan.checked += 1
        low, high = float(low), float(high)
        pay = checked_pay(low, high, period, currency, country)
        before = f"{low:,.0f}-{high:,.0f} {currency or '?'} a {period} ({country or '?'})"
        if pay is None:
            plan.clear.append(job_id)
            plan.examples.append(f"  clear   #{job_id}: {before}")
        elif pay != (low, high, period, currency):
            plan.correct.append((job_id, *pay))
            after = f"{pay[0]:,.0f}-{pay[1]:,.0f} {pay[3] or '?'} a {pay[2]}"
            plan.examples.append(f"  correct #{job_id}: {before} -> {after}")
    return plan


def plan_for(conn: psycopg.Connection) -> Plan:
    rows = conn.execute(
        "SELECT id, salary_min, salary_max, salary_period, salary_currency, countries[1]"
        " FROM jobs WHERE salary_min IS NOT NULL ORDER BY id"
    ).fetchall()
    return decide(rows)


def apply(conn: psycopg.Connection, plan: Plan) -> None:
    with conn.cursor() as cur:
        cur.executemany(
            "UPDATE jobs SET salary_min = %s, salary_max = %s, salary_period = %s, salary_currency = %s"
            " WHERE id = %s",
            [(low, high, period, code, job_id) for job_id, low, high, period, code in plan.correct],
        )
        if plan.clear:
            cur.execute(
                "UPDATE jobs SET salary_min = NULL, salary_max = NULL, salary_period = NULL,"
                " salary_currency = NULL WHERE id = ANY(%s)",
                (plan.clear,),
            )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--apply", action="store_true", help="make the changes (default: only show them)")
    args = parser.parse_args()
    with psycopg.connect(database_url(), connect_timeout=30) as conn:
        plan = plan_for(conn)
        print("\n".join(plan.examples))
        print(
            f"Checked {plan.checked} postings with pay: {len(plan.correct)} to correct, "
            f"{len(plan.clear)} to clear."
        )
        if not args.apply:
            print("Dry run: nothing changed. Run with --apply to make these changes.")
            return
        apply(conn, plan)
        conn.commit()
        print(f"OK: {len(plan.correct)} corrected, {len(plan.clear)} cleared.")


if __name__ == "__main__":
    main()
