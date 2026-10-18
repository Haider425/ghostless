"""Workday career sites (most banks and large enterprises).

Workday career sites are backed by a JSON API ("cxs"). The listing endpoint
returns titles and locations only, so descriptions need one extra request per
job, which we only make for relevant roles (see common.wants_detail).

Config slug, copied from the careers URL:
  https://td.wd3.myworkdayjobs.com/en-US/TD_Bank_Careers  ->  td.wd3.myworkdayjobs.com/TD_Bank_Careers
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone

from tracker.models import Company, Job, JobList
from tracker.sources import http
from tracker.sources.common import wants_detail
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
    )


def fetch_workday(company: Company, details: bool = True) -> JobList:
    base, tenant, site = parse_workday_slug(company.board_slug)
    api = f"{base}/wday/cxs/{tenant}/{site}"

    # 1. Page through every listing. Workday quirks:
    #    * only the first page reports `total`; later pages may say 0
    #    * the API stops returning results past an offset limit (2,000 on
    #      the tenants seen so far), so very large employers come back
    #      truncated. That is detected below and the listing marked partial.
    listings: dict[str, dict] = {}
    total = None
    offset = 0
    while True:
        page = http.request_json(
            "POST",
            f"{api}/jobs",
            {"appliedFacets": {}, "limit": PAGE_SIZE, "offset": offset, "searchText": ""},
        )
        if total is None:
            total = int(page.get("total") or 0)
        postings = page.get("jobPostings") or []
        for posting in postings:
            if posting.get("externalPath"):
                listings.setdefault(posting["externalPath"], posting)  # pages can shift mid-crawl
        offset += PAGE_SIZE
        if not postings or offset >= total:
            break

    complete = len(listings) >= total
    if not complete:
        log.warning(
            "%s: Workday returned %d of %d postings; treating the listing as partial",
            company.name,
            len(listings),
            total,
        )

    # 2. Details for relevant roles only. A failed detail call keeps the job
    #    (without a description) instead of failing the whole company, so
    #    closure tracking stays correct.
    jobs = JobList(complete=complete, total=total)
    for item in listings.values():
        detail = None
        if details and wants_detail(item.get("title", ""), item.get("locationsText", "")):
            try:
                detail = http.get_json(f"{api}{item['externalPath']}")
            except FetchError as exc:
                log.warning("%s: detail fetch failed for %s: %s", company.name, item["externalPath"], exc)
        jobs.append(parse_workday_job(item, detail, base, site))
    return jobs
