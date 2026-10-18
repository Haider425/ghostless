"""Public job lists on GitHub, read from their structured data.

Three formats are understood:

  simplify  SimplifyJobs' internship and new grad lists, and the many lists
            that copy their format, keep every entry in
            `.github/scripts/listings.json`: company, title, locations, link,
            season, dates and whether it's still open. Read instead of the
            README table, so formatting changes can't break it.
  markdown  A README table with Company, Role, Location, Apply and Date
            columns, as in negarprh/Canadian-Tech-Internships-2027. Rows
            marked closed (🔒) are skipped; "↳" repeats the company above.
  jobs-json A `{"jobs": [...]}` file with company, title, locationText,
            applyUrl and postedAt, as in Bobwillrule/Canadian-Internship-List.

raw.githubusercontent.com publishes no robots.txt, so reading it is allowed;
every request still goes through the polite HTTP layer.
"""

from __future__ import annotations

import hashlib
import html
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

from tracker.sources import http

RAW = "https://raw.githubusercontent.com/{repo}/{branch}/{path}"


@dataclass(frozen=True)
class JobList:
    """A list to read: a GitHub repository and the JSON file inside it."""

    repo: str  # owner/name
    branch: str = "dev"
    path: str = ".github/scripts/listings.json"
    label: str = ""  # shown on job pages: "SimplifyJobs internships"
    level: str | None = None  # every entry's level when the list is for one ("intern", "new_grad")
    format: str = "simplify"  # simplify | markdown | jobs-json

    @property
    def url(self) -> str:
        return RAW.format(repo=self.repo, branch=self.branch, path=self.path)

    @property
    def name(self) -> str:
        return self.label or self.repo


DEFAULT_LISTS = (
    JobList("SimplifyJobs/Summer2027-Internships", label="SimplifyJobs internships", level="intern"),
    JobList("SimplifyJobs/New-Grad-Positions", label="SimplifyJobs new grad roles", level="new_grad"),
    JobList("vanshb03/Summer2027-Internships", label="vanshb03 internships", level="intern"),
    JobList(
        "negarprh/Canadian-Tech-Internships-2027",
        branch="main",
        path="README.md",
        format="markdown",
        label="Canadian Tech Internships 2027",
        level="intern",
    ),
    JobList(
        "Bobwillrule/Canadian-Internship-List",
        branch="main",
        path="docs/data/jobs.json",
        format="jobs-json",
        label="Canadian Internship List",
        level="intern",
    ),
)


FORMATS = ("simplify", "markdown", "jobs-json")


@dataclass
class ListedJob:
    list_name: str
    id: str
    company: str
    title: str
    url: str
    locations: list[str]
    posted_at: datetime | None
    terms: list[str] = field(default_factory=list)
    category: str | None = None
    level: str | None = None  # from the list, when it's for one level


_SEASON = re.compile(r"^(Summer|Fall|Winter|Spring) \d{4}$")


def _when(value) -> datetime | None:
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc)
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def parse_simplify(data: list, list_name: str, level: str | None = None) -> list[ListedJob]:
    """Open, visible entries with a company, a title and a web link."""
    out: list[ListedJob] = []
    for item in data if isinstance(data, list) else []:
        if not isinstance(item, dict) or not item.get("active") or item.get("is_visible") is False:
            continue
        company = str(item.get("company_name") or "").strip()
        title = str(item.get("title") or "").strip()
        url = str(item.get("url") or "").strip()
        if not company or not title or not url.startswith(("https://", "http://")):
            continue
        out.append(
            ListedJob(
                list_name=list_name,
                id=str(item.get("id") or url),
                company=company,
                title=title,
                url=url,
                locations=[str(x).strip() for x in item.get("locations") or [] if str(x).strip()],
                posted_at=_when(item.get("date_posted")),
                terms=[t for t in item.get("terms") or [] if isinstance(t, str) and _SEASON.match(t)]
                or (
                    [item["season"]]
                    if isinstance(item.get("season"), str) and _SEASON.match(item["season"])
                    else []
                ),
                category=item.get("category"),
                level=level,
            )
        )
    return out


# ---------- other formats ----------

_TRACKING = re.compile(r"^(utm_[a-z]+|ref|source|src|gh_src|lever-source.*|trk)$", re.I)


def clean_url(url: str) -> str:
    """The link without tracking parameters or a trailing /apply, for spotting the same posting in two lists."""
    from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

    parts = urlsplit(url.strip())
    query = urlencode([(k, v) for k, v in parse_qsl(parts.query) if not _TRACKING.match(k)])
    path = re.sub(r"/apply/?$", "", parts.path).rstrip("/")
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, query, ""))


def _url_id(url: str) -> str:
    return "url:" + hashlib.sha1(clean_url(url).encode()).hexdigest()[:20]


