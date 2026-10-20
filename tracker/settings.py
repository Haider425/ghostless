"""Switches and limits for the parts of the crawler that grow it beyond
companies.yaml and the job lists. Each new source or discovery step is off
until its setting is turned on, so upgrading the code changes nothing by itself.

Set them as environment variables (in .env locally, or as repository
variables in the GitHub workflow):

    GHOSTLESS_SNOWBALL=1         register job boards linked from postings, and verify them
    GHOSTLESS_JSONLD=1           find and read company career sites that publish JSON-LD
    GHOSTLESS_INDEX_SEEDING=1    monthly: find job boards in Common Crawl's URL index (discover.yml,
                                 needs the optional `index` extra) and check them like the above

Limits, with their defaults (only used when the switch above is on):

    GHOSTLESS_VERIFY_PER_RUN=100         candidate boards and sites checked per run, one request each
    GHOSTLESS_JSONLD_PAGES_PER_SITE=25   job pages read per career site per run
    GHOSTLESS_JSONLD_SITEMAPS=3          sitemap files read per career site per run
    GHOSTLESS_JSONLD_URLS=2000           job links considered per career site
"""

from __future__ import annotations

import os


def _on(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


def _number(name: str, default: int, low: int = 0, high: int = 100_000) -> int:
    try:
        return max(low, min(high, int(os.environ.get(name, default))))
    except ValueError:
        return default


def snowball() -> bool:
    return _on("GHOSTLESS_SNOWBALL")


def jsonld() -> bool:
    return _on("GHOSTLESS_JSONLD")


def index_seeding() -> bool:
    return _on("GHOSTLESS_INDEX_SEEDING")


def verify_per_run() -> int:
    return _number("GHOSTLESS_VERIFY_PER_RUN", 100, high=1000)


def jsonld_pages_per_site() -> int:
    return _number("GHOSTLESS_JSONLD_PAGES_PER_SITE", 25, high=500)


def jsonld_sitemaps() -> int:
    return _number("GHOSTLESS_JSONLD_SITEMAPS", 3, low=1, high=20)


def jsonld_urls() -> int:
    return _number("GHOSTLESS_JSONLD_URLS", 2000, low=1, high=20_000)
