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

Search results carry only a short summary. Each posting's own page embeds
the full posting in the same hydration data (description, minimum and
preferred qualifications, and the "Pay & Benefits" footer with the pay
range), so that page is fetched once per posting, most relevant first and a
batch per run, like Workday (common.plan_details). Postings whose full text is
already stored are not fetched again.
"""

from __future__ import annotations

import html as html_lib
import json
import logging
import re
from collections.abc import Iterator
from typing import Any

from tracker.models import Company, Job
from tracker.sources import http
from tracker.sources.common import parse_iso, plan_details, slug_to_title
from tracker.sources.http import FetchError
from tracker.text import BULLET, html_to_text

log = logging.getLogger(__name__)

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


def _location_name(loc: dict) -> str:
    """'Place Ste-Foy, Canada' rather than a bare store name, so country
    detection works; country-level entries are just 'Canada'."""
    name = _first(loc, "name", "city") or ""
    country = loc.get("countryName") or ""
    if name and country and country.lower() not in name.lower():
        return f"{name}, {country}"
    return str(name or country)


def jobs_from_embedded(data: Any, locale: str) -> list[Job]:
    jobs: dict[str, Job] = {}
    for obj in _walk(data):
        title = _first(obj, "postingTitle", "jobTitle")
        # `id` is unique per posting location ("200607536-3250"); `positionId` is
        # shared by the same role at several stores, so it would merge postings.
        job_id = _first(obj, "id", "reqId", "positionId", "jobId")
        if not (isinstance(title, str) and job_id):
            continue
        job_id = str(job_id)
        slug = _first(obj, "transformedPostingTitle", "slug") or re.sub(
            r"[^a-z0-9]+", "-", title.lower()
        ).strip("-")
        team = obj.get("team") if isinstance(obj.get("team"), dict) else {}
        team_code = _first(team, "teamCode", "code")
        locations = obj.get("locations") if isinstance(obj.get("locations"), list) else []
        location_names = [_location_name(loc) for loc in locations if isinstance(loc, dict)]
        url_id = re.sub(r"^PIPE-", "", job_id)
        url = f"{BASE}/{locale}/details/{url_id}/{slug}" + (f"?team={team_code}" if team_code else "")
        jobs.setdefault(
            job_id,
            Job(
                external_id=job_id,
                title=title.strip(),
                url=url,
                location=" | ".join(n for n in location_names if n),
                department=_first(team, "teamName", "name") or team_code,
                description=html_to_text(_first(obj, "jobSummary", "summary") or ""),
                posted_at=parse_iso(obj.get("postDateInGMT")),
                source_remote=bool(obj.get("homeOffice")),
                # Apple's own flag for evergreen pipeline postings, which are
                # not a specific open position. Their posting date is
                # refreshed constantly, so first-seen dates matter here.
                vacancy="not_existing" if obj.get("managedPipelineRole") is True else None,
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


# ---------- the posting's own page ----------

# Full descriptions are built with these headings; a summary from the search
# results never contains them, which is how a stored full text is recognised.
FULL_HEADINGS = ("\n\nDescription\n", "\n\nMinimum Qualifications\n")


def is_full_description(text: str | None) -> bool:
    return bool(text) and any(heading in text for heading in FULL_HEADINGS)


def _lines_as_bullets(raw: str) -> str:
    lines = [line.strip(" •-\t") for line in html_to_text(raw.replace("\n", "<br>")).split("\n")]
    return "\n".join(BULLET + line for line in lines if line)


def parse_apple_detail(page_html: str) -> str:
    """The full posting from a job page: summary, description, qualifications
    and the footer sections (pay and benefits), as structured plain text.
    Empty when the page has no posting data."""
    data = _embedded_json(page_html)
    posting = next(
        (obj for obj in _walk(data) if "postingTitle" in obj and "minimumQualifications" in obj), None
    )
    if posting is None:
        return ""
    parts = []
    if posting.get("jobSummary"):
        parts.append(html_to_text(posting["jobSummary"]))
    if posting.get("description"):
        parts.append("Description\n" + html_to_text(posting["description"].replace("\n", "<br>")))
    for key, heading in (
        ("minimumQualifications", "Minimum Qualifications"),
        ("preferredQualifications", "Preferred Qualifications"),
    ):
        if posting.get(key):
            parts.append(f"{heading}\n{_lines_as_bullets(posting[key])}")
    for footer in posting.get("postingFooters") or []:
        localizations = (footer.get("localizations") or {}) if isinstance(footer, dict) else {}
        # one language is enough: prefer English, else whatever the page has
        sections = localizations.get("en_US") or next(iter(localizations.values()), [])
        for section in sorted(sections, key=lambda s: s.get("displayOrder") or 0):
            body = html_to_text(section.get("content") or "")
            if body:
                parts.append(f"{section.get('name')}\n{body}" if section.get("name") else body)
    text = "\n\n".join(p.strip() for p in parts if p.strip())
    # the summary alone is what the search results already gave
    return text if is_full_description(text) else ""


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


def fetch_apple(
    company: Company,
    details: bool = True,
    known: frozenset[str] = frozenset(),
    max_details: int | None = None,
) -> list[Job]:
    """Every posting in the search, with full descriptions for those not yet
    stored in full (`known`). A posting in `known` comes back with no
    description, so ingest keeps its stored full text instead of the summary."""
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

    for job_id in known & jobs.keys():
        jobs[job_id].description = ""  # reuse the stored full text
    if details:
        wanted = plan_details(
            [(j.external_id, j.title, j.location) for j in jobs.values()], known, max_details
        )
        for job_id in wanted:
            job = jobs[job_id]
            try:
                full = parse_apple_detail(http.get_text(job.url))
            except FetchError as exc:  # keep the summary; the page is tried again next run
                log.warning("%s: detail fetch failed for %s: %s", company.name, job_id, exc)
                continue
            if full:
                job.description = full
    return list(jobs.values())
