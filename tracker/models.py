from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class Company:
    name: str
    platform: str  # see tracker.sources for the full list
    board_slug: str
    region: str | None = None  # location used when a source publishes none
    domain: str | None = None  # company website, for its logo
    origin: str = "configured"  # configured | discovered | list (see schema.sql)


class JobList(list):
    """The jobs from one fetch, plus whether they are the source's complete
    listing. Closure tracking only runs on complete listings, because a job
    missing from a truncated listing has not necessarily closed.

    `not_modified` means the source answered 304: the board is exactly as
    stored, and the list is empty. `validators` (an http.Validators) are what
    to send next time to ask whether it changed.

    `listed` holds the ids of every posting the source listed, before the
    storage filter dropped the ones Ghostless doesn't keep (None: the jobs
    themselves are the whole listing). A stored posting that's still listed
    is still open, whether or not it would be stored today.

    `unchanged` holds the ids of listed postings left exactly as stored: they
    aren't in the list, are only marked seen, and their text is never read
    back from the database."""

    def __init__(
        self,
        jobs=(),
        complete: bool = True,
        total: int | None = None,
        not_modified: bool = False,
        validators=None,
        listed: frozenset[str] | None = None,
        unchanged: frozenset[str] = frozenset(),
    ):
        super().__init__(jobs)
        self.complete = complete
        self.total = total  # how many the source says exist, when it says
        self.not_modified = not_modified
        self.validators = validators
        self.listed = listed
        self.unchanged = unchanged

    def listed_ids(self) -> frozenset[str]:
        return self.listed if self.listed is not None else frozenset(job.external_id for job in self)

    def like(self, jobs) -> JobList:
        """Other jobs, with this fetch's flags."""
        return JobList(
            jobs, self.complete, self.total, self.not_modified, self.validators, self.listed, self.unchanged
        )

    @property
    def seen(self) -> int:
        """Postings in this fetch that are stored: saved again, or left as they were."""
        return len(self) + len(self.unchanged)


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
    terms: list[str] = field(default_factory=list)  # seasons, e.g. ["Summer 2027"]
    listed_in: str | None = None  # the public job list it came from, if any
    source_updated_at: datetime | None = None  # when the source last changed it (Greenhouse)

    # Filled in by enrich()
    level: str = "mid"
    role_type: str = "other"
    is_canada: bool = False
    is_remote: bool = False
    skills: list[str] = field(default_factory=list)

    # From the source's own fields (stage C1) or the text (C2); None means "not stated"
    seniority: str | None = None  # intern | new_grad | junior | mid | senior | staff
    workplace: str | None = None  # remote | hybrid | onsite
    employment_type: str | None = None  # full_time | part_time | contract | temporary | internship
    sponsorship: str | None = None  # available | not_available | unknown
    min_years_experience: float | None = None
    locations: list[dict] = field(default_factory=list)  # [{city, region, country}], in the order given
    countries: list[str] = field(default_factory=list)  # ISO codes, in the order given

    # Disclosures parsed from the description (None means "not stated")
    salary_min: float | None = None
    salary_max: float | None = None
    salary_period: str | None = None  # year | month | hour
    salary_currency: str | None = None  # CAD | USD
    vacancy: str | None = None  # existing | not_existing
    ai_screening: bool | None = None
    fingerprint: str = ""
