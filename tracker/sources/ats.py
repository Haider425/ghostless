"""More hiring systems (crawler plan, stage E), each off unless named in
GHOSTLESS_SOURCES (e.g. "workable,teamtailor"). Checked 21 October 2026:
robots.txt allows every endpoint used here, and each was tried once on a
real company before it was built.

| platform        | board slug                   | listing                                           | descriptions                     |
|-----------------|------------------------------|---------------------------------------------------|----------------------------------|
| workable        | acme                         | apply.workable.com widget API, details=true       | in the listing                   |
| teamtailor      | acme (acme.teamtailor.com)   | jobs.rss, paged; conditional                      | in the listing                   |
| personio        | acme.jobs.personio.de        | /xml?language=en; conditional                     | in the listing                   |
| breezy          | acme (acme.breezy.hr)        | /json; conditional                                | each job page's JSON-LD          |
| rippling        | acme (ats.rippling.com/acme) | api.rippling.com board API                        | the board API, one job at a time |
| recruitee       | acme (acme.recruitee.com)    | /api/offers/                                      | in the listing                   |
| smartrecruiters | Acme (jobs.smartrecruiters.com/Acme) | the company's public career page          | each job page's schema.org data  |

Recruitee couldn't be tried on a live board (none found); its adapter follows
the documented format. SmartRecruiters' API host disallows crawlers in
robots.txt and is never called: only its public pages are read. Its career
page shows the first postings of each location; a stored posting missing
from it is closed only when its own page is gone, checked a few per run.
"""

from __future__ import annotations

import html as html_lib
import logging
import re
import xml.etree.ElementTree as ET
from html.parser import HTMLParser

from tracker import settings
from tracker.models import Company, Job, JobList
from tracker.sources import http
from tracker.sources.common import (
    employment_type_of,
    parse_iso,
    plan_details,
    set_pay,
    workplace_of,
)
from tracker.sources.http import NOT_MODIFIED, FetchError, Validators
from tracker.sources.jsonld import parse_job_page
from tracker.text import html_to_text

log = logging.getLogger(__name__)

PLATFORMS = ("workable", "teamtailor", "personio", "breezy", "rippling", "recruitee", "smartrecruiters")
# whose server answers conditional requests with 304 (checked)
CONDITIONAL = {"teamtailor", "personio", "breezy"}
# whose descriptions need a request per posting (each fetched once, a capped batch per run)
PER_POSTING = {"breezy", "rippling", "smartrecruiters"}
SMARTRECRUITERS_RECHECKS = 20  # stored postings missing from the career page, checked per run


def enabled(platform: str) -> bool:
    return platform in settings.sources()


def listing_url(company: Company) -> str:
    slug = company.board_slug
    return {
        "workable": f"https://apply.workable.com/api/v1/widget/accounts/{slug}?details=true",
        "teamtailor": f"https://{slug}.teamtailor.com/jobs.rss?per_page=100",
        "personio": f"https://{slug}/xml?language=en",
        "breezy": f"https://{slug}.breezy.hr/json",
        "rippling": f"https://api.rippling.com/platform/api/ats/v1/board/{slug}/jobs",
        "recruitee": f"https://{slug}.recruitee.com/api/offers/",
        "smartrecruiters": f"https://jobs.smartrecruiters.com/{slug}",
    }[company.platform]


def _place(*parts) -> str:
    return ", ".join(str(p).strip() for p in parts if p and str(p).strip())


# ---------- Workable ----------


