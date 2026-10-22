from __future__ import annotations

import os
import re
from datetime import datetime

from tracker import currency as currencies
from tracker.classify import classify_role, is_canada, is_remote, title_worth_storing

_MULTI_LOCATION = re.compile(r"\b\d+\s+locations?\b", re.I)


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def slug_to_title(slug: str) -> str:
    """'software-developer-ii-cloud' -> 'Software Developer II Cloud'."""
    words = [w for w in re.split(r"[-_]+", slug) if w]
    roman = {"i", "ii", "iii", "iv", "v"}
    return " ".join(w.upper() if w.lower() in roman else w.capitalize() for w in words)


MAX_DETAILS_PER_RUN = int(os.environ.get("GHOSTLESS_MAX_DETAILS", "250"))


def detail_priority(title: str, location: str = "") -> int:
    """Order for fetching full descriptions: 0 tech roles in Canada, remote or
    an unknown or multi-city location, 1 other tech roles, 2 everything else."""
    if classify_role(title) == "other":
        return 2
    nearby = (
        not location or is_canada(location) or is_remote(location) or bool(_MULTI_LOCATION.search(location))
    )
    return 0 if nearby else 1


def plan_details(
    items: list[tuple[str, str, str]], known: frozenset[str], limit: int | None = None
) -> set[str]:
    """Which postings get an extra request for their full description.

    `items` are (id, title, location). Postings already stored with a
    description (`known`) are skipped, since their text is reused, so each
    posting is fetched once in its life. So are postings Ghostless won't
    store (non-tech roles above student level). The rest are taken in priority order
    up to `limit` per run; anything left over is fetched on later runs. This
    keeps request volume polite on sites with thousands of postings.
    """
    limit = MAX_DETAILS_PER_RUN if limit is None else limit
    todo = [
        (detail_priority(title, location), i, key)
        for i, (key, title, location) in enumerate(items)
        if key not in known and title_worth_storing(title)
    ]
    return {key for _, _, key in sorted(todo)[:limit]}


def split_queries(slug: str) -> list[str]:
    """Config slugs can hold several searches separated by `|`."""
    return [q.strip() for q in slug.split("|") if q.strip()]


# ---------- structured fields (crawler plan, stage C1) ----------
#
# What a source states in its own fields wins over what the text suggests:
# classify.enrich keeps these and reads the text only for what's missing.

_EMPLOYMENT = {
    "fulltime": "full_time", "parttime": "part_time", "intern": "internship", "internship": "internship",
    "contract": "contract", "contractor": "contract", "temporary": "temporary", "temp": "temporary",
    "seasonal": "temporary", "permanent": "full_time", "regular": "full_time",
}  # fmt: skip
_WORKPLACE = {
    "remote": "remote",
    "hybrid": "hybrid",
    "onsite": "onsite",
    "inoffice": "onsite",
    "telecommute": "remote",
}
_PERIODS = {
    "1year": "year", "year": "year", "peryearsalary": "year", "annual": "year", "yearly": "year",
    "1hour": "hour", "hour": "hour", "perhourwage": "hour", "hourly": "hour",
    "1month": "month", "month": "month", "permonthsalary": "month", "monthly": "month",
}  # fmt: skip


def _key(value) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())


def employment_type_of(value) -> str | None:
    """'FullTime', 'Full-time', 'FULL_TIME', 'Intern', ... -> full_time, internship, ..."""
    return _EMPLOYMENT.get(_key(value))


def workplace_of(value) -> str | None:
    """'OnSite', 'on-site', 'Hybrid', 'remote', 'TELECOMMUTE' -> onsite, hybrid, remote."""
    return _WORKPLACE.get(_key(value))


def period_of(value) -> str | None:
    return _PERIODS.get(_key(value))


def set_pay(job, low, high, currency, period) -> None:
    """Pay the source states in its own fields, when it's a usable range."""
    try:
        low, high = float(low), float(high if high is not None else low)
    except (TypeError, ValueError):
        return
    currency = (currency or "").upper() or None
    if period is None or low <= 0 or high < low or (currency is not None and not currencies.known(currency)):
        return  # a currency Ghostless doesn't know: the text may still state the pay in one it does
    job.salary_min, job.salary_max, job.salary_period = low, high, period
    job.salary_currency = currency
