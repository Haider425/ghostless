"""Response models. They define the API contract and the /docs page."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

Level = Literal["intern", "new_grad", "mid", "senior"]
RoleType = Literal["sde", "data_eng", "data", "other"]
GhostRisk = Literal["low", "medium", "high"]


class Salary(BaseModel):
    min: float
    max: float
    period: Literal["year", "hour"]
    currency: str | None = Field(None, description="CAD or USD; null when the posting does not say")


class GhostSignals(BaseModel):
    risk: GhostRisk | None = Field(None, description="null until the next ingest run computes it")
    flags: list[str] = Field(
        default_factory=list,
        description="not_existing_vacancy, reposted, duplicate_posting, open_unusually_long",
    )
    days_open: int
    age_known: bool | None = Field(
        None, description="false when the job was open before tracking began, so days_open is a minimum"
    )
    typical_days_open: int | None = Field(None, description="median for this company and role type")
    times_posted_before: int = 0


class JobSummary(BaseModel):
    id: int
    company: str
    title: str
    location: str | None
    url: str
    level: Level
    role_type: RoleType
    is_canada: bool
    is_remote: bool
    first_seen: datetime = Field(description="when Ghostless first saw the posting: its true age")
    closed_at: datetime | None
    is_active: bool
    salary: Salary | None
    vacancy: Literal["existing", "not_existing"] | None = Field(
        None, description="Ontario disclosure; null when not stated"
    )
    ai_screening: bool | None = Field(None, description="Ontario disclosure; null when not stated")
    skills: list[str]
    signals: GhostSignals


class RepostEntry(BaseModel):
    id: int
    url: str
    first_seen: datetime
    closed_at: datetime | None
    is_active: bool


class JobDetail(JobSummary):
    department: str | None
    description: str | None
    source_posted_at: datetime | None = Field(
        None, description="the date the source displays, which reposts refresh"
    )
    last_seen: datetime
    posting_history: list[RepostEntry] = Field(
        description="other postings of the same role at the same company, oldest first"
    )


class JobPage(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[JobSummary]


class Company(BaseModel):
    name: str
    platform: str
    active_jobs: int
    high_risk_jobs: int
    new_last_7_days: int


class LastRun(BaseModel):
    started_at: datetime
    finished_at: datetime | None
    companies_ok: int
    companies_failed: int
    jobs_seen: int
    jobs_new: int
    jobs_closed: int
    duration_seconds: float | None


class Stats(BaseModel):
    active_jobs: int
    companies: int
    new_last_7_days: int
    canada_active_jobs: int
    high_risk_active_jobs: int
    with_salary_active_jobs: int
    signals_computed_at: datetime | None
    last_run: LastRun | None


class SkillCount(BaseModel):
    skill: str
    postings: int
    share: float = Field(description="0 to 1, among matching postings with extracted skills")


class GapSkill(SkillCount):
    have: bool


class GapReport(BaseModel):
    total_postings: int
    recognized: list[str]
    unrecognized: list[str]
    missing_top_10: list[str]
    skills: list[GapSkill]


class CalendarEntry(BaseModel):
    company: str
    level: Level
    role_type: RoleType
    year: int
    first_opened: date
    last_opened: date
    postings: int