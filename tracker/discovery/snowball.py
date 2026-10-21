"""Discovery that grows by itself (GHOSTLESS_SNOWBALL, GHOSTLESS_JSONLD).

While postings are read, the job boards they link to are noted: a posting's
own address, and links in its description ("apply at jobs.lever.co/acme").
Job list entries that point at a company's own career site note that site,
to be read through its JSON-LD. Each run then:

1. registers what it noted as candidates in discovered_boards;
2. checks up to GHOSTLESS_VERIFY_PER_RUN candidates with one request each.
   A board with something worth storing becomes active and is read on the
   usual revisit schedule. One with nothing worth storing is "empty" and is
   checked again in a month. One that fails three checks is "dead" and is
   never registered again. A career site that links to a hiring system the
   tracker reads (Greenhouse, Lever, Ashby, Workday) is "replaced" by it.

Both switches are off by default; with them off, nothing here runs.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass

from tracker import db, settings
from tracker.classify import title_worth_storing
from tracker.discovery.boards import board_from_url, board_links, career_site, company_key
from tracker.models import Company
from tracker.parallel import run_by_site, site_of
from tracker.sources import http
from tracker.sources.boards import URLS
from tracker.sources.common import slug_to_title
from tracker.sources.http import FetchError
from tracker.sources.jsonld import parse_job_page
from tracker.sources.workday import _search, parse_workday_slug

log = logging.getLogger("tracker.discovery")

EMPTY_RECHECK_DAYS = 30
DEAD_AFTER_FAILURES = 3
ATS_PLATFORMS = ("greenhouse", "lever", "ashby", "workday")


@dataclass(frozen=True)
class Candidate:
    platform: str
    board_slug: str
    company_name: str
    found_in: str
    sample_url: str | None = None


class Noted:
    """Candidates noted during a run, from every thread."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.items: dict[tuple[str, str], Candidate] = {}

    def add(self, candidate: Candidate) -> None:
        key = (candidate.platform, candidate.board_slug.lower())
        with self._lock:
            self.items.setdefault(key, candidate)

    def take(self) -> list[Candidate]:
        with self._lock:
            items, self.items = list(self.items.values()), {}
        return items


noted = Noted()


def _name_for(slug: str, source: str) -> str:
    """A link in Acme's posting to jobs.lever.co/acme is Acme's own board."""
    return source if company_key(source) == company_key(slug) else slug_to_title(slug.split("/")[-1])


def note_postings(company: Company, jobs) -> None:
    """Note the boards linked from a company's postings (GHOSTLESS_SNOWBALL)."""
    if not settings.snowball():
        return
    own = (company.platform, company.board_slug.lower())
    for job in jobs:
        links = board_links(job.description or "")
        board = board_from_url(job.url or "")
        if board:
            links.add(board)
        for platform, slug in links:
            if (platform, slug.lower()) != own:
                noted.add(
                    Candidate(platform, slug, _name_for(slug, company.name), f"link:{company.name}", job.url)
                )


def note_list_entry(company: str, url: str, list_name: str) -> None:
    """A list entry on a company's own career site (GHOSTLESS_JSONLD)."""
    if not settings.jsonld() or board_from_url(url):
        return  # hiring-system links are registered by the lists step already
    site = career_site(url)
    if site:
        noted.add(Candidate("jsonld", site, company, list_name, url))


