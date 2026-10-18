"""Command line interface.

    ghostless verify                 check every source
    ghostless verify --only apple    check one company (by name or slug)
    ghostless verify --dump          also save raw responses to .debug/
    ghostless ingest                 run the pipeline into the database
    ghostless reprocess              re-derive flags and pay for stored postings after an upgrade
    ghostless discover               read public job lists and crawl discovered boards
    ghostless migrate                create or upgrade the database tables (no fetching)
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
    commands.add_parser(
        "dedupe", help="merge postings and boards that were stored twice (also part of ingest)"
    )
    admin = commands.add_parser("admin", help="manage admin accounts")
    admin.add_argument("action", choices=["add", "remove", "list"])
    admin.add_argument("email", nargs="?", help="the account's email (for add and remove)")

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
    if args.command == "dedupe":
        _dedupe()
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
