"""Recognize job boards in links, and match company names.

A link like https://job-boards.greenhouse.io/figma/jobs/123 reveals the
company's whole board ("figma" on Greenhouse), which the tracker can read in
full. Workday links reveal the tenant and site the same way.
"""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse

_GREENHOUSE_HOSTS = {
    "boards.greenhouse.io",
    "job-boards.greenhouse.io",
    "boards.eu.greenhouse.io",
    "job-boards.eu.greenhouse.io",
}
_SLUG = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,80}$")
_WORKDAY_HOST = re.compile(r"^([a-z0-9-]+)\.(wd\d+)\.myworkdayjobs\.com$", re.I)
_LOCALE = re.compile(r"^[a-z]{2}-[A-Z]{2}$")


def board_from_url(url: str) -> tuple[str, str] | None:
    """(platform, board slug) for a job link on a board the tracker can read."""
    try:
        parts = urlparse(url.strip())
    except ValueError:
        return None
    host = (parts.hostname or "").lower()
    path = [p for p in parts.path.split("/") if p]

    if host in _GREENHOUSE_HOSTS:
        if path[:1] == ["embed"]:  # boards.greenhouse.io/embed/job_app?for=acme&token=1
            slug = (parse_qs(parts.query).get("for") or [""])[0]
        else:
            slug = path[0] if path else ""
        return ("greenhouse", slug.lower()) if _SLUG.match(slug) else None
    if host == "jobs.lever.co" and path:
        return ("lever", path[0].lower()) if _SLUG.match(path[0]) else None
    if host == "jobs.ashbyhq.com" and path:
        return ("ashby", path[0]) if _SLUG.match(path[0]) else None
    match = _WORKDAY_HOST.match(host)
    if match and path:
        site = path[1] if _LOCALE.match(path[0]) and len(path) > 1 else path[0]
        if site.lower() in ("job", "details", "wday") or not _SLUG.match(site):
            return None
        return ("workday", f"{host}/{site}")
    return None


_SUFFIX = re.compile(
    r"\b(inc|incorporated|llc|ltd|limited|corp|corporation|co|company|plc|gmbh|sa|ag|lp|llp|technologies|technology|group|holdings)\b\.?",
    re.I,
)


def company_key(name: str) -> str:
    """A name reduced for matching: "Stripe, Inc." and "stripe" match."""
    reduced = _SUFFIX.sub(" ", name.lower().replace("&", " and "))
    return re.sub(r"[^a-z0-9]+", "", reduced) or re.sub(r"[^a-z0-9]+", "", name.lower())
