"""Company websites, for logos.

The website shows a company's logo from its domain. Configured companies have
one in companies.yaml; companies found through the public job lists and
discovered boards don't, so this step looks for it, in order of trust:

1. The job board itself, where the employer enters its website: Ashby's public
   board page ("publicWebsite") and Workable's account endpoint ("url"). One
   request per company, through the crawler's HTTP client (robots.txt and rate
   limits apply).
2. The company's own careers site, when its postings' apply links go there
   (careers.amd.com -> amd.com, lifeattiktok.com). A domain that apply links of
   differently named companies share is a hiring system, never an employer's.
3. Links and email addresses in the company's own postings, when the domain's
   name matches the company's name ("Pure Storage" -> purestorage.com). They are
   pulled out inside Postgres, so descriptions never leave the database.

A company with no website found is looked at again after RECHECK_DAYS, not
every run. A domain is only ever filled in, never replaced.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from tracker import db
from tracker.sources import http
from tracker.sources.http import FetchError

log = logging.getLogger(__name__)

RECHECK_DAYS = 30
LOOKUPS_PER_RUN = 200  # board requests per nightly run; `ghostless domains --all` lifts it

# second-level suffixes, so careers.example.co.uk becomes example.co.uk, not co.uk
TWO_LEVEL = {
    "co.uk",
    "org.uk",
    "ac.uk",
    "com.au",
    "net.au",
    "co.nz",
    "co.jp",
    "co.in",
    "co.kr",
    "co.il",
    "com.br",
    "com.mx",
    "com.sg",
    "com.cn",
    "com.hk",
    "com.tw",
    "co.za",
}
# hosts that are never a company's own site: job boards, social networks, link
# shorteners, and the government and vendor pages postings link to
NOT_A_COMPANY = re.compile(
    r"greenhouse|lever\.co|ashbyhq|workday|myworkday|smartrecruiters|workable|icims|jobvite|rippling|"
    r"paylocity|bamboohr|recruitee|teamtailor|personio|breezy|eightfold|successfactors|taleo|oraclecloud|"
    r"yello\.co|dayforce|ultipro|ukg|jazzhr|applytojob|pinpointhq|brassring|avature|phenompeople|csod|"
    r"cornerstoneondemand|paycom|paycor|dover\.com|gem\.com|trakstar|withgoogle|comeet|freshteam|zohorecruit|"
    r"simplify\.jobs|careerpuck|talentify|hirebridge|clearcompany|isolved|adp\.|recsolu|jobs2web|applicantpro|"
    r"tal\.net|hrmdirect|sapsf|hiringthing|"
    r"linkedin|indeed|glassdoor|ziprecruiter|wellfound|angel\.co|ycombinator|workatastartup|builtin|"
    r"crunchbase|levels\.fyi|payscale|google|youtube|facebook|instagram|twitter|^x\.com|tiktok|"
    r"github\.com|medium\.com|wikipedia|bit\.ly|shorturl|tinyurl|forms\.gle|calendly|zoom\.us|notion\.site|"
    r"\.gov$|\.gov\.|e-verify|everify|eeoc|onetrust|hirevue|hackerrank|codesignal|adp\.com|justworks|"
    r"gusto|trinet|deel\.com|techcrunch|forbes|bloomberg|reuters|example\.com",
    re.I,
)
# words that don't identify a company, ignored when matching a domain to a name
GENERIC = {
    "inc",
    "llc",
    "ltd",
    "the",
    "corp",
    "corporation",
    "company",
    "group",
    "technologies",
    "technology",
    "labs",
    "lab",
    "systems",
    "holdings",
    "and",
    "of",
    "international",
    "global",
}
# what companies add to their name in a domain: prysmiangroup.com, chaosinc.com
SUFFIXES = ("group", "inc", "corp", "co", "hq", "global", "usa", "us", "tech", "labs", "ai", "app")
# hosts in postings, as Postgres extracts them: links, bare www. names and email domains
HOST_PATTERN = r"(?:https?://|www\.|@)([a-z0-9][a-z0-9.-]*\.[a-z]{2,})"
ASHBY_WEBSITE = re.compile(r'"publicWebsite"\s*:\s*"([^"]+)"')


def registrable(host: str) -> str:
    """The part of a host name a company registers: jobs.example.com -> example.com."""
    parts = host.lower().strip(".").split(".")
    if len(parts) >= 3 and ".".join(parts[-2:]) in TWO_LEVEL:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def domain_of(website: str | None) -> str | None:
    """A website address as a logo domain, or None when it isn't a company's own site."""
    if not website:
        return None
    website = website.strip().replace("\\/", "/")
    if "://" not in website:
        website = f"https://{website}"
    host = (urlsplit(website).hostname or "").lower()
    if "." not in host or NOT_A_COMPANY.search(host):
        return None
    return registrable(host)


def _squash(text: str) -> str:
    plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]", "", plain)


def _words(name: str) -> list[str]:
    plain = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    return [w for w in re.findall(r"[a-z0-9]+", plain) if w not in GENERIC and len(w) >= 3]


def names_match(name: str, domain: str) -> bool:
    """Whether a domain plausibly belongs to a company with this name: its first
    label is the name ("Klaviyo" -> klaviyo.com), the name run together ("Pure
    Storage" -> purestorage.com), a long enough start of it ("KLA Corporation" ->
    kla.com, "Vishay Intertechnology" -> vishay.com), or the name plus a suffix
    ("WSFS Bank" -> wsfsbank.com), or its first word plus a usual suffix
    ("Prysmian Cables & Systems" -> prysmiangroup.com)."""
    label = _squash(domain.split(".")[0])
    whole = _squash(name)
    words = _words(name)
    if len(label) < 3 or not whole:
        return False
    if label == whole or (words and label == "".join(words)):
        return True
    if len(label) >= 4 and (whole.startswith(label) or label.startswith(whole)):
        return True
    if len(label) >= 4 and label in words:
        return True
    return bool(words) and len(words[0]) >= 4 and label in {f"{words[0]}{end}" for end in SUFFIXES}


def from_postings(name: str, hosts: Counter[str]) -> str | None:
    """The best domain among the hosts a company's postings mention (host ->
    how many postings), or None when none of them matches the company's name."""
    seen: Counter[str] = Counter()
    for host, count in hosts.items():
        if not NOT_A_COMPANY.search(host):
            seen[registrable(host)] += count
    fits = [(count, -len(domain), domain) for domain, count in seen.items() if names_match(name, domain)]
    return max(fits)[2] if fits else None


