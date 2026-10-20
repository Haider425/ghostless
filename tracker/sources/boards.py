"""Greenhouse, Lever and Ashby: public job board APIs.

Each board is one conditional GET: these APIs answer 304 Not Modified when
nothing changed since the last read, and the board is then left as stored.

Greenhouse is read in two steps. Its listing without descriptions is about
2% of the size with them, and says when each posting last changed. Only new
and changed postings are then downloaded, one request each; the rest keep
their stored description. When many changed (a first read, or a big update),
one request for the whole board with descriptions is cheaper, and it's also
the fallback if any single request fails, so every posting always ends up
with its full description.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from tracker.classify import title_worth_storing
from tracker.models import Company, Job, JobList
from tracker.sources import http
from tracker.sources.common import parse_iso
from tracker.sources.http import FetchError, Validators
from tracker.text import html_to_text

log = logging.getLogger(__name__)

URLS = {
    "greenhouse": "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs",
    "lever": "https://api.lever.co/v0/postings/{slug}?mode=json",
    "ashby": "https://api.ashbyhq.com/posting-api/job-board/{slug}",
}
GREENHOUSE_FULL = "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"
GREENHOUSE_JOB = "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs/{id}?pay_transparency=true"
# More new or changed postings than this: one request for the whole board instead
GREENHOUSE_MAX_DETAILS = 10

# {external_id: (source_updated_at, description, department)}, from db.stored_versions
Stored = dict[str, tuple[datetime, str, "str | None"]]


def board_url(company: Company) -> str:
    return URLS[company.platform].format(slug=company.board_slug)


def _greenhouse_job(item: dict, description: str | None = None, department: str | None = None) -> Job:
    departments = item.get("departments") or []
    return Job(
        external_id=str(item["id"]),
        title=item.get("title", "").strip(),
        url=item.get("absolute_url", ""),
        location=(item.get("location") or {}).get("name", "") or "",
        department=departments[0]["name"] if departments else department,
        description=html_to_text(item.get("content")) if description is None else description,
        posted_at=parse_iso(item.get("first_published") or item.get("updated_at")),
        source_updated_at=parse_iso(item.get("updated_at")),
    )


def parse_greenhouse(data: dict) -> list[Job]:
    return [_greenhouse_job(item) for item in data.get("jobs", [])]


def plan_greenhouse(items: list[dict], stored: Stored) -> list[str]:
    """Ids of listed postings that are new or changed since they were stored,
    leaving out the ones Ghostless won't store (their text isn't needed)."""
    todo = []
    for item in items:
        key = str(item["id"])
        if not title_worth_storing(item.get("title", "")):
            continue
        known = stored.get(key)
        if known is None or parse_iso(item.get("updated_at")) != known[0]:
            todo.append(key)
    return todo


def fetch_greenhouse(
    company: Company, cached: Validators | None = None, stored: Stored | None = None
) -> JobList:
    slug = company.board_slug
    data, validators = http.get_json_if_changed(URLS["greenhouse"].format(slug=slug), cached)
    if data is http.NOT_MODIFIED:
        return JobList(not_modified=True, validators=validators)
    items = data.get("jobs", [])
    stored = stored or {}
    todo = plan_greenhouse(items, stored)
    if len(todo) > GREENHOUSE_MAX_DETAILS:
        return JobList(
            parse_greenhouse(http.get_json(GREENHOUSE_FULL.format(slug=slug))), validators=validators
        )
    details: dict[str, dict] = {}
    try:
        for key in todo:
            details[key] = http.get_json(GREENHOUSE_JOB.format(slug=slug, id=key))
    except FetchError as exc:
        log.warning("%s: a posting couldn't be read (%s); reading the whole board instead", company.name, exc)
        return JobList(
            parse_greenhouse(http.get_json(GREENHOUSE_FULL.format(slug=slug))), validators=validators
        )
    jobs = JobList(validators=validators)
    for item in items:
        key = str(item["id"])
        if key in details:
            jobs.append(_greenhouse_job({**item, **details[key]}))
        elif key in stored:
            _, description, department = stored[key]
            jobs.append(_greenhouse_job(item, description, department))
        else:  # not stored and won't be: listed, so nothing it matches is taken for closed
            jobs.append(_greenhouse_job(item, ""))
    return jobs


def parse_lever(data: list) -> list[Job]:
    jobs = []
    for item in data:
        categories = item.get("categories") or {}
        sections = [html_to_text(item.get("description")) or (item.get("descriptionPlain") or "").strip()]
        for section in item.get("lists") or []:
            heading = (section.get("text") or "").strip()
            body = html_to_text("<ul>" + (section.get("content") or "") + "</ul>")
            sections.append(f"{heading}\n{body}".strip())
        sections.append(html_to_text(item.get("additional")) or (item.get("additionalPlain") or "").strip())
        created_ms = item.get("createdAt")
        jobs.append(
            Job(
                external_id=str(item["id"]),
                title=item.get("text", "").strip(),
                url=item.get("hostedUrl", ""),
                location=categories.get("location", "") or "",
                department=categories.get("team"),
                description="\n\n".join(part for part in sections if part),
                posted_at=(
                    datetime.fromtimestamp(created_ms / 1000, tz=timezone.utc) if created_ms else None
                ),
                source_remote=(item.get("workplaceType") == "remote"),
            )
        )
    return jobs


def parse_ashby(data: dict) -> list[Job]:
    jobs = []
    for item in data.get("jobs", []):
        if item.get("isListed") is False:
            continue
        jobs.append(
            Job(
                external_id=str(item["id"]),
                title=item.get("title", "").strip(),
                url=item.get("jobUrl", ""),
                location=item.get("location", "") or "",
                department=item.get("department"),
                description=html_to_text(item.get("descriptionHtml"))
                or (item.get("descriptionPlain") or "").strip(),
                posted_at=parse_iso(item.get("publishedAt")),
                source_remote=bool(item.get("isRemote")),
            )
        )
    return jobs


PARSERS = {"lever": parse_lever, "ashby": parse_ashby}


def fetch_board(
    company: Company, details: bool = True, cached: Validators | None = None, stored: Stored | None = None
) -> JobList:
    """A board's postings, or an empty list with `not_modified` when the
    server says it hasn't changed since `cached` was stored."""
    if company.platform == "greenhouse":
        return fetch_greenhouse(company, cached, stored)
    data, validators = http.get_json_if_changed(board_url(company), cached)
    if data is http.NOT_MODIFIED:
        return JobList(not_modified=True, validators=validators)
    return JobList(PARSERS[company.platform](data), validators=validators)
