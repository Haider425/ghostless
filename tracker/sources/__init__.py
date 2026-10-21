"""Job source adapters. `fetch_jobs(company)` is the single entry point.

| platform   | used by                                 | how                              |
|------------|-----------------------------------------|----------------------------------|
| greenhouse | Stripe, Airbnb, Datadog, ...            | public board API                 |
| lever      | Palantir, Spotify, ...                  | public board API                 |
| ashby      | OpenAI, Plaid, Wealthsimple, ...        | public board API                 |
| workday    | TD, RBC, BMO, CIBC, Nvidia, ...         | career site JSON API             |
| amazon     | Amazon                                  | amazon.jobs search JSON          |
| eightfold  | Microsoft                               | career site JSON API             |
| google     | Google                                  | HTML, first results page only    |
| apple      | Apple                                   | HTML result and job pages        |
| sitemap    | Shopify                                 | careers XML sitemap              |
| rss        | Scotiabank (SAP SuccessFactors)         | RSS job feed                     |
| jsonld     | company career sites (discovered)       | sitemaps + JSON-LD JobPosting    |
| workable, teamtailor, personio, breezy, rippling, recruitee, smartrecruiters | see sources/ats.py; each off unless in GHOSTLESS_SOURCES | |

Every request goes through `http`, which checks robots.txt first.
"""

from __future__ import annotations

from collections.abc import Callable

from tracker.models import Company, Job, JobList
from tracker.sources import ats
from tracker.sources.amazon import fetch_amazon, parse_amazon
from tracker.sources.apple import fetch_apple, is_full_description, parse_apple_detail, parse_apple_page
from tracker.sources.boards import fetch_board, parse_ashby, parse_greenhouse, parse_lever
from tracker.sources.eightfold import fetch_eightfold, parse_eightfold_position, parse_eightfold_slug
from tracker.sources.feeds import fetch_rss, fetch_sitemap, parse_rss, parse_sitemap
from tracker.sources.google import fetch_google, parse_google_detail, parse_google_listing
from tracker.sources.http import FetchError, Validators
from tracker.sources.jsonld import fetch_jsonld
from tracker.sources.workday import (
    fetch_workday,
    parse_workday_age,
    parse_workday_job,
    parse_workday_slug,
)

FETCHERS: dict[str, Callable[..., list[Job]]] = {
    "greenhouse": fetch_board,
    "lever": fetch_board,
    "ashby": fetch_board,
    "workday": fetch_workday,
    "amazon": fetch_amazon,
    "eightfold": fetch_eightfold,
    "google": fetch_google,
    "apple": fetch_apple,
    "sitemap": fetch_sitemap,
    "rss": fetch_rss,
    "jsonld": fetch_jsonld,
    **ats.FETCHERS,
}

# Platforms whose fetch returns only part of the open postings. Jobs missing
# from a partial listing are not necessarily closed, so the pipeline skips
# closure tracking for them.
PARTIAL_LISTINGS = {"google"}

PLATFORMS = set(FETCHERS)

# Platforms whose servers answer conditional requests with 304 (checked for
# each in docs/crawler-research.md; Workday, Workable and Rippling don't)
CONDITIONAL = {"greenhouse", "lever", "ashby"} | ats.CONDITIONAL


def listing_is_complete(company: Company) -> bool:
    return company.platform not in PARTIAL_LISTINGS


# Platforms that need one extra request per posting for its description.
# They accept `known`: ids already stored with a description, which are not
# fetched again.
INCREMENTAL_DETAILS = {"workday", "eightfold", "apple", "jsonld"} | ats.PER_POSTING

# Where a listing already carries part of the text (Apple's summary), a stored
# description only counts as known once it is the full posting.
_IS_FULL: dict[str, Callable[[str], bool]] = {"apple": is_full_description}


def complete_descriptions(platform: str, stored: dict[str, tuple[str, str]]) -> frozenset[str]:
    """Ids of stored postings whose description needs no further request."""
    is_full = _IS_FULL.get(platform)
    return frozenset(
        key for key, (description, _) in stored.items() if is_full is None or is_full(description)
    )


def fetch_jobs(
    company: Company,
    details: bool = True,
    known: frozenset[str] = frozenset(),
    cached: Validators | None = None,
    stored: dict | None = None,
) -> JobList:
    """Fetch current postings for a company.

    Returns a JobList whose `complete` flag is False when the platform only
    ever returns part of the postings (Google) or when this particular fetch
    came back truncated (very large Workday employers). `details=False` skips
    slow per-job requests on platforms that need them (used by verify), and
    `known` lists postings whose description is already stored, so it is not
    fetched again. Jobs with no location get the company's configured `region`.

    On the public job-board APIs (CONDITIONAL), `cached` asks the server
    whether the board changed since it was last read: if not, the result is
    empty with `not_modified` set. `stored` (Greenhouse) holds the stored
    postings' versions, so unchanged postings aren't downloaded again.
    """
    fetcher = FETCHERS.get(company.platform)
    if fetcher is None:
        raise FetchError(f"unknown platform: {company.platform}")
    if company.platform in ats.PLATFORMS:
        if not ats.enabled(company.platform):
            raise FetchError(f"{company.platform} is switched off (add it to GHOSTLESS_SOURCES)")
        result = fetcher(company, details=details, known=known, cached=cached, stored=stored)
    elif company.platform == "jsonld":  # pages are read again when their sitemap entry changes
        result = fetcher(company, details=details, known=known, stored=stored)
    elif company.platform in INCREMENTAL_DETAILS:
        result = fetcher(company, details=details, known=known)
    elif company.platform in CONDITIONAL:
        result = fetcher(company, details=details, cached=cached, stored=stored)
    else:
        result = fetcher(company, details=details)
    jobs = JobList(
        result,
        complete=listing_is_complete(company) and getattr(result, "complete", True),
        total=getattr(result, "total", None),
        not_modified=getattr(result, "not_modified", False),
        validators=getattr(result, "validators", None),
        listed=getattr(result, "listed", None),
    )
    if company.region:
        for job in jobs:
            if not job.location:
                job.location = company.region
    return jobs


__all__ = [
    "FetchError",
    "complete_descriptions",
    "is_full_description",
    "parse_apple_detail",
    "fetch_jobs",
    "listing_is_complete",
    "PLATFORMS",
    "parse_greenhouse",
    "parse_lever",
    "parse_ashby",
    "parse_workday_slug",
    "parse_workday_age",
    "parse_workday_job",
    "fetch_workday",
    "parse_amazon",
    "parse_eightfold_slug",
    "parse_eightfold_position",
    "parse_google_listing",
    "parse_google_detail",
    "parse_apple_page",
    "parse_sitemap",
    "parse_rss",
]
