"""Company career sites that publish their postings as JSON-LD (schema.org
JobPosting), the format search engines read for job listings.

A board here is a career site: its host and the path its job pages sit
under, e.g. "careers.acme.example/jobs". Reading one:

1. Job links come from the site's sitemaps (named in robots.txt, else
   /sitemap.xml): every page under the board's path. That's the whole
   listing, so a posting whose page leaves the sitemap has closed.
2. Job pages are read once each, newest first, a capped batch per run, and
   again only when the sitemap says the page changed (lastmod). A stored
   posting not re-read this run stays open while the sitemap still lists it.
3. Each page's JobPosting becomes a Job. A posting past its validThrough
   date is treated as closed.

Every request goes through `http`, so robots.txt and the site's pace apply.
"""

from __future__ import annotations

import gzip
import html
import io
import json
import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from urllib.parse import urlsplit

from tracker import settings
from tracker.models import Company, Job, JobList
from tracker.sources import http
from tracker.sources.common import employment_type_of, parse_iso
from tracker.sources.http import FetchError
from tracker.text import html_to_text

log = logging.getLogger(__name__)

_SCRIPT = re.compile(
    r"<script\b[^>]*\btype\s*=\s*[\"']?application/ld\+json[\"']?[^>]*>(.*?)</script\s*>", re.I | re.S
)


def _blocks(page: str):
    for match in _SCRIPT.finditer(page or ""):
        raw = match.group(1).strip()
        raw = re.sub(r"^\s*(<!--|//\s*<!\[CDATA\[|<!\[CDATA\[)", "", raw)
        raw = re.sub(r"(-->|//\s*\]\]>|\]\]>)\s*$", "", raw).strip()
        for text in (raw, html.unescape(raw)):
            try:
                yield json.loads(text, strict=False)  # strict=False: raw newlines inside strings
                break
            except ValueError:
                continue  # invalid JSON: try unescaped, then give up on this block


def _is_posting(node: dict) -> bool:
    kind = node.get("@type")
    kinds = kind if isinstance(kind, list) else [kind]
    return any(isinstance(k, str) and k.split("/")[-1] == "JobPosting" for k in kinds)


def find_postings(page: str) -> list[dict]:
    """Every JobPosting object in a page's JSON-LD: top level, in lists, or in @graph."""
    found: list[dict] = []

    def walk(node, depth=0):
        if depth > 6:
            return
        if isinstance(node, list):
            for item in node:
                walk(item, depth + 1)
        elif isinstance(node, dict):
            if _is_posting(node):
                found.append(node)
            elif "@graph" in node:
                walk(node["@graph"], depth + 1)

    for block in _blocks(page):
        walk(block)
    return found


def _text(value) -> str:
    if isinstance(value, dict):
        value = value.get("name") or value.get("value") or ""
    if isinstance(value, list):
        value = ", ".join(_text(v) for v in value if _text(v))
    return html.unescape(str(value or "")).strip()


def _place(location) -> str:
    if isinstance(location, list):
        return " | ".join(p for p in (_place(item) for item in location) if p)
    if not isinstance(location, dict):
        return _text(location)
    address = location.get("address") or location
    if isinstance(address, str):
        return address.strip()
    parts = [_text(address.get(k)) for k in ("addressLocality", "addressRegion", "addressCountry")]
    return ", ".join(p for p in parts if p) or _text(location.get("name"))


def _salary(posting: dict, job: Job) -> None:
    pay = posting.get("baseSalary") or posting.get("estimatedSalary")
    if isinstance(pay, list):
        pay = pay[0] if pay else None
    if not isinstance(pay, dict):
        return
    value = pay.get("value") if isinstance(pay.get("value"), dict) else pay
    try:
        low = value.get("minValue", value.get("value"))
        high = value.get("maxValue", low)
        low, high = float(low), float(high)
    except (TypeError, ValueError):
        return
    unit = str(value.get("unitText") or pay.get("unitText") or "").upper()
    period = {"YEAR": "year", "HOUR": "hour"}.get(unit)
    currency = str(pay.get("currency") or value.get("currency") or "").upper() or None
    if period and low > 0 and high >= low:
        job.salary_min, job.salary_max, job.salary_period = low, high, period
        job.salary_currency = currency if currency in ("CAD", "USD", "GBP", "EUR", "AUD") else None


