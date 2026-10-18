from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class Company:
    name: str
    platform: str  # see tracker.sources for the full list
    board_slug: str
    region: str | None = None  # location used when a source publishes none


class JobList(list):
    """The jobs from one fetch, plus whether they are the source's complete
    listing. Closure tracking only runs on complete listings, because a job
    missing from a truncated listing has not necessarily closed."""

    def __init__(self, jobs=(), complete: bool = True, total: int | None = None):
        super().__init__(jobs)
        self.complete = complete
        self.total = total  # how many the source says exist, when it says


@dataclass
class Job:
    """A posting normalized from any source platform."""

    external_id: str
    title: str
    url: str
    location: str = ""
    department: str | None = None
    description: str = ""
    posted_at: datetime | None = None
    source_remote: bool = False  # remote flag reported by the platform itself

    # Filled in by enrich()
    level: str = "mid"
    role_type: str = "other"
    is_canada: bool = False
    is_remote: bool = False
    skills: list[str] = field(default_factory=list)

    # Disclosures parsed from the description (None means "not stated")
    salary_min: float | None = None
    salary_max: float | None = None
    salary_period: str | None = None  # year | hour
    salary_currency: str | None = None  # CAD | USD
    vacancy: str | None = None  # existing | not_existing
    ai_screening: bool | None = None
    fingerprint: str = ""