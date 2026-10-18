"""Command line interface.

    ghostless verify                 check every source
    ghostless verify --only apple    check one company (by name or slug)
    ghostless verify --dump          also save raw responses to .debug/
    ghostless ingest                 run the pipeline into the database
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
    commands.add_parser("ingest", parents=[common], help="fetch postings into the database")

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

    level = logging.DEBUG if args.verbose else logging.INFO if args.command == "ingest" else logging.WARNING
    fmt = "%(asctime)s %(levelname)-7s %(message)s" if args.command == "ingest" else "      ↳ %(message)s"
    logging.basicConfig(level=level, format=fmt, datefmt="%H:%M:%S", stream=sys.stdout)

    from tracker.sources import http

    if args.dump:
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

        stats = ingest.run(args.only)
        if stats["companies_ok"] == 0:
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