def expired(posting: dict, now: datetime | None = None) -> bool:
    until = parse_iso(_text(posting.get("validThrough")))
    if until is None:
        return False
    if until.tzinfo is None:
        until = until.replace(tzinfo=timezone.utc)
    return until < (now or datetime.now(timezone.utc))


def _description(text: str) -> str:
    """HTML (the usual) as text; plain text kept as written, line breaks included."""
    if re.search(r"<[a-z!/][^>]*>", text, re.I):
        return html_to_text(text)
    text = text.replace("\r\n", "\n")
    return re.sub(r"[ \t]+", " ", re.sub(r"\n{3,}", "\n\n", text)).strip()


def posting_to_job(posting: dict, url: str) -> Job:
    remote = _text(posting.get("jobLocationType")).upper() == "TELECOMMUTE"
    location = _place(posting.get("jobLocation"))
    if not location and remote:
        location = _place(posting.get("applicantLocationRequirements")) or "Remote"
    job = Job(
        external_id=job_id(url),
        title=_text(posting.get("title")),
        url=url,
        location=location,
        department=_text(posting.get("occupationalCategory") or posting.get("industry")) or None,
        description=_description(_text(posting.get("description"))),
        posted_at=parse_iso(_text(posting.get("datePosted"))),
        source_remote=remote,
        workplace="remote" if remote else None,
        employment_type=_employment(posting.get("employmentType")),
    )
    _salary(posting, job)
    months = _months(posting.get("experienceRequirements"))
    if months is not None:
        job.min_years_experience = round(months / 12, 1)
    return job


def _employment(value) -> str | None:
    """employmentType is one value or a list (FULL_TIME, PART_TIME, CONTRACTOR, INTERN, ...)."""
    values = value if isinstance(value, list) else [value]
    kinds = [employment_type_of(v) for v in values if v]
    return next((k for k in kinds if k), None)


def _months(requirement) -> float | None:
    if isinstance(requirement, list):
        requirement = requirement[0] if requirement else None
    if not isinstance(requirement, dict):
        return None
    try:
        return float(requirement["monthsOfExperience"])
    except (KeyError, TypeError, ValueError):
        return None


def parse_job_page(page: str, url: str) -> tuple[list[Job], bool]:
    """The page's postings that are still open, and whether it had any posting at all."""
    postings = find_postings(page)
    return [posting_to_job(p, url) for p in postings if not expired(p) and _text(p.get("title"))], bool(
        postings
    )


def job_id(url: str) -> str:
    """A page's id: its address without query, fragment, trailing slash or scheme."""
    parts = urlsplit(url.strip())
    return f"{parts.netloc.lower()}{parts.path.rstrip('/')}"


# ---------- sitemaps ----------


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def parse_sitemap(xml_text: str) -> tuple[list[tuple[str, str | None]], list[str]]:
    """(pages as (url, lastmod), child sitemaps) from a sitemap or sitemap index."""
    try:
        root = ET.fromstring(xml_text.encode("utf-8"))
    except ET.ParseError:
        return [], []
    pages, children = [], []
    for node in root:
        kind = _local(node.tag)
        loc = lastmod = None
        for child in node:
            if _local(child.tag) == "loc":
                loc = (child.text or "").strip()
            elif _local(child.tag) == "lastmod":
                lastmod = (child.text or "").strip() or None
        if not loc:
            continue
        if kind == "sitemap":
            children.append(loc)
        elif kind == "url":
            pages.append((loc, lastmod))
    return pages, children


MAX_SITEMAP_BYTES = 50_000_000  # the sitemap protocol's own limit, uncompressed


def _sitemap_text(url: str) -> str:
    if not urlsplit(url).path.endswith(".gz"):
        return http.get_text(url)
    with gzip.GzipFile(fileobj=io.BytesIO(http.get_bytes(url))) as unzipped:
        return unzipped.read(MAX_SITEMAP_BYTES).decode("utf-8", errors="replace")


