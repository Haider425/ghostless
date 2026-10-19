"""Google Careers: server-rendered HTML, no public JSON API.

Google's robots.txt disallows crawling paginated result pages (`page=`), so
this adapter only reads the FIRST page (about 20 jobs) of each configured
search. Use narrow searches to cover what you care about, joined with `|`:

  location=Canada&q=software|location=Canada&q=data engineer|location=Canada&q=intern

Because the listing is partial, the pipeline never marks Google jobs closed
just because they are missing from a run (see sources.LISTING_IS_COMPLETE).

HTML parsing is the most fragile adapter here: if Google changes its markup,
`python -m tracker.verify` will report 0 jobs, which is the signal to update
the patterns below.
"""

from __future__ import annotations

import html as html_lib
import logging
import re
from urllib.parse import quote

from tracker.models import Company, Job
from tracker.sources import http
from tracker.sources.common import detail_priority, slug_to_title, split_queries
from tracker.sources.http import FetchError
from tracker.text import html_to_text

log = logging.getLogger(__name__)

BASE = "https://www.google.com/about/careers/applications/jobs/results/"
_JOB_LINK = re.compile(r"jobs/results/(\d{6,})-([a-z0-9-]+)")
_TITLE_TAG = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
_SECTION_START = re.compile(r"minimum qualifications", re.I)
# the posting ends where Google's privacy notice and page furniture begin
_SECTION_END = re.compile(r"Information collected and processed as part of your Google Careers profile", re.I)
MAX_DESCRIPTION_CHARS = 20_000  # only for a page without that notice: never cut a real posting short


def _encode_query(query: str) -> str:
    """Encode spaces in values while keeping the &/= structure."""
    return "&".join(
        "=".join(quote(part, safe="+") for part in pair.split("=", 1)) for pair in query.split("&")
    )


def parse_google_listing(page_html: str) -> list[tuple[str, str]]:
    """Return unique (job_id, slug) pairs in page order."""
    seen: dict[str, str] = {}
    for job_id, slug in _JOB_LINK.findall(page_html):
        seen.setdefault(job_id, slug)
    return list(seen.items())


def parse_google_detail(page_html: str) -> tuple[str | None, str]:
    """Return (title, description) from a job page."""
    title = None
    match = _TITLE_TAG.search(page_html)
    if match:
        raw = html_lib.unescape(match.group(1)).strip()
        title = re.split(r"\s+[—|–-]\s+Google", raw)[0].strip() or None
    text = html_to_text(page_html)
    start = _SECTION_START.search(text)
    if not start:
        return title, ""
    end = _SECTION_END.search(text, start.end())
    description = text[start.start() : end.start() if end else start.start() + MAX_DESCRIPTION_CHARS]
    return title, description.strip()


def fetch_google(company: Company, details: bool = True) -> list[Job]:
    jobs: dict[str, Job] = {}
    for query in split_queries(company.board_slug):
        listing = parse_google_listing(http.get_text(f"{BASE}?{_encode_query(query)}"))
        for job_id, slug in listing:
            if job_id in jobs:
                continue
            job = Job(
                external_id=job_id,
                title=slug_to_title(slug),
                url=f"{BASE}{job_id}-{slug}",
            )
            if details and detail_priority(job.title) < 2:  # tech roles; first page only, so small
                try:
                    title, description = parse_google_detail(http.get_text(job.url))
                    job.title = title or job.title
                    job.description = description
                except FetchError as exc:
                    log.warning("%s: detail fetch failed for %s: %s", company.name, job_id, exc)
            jobs[job_id] = job
    return list(jobs.values())