_LINK = re.compile(r"\((https?://[^)\s]+)\)|<(https?://[^>\s]+)>|(?<![(\[])(https?://[^\s|)\]]+)")
_MD_DATE = re.compile(r"([A-Z][a-z]{2})[a-z]*\.? (\d{1,2}),? (\d{4})")
_MONTHS = {
    m: i
    for i, m in enumerate(
        ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1
    )
}
_CLOSED = re.compile(r"🔒|\bclosed\b", re.I)
_COLUMNS = (
    ("company", ("company",)),
    ("title", ("role", "title", "position", "job")),
    ("location", ("location",)),
    ("link", ("apply", "link", "application")),
    ("date", ("date posted", "posted", "date", "age")),
)


def _md_text(cell: str) -> str:
    cell = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", cell)  # images, like Apply badges
    cell = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", cell)  # links: keep their text
    cell = re.sub(r"<[^>]+>|\*\*|__|~~", "", cell)
    return html.unescape(cell).strip()


def _md_date(cell: str) -> datetime | None:
    m = _MD_DATE.search(cell)
    if not m or m[1] not in _MONTHS:
        return None
    try:
        return datetime(int(m[3]), _MONTHS[m[1]], int(m[2]), tzinfo=timezone.utc)
    except ValueError:
        return None


def _header(cells: list[str]) -> dict[str, int] | None:
    lower = [_md_text(c).lower() for c in cells]
    if not any(c.startswith("company") for c in lower) or not any(
        c.startswith(("role", "title", "position")) for c in lower
    ):
        return None
    columns: dict[str, int] = {}
    for i, c in enumerate(lower):
        for key, names in _COLUMNS:
            if key not in columns and c.startswith(names):
                columns[key] = i
                break
    return columns


def parse_markdown(text: str, list_name: str, level: str | None = None) -> list[ListedJob]:
    """Open rows of every table whose header names a company, a role and a link."""
    out: list[ListedJob] = []
    columns: dict[str, int] | None = None
    company = ""
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            columns = None
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        header = _header(cells)
        if header is not None:
            columns, company = header, ""
            continue
        if columns is None or set(line) <= set("|-: "):
            continue

        def get(key: str, cells: list[str] = cells, columns: dict[str, int] = columns) -> str:
            i = columns.get(key)
            return cells[i] if i is not None and i < len(cells) else ""

        name = _md_text(get("company"))
        if name and name not in ("↳", "^", '"'):
            company = name
        title = _md_text(get("title"))
        link_cell = get("link") or line
        if _CLOSED.search(link_cell) or _CLOSED.search(get("title")):
            continue
        urls = [next(u for u in m if u) for m in _LINK.findall(link_cell)]
        urls = [u for u in urls if "shields.io" not in u and not u.endswith((".png", ".svg", ".gif"))]
        if not company or not title or not urls:
            continue
        places = [
            p.strip() for p in re.split(r"\s*/\s*|<br\s*/?>|;\s*", _md_text(get("location"))) if p.strip()
        ]
        out.append(
            ListedJob(
                list_name=list_name,
                id=_url_id(urls[0]),
                company=company,
                title=title,
                url=urls[0],
                locations=places,
                posted_at=_md_date(get("date")),
                level=level,
            )
        )
    return out


def _iso(value) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def parse_jobs_json(data: dict, list_name: str, level: str | None = None) -> list[ListedJob]:
    """Entries of a `{"jobs": [...]}` file that aren't hidden."""
    jobs = data.get("jobs") if isinstance(data, dict) else None
    out: list[ListedJob] = []
    for item in jobs if isinstance(jobs, list) else []:
        if not isinstance(item, dict) or item.get("hidden"):
            continue
        company = html.unescape(str(item.get("company") or "")).strip()
        title = html.unescape(str(item.get("title") or "")).strip()
        url = str(item.get("applyUrl") or item.get("url") or "").strip()
        if not company or not title or not url.startswith(("https://", "http://")):
            continue
        out.append(
            ListedJob(
                list_name=list_name,
                id=_url_id(url),
                company=company,
                title=title,
                url=url,
                locations=[p for p in [str(item.get("locationText") or "").strip()] if p],
                posted_at=_iso(item["postedAt"]) if item.get("postedAt") else None,
                level=level,
            )
        )
    return out


def fetch_list(job_list: JobList) -> list[ListedJob]:
    # entries name the repo they came from, so job pages can link to it
    if job_list.format == "markdown":
        return parse_markdown(http.get_text(job_list.url), job_list.repo, job_list.level)
    if job_list.format == "jobs-json":
        return parse_jobs_json(http.get_json(job_list.url), job_list.repo, job_list.level)
    return parse_simplify(http.get_json(job_list.url), job_list.repo, job_list.level)
