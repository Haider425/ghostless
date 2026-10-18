"""Greenhouse, Lever and Ashby: public job board APIs, one GET per company."""

from __future__ import annotations

from datetime import datetime, timezone

from tracker.models import Company, Job
from tracker.sources import http
from tracker.sources.common import parse_iso
from tracker.text import html_to_text

URLS = {
    "greenhouse": "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true",
    "lever": "https://api.lever.co/v0/postings/{slug}?mode=json",
    "ashby": "https://api.ashbyhq.com/posting-api/job-board/{slug}",
}


def parse_greenhouse(data: dict) -> list[Job]:
    jobs = []
    for item in data.get("jobs", []):
        departments = item.get("departments") or []
        jobs.append(
            Job(
                external_id=str(item["id"]),
                title=item.get("title", "").strip(),
                url=item.get("absolute_url", ""),
                location=(item.get("location") or {}).get("name", "") or "",
                department=departments[0]["name"] if departments else None,
                description=html_to_text(item.get("content")),
                posted_at=parse_iso(item.get("first_published") or item.get("updated_at")),
            )
        )
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


PARSERS = {"greenhouse": parse_greenhouse, "lever": parse_lever, "ashby": parse_ashby}


def fetch_board(company: Company, details: bool = True) -> list[Job]:
    data = http.get_json(URLS[company.platform].format(slug=company.board_slug))
    return PARSERS[company.platform](data)
