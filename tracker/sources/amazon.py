"""Amazon: the public JSON search API behind amazon.jobs.

Config slug: the search filters, e.g. `normalized_country_code[]=CAN`.
Several searches can be joined with `|`; results are de-duplicated.
"""

from __future__ import annotations

from datetime import datetime, timezone

from tracker.models import Company, Job
from tracker.sources import http
from tracker.sources.common import split_queries
from tracker.text import html_to_text

BASE = "https://www.amazon.jobs"
PAGE_SIZE = 100
MAX_OFFSET = 10_000  # the API stops serving results past this point


def parse_amazon_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(value.strip(), "%B %d, %Y").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def parse_amazon(data: dict) -> list[Job]:
    jobs = []
    for item in data.get("jobs") or []:
        description = " ".join(
            html_to_text(item.get(key))
            for key in ("description", "basic_qualifications", "preferred_qualifications")
            if item.get(key)
        )
        jobs.append(
            Job(
                external_id=str(item.get("id_icims") or item["id"]),
                title=(item.get("title") or "").strip(),
                url=BASE + item["job_path"] if item.get("job_path") else BASE,
                location=item.get("normalized_location") or item.get("location") or "",
                department=item.get("job_category"),
                description=description,
                posted_at=parse_amazon_date(item.get("posted_date")),
            )
        )
    return jobs


def fetch_amazon(company: Company, details: bool = True) -> list[Job]:
    seen: dict[str, Job] = {}
    for query in split_queries(company.board_slug):
        offset = 0
        while offset < MAX_OFFSET:
            data = http.get_json(
                f"{BASE}/en/search.json?{query}&result_limit={PAGE_SIZE}&offset={offset}&sort=recent"
            )
            page = parse_amazon(data)
            for job in page:
                seen.setdefault(job.external_id, job)
            offset += PAGE_SIZE
            if not page or offset >= int(data.get("hits") or 0):
                break
    return list(seen.values())
