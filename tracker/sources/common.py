from __future__ import annotations

import re
from datetime import datetime

from tracker.classify import classify_role, is_canada, is_remote

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


def wants_detail(title: str, location: str = "") -> bool:
    """Is a posting worth an extra request for its full description?

    Only tech roles in Canada, remote, or with an unknown or multi-city
    location. This keeps runs fast and keeps request volume low on sites
    with thousands of postings.
    """
    if classify_role(title) == "other":
        return False
    return (
        not location or is_canada(location) or is_remote(location) or bool(_MULTI_LOCATION.search(location))
    )


def split_queries(slug: str) -> list[str]:
    """Config slugs can hold several searches separated by `|`."""
    return [q.strip() for q in slug.split("|") if q.strip()]