def shared_domains(apply_hosts: dict[str, set[str]]) -> set[str]:
    """Domains that apply links of differently named companies point to (host ->
    company names): hiring systems, never one employer's site. Two records of the
    same company ("KLA", "KLA Corporation") don't make a domain shared."""
    by_domain: dict[str, set[str]] = {}
    for host, names in apply_hosts.items():
        firsts = {(_words(n) or [_squash(n)])[0] for n in names}
        by_domain.setdefault(registrable(host), set()).update(firsts)
    return {domain for domain, firsts in by_domain.items() if len(firsts) > 1}


def from_apply_links(hosts: Counter[str], shared: set[str]) -> str | None:
    """The employer's domain when its postings' apply links go to its own careers
    site (host -> how many postings), or None when they go to a hiring system."""
    seen: Counter[str] = Counter()
    for host, count in hosts.items():
        domain = registrable(host)
        if "." in host and not NOT_A_COMPANY.search(host) and domain not in shared:
            seen[domain] += count
    return max(seen.items(), key=lambda kv: (kv[1], -len(kv[0])))[0] if seen else None


def from_ashby(slug: str) -> str | None:
    match = ASHBY_WEBSITE.search(http.get_text(f"https://jobs.ashbyhq.com/{slug}"))
    return domain_of(match.group(1)) if match else None


def from_workable(slug: str) -> str | None:
    data = http.get_json(f"https://apply.workable.com/api/v1/accounts/{slug}") or {}
    return domain_of(data.get("url")) if isinstance(data, dict) else None


BOARDS = {"ashby": from_ashby, "workable": from_workable}


@dataclass
class Candidate:
    id: int
    name: str
    open_jobs: int
    boards: list[tuple[str, str]] = field(default_factory=list)  # (ashby or workable, slug)
    apply_hosts: Counter[str] = field(default_factory=Counter)  # where its apply links go
    hosts: Counter[str] = field(default_factory=Counter)  # hosts its descriptions mention


@dataclass
class Report:
    looked_at: int = 0
    from_board: int = 0
    from_careers_site: int = 0
    from_postings: int = 0
    not_found: int = 0
    lookups: int = 0
    failed_lookups: int = 0
    found: list[tuple[str, str, str]] = field(default_factory=list)  # (company, domain, source)

    def summary(self) -> str:
        return (
            f"looked at {self.looked_at} companies: {self.from_board} websites from their job board, "
            f"{self.from_careers_site} from their careers site, {self.from_postings} from their postings, "
            f"{self.not_found} not found "
            f"({self.lookups} board requests, {self.failed_lookups} failed)"
        )


