"""Response models. They define the API contract and the /docs page."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

Level = Literal["intern", "new_grad", "mid", "senior"]
RoleType = Literal["sde", "data_eng", "data", "ml", "hardware", "security", "other"]
GhostRisk = Literal["low", "medium", "high"]


class Salary(BaseModel):
    min: float
    max: float
    period: Literal["year", "month", "hour"] = Field(description="what the amounts are paid per")
    currency: str | None = Field(
        None,
        description="ISO 4217 code: CAD, USD, GBP, EUR, INR, PLN, SGD, ...; when the posting doesn't name "
        "one, its country's currency; null only when neither is known (then it's dollars)",
    )


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
    company_slug: str = Field(description="for /companies/{slug}")
    company_domain: str | None = Field(None, description="the company's website, for its logo")
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
    terms: list[str] = Field(default_factory=list, description='seasons, e.g. "Summer 2027"')
    listed_in: str | None = Field(None, description="the public job list this posting came from, if any")
    signals: GhostSignals


class RepostEntry(BaseModel):
    id: int
    url: str
    first_seen: datetime
    closed_at: datetime | None
    is_active: bool


class Evidence(BaseModel):
    """The sentence in the posting each disclosure was read from, so readers
    can check it themselves."""

    vacancy: str | None = None
    salary: str | None = None
    ai_screening: str | None = None


class JobDetail(JobSummary):
    department: str | None
    evidence: Evidence
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
    slug: str
    domain: str | None
    platform: str
    origin: Literal["configured", "discovered", "list"] = Field(
        "configured",
        description="configured: tracked by name; discovered: board found through a job list; list: only known from the lists",
    )
    active_jobs: int
    tech_active_jobs: int = Field(description="software, data engineering and data roles")
    high_risk_jobs: int
    new_last_7_days: int
    typical_days_open: int | None = Field(
        None, description="median days from first seen to closed, once 5+ postings have closed"
    )


class CompanyPage(BaseModel):
    """One page of employers, with the totals the Companies page shows."""

    total: int = Field(description="employers matching the search and source")
    page: int = Field(description="the page returned (an out-of-range page gives the last one)")
    per_page: int
    employers: int = Field(description="every employer with postings")
    from_lists: int = Field(description="employers only known from the job lists")
    total_open: int = Field(description="open tech roles across every employer")
    items: list[Company]


class CompanyName(BaseModel):
    name: str
    slug: str
    domain: str | None
    tech_active_jobs: int


class TermCount(BaseModel):
    term: str
    jobs: int


class Count(BaseModel):
    key: str
    count: int


class WeekCount(BaseModel):
    week_start: date = Field(description="Monday, Toronto time")
    new: int = Field(description="postings first seen that week (after tracking began)")
    closed: int


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
    tech_active_jobs: int
    tech_new_last_7_days: int
    tech_high_risk_active_jobs: int
    tech_with_salary_active_jobs: int
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


class CompanyDetail(Company):
    tracking_since: datetime
    closed_last_30_days: int
    with_salary_active_jobs: int
    roles: list[Count] = Field(description="active postings by role type")
    levels: list[Count] = Field(description="active tech postings by level")
    weekly: list[WeekCount] = Field(description="tech postings, oldest week first")
    top_skills: list[SkillCount]


# ---------- accounts ----------

Theme = Literal["system", "light", "dark"]
TextSize = Literal["sm", "md", "lg", "xl"]
Density = Literal["comfortable", "compact"]
LocationPref = Literal["any", "canada", "remote", "canada_or_remote"]


class Settings(BaseModel):
    """Display and search preferences. Unknown keys are dropped."""

    theme: Theme = "system"
    text_size: TextSize = "md"
    density: Density = "comfortable"
    reduce_motion: bool = False
    underline_links: bool = False
    default_location: LocationPref = "any"
    hide_high_risk: bool = False
    analytics: bool = Field(True, description="share anonymous usage stats")


OAuthProvider = Literal["google", "github"]


class User(BaseModel):
    id: int
    email: str
    name: str | None
    role: Literal["user", "admin"]
    email_verified: bool
    settings: Settings
    created_at: datetime
    has_password: bool = Field(
        True, description="false for accounts made with Google or GitHub, until a password is set"
    )
    sign_in_providers: list[OAuthProvider] = Field(
        default_factory=list, description="linked Google or GitHub sign-ins"
    )


class Providers(BaseModel):
    google: bool
    github: bool


class AuthorizeOut(BaseModel):
    url: str


class OAuthIn(BaseModel):
    code: str = Field(min_length=1, max_length=2000)
    redirect_uri: str = Field(min_length=1, max_length=500)
    code_verifier: str = Field(min_length=43, max_length=128)


class Session(BaseModel):
    token: str = Field(description="send as `Authorization: Bearer <token>`")
    user: User


class SignupIn(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=256)
    name: str | None = Field(None, max_length=80)


class LoginIn(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=256)


class EmailIn(BaseModel):
    email: str = Field(min_length=3, max_length=254)


class TokenIn(BaseModel):
    token: str = Field(min_length=10, max_length=200)


class ResetIn(TokenIn):
    password: str = Field(min_length=1, max_length=256)


class ProfileIn(BaseModel):
    name: str | None = Field(None, max_length=80)


class PasswordChangeIn(BaseModel):
    current_password: str = Field(
        "", max_length=256, description="leave empty when the account has no password yet"
    )
    new_password: str = Field(min_length=1, max_length=256)


class PasswordIn(BaseModel):
    password: str = Field("", max_length=256, description="leave empty when the account has no password")


class SavedJobsIn(BaseModel):
    job_ids: list[int] = Field(max_length=500)


ApplicationStatus = Literal["saved", "applied", "interviewing", "offer", "rejected"]


class SavedUpdateIn(BaseModel):
    status: ApplicationStatus | None = None
    notes: str | None = Field(None, max_length=2000, description="private notes; empty string clears them")
    applied_at: datetime | None = Field(
        None,
        description="when you applied; null clears it, leaving it out keeps it. Moving to applied sets it to now",
    )


class SavedJob(BaseModel):
    job: JobSummary
    status: ApplicationStatus
    notes: str | None
    saved_at: datetime
    updated_at: datetime
    applied_at: datetime | None = Field(None, description="when you said you applied; null when not recorded")


class ApplicationIn(BaseModel):
    source: Literal["apply_prompt", "tracker"] = Field(
        "apply_prompt", description="apply_prompt: answered on returning from the employer's site"
    )


class Application(BaseModel):
    job_id: int
    status: ApplicationStatus
    applied_at: datetime | None
    changed: bool = Field(description="false when it was already recorded (or further along)")


class Message(BaseModel):
    detail: str