def split_slug(slug: str) -> tuple[str, str]:
    host, _, prefix = slug.strip("/").partition("/")
    return host.lower(), prefix.strip("/")


def _under(url: str, host: str, prefix: str) -> bool:
    parts = urlsplit(url)
    if (parts.hostname or "").lower() != host:
        return False
    path = parts.path.strip("/")
    if not prefix:
        return bool(path)
    return path.startswith(prefix + "/") and len(path) > len(prefix) + 1


def list_job_pages(slug: str) -> dict[str, tuple[str, str | None]]:
    """{job id: (url, lastmod)} for every page under the board's path in the
    site's sitemaps, reading at most GHOSTLESS_JSONLD_SITEMAPS files. When
    nothing sits under that path, its parent paths are tried (a job link's
    path can be more specific than where the site lists its jobs), down to
    one segment."""
    host, prefix = split_slug(slug)
    base = f"https://{host}"
    queue = http.robots.sitemaps(base) or [f"{base}/sitemap.xml"]
    # sitemaps about jobs first: an index often lists one per section
    wanted = re.compile(r"job|career|position|opening|vacanc|posting", re.I)
    limit = settings.jsonld_urls()
    seen: set[str] = set()
    entries: list[tuple[str, str | None]] = []  # every page on the host, for the fallback
    reads = 0
    while queue and reads < settings.jsonld_sitemaps() and len(entries) < limit * 5:
        queue.sort(key=lambda u: 0 if wanted.search(u) else 1)
        url = queue.pop(0)
        if url in seen:
            continue
        seen.add(url)
        reads += 1
        try:
            found, children = parse_sitemap(_sitemap_text(url))
        except (FetchError, OSError, EOFError) as exc:
            log.info("%s: sitemap %s unreadable: %s", slug, url, exc)
            continue
        queue.extend(c for c in children if c not in seen)
        entries.extend((loc, lastmod) for loc, lastmod in found if _under(loc, host, ""))
    if not prefix:
        return _pages_under(entries, host, "", limit)
    sections = prefix.split("/")
    for depth in range(len(sections), 0, -1):  # the path, then its parents, never the whole host
        pages = _pages_under(entries, host, "/".join(sections[:depth]), limit)
        if pages:
            return pages
    return {}


def _pages_under(entries, host: str, prefix: str, limit: int) -> dict[str, tuple[str, str | None]]:
    pages: dict[str, tuple[str, str | None]] = {}
    for loc, lastmod in entries:
        if _under(loc, host, prefix):
            pages.setdefault(job_id(loc), (loc, lastmod))
            if len(pages) >= limit:
                break
    return pages


def fetch_jsonld(
    company: Company,
    details: bool = True,
    known: frozenset[str] = frozenset(),
    stored: dict | None = None,
) -> JobList:
    """The career site's open postings. `known` are ids stored with a
    description; `stored` (db.stored_versions) says when each was last read,
    so a page is read again only when its lastmod is newer."""
    pages = list_job_pages(company.board_slug)
    if not pages:
        raise FetchError(f"no job pages under {company.board_slug} in the site's sitemaps")
    stored = stored or {}

    def due(key: str, lastmod: str | None) -> bool:
        if key not in known:
            return True
        when = parse_iso(lastmod) if lastmod else None
        version = stored.get(key, (None,))[0]
        return bool(when and version and when > version)

    todo = sorted(
        ((lastmod or "", key, url) for key, (url, lastmod) in pages.items() if due(key, lastmod)),
        reverse=True,  # newest first
    )
    limit = settings.jsonld_pages_per_site() if details else 0
    listed = set(pages)
    jobs = JobList(complete=True)
    for lastmod, key, url in todo[:limit]:
        try:
            page = http.get_text(url)
        except FetchError as exc:
            log.info("%s: page %s unreadable: %s", company.name, url, exc)
            continue  # stays listed: a stored copy isn't closed for a failed read
        found, any_posting = parse_job_page(page, url)
        if any_posting and not found:
            listed.discard(key)  # past its validThrough date: closed
        for job in found[:1]:  # one posting per page; the page is its id
            job.source_updated_at = parse_iso(lastmod) if lastmod else None
            jobs.append(job)
    jobs.listed = frozenset(listed)
    return jobs