CANDIDATES_SQL = f"""
    SELECT c.id, c.name, count(*) AS open_jobs,
           array_remove(array_agg(DISTINCT CASE WHEN c.platform = 'ashby' THEN c.board_slug END), NULL)
           || array_remove(array_agg(DISTINCT substring(j.url FROM '^https?://jobs\\.ashbyhq\\.com/([^/?#]+)')), NULL)
               AS ashby,
           array_remove(array_agg(DISTINCT CASE WHEN c.platform = 'workable' THEN c.board_slug END), NULL)
           || array_remove(array_agg(DISTINCT substring(j.url FROM '^https?://apply\\.workable\\.com/([^/?#]+)')), NULL)
               AS workable
    FROM companies c
    JOIN jobs j ON j.company_id = c.id AND j.closed_at IS NULL
    WHERE c.domain IS NULL
      AND (c.domain_checked_at IS NULL OR c.domain_checked_at < now() - interval '{RECHECK_DAYS} days')
    GROUP BY c.id, c.name
    ORDER BY count(*) DESC, c.id
"""
# where every company's apply links go, to tell hiring systems from employers' sites
APPLY_HOSTS_SQL = """
    SELECT lower(split_part(split_part(j.url, '://', 2), '/', 1)) AS host, c.name, j.company_id, count(*)
    FROM jobs j JOIN companies c ON c.id = j.company_id
    WHERE j.closed_at IS NULL
    GROUP BY 1, 2, 3
"""
# only the matched host names come back, never the descriptions
HOSTS_SQL = f"""
    SELECT j.company_id, lower(m[1]) AS host, count(DISTINCT j.id)
    FROM jobs j, regexp_matches(j.description, '{HOST_PATTERN}', 'gi') AS m
    WHERE j.company_id = ANY(%s) AND j.closed_at IS NULL AND j.description IS NOT NULL
    GROUP BY 1, 2
"""


def candidates(conn) -> tuple[list[Candidate], set[str]]:
    """Companies due a look, and the domains hiring systems share."""
    found = []
    for cid, name, open_jobs, ashby, workable in conn.execute(CANDIDATES_SQL).fetchall():
        boards = [("ashby", s) for s in dict.fromkeys(ashby or [])]
        boards += [("workable", s) for s in dict.fromkeys(workable or [])]
        found.append(Candidate(cid, name, open_jobs, boards))
    by_id = {c.id: c for c in found}
    if not by_id:  # nothing due: read nothing more (most nights, once every company has been looked at)
        return [], set()
    names_by_host: dict[str, set[str]] = {}
    for host, name, cid, count in conn.execute(APPLY_HOSTS_SQL).fetchall():
        names_by_host.setdefault(host, set()).add(name)
        if cid in by_id:
            by_id[cid].apply_hosts[host] += count
    for cid, host, count in conn.execute(HOSTS_SQL, (list(by_id),)).fetchall():
        by_id[cid].hosts[host] += count
    return found, shared_domains(names_by_host)


def fill(dsn: str, lookups: int | None = LOOKUPS_PER_RUN, dry_run: bool = False) -> Report:
    """Find websites for companies without one. `lookups` caps the job-board
    requests (None for no cap); companies with the most open jobs go first."""
    report = Report()
    with db.connect(dsn) as conn:
        todo, shared = candidates(conn)
    found: list[tuple[int, str]] = []
    checked: list[int] = []
    for company in todo:
        domain, source, failed = None, "", False
        for board, slug in company.boards:
            if lookups is not None and report.lookups >= lookups:
                break
            report.lookups += 1
            try:
                domain = BOARDS[board](slug)
            except FetchError as exc:
                report.failed_lookups += 1
                failed = True
                log.debug("%s: %s board lookup failed: %s", company.name, board, exc)
                continue
            if domain:
                source = board
                break
        out_of_lookups = lookups is not None and report.lookups >= lookups and not domain
        if not domain:
            domain = from_apply_links(company.apply_hosts, shared)
            source = "careers site" if domain else ""
        if not domain:
            domain = from_postings(company.name, company.hosts)
            source = "postings" if domain else ""
        if not domain and (failed or (out_of_lookups and company.boards)):
            continue  # its board wasn't read this run: try again next run, don't mark it checked
        report.looked_at += 1
        if domain:
            found.append((company.id, domain))
            report.found.append((company.name, domain, source))
            if source == "postings":
                report.from_postings += 1
            elif source == "careers site":
                report.from_careers_site += 1
            else:
                report.from_board += 1
        else:
            report.not_found += 1
        checked.append(company.id)
    if not dry_run and checked:
        with db.connect(dsn) as conn:
            with conn.cursor() as cur:
                cur.executemany(
                    "UPDATE companies SET domain = coalesce(domain, %s), domain_checked_at = now() WHERE id = %s",
                    [(domain, cid) for cid, domain in found],
                )
                done = {cid for cid, _ in found}
                cur.execute(
                    "UPDATE companies SET domain_checked_at = now() WHERE id = ANY(%s)",
                    ([cid for cid in checked if cid not in done],),
                )
            conn.commit()
    log.info("company websites: %s", report.summary())
    return report