def parse_workable(data: dict) -> list[Job]:
    jobs = []
    for item in data.get("jobs") or []:
        places = [
            _place(loc.get("city"), loc.get("region"), loc.get("country"))
            for loc in item.get("locations") or []
            if isinstance(loc, dict)
        ] or [_place(item.get("city"), item.get("state"), item.get("country"))]
        remote = str(item.get("telecommuting")).lower() == "true"
        jobs.append(
            Job(
                external_id=str(item.get("shortcode") or item.get("code") or item["url"]),
                title=(item.get("title") or "").strip(),
                url=item.get("url") or item.get("shortlink") or "",
                location=" | ".join(p for p in places if p),
                department=item.get("department") or None,
                description=html_to_text(item.get("description")),
                posted_at=parse_iso(item.get("published_on") or item.get("created_at")),
                source_remote=remote,
                workplace="remote" if remote else None,
                employment_type=employment_type_of(item.get("employment_type")),
            )
        )
    return jobs


def fetch_workable(company: Company, **_) -> JobList:
    return JobList(parse_workable(http.get_json(listing_url(company))))


# ---------- XML feeds: Teamtailor, Personio ----------


def _xml(text: str) -> ET.Element:
    try:
        return ET.fromstring(text.encode("utf-8"))
    except ET.ParseError as exc:
        raise FetchError(f"invalid XML: {exc}") from exc


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _child(node: ET.Element, name: str) -> str:
    for child in node:
        if _local(child.tag) == name:
            return (child.text or "").strip()
    return ""


_TEAMTAILOR_REMOTE = {"fully": "remote", "hybrid": "hybrid", "none": "onsite"}


def parse_teamtailor(text: str) -> list[Job]:
    jobs = []
    for item in _xml(text).iter("item"):
        places = []
        for node in item.iter():
            if _local(node.tag) == "location":
                places.append(_place(_child(node, "city") or _child(node, "name"), _child(node, "country")))
        remote = _child(item, "remoteStatus").lower()
        jobs.append(
            Job(
                external_id=_child(item, "guid") or _child(item, "link"),
                title=_child(item, "title"),
                url=_child(item, "link"),
                location=" | ".join(p for p in places if p),
                department=_child(item, "department") or None,
                description=html_to_text(_child(item, "description")),
                posted_at=_rss_date(_child(item, "pubDate")),
                source_remote=remote == "fully",
                workplace=_TEAMTAILOR_REMOTE.get(remote),
            )
        )
    return jobs


def _rss_date(value: str):
    import email.utils

    try:
        return email.utils.parsedate_to_datetime(value) if value else None
    except (TypeError, ValueError):
        return None


def _get_text_if_changed(url: str, cached: Validators | None):
    extra = cached.headers() if cached and cached.url == url else None
    resp = http._send("GET", url, None, "application/xml,text/xml;q=0.9,*/*;q=0.8", extra)
    if resp.status_code == 304:
        return NOT_MODIFIED, cached
    return resp.text, Validators.of(url, resp)


def fetch_teamtailor(company: Company, cached: Validators | None = None, **_) -> JobList:
    first = listing_url(company)
    text, validators = _get_text_if_changed(first, cached)
    if text is NOT_MODIFIED:
        return JobList(not_modified=True, validators=validators)
    jobs = parse_teamtailor(text)
    page = jobs
    offset = 100
    while len(page) >= 100 and offset < 5000:  # 100 a page; a board larger than 5,000 is read in part
        page = parse_teamtailor(http.get_text(f"{first}&offset={offset}"))
        jobs += page
        offset += 100
    return JobList(jobs, complete=len(page) < 100, validators=validators)


_PERSONIO_TYPES = {
    "intern": "internship", "trainee": "internship", "working_student": "internship",
    "freelance": "contract", "temporary": "temporary",
}  # fmt: skip


