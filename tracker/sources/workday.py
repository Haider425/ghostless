"""Workday career sites (most banks and large enterprises).

Workday career sites are backed by a JSON API ("cxs"). The listing endpoint
returns titles and locations only, so descriptions need one extra request per
job. Each posting is fetched once: the pipeline reuses stored descriptions,
and new postings are taken in priority order up to a cap per run (see
common.plan_details).

Config slug, copied from the careers URL:
  https://td.wd3.myworkdayjobs.com/en-US/TD_Bank_Careers  ->  td.wd3.myworkdayjobs.com/TD_Bank_Careers
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone

from tracker.classify import classify_level
from tracker.models import Company, Job, JobList
from tracker.sources import http
from tracker.sources.common import employment_type_of, plan_details, workplace_of
from tracker.sources.http import FetchError
from tracker.text import html_to_text

log = logging.getLogger(__name__)

PAGE_SIZE = 20  # the API's maximum page size

_AGE = re.compile(r"(\d+)\+?\s*days?\s*ago", re.I)


def parse_workday_slug(slug: str) -> tuple[str, str, str]:
    """Return (base_url, tenant, site) from 'tenant.wdN.myworkdayjobs.com/[locale/]Site'."""
    cleaned = re.sub(r"^https?://", "", slug.strip()).strip("/")
    host, _, path = cleaned.partition("/")
    parts = [p for p in path.split("/") if p]
    if parts and re.fullmatch(r"[a-z]{2}-[A-Z]{2}", parts[0]):  # drop locale like en-US
        parts = parts[1:]
    if not host.endswith("myworkdayjobs.com") or not parts:
        raise FetchError(f"bad workday slug {slug!r}; expected tenant.wdN.myworkdayjobs.com/Site")
    return f"https://{host}", host.split(".")[0], parts[0]


def parse_workday_age(posted_on: str | None, now: datetime | None = None) -> datetime | None:
    """Convert Workday's 'Posted 3 Days Ago' style text into a datetime."""
    if not posted_on:
        return None
    now = now or datetime.now(timezone.utc)
    text = posted_on.lower()
    if "today" in text:
        return now
    if "yesterday" in text:
        return now - timedelta(days=1)
    match = _AGE.search(text)
    return now - timedelta(days=int(match.group(1))) if match else None


def is_student_title(title: str) -> bool:
    return classify_level(title) in ("intern", "new_grad")


def parse_workday_job(item: dict, detail: dict | None, base: str, site: str) -> Job:
    info = (detail or {}).get("jobPostingInfo") or {}
    path = item["externalPath"]
    locations = [info.get("location")] + list(info.get("additionalLocations") or [])
    location = " | ".join(loc for loc in locations if loc) or item.get("locationsText", "")
    return Job(
        external_id=path,  # stable across runs, unlike the posting age text
        title=(info.get("title") or item.get("title", "")).strip(),
        url=info.get("externalUrl") or f"{base}/en-US/{site}{path}",
        location=location,
        description=html_to_text(info.get("jobDescription")),
        posted_at=parse_workday_age(item.get("postedOn")),
        source_remote=bool(info.get("remoteType") and "remote" in info["remoteType"].lower()),
        workplace=workplace_of(info.get("remoteType")),  # stage C1: "Hybrid", "Remote", "On-site"
        employment_type=employment_type_of(info.get("timeType")),  # "Full time", "Part time"
    )


# Workday stops returning results past this many per search, however many
# match. Employers with more postings are fetched as several smaller
# searches, split by one of the site's own filters (facets).
OFFSET_LIMIT = 2000
MAX_SPLIT_DEPTH = 2


def flatten_facets(facets: list | None) -> dict[str, list[tuple[str, int]]]:
    """{facetParameter: [(value id, count), ...]} from Workday's facet tree.

    Facets nest: a value can itself carry a facetParameter and values (for
    example, location groups containing countries). Leaves have an id and a
    count.
    """
    found: dict[str, list[tuple[str, int]]] = {}

    def walk(node: dict, parameter: str | None) -> None:
        param = node.get("facetParameter") or parameter
        children = node.get("values")
        if isinstance(children, list) and children:
            for child in children:
                if isinstance(child, dict):
                    walk(child, param)
        elif param and node.get("id") and isinstance(node.get("count"), int):
            found.setdefault(param, []).append((str(node["id"]), node["count"]))

    for facet in facets or []:
        if isinstance(facet, dict):
            walk(facet, None)
    return found


def choose_split(
    facets: dict[str, list[tuple[str, int]]], total: int, applied: dict
) -> tuple[str, list[str]] | None:
    """The facet that best splits a search into searches under the limit.

    It must cover (nearly) every posting, so nothing is lost, and its
    largest value should be as small as possible.
    """
    best = None
    for param, values in facets.items():
        if param in applied or len(values) < 2:
            continue
        covered = sum(count for _, count in values)
        if covered < total * 0.98:
            continue  # postings without a value for this facet would be missed
        largest = max(count for _, count in values)
        if best is None or largest < best[0]:
            best = (largest, param, [value for value, count in values if count > 0])
    return (best[1], best[2]) if best else None


