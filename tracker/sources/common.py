from __future__ import annotations

import os
import re
from datetime import datetime

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