def parse_personio(text: str, host: str) -> list[Job]:
    jobs = []
    for position in _xml(text).iter("position"):
        offices = [_child(position, "office")] + [
            (o.text or "").strip() for extra in position.iter("additionalOffices") for o in extra
        ]
        sections = []
        for description in position.iter("jobDescription"):
            name, value = _child(description, "name"), _child(description, "value")
            sections.append(f"{html_lib.unescape(name)}\n{html_to_text(value)}".strip())
        kind = _PERSONIO_TYPES.get(_child(position, "employmentType").lower())
        if kind is None:
            schedule = _child(position, "schedule").lower()
            kind = "part_time" if "part" in schedule else "full_time" if "full" in schedule else None
        job = Job(
            external_id=_child(position, "id"),
            title=html_lib.unescape(_child(position, "name")),
            url=f"https://{host}/job/{_child(position, 'id')}",
            location=" | ".join(o for o in offices if o),
            department=_child(position, "department") or None,
            description="\n\n".join(s for s in sections if s),
            posted_at=parse_iso(_child(position, "createdAt")),
            employment_type=kind,
        )
        years = re.match(r"\s*(\d+)", _child(position, "yearsOfExperience"))
        if years:
            job.min_years_experience = float(years.group(1))
        jobs.append(job)
    return jobs


def fetch_personio(company: Company, cached: Validators | None = None, **_) -> JobList:
    text, validators = _get_text_if_changed(listing_url(company), cached)
    if text is NOT_MODIFIED:
        return JobList(not_modified=True, validators=validators)
    return JobList(parse_personio(text, company.board_slug), validators=validators)


# ---------- Breezy ----------


def parse_breezy(data: list) -> list[Job]:
    from tracker.disclosures import parse_salary

    jobs = []
    for item in data or []:
        locations = item.get("locations") or [item.get("location") or {}]
        places = [
            _place(
                loc.get("city"),
                (loc.get("state") or {}).get("id")
                if isinstance(loc.get("state"), dict)
                else loc.get("state"),
                (loc.get("country") or {}).get("name")
                if isinstance(loc.get("country"), dict)
                else loc.get("country"),
            )
            for loc in locations
            if isinstance(loc, dict)
        ]
        remote = any(isinstance(loc, dict) and loc.get("is_remote") for loc in locations)
        job = Job(
            external_id=str(item["id"]),
            title=(item.get("name") or "").strip(),
            url=item.get("url") or "",
            location=" | ".join(p for p in places if p),
            department=item.get("department") or None,
            posted_at=parse_iso(item.get("published_date")),
            source_remote=remote,
            employment_type=employment_type_of((item.get("type") or {}).get("id")),
        )
        pay = parse_salary(f"Salary: {item['salary']}") if item.get("salary") else None
        if pay:
            set_pay(job, pay.minimum, pay.maximum, pay.currency, pay.period)
        jobs.append(job)
    return jobs


def fetch_breezy(
    company: Company,
    details: bool = True,
    known: frozenset[str] = frozenset(),
    cached: Validators | None = None,
    **_,
) -> JobList:
    data, validators = http.get_json_if_changed(listing_url(company), cached)
    if data is NOT_MODIFIED:
        return JobList(not_modified=True, validators=validators)
    jobs = JobList(parse_breezy(data), validators=validators)
    _page_details(company, jobs, known, details)
    return jobs


def _page_details(company: Company, jobs: list[Job], known: frozenset[str], details: bool) -> None:
    """Descriptions from each job page's JSON-LD, for postings not stored yet."""
    if not details:
        return
    wanted = plan_details([(j.external_id, j.title, j.location) for j in jobs], known)
    for job in jobs:
        if job.external_id not in wanted or not job.url:
            continue
        try:
            found, _ = parse_job_page(http.get_text(job.url), job.url)
        except FetchError as exc:
            log.info("%s: page %s unreadable: %s", company.name, job.url, exc)
            continue
        if found:
            job.description = found[0].description
            job.employment_type = job.employment_type or found[0].employment_type
            if job.salary_min is None and found[0].salary_min is not None:
                job.salary_min, job.salary_max = found[0].salary_min, found[0].salary_max
                job.salary_period, job.salary_currency = found[0].salary_period, found[0].salary_currency


# ---------- Rippling ----------


