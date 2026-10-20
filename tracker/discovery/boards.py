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
_LOCALE = re.compile(r"^[a-z]{2}-[a-z]{2}$", re.I)  # en-US, and en-us as some lists write it


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


_LINK = re.compile(r"https?://[^\s<>\"'()\[\]{}|\\^`]+", re.I)


def board_links(text: str) -> set[tuple[str, str]]:
    """Every job board linked from a piece of text ("apply at jobs.lever.co/acme")."""
    found = set()
    for match in _LINK.finditer(text or ""):
        board = board_from_url(match.group(0).rstrip(".,;:!?"))
        if board:
            found.add(board)
    return found


# Hosts a company career site can't be on: job sites and aggregators (never
# read: LinkedIn, Indeed and the like), and hiring systems shared by many
# companies, which need their own adapter rather than the JSON-LD reader.
_NOT_CAREER_SITES = (
    "linkedin.com",
    "indeed.com",
    "glassdoor.com",
    "glassdoor.ca",
    "ziprecruiter.com",
    "monster.com",
    "simplify.jobs",
    "handshake.com",
    "joinhandshake.com",
    "wellfound.com",
    "angel.co",
    "builtin.com",
    "dice.com",
    "careerbuilder.com",
    "jobbank.gc.ca",
    "workopolis.com",
    "eluta.ca",
    "talent.com",
    "facebook.com",
    "meta.com",
    "metacareers.com",
    "instagram.com",
    "twitter.com",
    "x.com",
    "github.com",
    "google.com",
    "goo.gl",
    "bit.ly",
    "youtube.com",
    "notion.site",
    "notion.so",
    "greenhouse.io",
    "lever.co",
    "ashbyhq.com",
    "myworkdayjobs.com",
    "myworkdaysite.com",
    "workday.com",
    "icims.com",
    "taleo.net",
    "successfactors.com",
    "successfactors.eu",
    "sapsf.com",
    "smartrecruiters.com",
    "workable.com",
    "teamtailor.com",
    "personio.de",
    "personio.com",
    "breezy.hr",
    "rippling.com",
    "recruitee.com",
    "jobvite.com",
    "bamboohr.com",
    "adp.com",
    "ultipro.com",
    "paylocity.com",
    "dayforcehcm.com",
    "oraclecloud.com",
    "eightfold.ai",
    "jazzhr.com",
    "applytojob.com",
    "pinpointhq.com",
    "avature.net",
    "jibeapply.com",
    "phenompeople.com",
    "brassring.com",
    "amazon.jobs",
    "jobs.apple.com",
    "careers.microsoft.com",
)


def career_site(url: str) -> str | None:
    """The career site a job link is on, as a JSON-LD board slug: its host and
    the path its job pages sit under ("careers.acme.example/jobs"). None for
    job sites, aggregators and shared hiring systems."""
    try:
        parts = urlparse(url.strip())
    except ValueError:
        return None
    host = (parts.hostname or "").lower()
    if parts.scheme not in ("http", "https") or "." not in host or parts.port:
        return None
    if any(host == d or host.endswith("." + d) for d in _NOT_CAREER_SITES):
        return None
    path = [p for p in parts.path.split("/") if p]
    if not path:
        return None  # a home page, not a job page
    section = path[:-1]
    # "/job/8196515/title" and "/JobDetail/Senior-Data-Analyst/123": the id and title aren't the section
    while section and (_ID_SEGMENT.search(section[-1]) or _TITLE_SEGMENT.match(section[-1])):
        section.pop()
    prefix = "/".join(section)
    return f"{host}/{prefix}" if prefix else host


_ID_SEGMENT = re.compile(r"\d{4,}|^[0-9a-f]{8}-[0-9a-f]{4}-", re.I)
_TITLE_SEGMENT = re.compile(r"^(?=.{16,})[^/\s-]+(-[^/\s-]+){2,}$")  # three or more hyphenated words


_SUFFIX = re.compile(
    r"\b(inc|incorporated|llc|ltd|limited|corp|corporation|co|company|plc|gmbh|sa|ag|lp|llp|technologies|technology|group|holdings)\b\.?",
    re.I,
)


def company_key(name: str) -> str:
    """A name reduced for matching: "Stripe, Inc." and "stripe" match."""
    reduced = _SUFFIX.sub(" ", name.lower().replace("&", " and "))
    return re.sub(r"[^a-z0-9]+", "", reduced) or re.sub(r"[^a-z0-9]+", "", name.lower())