def _search(
    api: str, applied: dict, text: str = "", limit: int = OFFSET_LIMIT
) -> tuple[dict[str, dict], int, list]:
    """One search, paged to the end, the offset limit, or `limit` results."""
    listings: dict[str, dict] = {}
    total = None
    facets: list = []
    offset = 0
    while offset < min(limit, OFFSET_LIMIT):
        page = http.request_json(
            "POST",
            f"{api}/jobs",
            {"appliedFacets": applied, "limit": PAGE_SIZE, "offset": offset, "searchText": text},
        )
        if total is None:  # Workday quirk: only the first page reports total and facets
            total = int(page.get("total") or 0)
            facets = page.get("facets") or []
        postings = page.get("jobPostings") or []
        for posting in postings:
            if posting.get("externalPath"):
                listings.setdefault(posting["externalPath"], posting)  # pages can shift mid-crawl
        offset += PAGE_SIZE
        if not postings or offset >= total:
            break
    return listings, total or 0, facets


def _crawl(api: str, applied: dict, depth: int = 0) -> tuple[dict[str, dict], int]:
    """Every posting matching `applied`, splitting the search when it's too big."""
    listings, total, facets = _search(api, applied)
    if len(listings) >= total or depth >= MAX_SPLIT_DEPTH:
        return listings, total
    split = choose_split(flatten_facets(facets), total, applied)
    if split is None:
        return listings, total
    param, values = split
    log.info("splitting a search of %d postings by %s (%d values)", total, param, len(values))
    for value in values:
        part, _ = _crawl(api, {**applied, param: [value]}, depth + 1)
        for path, posting in part.items():
            listings.setdefault(path, posting)
    return listings, total


def list_workday(company: Company) -> tuple[set[str], bool]:
    """Every posting id on the board (no descriptions), and whether the listing
    came back complete. Used to close postings once a week on boards that are
    otherwise only searched for student roles.

    Only listings that fit in one search (Workday pages stop at 2,000) are
    read: at most 100 requests. A bigger board would need the search split
    by facets, which on some boards takes over 1,500 requests (measured), so
    it's reported as incomplete after one request and nothing is closed."""
    base, tenant, site = parse_workday_slug(company.board_slug)
    api = f"{base}/wday/cxs/{tenant}/{site}"
    first, total, _ = _search(api, {}, limit=PAGE_SIZE)
    if total > OFFSET_LIMIT:
        log.info("%s: %d postings, too many for the weekly full read", company.name, total)
        return set(first), False
    listings, total, _ = _search(api, {}) if total > len(first) else (first, total, None)
    return set(listings), len(listings) >= total


def fetch_workday(
    company: Company,
    details: bool = True,
    known: frozenset[str] = frozenset(),
    queries: tuple[str, ...] | None = None,
    per_query: int = 200,
    max_details: int | None = None,
) -> JobList:
    """Every posting, or with `queries` only those matching the searches
    (used for discovered employers: internships and new grad roles)."""
    base, tenant, site = parse_workday_slug(company.board_slug)
    api = f"{base}/wday/cxs/{tenant}/{site}"

    # 1. Every listing. Workday stops paging at an offset limit (2,000), so a
    #    big employer's search is split by one of its facets (job family,
    #    country, ...) into searches under the limit. If even that comes back
    #    short, the listing is marked partial so nothing is wrongly closed.
    if queries:
        listings, total, complete = {}, 0, True
        for text in queries:
            found, matched, _ = _search(api, {}, text, per_query)
            complete = complete and len(found) >= matched  # complete for this search's scope
            total += matched
            for path, posting in found.items():
                listings.setdefault(path, posting)
        # Workday's search matches words inside words and in descriptions: "intern"
        # finds International and Internal Audit. Keep what the title says is a
        # student role, so nothing else is stored or sent for a description.
        listings = {path: item for path, item in listings.items() if is_student_title(item.get("title", ""))}
    else:
        listings, total = _crawl(api, {})
        complete = len(listings) >= total
    if not complete:
        log.warning(
            "%s: Workday returned %d of %d postings; treating the listing as partial",
            company.name,
            len(listings),
            total,
        )

    # 2. Details for postings not stored yet, most relevant first. A failed
    #    detail call keeps the job (without a description) instead of failing
    #    the whole company, so closure tracking stays correct.
    wanted = (
        plan_details(
            [(path, item.get("title", ""), item.get("locationsText", "")) for path, item in listings.items()],
            known,
            max_details,
        )
        if details
        else set()
    )
    jobs = JobList(complete=complete, total=total)
    for path, item in listings.items():
        detail = None
        if path in wanted:
            try:
                detail = http.get_json(f"{api}{item['externalPath']}")
            except FetchError as exc:
                log.warning("%s: detail fetch failed for %s: %s", company.name, item["externalPath"], exc)
        jobs.append(parse_workday_job(item, detail, base, site))
    return jobs