def parse_rippling(item: dict, detail: dict | None = None) -> Job:
    detail = detail or {}
    work = item.get("workLocation") or {}
    places = detail.get("workLocations") or [work.get("label") if isinstance(work, dict) else work]
    description = detail.get("description") or {}
    if isinstance(description, dict):
        text = "\n\n".join(html_to_text(part) for part in description.values() if isinstance(part, str))
    else:
        text = html_to_text(description)
    department = item.get("department") or detail.get("department") or {}
    kind = (detail.get("employmentType") or {}).get("label", "")
    job = Job(
        external_id=str(item.get("uuid") or item.get("id")),
        title=(item.get("name") or "").strip(),
        url=item.get("url") or "",
        location=" | ".join(p for p in places if p),
        department=(department.get("label") or department.get("name")) if isinstance(department, dict) else None,
        description=text,
        posted_at=parse_iso(detail.get("createdOn")),
        employment_type=(
            "internship" if "INTERN" in kind else "contract" if "CONTRACT" in kind
            else "part_time" if kind.endswith("_PT") else "full_time" if kind.endswith("_FT") else None
        ),
    )  # fmt: skip
    for pay in detail.get("payRangeDetails") or []:
        if isinstance(pay, dict):
            low = pay.get("rangeStart", pay.get("min"))
            high = pay.get("rangeEnd", pay.get("max"))
            period = {"YEAR": "year", "HOUR": "hour", "MONTH": "month"}.get(
                str(pay.get("frequency", "YEAR")).upper()
            )
            set_pay(job, low, high, pay.get("currency"), period)
            break
    return job


def fetch_rippling(
    company: Company, details: bool = True, known: frozenset[str] = frozenset(), **_
) -> JobList:
    base = listing_url(company)
    items = http.get_json(base) or []
    wanted = (
        plan_details([(str(i.get("uuid")), i.get("name", ""), "") for i in items], known)
        if details
        else set()
    )
    jobs = JobList()
    for item in items:
        detail = None
        if str(item.get("uuid")) in wanted:
            try:
                detail = http.get_json(f"{base}/{item['uuid']}")
            except FetchError as exc:
                log.info("%s: detail for %s unreadable: %s", company.name, item.get("uuid"), exc)
        jobs.append(parse_rippling(item, detail))
    return jobs


# ---------- Recruitee ----------


def parse_recruitee(data: dict, slug: str) -> list[Job]:
    jobs = []
    for offer in data.get("offers") or []:
        remote = bool(offer.get("remote"))
        description = "\n\n".join(
            html_to_text(offer.get(k)) for k in ("description", "requirements") if offer.get(k)
        )
        jobs.append(
            Job(
                external_id=str(offer.get("id") or offer.get("slug")),
                title=(offer.get("title") or "").strip(),
                url=offer.get("careers_url") or f"https://{slug}.recruitee.com/o/{offer.get('slug', '')}",
                location=offer.get("location") or _place(offer.get("city"), offer.get("country")),
                department=offer.get("department") or None,
                description=description,
                posted_at=parse_iso(offer.get("published_at") or offer.get("created_at")),
                source_remote=remote,
                workplace="remote" if remote else None,
                employment_type=employment_type_of(offer.get("employment_type_code")),
            )
        )
    return jobs


def fetch_recruitee(company: Company, **_) -> JobList:
    return JobList(parse_recruitee(http.get_json(listing_url(company)), company.board_slug))


# ---------- SmartRecruiters (public pages only) ----------