def register(dsn: str, known_names: set[str] = frozenset()) -> int:
    """Store what was noted as candidates. Boards already known in any state,
    and career sites of companies already read through a hiring system, are
    skipped. Returns how many were added."""
    items = noted.take()
    if not items:
        return 0
    with db.connect(dsn) as conn:
        read_names = known_names | {
            company_key(name)
            for (name,) in conn.execute(
                "SELECT name FROM companies WHERE platform <> 'jsonld' AND platform <> 'list'"
            )
        }
        rows = [
            (c.platform, c.board_slug, c.company_name, c.found_in, c.sample_url)
            for c in items
            if not (c.platform == "jsonld" and company_key(c.company_name) in read_names)
        ]
        before = conn.execute("SELECT count(*) FROM discovered_boards").fetchone()[0]
        with conn.cursor() as cur:
            cur.executemany(
                """INSERT INTO discovered_boards (platform, board_slug, company_name, found_in, sample_url, state)
                   SELECT %s, %s, %s, %s, %s, 'candidate'
                   WHERE NOT EXISTS (SELECT 1 FROM discovered_boards d
                                     WHERE d.platform = %s AND lower(d.board_slug) = lower(%s))
                   ON CONFLICT (platform, board_slug) DO NOTHING""",
                [(*row, row[0], row[1]) for row in rows],
            )
        added = conn.execute("SELECT count(*) FROM discovered_boards").fetchone()[0] - before
    if added:
        log.info("snowball: %d new candidate boards", added)
    return added


# ---------- checking candidates ----------


@dataclass
class Check:
    outcome: str  # active | empty | failed | replaced
    name: str | None = None  # the board's own name for its company, when it says
    replaced_by: tuple[str, str] | None = None
    worth: int = 0  # postings worth storing seen in the check


def _worth(titles) -> int:
    return sum(1 for title in titles if title_worth_storing(title or ""))


def check(platform: str, slug: str, sample_url: str | None) -> Check:
    """One request: does the board answer, with something worth storing?"""
    try:
        if platform == "greenhouse":
            data = http.get_json(URLS["greenhouse"].format(slug=slug))
            items = data.get("jobs") or []
            name = next((i.get("company_name") for i in items if i.get("company_name")), None)
            worth = _worth(i.get("title") for i in items)
            return Check("active" if worth else "empty", name, worth=worth)
        if platform == "lever":
            items = http.get_json(URLS["lever"].format(slug=slug)) or []
            worth = _worth(i.get("text") for i in items)
            return Check("active" if worth else "empty", worth=worth)
        if platform == "ashby":
            items = (http.get_json(URLS["ashby"].format(slug=slug)) or {}).get("jobs") or []
            worth = _worth(i.get("title") for i in items if i.get("isListed") is not False)
            return Check("active" if worth else "empty", worth=worth)
        if platform == "workday":
            # discovered Workday boards are searched for student roles only
            base, tenant, site = parse_workday_slug(slug)
            found, _, _ = _search(f"{base}/wday/cxs/{tenant}/{site}", {}, "intern", 20)
            worth = _worth(i.get("title") for i in found.values())
            return Check("active" if worth else "empty", worth=worth)
        if platform in settings.NEW_SOURCES:  # stage E: the listing alone, no descriptions
            from tracker.sources import ats

            if not ats.enabled(platform):
                return Check("failed")
            company = Company(name=slug, platform=platform, board_slug=slug, origin="discovered")
            jobs = ats.FETCHERS[platform](company, details=False)
            worth = _worth(j.title for j in jobs)
            return Check("active" if worth else "empty", worth=worth)
        if platform == "jsonld":
            if not sample_url:
                return Check("failed")
            page = http.get_text(sample_url)
            ats = sorted(board_links(page))
            if ats:  # the site's hiring system is cheaper to read, and complete
                return Check("replaced", replaced_by=ats[0])
            jobs, any_posting = parse_job_page(page, sample_url)
            if not any_posting:
                return Check("failed")  # no JobPosting on a job page: this site can't be read this way
            return Check(
                "active" if _worth(j.title for j in jobs) else "empty", worth=_worth(j.title for j in jobs)
            )
    except FetchError as exc:
        log.info("candidate %s %s: %s", platform, slug, exc)
        return Check("failed")
    return Check("failed")


