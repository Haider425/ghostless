"""Command line interface.

    ghostless verify                 check every source
    ghostless verify --only apple    check one company (by name or slug)
    ghostless verify --dump          also save raw responses to .debug/
    ghostless ingest                 run the pipeline into the database
    ghostless reprocess              re-derive flags and pay for stored postings after an upgrade
    ghostless discover               read public job lists and crawl discovered boards
    ghostless migrate                create or upgrade the database tables (no fetching)
    ghostless health                 what the last ingest run did, per source
    ghostless evaluate [--full]      accuracy of extracted fields on the labelled postings
    ghostless seed-boards --dry-run  find job boards in Common Crawl's URL index (needs the index extra)
    ghostless admin add EMAIL        give an account access to the admin dashboard
    ghostless gap --have "Python, SQL"   compare your skills with what postings ask for
    ghostless serve                   run the web API on http://127.0.0.1:8000

`python -m tracker ...` works too.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

from tracker import __version__
from tracker.insights import LEVELS, ROLE_TYPES


def load_dotenv(path: Path = Path(".env")) -> None:
    """Load KEY=VALUE lines from .env without overriding real environment variables."""
    if not path.is_file():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ghostless", description="Ghostless: tech job postings that are actually hiring."
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--only", metavar="COMPANY", help="run for one company, by name or slug")
    common.add_argument(
        "--dump",
        nargs="?",
        const=".debug",
        metavar="DIR",
        help="save every raw response to DIR (default .debug) for debugging parsers",
    )
    common.add_argument("-v", "--verbose", action="store_true", help="show detailed logs")

    commands.add_parser("verify", parents=[common], help="check that every source works")
    ingest = commands.add_parser("ingest", parents=[common], help="fetch postings into the database")
    ingest.add_argument(
        "--shard",
        metavar="K/N",
        help="collect only part K of N (one of several machines); run `ghostless finish` after all parts",
    )
    commands.add_parser(
        "finish", help="after a sharded ingest: read the job lists, refresh signals and clean up"
    )
    discover = commands.add_parser(
        "discover", help="read the public job lists and crawl discovered job boards (part of ingest)"
    )
    discover.add_argument(
        "--boards",
        type=int,
        default=None,
        metavar="N",
        help="the most discovered boards to crawl (default: every board that's due)",
    )

    commands.add_parser("migrate", help="create or upgrade the database tables")
    evaluate = commands.add_parser("evaluate", help="accuracy of extracted fields on the labelled test set")
    evaluate.add_argument("--full", action="store_true", help="use the full local text, not the excerpts")
    evaluate.add_argument("--misses", metavar="FIELD", help="list the postings a field gets wrong")
    evaluate.add_argument("--holdout", action="store_true", help="score the 50 held-out postings")
    commands.add_parser(
        "health", help="what the last ingest run did per source (every part of a sharded run)"
    )
    commands.add_parser(
        "dedupe", help="merge postings and boards that were stored twice (also part of ingest)"
    )
    seed = commands.add_parser(
        "seed-boards",
        help="find job boards in Common Crawl's URL index and register them as candidates "
        "(monthly; needs GHOSTLESS_INDEX_SEEDING=1 and pip install '.[index]')",
    )
    seed.add_argument("--dry-run", action="store_true", help="only count what would be registered")
    seed.add_argument(
        "--files", type=int, default=None, metavar="N", help="read only the first N index files"
    )
    seed.add_argument("-v", "--verbose", action="store_true", help="show progress")
    admin = commands.add_parser("admin", help="manage admin accounts")
    admin.add_argument("action", choices=["add", "remove", "list"])
    admin.add_argument("email", nargs="?", help="the account's email (for add and remove)")

    label_resume = commands.add_parser(
        "label-resume", help="build and label the resume evaluation set (eval/resume)"
    )
    label_resume.add_argument(
        "action", nargs="?", default="label", choices=["label", "review", "agreement", "pool", "rebalance", "status"],
        help="label pairs blind (default); review: tuning pairs with their pre-labels; agreement: how your "
        "labels compare with the pre-labels; pool: choose postings to label; rebalance: add likely strong and "
        "okay pairs and trim the weak ones; status: progress",
    )  # fmt: skip
    label_resume.add_argument(
        "--web", action="store_true", help="label in a local web page (http://127.0.0.1 only) instead"
    )
    label_resume.add_argument("--port", type=int, default=8765, help="for --web (default 8765)")
    part = label_resume.add_mutually_exclusive_group()
    part.add_argument("--holdout", action="store_true", help="only the held-out pairs (always blind)")
    part.add_argument("--tuning", action="store_true", help="only the tuning pairs")
    label_resume.add_argument(
        "--db",
        metavar="URL",
        help="for pool and rebalance: the database to read postings from (use a local copy)",
    )
    label_resume.add_argument("--per", type=int, default=8, help="for pool: postings per resume (default 8)")
    label_resume.add_argument("--only", metavar="ID", help="one resume only, by its id")
    domains = commands.add_parser(
        "domains", help="find company websites, for logos (also part of ingest, a few hundred a night)"
    )
    domains.add_argument("--dry-run", action="store_true", help="only show what would be filled in")
    domains.add_argument(
        "--all", action="store_true", help="look up every company that's due, not a night's share"
    )
    domains.add_argument("-v", "--verbose", action="store_true", help="list every website found")
    commands.add_parser(
        "reprocess", help="re-derive pay, disclosures and repost links for stored postings (no fetching)"
    )

    serve = commands.add_parser("serve", help="run the web API (needs the api extra)")
    serve.add_argument("--host", default="127.0.0.1", help="use 0.0.0.0 when deploying")
    serve.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")))
    serve.add_argument("--reload", action="store_true", help="restart on code changes (development)")

    gap = commands.add_parser("gap", help="compare your skills with what postings ask for")
    gap.add_argument("--have", required=True, help='your skills, comma separated: "Python, SQL, React"')
    gap.add_argument(
        "--role", action="append", choices=ROLE_TYPES, help="role type (repeatable, default sde)"
    )
    gap.add_argument(
        "--level", action="append", choices=LEVELS, help="level (repeatable, default intern and new_grad)"
    )
    gap.add_argument("--anywhere", action="store_true", help="include postings outside Canada / remote")
    gap.add_argument("--top", type=int, default=15, help="how many skills to show (default 15)")
    return parser


def main(argv: list[str] | None = None) -> None:
    args = _parser().parse_args(argv)
    load_dotenv()  # before importing sources, so GHOSTLESS_CONTACT is picked up

    if args.command == "gap":
        _gap(args)
        return
    if args.command == "serve":
        _serve(args)
        return
    if args.command == "reprocess":
        _reprocess()
        return
    if args.command == "discover":
        _discover(args)
        return
    if args.command == "migrate":
        _migrate()
        return
    if args.command == "evaluate":
        from tracker.evaluate import main as evaluate

        evaluate(full=args.full, misses=args.misses, holdout=args.holdout)
        return
    if args.command == "health":
        _health()
        return
    if args.command == "seed-boards":
        _seed_boards(args)
        return
    if args.command == "dedupe":
        _dedupe()
        return
    if args.command == "domains":
        _domains(args)
        return
    if args.command == "label-resume":
        _label_resume(args)
        return
    if args.command == "admin":
        _admin(args)
        return

    logs_progress = args.command in ("ingest", "finish")
    level = (
        logging.DEBUG
        if getattr(args, "verbose", False)
        else logging.INFO
        if logs_progress
        else logging.WARNING
    )
    fmt = "%(asctime)s %(levelname)-7s %(message)s" if logs_progress else "      ↳ %(message)s"
    logging.basicConfig(level=level, format=fmt, datefmt="%H:%M:%S", stream=sys.stdout)

    from tracker.sources import http

    if getattr(args, "dump", None):
        http.dump_dir = Path(args.dump)
        logging.getLogger("tracker.sources.http").setLevel(logging.INFO)

    if args.command == "verify":
        from tracker import verify

        problems = verify.run(args.only)
        if args.dump:
            print(f"\nRaw responses saved in {args.dump}/")
        if problems:
            raise SystemExit(f"\n{problems} source(s) need attention")
    else:
        from tracker import ingest

        if args.command == "finish":
            ingest.finish()
            return
        from tracker.parallel import parse_shard

        stats = ingest.run(args.only, shard=parse_shard(args.shard))
        if stats["companies_ok"] == 0 and stats.get("discovered_ok", 0) == 0:
            raise SystemExit(1)


def _serve(args: argparse.Namespace) -> None:
    try:
        import uvicorn
    except ImportError:
        raise SystemExit('The API needs extra packages: pip install -e ".[api]"') from None
    from tracker.config import database_url

    database_url()  # fail fast with a clear message if it is missing
    print(f"Ghostless API on http://{args.host}:{args.port}  (docs at /docs)", flush=True)
    uvicorn.run(
        "tracker.api:create_app",
        factory=True,
        host=args.host,
        port=args.port,
        reload=args.reload,
        proxy_headers=True,
    )


def _migrate() -> None:
    from tracker import db
    from tracker.config import database_url

    with db.connect(database_url()) as conn:
        db.apply_schema(conn)
    print("Database is up to date.")


def _health() -> None:
    from tracker import db
    from tracker.config import database_url
    from tracker.health import render

    with db.connect(database_url()) as conn:
        # the parts of a sharded run start within minutes of each other
        rows = conn.execute(
            """SELECT started_at AT TIME ZONE 'UTC', health FROM ingest_runs
               WHERE health IS NOT NULL
                 AND started_at > (SELECT max(started_at) FROM ingest_runs WHERE health IS NOT NULL)
                                  - interval '30 minutes'
               ORDER BY started_at"""
        ).fetchall()
    if not rows:
        print("No run has a health report yet (they start with the next ingest).")
        return
    for started_at, report in rows:
        print(render(report, f"Run started {started_at:%Y-%m-%d %H:%M} UTC"))


def _seed_boards(args: argparse.Namespace) -> None:
    from collections import Counter

    from tracker import db, settings
    from tracker.config import database_url

    if not args.dry_run and not settings.index_seeding():
        print("Index seeding is off. Set GHOSTLESS_INDEX_SEEDING=1 to register boards, or use --dry-run.")
        return
    try:
        import pyarrow  # noqa: F401
    except ImportError:
        raise SystemExit("seed-boards needs the optional index extra: pip install '.[index]'") from None
    from tracker.discovery import index, snowball
    from tracker.sources.common import slug_to_title

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(asctime)s %(message)s",
        stream=sys.stdout,
    )
    crawl, files = index.latest_crawl()
    boards, counts = index.find_boards(files, args.files)
    with db.connect(database_url()) as conn:
        conn.read_only = args.dry_run
        known = {
            (p, s.lower()) for p, s in conn.execute("SELECT platform, board_slug FROM discovered_boards")
        }
        known |= {(p, s.lower()) for p, s in conn.execute("SELECT platform, board_slug FROM companies")}
        conn.rollback()
    new = {key: link for key, link in boards.items() if key not in known}
    print(
        f"{crawl}: read {counts.get('files', 0)} index files ({counts.get('row_groups_read', 0)} row groups)"
    )
    print(f"boards in the index: {dict(Counter(p for p, _ in boards))}")
    print(f"new to Ghostless:    {dict(Counter(p for p, _ in new))}")
    if args.dry_run:
        print("Dry run: nothing registered.")
        return
    for (platform, slug), link in new.items():
        board = index.board_from_url(link) or (platform, slug)  # the link's own spelling of the slug
        name = slug_to_title(board[1].split("/")[-1])
        snowball.noted.add(snowball.Candidate(board[0], board[1], name, f"common-crawl:{crawl}", link))
    added = snowball.register(database_url())
    print(
        f"Registered {added} candidate boards; each is checked (GHOSTLESS_VERIFY_PER_RUN a run) before it's read."
    )


def _dedupe() -> None:
    from tracker import db
    from tracker.config import database_url
    from tracker.discovery.dedupe import merge_duplicates

    with db.connect(database_url()) as conn:
        db.apply_schema(conn)
        result = merge_duplicates(conn)
        db.refresh_signals(conn)
    print(
        f"Removed {result['boards']} duplicate boards, {result['companies']} duplicate companies "
        f"and {result['jobs']} duplicate postings."
    )


def _label_resume(args: argparse.Namespace) -> None:
    from tracker.resume import label

    if args.action in ("pool", "rebalance"):
        if not args.db:
            raise SystemExit(
                f"{args.action} reads postings from a database: pass --db with a local copy's URL "
                '(or --db "$DATABASE_URL" to read Neon, which counts toward its transfer)'
            )
        if args.action == "pool":
            label.pool(args.db, per_resume=args.per, only=args.only)
        else:
            label.rebalance(args.db, only=args.only)
    elif args.action == "status":
        label.status()
    elif args.action == "agreement":
        label.agreement_report()
    elif args.web:
        from tracker.resume import label_web

        label_web.serve(args.port)
    else:
        part = "holdout" if args.holdout else "tuning" if args.tuning else "all"
        label.label(only=args.only, part=part, review=args.action == "review")


def _domains(args: argparse.Namespace) -> None:
    from tracker import db, domains
    from tracker.config import database_url

    logging.basicConfig(level=logging.WARNING, format="      ↳ %(message)s", stream=sys.stdout)
    dsn = database_url()
    if not args.dry_run:
        with db.connect(dsn) as conn:
            db.apply_schema(conn)
    report = domains.fill(dsn, lookups=None if args.all else domains.LOOKUPS_PER_RUN, dry_run=args.dry_run)
    if args.verbose:
        for name, domain, source in report.found:
            print(f"  {name:40} {domain:32} {source}")
    print(("Would fill in: " if args.dry_run else "Filled in: ") + report.summary())


def _admin(args: argparse.Namespace) -> None:
    from tracker import db
    from tracker.accounts import store
    from tracker.config import database_url

    with db.connect(database_url()) as conn:
        db.apply_schema(conn)
        if args.action == "list":
            rows = conn.execute(
                "SELECT email, created_at FROM users WHERE role = 'admin' ORDER BY email"
            ).fetchall()
            print(
                "\n".join(f"{email}  (since {created:%Y-%m-%d})" for email, created in rows)
                or "No admins yet."
            )
            return
        if not args.email:
            raise SystemExit("Give the account's email, e.g. ghostless admin add you@example.com")
        role = "admin" if args.action == "add" else "user"
        if not store.set_role(conn, args.email, role):
            raise SystemExit(f"No account with the email {args.email}. Sign up on the website first.")
        conn.commit()
    print(f"{args.email} is {'now an admin' if role == 'admin' else 'no longer an admin'}.")


def _discover(args: argparse.Namespace) -> None:
    from datetime import datetime, timezone

    from tracker import db
    from tracker.config import database_url, load_companies, load_lists
    from tracker.discovery import run as discovery

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S", stream=sys.stdout
    )
    if args.boards is not None:
        discovery.BOARDS_PER_RUN = args.boards
    dsn = database_url()
    with db.connect(dsn) as conn:
        db.apply_schema(conn)
    stats = dict(jobs_seen=0, jobs_new=0, jobs_closed=0)
    discovery.run(dsn, load_companies(), load_lists(), datetime.now(timezone.utc), stats)
    with db.connect(dsn) as conn:
        db.refresh_signals(conn)
    print(
        f"Discovery: {stats.get('discovered_ok', 0)} boards crawled, {stats.get('list_companies', 0)} list-only "
        f"companies, {stats['jobs_new']} new and {stats['jobs_closed']} closed postings."
    )


def _reprocess() -> None:
    from tracker import reprocess
    from tracker.config import database_url, load_companies

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S", stream=sys.stdout
    )
    result = reprocess.run(database_url(), load_companies())
    print(f"Reprocessed {result['postings']} postings; {result['reposts_linked']} linked as reposts.")


def _gap(args: argparse.Namespace) -> None:
    from tracker import db, insights
    from tracker.config import database_url

    roles = tuple(args.role or ["sde"])
    levels = tuple(args.level or ["intern", "new_grad"])
    where = "anywhere" if args.anywhere else "Canada or remote"
    description = f"{'/'.join(levels).replace('_', ' ')} {'/'.join(roles)} ({where})"
    with db.connect(database_url()) as conn:
        report = insights.skills_gap(
            conn,
            have=args.have.split(","),
            role_types=roles,
            levels=levels,
            canada_or_remote=not args.anywhere,
            limit=args.top,
        )
    print(insights.format_gap(report, description))


if __name__ == "__main__":
    main()
