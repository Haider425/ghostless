"""Repair discovered Workday boards stored under a bare language instead of the site.

Links like https://3m.wd1.myworkdayjobs.com/en/Search were read as the board
"3m.wd1.myworkdayjobs.com/en" until the link parser learned that a bare
two-letter language can come before the site. For each stored board whose site
is two letters, the board is worked out again from its sample link:

    rewrite   the link names the real board, which isn't registered yet
    remove    the real board is already registered (a discovered board or a company)
    keep      no sample link, or the link shows the two letters are the site
              itself (howard.wd1.myworkdayjobs.com/en-us/hu/job/1)

Boards with stored postings are never touched; they're listed instead.
Rewritten boards become candidates again, so they're checked before they're read.

    python scripts/fix_workday_languages.py            show what it would do (reads only)
    python scripts/fix_workday_languages.py --apply    make the changes, in one transaction

Run from the repository root. It reads only the boards it's about (a few kB).
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass, field

import psycopg

from tracker.discovery.boards import board_from_url
from tracker.sources.common import slug_to_title

# a Workday board whose site is two letters: tenant.wdN.myworkdayjobs.com/es
TWO_LETTER_SITE = r"^[^/]+\.myworkdayjobs\.com/[A-Za-z]{2}$"


@dataclass
class Plan:
    rewrite: dict[str, str] = field(default_factory=dict)  # old slug -> new slug
    remove: list[str] = field(default_factory=list)
    keep: list[str] = field(default_factory=list)
    has_postings: list[str] = field(default_factory=list)
    states: Counter = field(default_factory=Counter)


def decide(rows, registered: set[str], with_postings: set[str]) -> Plan:
    """rows: (slug, state, sample_url). registered: lowercased Workday slugs already
    stored, as discovered boards or companies. with_postings: slugs with postings."""
    plan = Plan()
    taken = set(registered)
    for slug, state, sample_url in sorted(rows):
        plan.states[state] += 1
        if slug.lower() in with_postings:
            plan.has_postings.append(slug)
            continue
        board = board_from_url(sample_url) if sample_url else None
        if board is None or board[0] != "workday" or board[1].lower() == slug.lower():
            plan.keep.append(slug)
        elif board[1].lower() in taken:
            plan.remove.append(slug)
        else:
            plan.rewrite[slug] = board[1]
            taken.add(board[1].lower())  # a second link to the same board is a duplicate
    return plan


def plan_for(conn: psycopg.Connection) -> Plan:
    rows = conn.execute(
        "SELECT board_slug, state, sample_url FROM discovered_boards"
        " WHERE platform = 'workday' AND board_slug ~ %s",
        (TWO_LETTER_SITE,),
    ).fetchall()
    targets = {
        board[1].lower()
        for _, _, url in rows
        if url and (board := board_from_url(url)) and board[0] == "workday"
    }
    registered = {
        s
        for (s,) in conn.execute(
            "SELECT lower(board_slug) FROM discovered_boards WHERE platform = 'workday'"
            " AND lower(board_slug) = ANY(%(t)s)"
            " UNION SELECT lower(board_slug) FROM companies WHERE platform = 'workday'"
            " AND lower(board_slug) = ANY(%(t)s)",
            {"t": list(targets)},
        )
    }
    with_postings = {
        s
        for (s,) in conn.execute(
            "SELECT DISTINCT lower(c.board_slug) FROM companies c JOIN jobs j ON j.company_id = c.id"
            " WHERE c.platform = 'workday' AND lower(c.board_slug) = ANY(%s)",
            ([r[0].lower() for r in rows],),
        )
    }
    return decide(rows, registered, with_postings)


def apply(conn: psycopg.Connection, plan: Plan) -> None:
    for old, new in plan.rewrite.items():
        conn.execute(
            "UPDATE discovered_boards SET board_slug = %s, company_name = %s, state = 'candidate',"
            " failures = 0, next_due = NULL WHERE platform = 'workday' AND board_slug = %s",
            (new, slug_to_title(new.split("/")[-1]), old),
        )
    if plan.remove:
        conn.execute(
            "DELETE FROM discovered_boards WHERE platform = 'workday' AND board_slug = ANY(%s)",
            (plan.remove,),
        )
    # a company made for a board being rewritten or removed, with no postings
    gone = list(plan.rewrite) + plan.remove
    if gone:
        conn.execute(
            "DELETE FROM companies c WHERE c.platform = 'workday' AND c.board_slug = ANY(%s)"
            " AND NOT EXISTS (SELECT 1 FROM jobs j WHERE j.company_id = c.id)",
            (gone,),
        )


def report(plan: Plan) -> None:
    total = len(plan.rewrite) + len(plan.remove) + len(plan.keep) + len(plan.has_postings)
    print(f"Workday boards with a two-letter site: {total} (by state: {dict(plan.states)})")
    print(f"  rewrite to the real board:     {len(plan.rewrite)}")
    for old, new in list(plan.rewrite.items())[:10]:
        print(f"      {old}  ->  {new}")
    print(f"  remove (real board known):     {len(plan.remove)}")
    for slug in plan.remove[:10]:
        print(f"      {slug}")
    print(f"  keep (the site's real name, or no link to tell): {len(plan.keep)}")
    for slug in plan.keep[:10]:
        print(f"      {slug}")
    print(f"  not touched, has postings:     {len(plan.has_postings)}")
    for slug in plan.has_postings[:10]:
        print(f"      {slug}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--apply", action="store_true", help="make the changes (otherwise only show them)")
    args = parser.parse_args()

    from tracker import db
    from tracker.cli import load_dotenv
    from tracker.config import database_url

    load_dotenv()
    with db.connect(database_url()) as conn:
        conn.read_only = not args.apply
        plan = plan_for(conn)
        report(plan)
        if not args.apply:
            conn.rollback()
            print("\nNothing written. Run again with --apply to make these changes.")
            return
        apply(conn, plan)
        conn.commit()
        print("\nDone.")


if __name__ == "__main__":
    main()
