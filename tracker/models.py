from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class Company:
    name: str
    platform: str  # see tracker.sources for the full list
    board_slug: str
    region: str | None = None  # location used when a source publishes none


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