def verify(dsn: str, budget: int | None = None) -> dict[str, int]:
    """Check up to `budget` candidates (and empty boards due a recheck)."""
    platforms = [p for p, on in (("jsonld", settings.jsonld()),) if on]
    if settings.snowball() or settings.index_seeding():  # boards from links or from the URL index
        platforms += list(ATS_PLATFORMS) + sorted(settings.sources())
    budget = settings.verify_per_run() if budget is None else budget
    counts = dict(checked=0, active=0, empty=0, failed=0, dead=0, replaced=0)
    if not platforms or budget <= 0:
        return counts
    with db.connect(dsn) as conn:
        rows = conn.execute(
            """SELECT platform, board_slug, company_name, sample_url FROM discovered_boards
               WHERE platform = ANY(%s)
                 AND (state = 'candidate' OR state = 'empty')
                 AND (next_due IS NULL OR next_due <= now() + interval '1 hour')
               ORDER BY state = 'empty', next_due NULLS FIRST, first_seen
               LIMIT %s""",
            (platforms, budget),
        ).fetchall()
    companies = {(p, s): (n, u) for p, s, n, u in rows}

    def work(company: Company) -> Check:
        return check(
            company.platform, company.board_slug, companies[(company.platform, company.board_slug)][1]
        )

    targets = [
        Company(name=n, platform=p, board_slug=s, origin="discovered") for (p, s), (n, _) in companies.items()
    ]
    for company, result in run_by_site(targets, site_of, work):
        if isinstance(result, BaseException):
            log.error("candidate %s: %s", company.board_slug, result)
            result = Check("failed")
        counts["checked"] += 1
        state = _record(dsn, company, result)
        counts[state] = counts.get(state, 0) + 1
    if counts["checked"]:
        log.info(
            "candidates checked: %d (%d active, %d empty, %d failed, %d dead, %d replaced)",
            counts["checked"], counts["active"], counts["empty"], counts["failed"], counts["dead"], counts["replaced"],
        )  # fmt: skip
    return counts


def _record(dsn: str, company: Company, result: Check) -> str:
    key = (company.platform, company.board_slug)
    with db.connect(dsn) as conn:
        if result.outcome == "active":
            conn.execute(
                """UPDATE discovered_boards SET state = 'active', failures = 0, next_due = now(),
                          company_name = coalesce(%s, company_name)
                   WHERE platform = %s AND board_slug = %s""",
                (result.name, *key),
            )
            return "active"
        if result.outcome == "empty":
            conn.execute(
                """UPDATE discovered_boards SET state = 'empty', failures = 0, last_crawled = now(),
                          next_due = now() + make_interval(days => %s), company_name = coalesce(%s, company_name)
                   WHERE platform = %s AND board_slug = %s""",
                (EMPTY_RECHECK_DAYS, result.name, *key),
            )
            return "empty"
        if result.outcome == "replaced" and result.replaced_by:
            platform, slug = result.replaced_by
            conn.execute(
                "UPDATE discovered_boards SET state = 'replaced' WHERE platform = %s AND board_slug = %s", key
            )
            conn.execute(
                """INSERT INTO discovered_boards (platform, board_slug, company_name, found_in, state)
                   SELECT %s, %s, %s, %s, 'candidate'
                   WHERE NOT EXISTS (SELECT 1 FROM discovered_boards d
                                     WHERE d.platform = %s AND lower(d.board_slug) = lower(%s))
                   ON CONFLICT (platform, board_slug) DO NOTHING""",
                (platform, slug, company.name, f"site:{company.board_slug}", platform, slug),
            )
            return "replaced"
        failures = conn.execute(
            """UPDATE discovered_boards SET failures = failures + 1, last_crawled = now(),
                      next_due = now() + interval '1 day'
               WHERE platform = %s AND board_slug = %s RETURNING failures""",
            key,
        ).fetchone()
        if failures and failures[0] >= DEAD_AFTER_FAILURES:
            conn.execute(
                "UPDATE discovered_boards SET state = 'dead', next_due = NULL WHERE platform = %s AND board_slug = %s",
                key,
            )
            return "dead"
        return "failed"
