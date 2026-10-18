"""Public job lists on GitHub, read from their structured data.

SimplifyJobs' internship and new grad lists (and the many lists that use the
same format) keep every entry in `.github/scripts/listings.json`: company,
title, locations, link, season, dates and whether it's still open. That file
is read instead of the README table, so formatting changes can't break it.
raw.githubusercontent.com publishes no robots.txt, so reading it is allowed;
every request still goes through the polite HTTP layer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

from tracker.sources import http

RAW = "https://raw.githubusercontent.com/{repo}/{branch}/{path}"


@dataclass(frozen=True)
class JobList:
    """A list to read: a GitHub repository and the JSON file inside it."""

    repo: str  # owner/name
    branch: str = "dev"
    path: str = ".github/scripts/listings.json"
    label: str = ""  # shown on job pages: "SimplifyJobs internships"
    level: str | None = None  # every entry's level when the list is for one ("intern", "new_grad")

    @property
    def url(self) -> str:
        return RAW.format(repo=self.repo, branch=self.branch, path=self.path)

    @property
    def name(self) -> str:
        return self.label or self.repo


DEFAULT_LISTS = (
    JobList("SimplifyJobs/Summer2027-Internships", label="SimplifyJobs internships", level="intern"),
    JobList("SimplifyJobs/New-Grad-Positions", label="SimplifyJobs new grad roles", level="new_grad"),
)


@dataclass
class ListedJob:
    list_name: str
    id: str
    company: str
    title: str
    url: str
    locations: list[str]
    posted_at: datetime | None
    terms: list[str] = field(default_factory=list)
    category: str | None = None
    level: str | None = None  # from the list, when it's for one level


_SEASON = re.compile(r"^(Summer|Fall|Winter|Spring) \d{4}$")


def _when(value) -> datetime | None:
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc)
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def parse_simplify(data: list, list_name: str, level: str | None = None) -> list[ListedJob]:
    """Open, visible entries with a company, a title and a web link."""
    out: list[ListedJob] = []
    for item in data if isinstance(data, list) else []:
        if not isinstance(item, dict) or not item.get("active") or item.get("is_visible") is False:
            continue
        company = str(item.get("company_name") or "").strip()
        title = str(item.get("title") or "").strip()
        url = str(item.get("url") or "").strip()
        if not company or not title or not url.startswith(("https://", "http://")):
            continue
        out.append(
            ListedJob(
                list_name=list_name,
                id=str(item.get("id") or url),
                company=company,
                title=title,
                url=url,
                locations=[str(x).strip() for x in item.get("locations") or [] if str(x).strip()],
                posted_at=_when(item.get("date_posted")),
                terms=[t for t in item.get("terms") or [] if isinstance(t, str) and _SEASON.match(t)],
                category=item.get("category"),
                level=level,
            )
        )
    return out


def fetch_list(job_list: JobList) -> list[ListedJob]:
    # entries name the repo they came from, so job pages can link to it
    return parse_simplify(http.get_json(job_list.url), job_list.repo, job_list.level)