class _Microdata(HTMLParser):
    """schema.org properties on a page (itemprop), as text or their content attribute."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.values: dict[str, str] = {}
        self.workplace: str | None = None
        self._open: list[tuple[str, str, int, list[str]]] = []  # (prop, tag, depth, parts)
        self._depth = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "spl-job-location" and attrs.get("workplacetype"):
            self.workplace = workplace_of(attrs["workplacetype"])
        prop = attrs.get("itemprop")
        if tag in ("meta", "link"):
            if prop and prop not in self.values:
                self.values[prop] = attrs.get("content") or attrs.get("href") or ""
            return
        self._depth += 1
        for _, _, _, parts in self._open:
            parts.append(self.get_starttag_text() or "")
        if prop and "itemscope" not in attrs:
            self._open.append((prop, tag, self._depth, []))

    def handle_endtag(self, tag):
        for _, _, _, parts in self._open:
            parts.append(f"</{tag}>")
        while self._open and self._open[-1][2] == self._depth:
            prop, _, _, parts = self._open.pop()
            self.values.setdefault(prop, "".join(parts[:-1]))
        self._depth -= 1

    def handle_data(self, data):
        for _, _, _, parts in self._open:
            parts.append(html_lib.escape(data))


def parse_smartrecruiters_job(page: str, url: str, external_id: str) -> Job | None:
    """A job page's schema.org JobPosting (microdata), or None if it has none."""
    if "schema.org/JobPosting" not in page:
        return None
    reader = _Microdata()
    reader.feed(page)
    values = reader.values
    title = html_to_text(values.get("title", "")) or html_to_text(values.get("name", ""))
    return Job(
        external_id=external_id,
        title=title,
        url=url,
        location=_place(
            values.get("addressLocality"), values.get("addressRegion"), values.get("addressCountry")
        ),
        description=html_to_text(values.get("description", "")),
        posted_at=parse_iso(values.get("datePosted")),
        workplace=reader.workplace,
        employment_type=employment_type_of(html_to_text(values.get("employmentType", ""))),
    )


def _smartrecruiters_links(page: str, slug: str) -> dict[str, tuple[str, str]]:
    """{posting id: (url, title)} from a company career page."""
    found = {}
    pattern = rf'href="(https://jobs\.smartrecruiters\.com/{re.escape(slug)}/(\d+)-[^"]*)"[^>]*>(.*?)</a>'
    for url, posting_id, inner in re.findall(pattern, page, re.I | re.S):
        title = (
            html_to_text(re.search(r"<h4[^>]*>(.*?)</h4>", inner, re.S).group(1)) if "<h4" in inner else ""
        )
        found.setdefault(posting_id, (html_lib.unescape(url), title or html_to_text(inner)))
    return found


def fetch_smartrecruiters(
    company: Company, details: bool = True, known: frozenset[str] = frozenset(), **_
) -> JobList:
    page = http.get_text(listing_url(company))
    links = _smartrecruiters_links(page, company.board_slug)
    if not links:
        raise FetchError(f"no postings on the SmartRecruiters page of {company.board_slug}")
    wanted = (
        plan_details([(pid, title, "") for pid, (_, title) in links.items()], known) if details else set()
    )
    jobs = JobList()
    listed = set(links)
    for pid, (url, title) in links.items():
        job = None
        if pid in wanted:
            try:
                job = parse_smartrecruiters_job(http.get_text(url), url, pid)
            except FetchError as exc:
                log.info("%s: page %s unreadable: %s", company.name, url, exc)
        jobs.append(job or Job(external_id=pid, title=title, url=url))
    # the page shows the first postings of each location: a stored posting
    # missing from it is closed only once its own page is gone (404, or no
    # posting on it); the rest wait for a later run, still open
    missing = sorted(known - listed)
    for pid in missing[:SMARTRECRUITERS_RECHECKS]:
        try:
            still = parse_smartrecruiters_job(
                http.get_text(f"https://jobs.smartrecruiters.com/{company.board_slug}/{pid}"), "", pid
            )
        except FetchError as exc:
            if "404" not in str(exc):
                listed.add(pid)  # couldn't tell: keep it open
            continue
        if still is not None:
            listed.add(pid)
    listed |= set(missing[SMARTRECRUITERS_RECHECKS:])
    jobs.listed = frozenset(listed)
    return jobs


FETCHERS = {
    "workable": fetch_workable,
    "teamtailor": fetch_teamtailor,
    "personio": fetch_personio,
    "breezy": fetch_breezy,
    "rippling": fetch_rippling,
    "recruitee": fetch_recruitee,
    "smartrecruiters": fetch_smartrecruiters,
}
