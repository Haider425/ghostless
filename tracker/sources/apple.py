"""Apple: search result pages on jobs.apple.com.

Config slug: the search path, e.g. `en-ca/search?location=canada-CANC`.

Apple's pages are rendered by JavaScript from data embedded in the page, so
the parser tries, in order:

  1. embedded JSON (React Router hydration data or a Next.js data block),
     walking it for any object that looks like a job posting
  2. job links in the HTML (`/en-ca/details/<id>/<slug>`)
  3. job links inside escaped script text (`\\/en-ca\\/details\\/...`)

Using several strategies keeps the adapter working through small markup
changes. If all three find nothing, `verify` reports WARN; rerun it with
`--dump` and inspect the saved page.

Apple's job pages need JavaScript for the full description, so only the
short summary from the search data (when present) is stored.
"""

from __future__ import annotations

import html as html_lib
import json
import re
from collections.abc import Iterator
from typing import Any

from tracker.models import Company, Job
from tracker.sources import http
from tracker.sources.common import slug_to_title
from tracker.text import html_to_text

BASE = "https://jobs.apple.com"
MAX_PAGES = 100  # safety stop

_HYDRATION = re.compile(r"__staticRouterHydrationData\s*=\s*JSON\.parse\((\"(?:[^\"\\]|\\.)*\")\)", re.S)
_NEXT_DATA = re.compile(r'<script[^>]+id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)
_LINK = re.compile(
    r"""<a\b[^>]*href=["'](?:https://jobs\.apple\.com)?(/[a-z]{2}-[a-z]{2}/details/([\w-]+)/([\w-]+)[^"']*)["'][^>]*>(.*?)</a>""",
    re.I | re.S,
)
_ESCAPED_LINK = re.compile(r"\\?/([a-z]{2}-[a-z]{2})\\?/details\\?/([\w-]+)\\?/([\w-]+)", re.I)
_TEAM = re.compile(r"[?&]team=(\w+)")
_TOTAL = re.compile(r"([\d,]+)\s+Result\(s\)", re.I)


def _locale(search: str) -> str:
    match = re.match(r"([a-z]{2}-[a-z]{2})/", search)
    return match.group(1) if match else "en-us"


# ---------- strategy 1: embedded JSON ----------


def _embedded_json(page_html: str) -> Any | None:
    match = _HYDRATION.search(page_html)
    if match:
        try:
            return json.loads(json.loads(match.group(1)))  # JS string literal, then JSON
        except (ValueError, TypeError):
            pass
    match = _NEXT_DATA.search(page_html)
    if match:
        try:
            return json.loads(match.group(1))
        except ValueError:
            pass
    return None


def _walk(node: Any) -> Iterator[dict]:
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _walk(value)
    elif isinstance(node, list):
        for value in node:
            yield from _walk(value)


def _first(obj: dict, *keys: str) -> Any:
    for key in keys:
        if obj.get(key):
            return obj[key]
    return None


def _total_from(data: Any) -> int | None:
    for obj in _walk(data):
        value = _first(obj, "totalRecords", "totalResults", "total")
        if isinstance(value, int):
            return value
    return None


def jobs_from_embedded(data: Any, locale: str) -> list[Job]:
    jobs: dict[str, Job] = {}
    for obj in _walk(data):
        title = _first(obj, "postingTitle", "jobTitle")
        job_id = _first(obj, "positionId", "reqId", "jobId")
        if not (isinstance(title, str) and job_id):
            continue
        job_id = str(job_id)
        slug = _first(obj, "transformedPostingTitle", "slug") or re.sub(
            r"[^a-z0-9]+", "-", title.lower()
        ).strip("-")
        team = obj.get("team") if isinstance(obj.get("team"), dict) else {}
        team_code = _first(team, "teamCode", "code")
        locations = obj.get("locations") if isinstance(obj.get("locations"), list) else []
        location_names = [
            str(_first(loc, "name", "city", "countryName"))
            for loc in locations
            if isinstance(loc, dict) and _first(loc, "name", "city", "countryName")
        ]
        url = f"{BASE}/{locale}/details/{job_id}/{slug}" + (f"?team={team_code}" if team_code else "")
        jobs.setdefault(
            job_id,
            Job(
                external_id=job_id,
                title=title.strip(),
                url=url,
                location=" | ".join(location_names),
                department=_first(team, "teamName", "name") or team_code,
                description=html_to_text(_first(obj, "jobSummary", "summary") or ""),
                source_remote=bool(obj.get("homeOffice")),
            ),
        )
    return list(jobs.values())


# ---------- strategies 2 and 3: links ----------


def jobs_from_links(page_html: str, locale: str) -> list[Job]:
    jobs: dict[str, Job] = {}
    for href, job_id, slug, inner in _LINK.findall(page_html):
        if job_id in jobs:
            continue
        team = _TEAM.search(html_lib.unescape(href))
        jobs[job_id] = Job(
            external_id=job_id,
            title=html_to_text(inner) or slug_to_title(slug),
            url=BASE + html_lib.unescape(href),
            department=team.group(1) if team else None,
        )
    if jobs:
        return list(jobs.values())
    for link_locale, job_id, slug in _ESCAPED_LINK.findall(page_html):
        jobs.setdefault(
            job_id,
            Job(
                external_id=job_id,
                title=slug_to_title(slug),
                url=f"{BASE}/{link_locale}/details/{job_id}/{slug}",
            ),
        )
    return list(jobs.values())


def parse_apple_page(page_html: str, locale: str = "en-us") -> tuple[list[Job], int | None]:
    """Return (jobs on this page, total result count if known)."""
    data = _embedded_json(page_html)
    if data is not None:
        jobs = jobs_from_embedded(data, locale)
        if jobs:
            return jobs, _total_from(data)
    jobs = jobs_from_links(page_html, locale)
    total = _TOTAL.search(html_to_text(page_html))
    return jobs, int(total.group(1).replace(",", "")) if total else None


def fetch_apple(company: Company, details: bool = True) -> list[Job]:
    search = company.board_slug.strip("/")
    locale = _locale(search)
    sep = "&" if "?" in search else "?"
    jobs: dict[str, Job] = {}
    for page_number in range(1, MAX_PAGES + 1):
        page_jobs, total = parse_apple_page(http.get_text(f"{BASE}/{search}{sep}page={page_number}"), locale)
        new = [j for j in page_jobs if j.external_id not in jobs]
        for job in new:
            jobs[job.external_id] = job
        if not new or (total is not None and len(jobs) >= total):
            break
    return list(jobs.values())
